"""小程序路由后台 worker。"""

from __future__ import annotations

import asyncio
import contextlib
import multiprocessing as mp
import queue

from package.applet_routes.bridge import RealRouteEngineBridge
from package.applet_routes.navigator import MiniProgramRouteNavigator
from package.applet_routes.state import copy_route_state, default_route_state


class AsyncRouteWorker:
    """在独立进程中串行调度路由命令并隔离单任务异常。"""

    def __init__(
        self,
        event_queue: mp.Queue,
        command_queue: mp.Queue,
        bridge_factory=None,
        navigator_factory=None,
        poll_interval: float = 0.03,
    ) -> None:
        """保存队列、工厂方法和运行时状态。"""
        self.event_queue = event_queue
        self.command_queue = command_queue
        self.bridge_factory = bridge_factory or RealRouteEngineBridge
        self.navigator_factory = navigator_factory or MiniProgramRouteNavigator
        self.poll_interval = float(poll_interval)
        self.running = True
        self.bridge = None
        self.navigator = None
        self.record_states: dict[int, dict] = {}
        self.record_tasks: dict[int, asyncio.Task] = {}

    async def run(self) -> None:
        """持续轮询命令队列，直到收到 shutdown 命令。"""
        try:
            while self.running:
                await self.process_commands()
                await asyncio.sleep(self.poll_interval)
        finally:
            await self.cancel_all_tasks()
            await self.stop_bridge()

    async def process_commands(self) -> None:
        """非阻塞消费 UI 发来的后台命令。"""
        while True:
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                return
            await self.handle_command(command)

    async def handle_command(self, command: dict) -> None:
        """按命令类型创建、取消或停止对应的路由任务。"""
        command_type = str(command.get("type") or "")
        record_id = int(command.get("record_id") or 0)
        if command_type == "shutdown":
            self.running = False
            return
        if command_type == "cancel_record_tasks":
            await self.cancel_record_task(record_id)
            return
        if command_type == "attach_record":
            await self.schedule_record_task(record_id, self.attach_record(command))
            return
        if command_type == "refresh_routes":
            await self.schedule_record_task(record_id, self.refresh_routes(command))
            return
        if command_type == "execute_route_action":
            await self.schedule_record_task(record_id, self.execute_route_action(command))
            return
        if command_type == "navigate_back":
            await self.schedule_record_task(record_id, self.navigate_back(command))

    async def wait_for_record_task(self, record_id: int) -> None:
        """供测试等待某个卡片对应的后台任务执行完成。"""
        task = self.record_tasks.get(int(record_id or 0))
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def schedule_record_task(self, record_id: int, coroutine) -> None:
        """替换同一张卡片上一个尚未结束的后台任务。"""
        await self.cancel_record_task(record_id)
        self.record_tasks[record_id] = asyncio.create_task(coroutine)

    async def cancel_record_task(self, record_id: int) -> None:
        """取消指定卡片当前正在执行的后台任务。"""
        task = self.record_tasks.pop(int(record_id or 0), None)
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def cancel_all_tasks(self) -> None:
        """在 worker 退出前取消全部未完成的卡片任务。"""
        for record_id in list(self.record_tasks):
            await self.cancel_record_task(record_id)

    async def attach_record(self, command: dict) -> None:
        """接管当前卡片并枚举该小程序的路由数据。"""
        record_id = int(command.get("record_id") or 0)
        state = self.ensure_state(command, status="starting", message="正在接管路由会话", error="")
        self.emit_state(record_id)
        try:
            await self.ensure_bridge_started()
            payload = await self.navigator.fetch_routes()
        except Exception as exc:
            state.update({"status": "failed", "attached": False, "message": "接管失败", "error": str(exc)})
            self.emit_state(record_id)
            return
        state.update(
            {
                "status": "ready",
                "worker_alive": True,
                "attached": True,
                "pages": payload["pages"],
                "tabbar_pages": payload["tabbar_pages"],
                "current_route": payload["current_route"],
                "message": "路由已就绪",
                "error": "",
            }
        )
        self.emit_state(record_id)

    async def refresh_routes(self, command: dict) -> None:
        """重新获取当前卡片对应小程序的路由列表。"""
        record_id = int(command.get("record_id") or 0)
        state = self.ensure_state(command, status="refreshing", message="正在刷新路由", error="")
        self.emit_state(record_id)
        try:
            await self.ensure_bridge_started()
            payload = await self.navigator.fetch_routes()
        except Exception as exc:
            state.update({"status": "failed", "message": "刷新失败", "error": str(exc)})
            self.emit_state(record_id)
            return
        state.update(
            {
                "status": "ready",
                "attached": True,
                "pages": payload["pages"],
                "tabbar_pages": payload["tabbar_pages"],
                "current_route": payload["current_route"],
                "message": "路由已刷新",
                "error": "",
            }
        )
        self.emit_state(record_id)

    async def execute_route_action(self, command: dict) -> None:
        """执行页面跳转动作并把结果回写到当前卡片状态。"""
        record_id = int(command.get("record_id") or 0)
        action = str(command.get("action") or "")
        route = str(command.get("route") or "")
        state = self.ensure_state(command, status="executing", message=f"正在执行 {action}", error="")
        self.emit_state(record_id)
        try:
            await self.ensure_bridge_started()
            handler = getattr(self.navigator, action)
            result = await handler(route)
        except Exception as exc:
            state.update({"status": "failed", "message": f"{action} 执行失败", "error": str(exc)})
            self.emit_state(record_id)
            return
        state.update(
            {
                "status": "ready" if result.get("ok") else "failed",
                "attached": True,
                "last_action": action,
                "current_route": str(result.get("currentRoute") or state.get("current_route") or ""),
                "message": f"{action} 执行完成" if result.get("ok") else f"{action} 执行失败",
                "error": str(result.get("error") or ""),
            }
        )
        self.emit_state(record_id)

    async def navigate_back(self, command: dict) -> None:
        """执行返回上一页动作并刷新当前路由。"""
        record_id = int(command.get("record_id") or 0)
        state = self.ensure_state(command, status="executing", message="正在返回上一页", error="")
        self.emit_state(record_id)
        try:
            await self.ensure_bridge_started()
            result = await self.navigator.navigate_back(int(command.get("delta") or 1))
        except Exception as exc:
            state.update({"status": "failed", "message": "返回失败", "error": str(exc)})
            self.emit_state(record_id)
            return
        state.update(
            {
                "status": "ready" if result.get("ok") else "failed",
                "attached": True,
                "last_action": "navigate_back",
                "current_route": str(result.get("currentRoute") or state.get("current_route") or ""),
                "message": "返回完成" if result.get("ok") else "返回失败",
                "error": str(result.get("error") or ""),
            }
        )
        self.emit_state(record_id)

    async def ensure_bridge_started(self) -> None:
        """按需启动 bridge 并创建对应导航器。"""
        if self.bridge is not None and self.navigator is not None:
            return
        self.bridge = self.bridge_factory()
        await self.bridge.start()
        self.navigator = self.navigator_factory(self.bridge)

    async def stop_bridge(self) -> None:
        """停止当前 bridge 并清空导航器引用。"""
        bridge = self.bridge
        self.bridge = None
        self.navigator = None
        if bridge is not None:
            await bridge.stop()

    def ensure_state(self, command: dict, *, status: str, message: str, error: str) -> dict:
        """确保某个卡片始终有一份可更新的路由状态快照。"""
        record_id = int(command.get("record_id") or 0)
        state = self.record_states.setdefault(
            record_id,
            default_route_state(
                record_id=record_id,
                owner_key=str(command.get("owner_key") or ""),
                display_name=str(command.get("display_name") or ""),
                worker_alive=True,
            ),
        )
        state.update(
            {
                "record_id": record_id,
                "owner_key": str(command.get("owner_key") or state.get("owner_key") or ""),
                "display_name": str(command.get("display_name") or state.get("display_name") or ""),
                "worker_alive": True,
                "status": status,
                "message": message,
                "error": error,
            }
        )
        return state

    def emit_state(self, record_id: int) -> None:
        """把指定卡片的最新状态通过事件队列回推给 UI。"""
        self.event_queue.put(
            {
                "type": "route_state",
                "record_id": int(record_id or 0),
                "state": copy_route_state(self.record_states.get(int(record_id or 0), {})),
            }
        )


def route_worker_main(event_queue: mp.Queue, command_queue: mp.Queue) -> None:
    """Route worker 进程入口。"""
    asyncio.run(AsyncRouteWorker(event_queue, command_queue).run())
