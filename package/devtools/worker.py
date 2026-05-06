"""负责调度共享 DevTools 会话的后台多进程 worker。"""

from __future__ import annotations

import asyncio
import contextlib
import multiprocessing as mp
import queue
import socket
from typing import Awaitable, Callable

from package.applet_debug import copy_debug_toggle_state, default_debug_toggle_state
from package.applet_debug.runtime import DebugToggleRuntime
from package.applet_routes.navigator import MiniProgramRouteNavigator
from package.applet_routes.state import copy_route_state, default_route_state
from package.config.defaults import normalize_cloud_call_timeout
from package.cloud_audit import CloudAuditRuntime, copy_cloud_state, default_cloud_state
from package.cloud_audit.runtime import cloud_call_transport_timeout
from package.devtools.bridge import EngineBridge, RealDebugEngineBridge
from package.devtools.constants import CDP_PORT_END, CDP_PORT_START, DEBUG_PORT
from package.devtools.state import build_devtools_link, copy_state, default_state

MINIAPP_RESTART_HINT = "如小程序已提前打开，请重启小程序后再试"
ROUTE_ACTION_LABELS = {
    "switch_tab": "切换标签页",
    "navigate_to": "打开新页面",
    "redirect_to": "替换当前页",
    "relaunch": "重启到页面",
    "navigate_back": "返回上一页",
}
DEBUG_TOGGLE_ACTION_LABELS = {
    "detect": "检测调试状态",
    "enable": "开启调试",
    "disable": "关闭调试",
}


def find_available_cdp_port(start: int = CDP_PORT_START) -> int:
    """查找首个可用的 CDP 代理端口。"""
    for port in range(int(start), CDP_PORT_END + 1):
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available CDP port found")


class AsyncDevtoolsWorker:
    """支持调试与路由切换的单会话异步 worker。"""

    def __init__(
        self,
        event_queue: mp.Queue,
        command_queue: mp.Queue,
        bridge_factory: Callable[[], EngineBridge] | None = None,
        navigator_factory: Callable[[EngineBridge], MiniProgramRouteNavigator] | None = None,
        debug_runtime_factory: Callable[[EngineBridge, MiniProgramRouteNavigator], DebugToggleRuntime] | None = None,
        poll_interval: float = 0.03,
        miniapp_ready_timeout: float = 15.0,
        traverse_route_delay: float = 2.0,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.event_queue = event_queue
        self.command_queue = command_queue
        self.bridge_factory = bridge_factory or RealDebugEngineBridge
        self.navigator_factory = navigator_factory or MiniProgramRouteNavigator
        self.debug_runtime_factory = debug_runtime_factory or DebugToggleRuntime
        self.poll_interval = float(poll_interval)
        self.miniapp_ready_timeout = float(miniapp_ready_timeout)
        self.traverse_route_delay = max(float(traverse_route_delay or 0.0), 0.0)
        self.sleep_func = sleep_func or asyncio.sleep
        self.running = True
        self.bridge: EngineBridge | None = None
        self.route_navigator: MiniProgramRouteNavigator | None = None
        self.transition_task: asyncio.Task | None = None
        self.route_tasks: dict[int, asyncio.Task] = {}
        self.debug_tasks: dict[int, asyncio.Task] = {}
        self.debug_states: dict[int, dict] = {}
        self.route_states: dict[int, dict] = {}
        self.cloud_runtime: CloudAuditRuntime | None = None
        self.cloud_operation_task: asyncio.Task | None = None
        self.cloud_poll_task: asyncio.Task | None = None
        self.cloud_state = default_cloud_state()
        self.cloud_calls: list[dict] = []
        self.cloud_call_history: list[dict] = []
        self.state = default_state()

    async def run(self) -> None:
        """持续运行 worker 主循环，并隔离调试生命周期异常。"""
        self.state = default_state(worker_alive=True, message="Devtools worker 已就绪")
        self.cloud_state = default_cloud_state(worker_alive=True, message="云审计 worker 已就绪")
        self.emit_state()
        self.emit_cloud_state()
        try:
            while self.running:
                await self.process_commands()
                await asyncio.sleep(self.poll_interval)
        except Exception as exc:
            self.state.update(
                {
                    "status": "failed",
                    "message": f"Devtools worker 异常：{exc}",
                    "error": str(exc),
                }
            )
            self.emit_state()
        finally:
            await self.cancel_transition()
            await self.cancel_all_debug_tasks()
            await self.cancel_all_route_tasks()
            with contextlib.suppress(Exception):
                await self.stop_bridge()
            self.state = default_state()
            self.emit_state()
            self.cloud_state = default_cloud_state()
            self.emit_cloud_state()

    def emit(self, event: dict) -> None:
        """向界面侧发送通用 worker 事件。"""
        self.event_queue.put(event)

    def emit_state(self) -> None:
        """向界面侧发布最新的全局调试状态快照。"""
        self.event_queue.put({"type": "devtools_state", "state": copy_state(self.state)})

    def emit_route_state(self, record_id: int) -> None:
        """向界面侧发布指定记录的最新路由状态。"""
        self.event_queue.put(
            {
                "type": "route_state",
                "record_id": int(record_id or 0),
                "state": copy_route_state(self.route_states.get(int(record_id or 0), {})),
            }
        )

    def emit_debug_state(self, record_id: int) -> None:
        """向界面侧发布指定记录的调试开关状态。"""
        self.event_queue.put(
            {
                "type": "debug_toggle_state",
                "record_id": int(record_id or 0),
                "state": copy_debug_toggle_state(self.debug_states.get(int(record_id or 0), {})),
            }
        )

    def emit_debug_log(self, command: dict, *, level: str, stage: str, action: str, message: str) -> None:
        """向界面侧发布调试开关链路上的结构化日志。"""
        session = self.build_session(command)
        self.emit(
            {
                "type": "debug_toggle_log",
                "record_id": int(session["record_id"] or 0),
                "owner_key": session["owner_key"],
                "display_name": session["display_name"],
                "level": str(level or "INFO").upper(),
                "stage": str(stage or "").strip(),
                "action": str(action or "").strip(),
                "message": str(message or "").strip(),
            }
        )

    async def process_commands(self) -> None:
        """以非阻塞方式消费界面层发来的命令。"""
        while True:
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                return
            await self.handle_command(command)

    async def handle_command(self, command: dict) -> None:
        """统一分发单条命令，供真实队列轮询和测试场景共同复用。"""
        command_type = str(command.get("type") or "")
        record_id = int(command.get("record_id") or 0)
        if command_type == "shutdown":
            self.running = False
            await self.cancel_transition()
            await self.cancel_all_debug_tasks()
            await self.cancel_cloud_operation()
            await self.cancel_all_route_tasks()
            with contextlib.suppress(Exception):
                await self.stop_bridge()
            return
        if command_type == "query_state":
            self.emit_state()
            return
        if command_type == "stop_session":
            await self.schedule_transition(self.stop_transition())
            return
        if command_type == "start_session":
            await self.schedule_transition(self.start_transition(command))
            return
        if command_type == "detect_debug_toggle":
            await self.schedule_debug_task(record_id, self.detect_debug_toggle(command))
            return
        if command_type == "set_debug_toggle":
            await self.schedule_debug_task(record_id, self.set_debug_toggle(command))
            return
        if command_type == "cancel_debug_toggle":
            await self.cancel_debug_task(record_id)
            return
        if command_type == "start_cloud_audit":
            await self.schedule_cloud_operation(self.start_cloud_audit(command))
            return
        if command_type == "stop_cloud_audit":
            await self.schedule_cloud_operation(self.stop_cloud_audit())
            return
        if command_type == "clear_cloud_audit":
            await self.clear_cloud_audit()
            return
        if command_type == "call_cloud_function":
            await self.schedule_cloud_operation(self.call_cloud_function(command))
            return
        if command_type == "scan_cloud_static":
            await self.schedule_cloud_operation(self.scan_cloud_static(command))
            return
        if command_type == "cancel_route_tasks":
            await self.cancel_route_task(record_id)
            return
        if command_type == "attach_route":
            await self.schedule_route_task(record_id, self.attach_route(command))
            return
        if command_type == "refresh_routes":
            await self.schedule_route_task(record_id, self.refresh_routes(command))
            return
        if command_type == "execute_route_action":
            await self.schedule_route_task(record_id, self.execute_route_action(command))
            return
        if command_type == "navigate_back_route":
            await self.schedule_route_task(record_id, self.navigate_back_route(command))
            return
        if command_type == "traverse_routes":
            await self.schedule_route_task(record_id, self.traverse_routes(command))
            return
        if command_type == "toggle_route_guard":
            await self.schedule_route_task(record_id, self.toggle_route_guard(command))

    async def schedule_transition(self, transition_coro) -> None:
        """用新的调试切换任务替换当前仍在执行的切换任务。"""
        await self.cancel_transition()
        self.transition_task = asyncio.create_task(transition_coro)

    async def cancel_transition(self) -> None:
        """取消当前尚未结束的调试切换任务。"""
        task = self.transition_task
        self.transition_task = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def wait_for_transition(self) -> None:
        """等待当前调试切换任务执行完成。"""
        task = self.transition_task
        if task is None:
            return
        try:
            await task
        finally:
            if self.transition_task is task:
                self.transition_task = None

    async def schedule_debug_task(self, record_id: int, debug_coro) -> None:
        """为指定记录替换掉仍在执行中的调试开关任务。"""
        await self.cancel_debug_task(record_id)
        self.debug_tasks[record_id] = asyncio.create_task(self.run_debug_task(record_id, debug_coro))
        await asyncio.sleep(0)

    async def run_debug_task(self, record_id: int, debug_coro) -> None:
        """运行单个调试开关任务，并确保取消后不会残留忙碌态。"""
        try:
            await debug_coro
        except asyncio.CancelledError:
            self.mark_debug_task_cancelled(record_id)
            raise

    def mark_debug_task_cancelled(self, record_id: int) -> None:
        """把被取消的调试开关任务回写为失败状态，允许页面重试。"""
        state = self.debug_states.get(int(record_id or 0))
        if not isinstance(state, dict):
            return
        if str(state.get("status") or "") not in {"idle", "detecting", "enabling", "disabling"}:
            return
        state.update(
            {
                "status": "failed",
                "message": "调试任务已取消，可重新执行",
                "error": "debug task cancelled",
            }
        )
        self.emit_debug_state(record_id)

    async def cancel_debug_task(self, record_id: int) -> None:
        """取消指定记录当前正在执行的调试开关任务。"""
        task = self.debug_tasks.pop(int(record_id or 0), None)
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        self.mark_debug_task_cancelled(record_id)

    async def cancel_all_debug_tasks(self) -> None:
        """在 worker 退出前取消全部未完成的调试开关任务。"""
        for record_id in list(self.debug_tasks):
            await self.cancel_debug_task(record_id)

    async def wait_for_debug_task(self, record_id: int) -> None:
        """等待指定记录的调试开关任务完成，供测试复用。"""
        task = self.debug_tasks.get(int(record_id or 0))
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def schedule_route_task(self, record_id: int, route_coro) -> None:
        """为指定记录替换掉仍在执行中的路由任务。"""
        await self.cancel_route_task(record_id)
        self.route_tasks[record_id] = asyncio.create_task(self.run_route_task(record_id, route_coro))
        await asyncio.sleep(0)

    async def run_route_task(self, record_id: int, route_coro) -> None:
        """运行单个路由任务，并确保取消不会把 UI 留在 busy 状态。"""
        try:
            await route_coro
        except asyncio.CancelledError:
            self.mark_route_task_cancelled(record_id)
            raise

    def mark_route_task_cancelled(self, record_id: int) -> None:
        """把被取消的路由任务落盘为失败状态，避免按钮永久停在执行中。"""
        state = self.route_states.get(int(record_id or 0))
        if not isinstance(state, dict):
            return
        if str(state.get("status") or "") not in {"starting", "refreshing", "executing", "traversing"}:
            return
        state.update(
            {
                "status": "failed",
                "attached": False,
                "message": "路由任务已取消，请重新接管路由",
                "error": "route task cancelled",
            }
        )
        self.emit_route_state(record_id)

    async def cancel_route_task(self, record_id: int) -> None:
        """取消指定记录当前正在执行的路由任务。"""
        task = self.route_tasks.pop(int(record_id or 0), None)
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def cancel_all_route_tasks(self) -> None:
        """在 worker 退出前取消全部未完成的路由任务。"""
        for record_id in list(self.route_tasks):
            await self.cancel_route_task(record_id)

    async def wait_for_route_task(self, record_id: int) -> None:
        """等待指定记录的路由任务完成，供测试复用。"""
        task = self.route_tasks.get(int(record_id or 0))
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def start_transition(self, command: dict) -> None:
        """停止旧会话，并为目标记录启动新的共享调试会话。"""
        session = self.build_session(command)

        if self.bridge is not None:
            self.state.update({"status": "stopping", "message": "正在停止旧调试会话", "error": ""})
            self.emit_state()
            await self.stop_cloud_poll()
            await self.stop_cloud_runtime()
            self.cloud_state = default_cloud_state(worker_alive=True, message="云审计已切换到新会话")
            self.emit_cloud_state()
            await self.stop_bridge()

        self.apply_session_state(
            session,
            status="starting",
            message="正在启动调试",
            error="",
            link="",
            cdp_port=0,
            frida=False,
            miniapp=False,
            devtools=False,
        )
        self.emit_state()

        bridge = self.bridge_factory()
        self.bridge = bridge
        try:
            cdp_port = find_available_cdp_port(CDP_PORT_START)
            await bridge.start(session, DEBUG_PORT, cdp_port, self.handle_bridge_status)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await self.stop_bridge()
            self.state = default_state(worker_alive=True, message="调试已停止")
            self.emit_state()
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await self.stop_bridge()
            self.apply_session_state(
                session,
                status="failed",
                message=f"启动失败：{exc}",
                error=str(exc),
                link="",
                cdp_port=0,
                frida=False,
                miniapp=False,
                devtools=False,
            )
            self.emit_state()
            return

        self.state.update(
            {
                "status": "running",
                "cdp_port": cdp_port,
                "link": build_devtools_link(cdp_port),
                "error": "",
                "message": self.running_message(),
            }
        )
        self.emit_state()

    async def stop_transition(self) -> None:
        """停止当前共享调试会话，但保持 worker 继续运行。"""
        await self.cancel_all_route_tasks()
        self.state.update({"status": "stopping", "message": "正在停止调试", "error": ""})
        self.emit_state()
        try:
            await self.stop_cloud_poll()
            await self.stop_cloud_runtime()
            self.cloud_state = default_cloud_state(worker_alive=True, message="云函数捕获已停止")
            self.emit_cloud_state()
            await self.stop_bridge()
        except Exception as exc:
            self.state = default_state(worker_alive=True)
            self.state.update(
                {
                    "status": "failed",
                    "message": f"停止失败：{exc}",
                    "error": str(exc),
                }
            )
            self.emit_state()
            return

        self.state = default_state(worker_alive=True, message="调试已停止")
        self.emit_state()
        self.mark_route_states_stopped("调试已停止，请重新接管路由")

    async def attach_route(self, command: dict) -> None:
        """把路由能力挂到共享会话上，并读取当前可用路由。"""
        record_id = int(command.get("record_id") or 0)
        state = self.ensure_route_state(command, status="starting", message="正在接管路由，等待小程序回连", error="")
        self.emit_route_state(record_id)
        try:
            await self.ensure_route_session(command)
            payload = await self.route_navigator.fetch_routes()
        except Exception as exc:
            state.update(
                {
                    "status": "failed",
                    "attached": False,
                    "message": str(exc) or "接管失败",
                    "error": str(exc),
                }
            )
            self.emit_route_state(record_id)
            return
        state.update(
            {
                "status": "ready",
                "worker_alive": True,
                "attached": True,
                "pages": payload["pages"],
                "tabbar_pages": payload["tabbar_pages"],
                "current_route": payload["current_route"],
                "guard_enabled": bool(payload.get("guard_enabled")),
                "blocked_redirects_count": int(payload.get("blocked_redirects_count") or 0),
                "message": "路由已就绪",
                "error": "",
            }
        )
        self.emit_route_state(record_id)

    async def refresh_routes(self, command: dict) -> None:
        """刷新当前记录对应的小程序路由列表。"""
        record_id = int(command.get("record_id") or 0)
        state = self.ensure_route_state(command, status="refreshing", message="正在刷新路由", error="")
        self.emit_route_state(record_id)
        try:
            await self.ensure_route_session(command)
            payload = await self.route_navigator.fetch_routes()
        except Exception as exc:
            state.update({"status": "failed", "message": str(exc) or "刷新失败", "error": str(exc)})
            self.emit_route_state(record_id)
            return
        state.update(
            {
                "status": "ready",
                "attached": True,
                "pages": payload["pages"],
                "tabbar_pages": payload["tabbar_pages"],
                "current_route": payload["current_route"],
                "guard_enabled": bool(payload.get("guard_enabled")),
                "blocked_redirects_count": int(payload.get("blocked_redirects_count") or 0),
                "message": "路由已刷新",
                "error": "",
            }
        )
        self.emit_route_state(record_id)

    async def execute_route_action(self, command: dict) -> None:
        """通过共享调试会话执行指定的路由跳转动作。"""
        record_id = int(command.get("record_id") or 0)
        action = str(command.get("action") or "")
        route = str(command.get("route") or "")
        action_label = ROUTE_ACTION_LABELS.get(action, action)
        state = self.ensure_route_state(command, status="executing", message=f"正在执行{action_label}", error="")
        self.emit_route_state(record_id)
        try:
            await self.ensure_route_session(command)
            handler = getattr(self.route_navigator, action)
            result = await handler(route)
            payload = await self.route_navigator.fetch_routes() if result.get("ok") else None
        except Exception as exc:
            state.update({"status": "failed", "message": f"{action_label}失败", "error": str(exc)})
            self.emit_route_state(record_id)
            return
        if payload is not None:
            state["pages"] = payload["pages"]
            state["tabbar_pages"] = payload["tabbar_pages"]
            state["guard_enabled"] = bool(payload.get("guard_enabled"))
            state["blocked_redirects_count"] = int(payload.get("blocked_redirects_count") or 0)
        state["current_route"] = str(
            result.get("currentRoute") or (payload or {}).get("current_route") or state.get("current_route") or ""
        )
        state.update(
            {
                "status": "ready" if result.get("ok") else "failed",
                "attached": True,
                "last_action": action,
                "message": f"{action_label}完成" if result.get("ok") else f"{action_label}失败",
                "error": str(result.get("error") or ""),
            }
        )
        self.emit_route_state(record_id)

    async def navigate_back_route(self, command: dict) -> None:
        """通过共享调试会话执行返回上一页动作。"""
        record_id = int(command.get("record_id") or 0)
        state = self.ensure_route_state(command, status="executing", message="正在返回上一页", error="")
        self.emit_route_state(record_id)
        try:
            await self.ensure_route_session(command)
            result = await self.route_navigator.navigate_back(int(command.get("delta") or 1))
            payload = await self.route_navigator.fetch_routes() if result.get("ok") else None
        except Exception as exc:
            state.update({"status": "failed", "message": ROUTE_ACTION_LABELS["navigate_back"] + "失败", "error": str(exc)})
            self.emit_route_state(record_id)
            return
        if payload is not None:
            state["pages"] = payload["pages"]
            state["tabbar_pages"] = payload["tabbar_pages"]
            state["guard_enabled"] = bool(payload.get("guard_enabled"))
            state["blocked_redirects_count"] = int(payload.get("blocked_redirects_count") or 0)
        state["current_route"] = str(
            result.get("currentRoute") or (payload or {}).get("current_route") or state.get("current_route") or ""
        )
        state.update(
            {
                "status": "ready" if result.get("ok") else "failed",
                "attached": True,
                "last_action": "navigate_back",
                "message": "返回完成" if result.get("ok") else "返回失败",
                "error": str(result.get("error") or ""),
            }
        )
        self.emit_route_state(record_id)

    async def traverse_routes(self, command: dict) -> None:
        """依次遍历当前记录的全部路由，并回写最终路由状态。"""
        record_id = int(command.get("record_id") or 0)
        state = self.ensure_route_state(command, status="traversing", message="正在遍历全部路由", error="")
        self.emit_route_state(record_id)
        try:
            await self.ensure_route_session(command)
            payload = await self.route_navigator.fetch_routes()
            pages = payload.get("pages") if isinstance(payload.get("pages"), list) else []
            for index, page in enumerate(pages):
                route = str(page.get("route") or "").strip()
                if not route:
                    continue
                result = await self.route_navigator.visit_route(route, is_tabbar=bool(page.get("is_tabbar")))
                if not result.get("ok"):
                    raise RuntimeError(str(result.get("error") or f"遍历路由失败：{route}"))
                if index < len(pages) - 1 and self.traverse_route_delay > 0:
                    await self.sleep_func(self.traverse_route_delay)
            payload = await self.route_navigator.fetch_routes()
        except Exception as exc:
            state.update({"status": "failed", "message": str(exc) or "遍历失败", "error": str(exc)})
            self.emit_route_state(record_id)
            return
        state.update(
            {
                "status": "ready",
                "attached": True,
                "pages": payload["pages"],
                "tabbar_pages": payload["tabbar_pages"],
                "current_route": payload["current_route"],
                "guard_enabled": bool(payload.get("guard_enabled")),
                "blocked_redirects_count": int(payload.get("blocked_redirects_count") or 0),
                "message": "遍历完成",
                "error": "",
            }
        )
        self.emit_route_state(record_id)

    async def build_debug_runtime(self, command: dict) -> DebugToggleRuntime:
        """确保共享会话和导航桥就绪后构造调试开关运行时。"""
        await self.ensure_route_session(command)
        return self.debug_runtime_factory(self.bridge, self.route_navigator)

    async def detect_debug_toggle(self, command: dict) -> None:
        """检测当前记录对应小程序的调试开关状态。"""
        record_id = int(command.get("record_id") or 0)
        self.emit_debug_log(
            command,
            level="DEBUG",
            stage="command_received",
            action="detect",
            message="worker 已收到调试状态检测命令",
        )
        state = self.ensure_debug_state(
            command,
            status="detecting",
            message="正在检测调试状态",
            error="",
            last_action="detect",
        )
        self.emit_debug_state(record_id)
        try:
            self.emit_debug_log(
                command,
                level="DEBUG",
                stage="prepare_runtime",
                action="detect",
                message=self.describe_debug_runtime_prepare_message(command),
            )
            runtime = await self.build_debug_runtime(command)
            self.emit_debug_log(
                command,
                level="DEBUG",
                stage="runtime_ready",
                action="detect",
                message="调试运行时已就绪，开始读取当前调试状态",
            )
            result = await runtime.detect()
        except asyncio.CancelledError:
            self.emit_debug_log(
                command,
                level="WARNING",
                stage="cancelled",
                action="detect",
                message="调试状态检测已取消",
            )
            raise
        except Exception as exc:
            self.emit_debug_log(
                command,
                level="ERROR",
                stage="detect_failed",
                action="detect",
                message=f"调试状态检测失败：{exc}",
            )
            state.update({"status": "failed", "message": str(exc) or "检测失败", "error": str(exc)})
            self.emit_debug_state(record_id)
            return
        self.emit_debug_log(
            command,
            level="INFO",
            stage="detect_result",
            action="detect",
            message=f"调试状态检测完成，debug={bool(result.get('debug_enabled'))}，vConsole={bool(result.get('vconsole_visible'))}",
        )
        state.update(
            {
                "status": "ready",
                "debug_enabled": bool(result.get("debug_enabled")),
                "vconsole_visible": bool(result.get("vconsole_visible")),
                "message": "调试状态检测完成",
                "error": "",
            }
        )
        self.emit_debug_state(record_id)

    async def set_debug_toggle(self, command: dict) -> None:
        """开启或关闭当前记录对应小程序的调试开关，并提示用户重启后再确认结果。"""
        record_id = int(command.get("record_id") or 0)
        enabled = bool(command.get("enabled"))
        action = "enable" if enabled else "disable"
        state = self.ensure_debug_state(
            command,
            status="enabling" if enabled else "disabling",
            message="正在开启调试" if enabled else "正在关闭调试",
            error="",
            last_action=action,
        )
        self.emit_debug_log(
            command,
            level="DEBUG",
            stage="command_received",
            action=action,
            message="worker 已收到开启调试命令" if enabled else "worker 已收到关闭调试命令",
        )
        self.emit_debug_state(record_id)
        try:
            self.emit_debug_log(
                command,
                level="DEBUG",
                stage="prepare_runtime",
                action=action,
                message=self.describe_debug_runtime_prepare_message(command),
            )
            runtime = await self.build_debug_runtime(command)
            self.emit_debug_log(
                command,
                level="DEBUG",
                stage="runtime_ready",
                action=action,
                message=f"调试运行时已就绪，开始调用 wx.setEnableDebug({'true' if enabled else 'false'})",
            )
            await runtime.set_enabled(enabled)
        except asyncio.CancelledError:
            self.emit_debug_log(
                command,
                level="WARNING",
                stage="cancelled",
                action=action,
                message=f"{self.debug_toggle_action_label(action)}任务已取消",
            )
            raise
        except Exception as exc:
            self.emit_debug_log(
                command,
                level="ERROR",
                stage="set_enable_debug_failed",
                action=action,
                message=f"wx.setEnableDebug({'true' if enabled else 'false'}) 调用失败：{exc}",
            )
            state.update({"status": "failed", "message": str(exc) or "调试开关操作失败", "error": str(exc)})
            self.emit_debug_state(record_id)
            return
        self.emit_debug_log(
            command,
            level="INFO",
            stage="set_enable_debug",
            action=action,
            message=f"wx.setEnableDebug({'true' if enabled else 'false'}) 调用成功，请重启小程序等待回连",
        )
        state.update(
            {
                "status": "ready",
                "debug_enabled": enabled,
                "vconsole_visible": False,
                "message": "调试已开启，请重启小程序确认最终效果" if enabled else "调试已关闭，请重启小程序确认最终效果",
                "error": "",
            }
        )
        self.emit_debug_state(record_id)

    async def start_cloud_audit(self, command: dict) -> None:
        """为当前记录启动动态云函数 Hook，并开启轮询任务。"""
        record_id = int(command.get("record_id") or 0)
        self.ensure_cloud_state(command, status="starting", message="正在启动云函数捕获", error="")
        self.emit_cloud_state()
        try:
            await self.ensure_route_session(command)
            state = self.ensure_cloud_state(command, status="starting", message="正在启动云函数捕获", error="")
            if self.cloud_runtime is None:
                self.cloud_runtime = CloudAuditRuntime(self.bridge)
            result = await self.cloud_runtime.start()
        except Exception as exc:
            self.cloud_state.update({"status": "failed", "enabled": False, "message": str(exc) or "云函数捕获启动失败", "error": str(exc)})
            self.emit_cloud_state()
            return
        if not bool(result.get("ok")):
            self.cloud_state.update({"status": "failed", "enabled": False, "message": str(result.get("reason") or "云函数捕获启动失败"), "error": str(result.get("reason") or "")})
            self.emit_cloud_state()
            return
        self.cloud_state.update({"status": "running", "enabled": True, "message": "云函数捕获中", "error": ""})
        self.emit_cloud_state()
        await self.start_cloud_poll(record_id)

    async def stop_cloud_audit(self) -> None:
        """停止动态云函数捕获并清理轮询任务。"""
        self.cloud_state.update({"status": "stopping", "message": "正在停止云函数捕获", "error": ""})
        self.emit_cloud_state()
        await self.stop_cloud_poll()
        await self.stop_cloud_runtime()
        self.cloud_state = default_cloud_state(worker_alive=True, message="云函数捕获已停止")
        self.emit_cloud_state()

    async def clear_cloud_audit(self) -> None:
        """清空当前动态云函数捕获记录。"""
        self.cloud_calls.clear()
        self.cloud_state["captured_count"] = 0
        self.emit_cloud_state()
        if self.cloud_runtime is not None:
            with contextlib.suppress(Exception):
                await self.cloud_runtime.clear()

    async def scan_cloud_static(self, command: dict) -> None:
        """执行一次运行时静态扫描，并把结果发回 UI。"""
        record_id = int(command.get("record_id") or 0)
        try:
            await self.ensure_route_session(command)
            if self.cloud_runtime is None:
                self.cloud_runtime = CloudAuditRuntime(self.bridge)

            def on_progress(message: str) -> None:
                self.emit(
                    {
                        "type": "cloud_audit_static_scan_progress",
                        "record_id": record_id,
                        "message": str(message or ""),
                    }
                )

            results = await self.cloud_runtime.static_scan(on_progress=on_progress)
            self.emit(
                {
                    "type": "cloud_audit_static_scan_result",
                    "record_id": record_id,
                    "results": [dict(item) for item in results if isinstance(item, dict)],
                }
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self.emit(
                {
                    "type": "scan_cloud_static_error",
                    "record_id": record_id,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=3),
                }
            )

    async def call_cloud_function(self, command: dict) -> None:
        """手动调用目标小程序内的云函数。"""
        record_id = int(command.get("record_id") or 0)
        name = str(command.get("name") or "").strip()
        data = command.get("data") if isinstance(command.get("data"), dict) else {}
        timeout_seconds = normalize_cloud_call_timeout(
            command.get("timeout_seconds"),
            minimum=0.05,
            maximum=120,
        )
        hard_timeout = cloud_call_transport_timeout(float(timeout_seconds)) + 0.1
        was_enabled = bool(self.cloud_state.get("enabled"))
        self.ensure_cloud_state(command, status="calling", message=f"正在调用 {name}", error="")
        self.emit_cloud_state()
        try:
            result = await asyncio.wait_for(
                self.execute_cloud_function_call(command, name, data, timeout_seconds),
                timeout=hard_timeout,
            )
        except asyncio.TimeoutError:
            result = {
                "ok": False,
                "status": "timeout",
                "name": name,
                "data": data,
                "timeout_seconds": timeout_seconds,
                "error": f"调用超时({timeout_seconds}s)",
            }
        except Exception as exc:
            result = {"ok": False, "status": "fail", "name": name, "data": data, "error": str(exc)}
        if not isinstance(result, dict):
            result = {"ok": False, "status": "fail", "name": name, "data": data, "error": "返回结果格式错误"}
        result.setdefault("name", name)
        result.setdefault("data", data)
        result.setdefault("record_id", record_id)
        result.setdefault("timeout_seconds", timeout_seconds)
        self.cloud_call_history.append(dict(result))
        self.cloud_call_history = self.cloud_call_history[-200:]
        self.emit({"type": "cloud_audit_call_result", "result": dict(result)})
        self.cloud_state.update(
            {
                "status": "running" if was_enabled else "stopped",
                "enabled": was_enabled,
                "message": "云函数捕获中" if was_enabled else "云函数调用完成",
                "error": "",
            }
        )
        self.emit_cloud_state()

    async def execute_cloud_function_call(self, command: dict, name: str, data: dict, timeout_seconds: float) -> dict:
        """执行云函数调用的完整流程，便于在外层统一加硬超时。"""
        await self.ensure_route_session(command)
        self.ensure_cloud_state(command, status="calling", message=f"正在调用 {name}", error="")
        if self.cloud_runtime is None:
            self.cloud_runtime = CloudAuditRuntime(self.bridge)
        return await self.cloud_runtime.call_function(name, data, timeout_seconds=timeout_seconds)

    async def start_cloud_poll(self, record_id: int) -> None:
        """启动动态云函数轮询任务。"""
        await self.stop_cloud_poll()
        self.cloud_poll_task = asyncio.create_task(self.poll_cloud_calls(record_id))

    async def poll_cloud_calls(self, record_id: int) -> None:
        """轮询新抓到的动态云函数调用并发送到 UI。"""
        try:
            while self.running and self.cloud_state.get("enabled"):
                await asyncio.sleep(1.5)
                if self.cloud_runtime is None:
                    continue
                calls = await self.cloud_runtime.poll()
                if not calls:
                    continue
                self.cloud_calls.extend(dict(call) for call in calls if isinstance(call, dict))
                self.cloud_state["captured_count"] = len(self.cloud_calls)
                self.emit({"type": "cloud_audit_calls", "record_id": record_id, "calls": [dict(call) for call in calls if isinstance(call, dict)]})
                self.emit_cloud_state()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.cloud_state.update({"status": "failed", "enabled": False, "message": "云函数捕获异常", "error": str(exc)})
            self.emit_cloud_state()

    async def stop_cloud_poll(self) -> None:
        """取消动态云函数轮询任务。"""
        task = self.cloud_poll_task
        self.cloud_poll_task = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def stop_cloud_runtime(self) -> None:
        """释放动态云函数运行时并恢复原始方法。"""
        runtime = self.cloud_runtime
        self.cloud_runtime = None
        if runtime is not None:
            with contextlib.suppress(Exception):
                await runtime.stop()

    async def schedule_cloud_operation(self, cloud_coro) -> None:
        """替换当前仍在运行的云审计操作任务。"""
        await self.cancel_cloud_operation()
        self.cloud_operation_task = asyncio.create_task(cloud_coro)
        await asyncio.sleep(0)

    async def cancel_cloud_operation(self) -> None:
        """取消当前未完成的云审计操作任务。"""
        task = self.cloud_operation_task
        self.cloud_operation_task = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    def emit_cloud_state(self) -> None:
        """向 UI 进程发送当前云审计状态快照。"""
        self.event_queue.put({"type": "cloud_audit_state", "state": copy_cloud_state(self.cloud_state)})

    def ensure_cloud_state(self, command: dict, *, status: str, message: str, error: str) -> dict:
        """确保当前记录始终有一份可更新的云审计状态。"""
        session = self.build_session(command)
        record_id = int(session["record_id"] or 0)
        self.cloud_state.update(
            {
                "record_id": record_id,
                "owner_key": session["owner_key"],
                "display_name": session["display_name"],
                "worker_alive": True,
                "status": status,
                "enabled": status == "running",
                "message": message,
                "error": error,
            }
        )
        return self.cloud_state

    def ensure_debug_state(
        self,
        command: dict,
        *,
        status: str,
        message: str,
        error: str,
        last_action: str,
    ) -> dict:
        """确保指定记录始终有一份可更新的调试开关状态缓存。"""
        session = self.build_session(command)
        record_id = int(session["record_id"] or 0)
        state = self.debug_states.setdefault(
            record_id,
            default_debug_toggle_state(
                record_id=record_id,
                owner_key=session["owner_key"],
                display_name=session["display_name"],
                worker_alive=True,
            ),
        )
        state.update(
            {
                "record_id": record_id,
                "owner_key": session["owner_key"],
                "display_name": session["display_name"],
                "worker_alive": True,
                "status": status,
                "message": message,
                "error": error,
                "last_action": last_action,
            }
        )
        return state

    async def toggle_route_guard(self, command: dict) -> None:
        """切换当前记录的防跳转开关，并同步最新守卫状态。"""
        record_id = int(command.get("record_id") or 0)
        enabled = bool(command.get("enabled"))
        state = self.ensure_route_state(
            command,
            status="executing",
            message="正在开启防跳转" if enabled else "正在关闭防跳转",
            error="",
        )
        self.emit_route_state(record_id)
        try:
            await self.ensure_route_session(command)
            if enabled:
                result = await self.route_navigator.enable_redirect_guard()
            else:
                result = await self.route_navigator.disable_redirect_guard()
            payload = await self.route_navigator.fetch_routes()
        except Exception as exc:
            state.update({"status": "failed", "message": str(exc) or "防跳转切换失败", "error": str(exc)})
            self.emit_route_state(record_id)
            return
        state.update(
            {
                "status": "ready" if result.get("ok", True) else "failed",
                "attached": True,
                "pages": payload["pages"],
                "tabbar_pages": payload["tabbar_pages"],
                "current_route": payload["current_route"],
                "guard_enabled": bool(payload.get("guard_enabled")),
                "blocked_redirects_count": int(payload.get("blocked_redirects_count") or 0),
                "message": "防跳转已开启" if enabled else "防跳转已关闭",
                "error": str(result.get("error") or ""),
            }
        )
        self.emit_route_state(record_id)

    async def ensure_route_session(self, command: dict) -> None:
        """确保共享 bridge 已切到目标记录，且小程序端已重新连上。"""
        session = self.build_session(command)
        needs_switch = (
            self.bridge is None
            or str(self.state.get("owner_key") or "") != session["owner_key"]
            or self.state.get("status") not in {"starting", "running"}
        )
        if needs_switch:
            await self.cancel_transition()
            self.transition_task = asyncio.create_task(self.start_transition(command))
            await self.wait_for_transition()
        elif self.transition_task is not None:
            await self.wait_for_transition()
        if self.bridge is None:
            raise RuntimeError("devtools session unavailable")
        await self.wait_for_miniapp_connection()
        if self.route_navigator is None:
            self.route_navigator = self.navigator_factory(self.bridge)

    async def wait_for_miniapp_connection(self) -> None:
        """在执行路由脚本前等待小程序客户端连接完成。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.miniapp_ready_timeout
        while not bool(self.state.get("miniapp")):
            if self.state.get("status") == "failed":
                raise RuntimeError(str(self.state.get("error") or self.state.get("message") or "debug session failed"))
            if self.bridge is None:
                raise RuntimeError("devtools bridge unavailable")
            if loop.time() >= deadline:
                timeout_message = f"等待小程序回连超时，{MINIAPP_RESTART_HINT}"
                self.state["message"] = timeout_message
                self.emit_state()
                raise TimeoutError(timeout_message)
            await self.sleep_func(self.poll_interval)

    def build_session(self, command: dict) -> dict:
        """把记录相关命令整理成统一的会话描述结构。"""
        session = {
            "record_id": int(command.get("record_id") or 0),
            "owner_key": str(command.get("owner_key") or "").strip(),
            "display_name": str(command.get("display_name") or "").strip(),
        }
        if not session["owner_key"]:
            fallback_id = int(session["record_id"] or 0)
            session["owner_key"] = str(fallback_id) if fallback_id > 0 else session["display_name"]
        if not session["display_name"]:
            session["display_name"] = session["owner_key"] or "当前小程序"
        return session

    def debug_toggle_action_label(self, action: str) -> str:
        """返回调试开关动作的中文名称。"""
        return DEBUG_TOGGLE_ACTION_LABELS.get(str(action or "").strip(), "调试开关")

    def describe_debug_runtime_prepare_message(self, command: dict) -> str:
        """根据当前共享会话状态生成更详细的调试准备日志。"""
        session = self.build_session(command)
        owner_key = str(session["owner_key"] or "")
        current_owner_key = str(self.state.get("owner_key") or "")
        status = str(self.state.get("status") or "")
        if self.bridge is None or status not in {"starting", "running"}:
            return "当前无可用调试会话，准备自动启动 DevTools 并等待小程序回连"
        if current_owner_key and current_owner_key != owner_key:
            return "检测到共享调试会话归属不同，准备切换到当前小程序并等待回连"
        if not bool(self.state.get("miniapp")):
            return "共享调试会话已就绪，正在等待小程序重新连接"
        return "复用当前共享调试会话，准备直接执行调试脚本"

    def ensure_route_state(self, command: dict, *, status: str, message: str, error: str) -> dict:
        """确保指定记录始终持有一份可更新的路由状态缓存。"""
        session = self.build_session(command)
        record_id = int(session["record_id"] or 0)
        state = self.route_states.setdefault(
            record_id,
            default_route_state(
                record_id=record_id,
                owner_key=session["owner_key"],
                display_name=session["display_name"],
                worker_alive=True,
            ),
        )
        state.update(
            {
                "record_id": record_id,
                "owner_key": session["owner_key"],
                "display_name": session["display_name"],
                "worker_alive": True,
                "status": status,
                "message": message,
                "error": error,
            }
        )
        return state

    def mark_route_states_stopped(self, message: str) -> None:
        """调试会话停止后同步清理所有已接管的路由状态。"""
        for record_id, state in list(self.route_states.items()):
            if not isinstance(state, dict):
                continue
            state.update(
                {
                    "status": "stopped",
                    "attached": False,
                    "worker_alive": True,
                    "message": str(message or "调试已停止，请重新接管路由"),
                    "error": "",
                }
            )
            self.emit_route_state(record_id)

    def apply_session_state(
        self,
        session: dict,
        *,
        status: str,
        message: str,
        error: str,
        link: str,
        cdp_port: int,
        frida: bool,
        miniapp: bool,
        devtools: bool,
    ) -> None:
        """按指定会话拥有者更新全局调试状态快照。"""
        self.state.update(
            {
                "status": status,
                "worker_alive": True,
                "owner_key": str(session.get("owner_key") or ""),
                "display_name": str(session.get("display_name") or ""),
                "record_id": int(session.get("record_id") or 0),
                "debug_port": DEBUG_PORT,
                "cdp_port": int(cdp_port or 0),
                "link": link,
                "frida": bool(frida),
                "miniapp": bool(miniapp),
                "devtools": bool(devtools),
                "message": message,
                "error": error,
            }
        )

    def handle_bridge_status(self, status: dict) -> None:
        """把 bridge 连通性变化合并进全局调试状态。"""
        for key in ("frida", "miniapp", "devtools"):
            self.state[key] = bool(status.get(key, False))
        if self.state.get("status") in {"starting", "running"}:
            self.state["message"] = self.running_message()
            self.emit_state()

    def running_message(self) -> str:
        """生成用于界面展示的简洁会话状态文案。"""
        parts = [
            "Frida 已连接" if self.state.get("frida") else "Frida 未连接",
            "小程序已回连" if self.state.get("miniapp") else "等待小程序回连",
            "DevTools 已连接" if self.state.get("devtools") else "等待 DevTools 连接",
        ]
        return " | ".join(parts)

    async def stop_bridge(self) -> None:
        """停止当前 bridge，并清理会话中的瞬时连接状态。"""
        bridge = self.bridge
        self.bridge = None
        self.route_navigator = None
        await self.stop_cloud_poll()
        await self.stop_cloud_runtime()
        self.cloud_state = default_cloud_state(worker_alive=True, message="云函数捕获已停止")
        self.emit_cloud_state()
        if bridge is not None:
            await bridge.stop()
        for key in ("frida", "miniapp", "devtools"):
            self.state[key] = False
        self.state["cdp_port"] = 0
        self.state["link"] = ""


def devtools_worker_main(event_queue: mp.Queue, command_queue: mp.Queue) -> None:
    """共享 DevTools worker 进程入口。"""
    asyncio.run(AsyncDevtoolsWorker(event_queue, command_queue).run())
