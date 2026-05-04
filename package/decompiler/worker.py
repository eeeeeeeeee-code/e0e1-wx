"""反编译 worker 主循环，负责命令接收、任务分发和取消管理。"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import queue
import threading
import traceback

from package.decompiler.core import WxapkgError
from package.decompiler.worker_auto import AutoProcessTaskMixin
from package.decompiler.worker_decompile import DecompileTaskMixin
from package.decompiler.worker_files import FileTaskMixin
from package.decompiler.worker_matches import MatchTaskMixin
from package.decompiler.worker_optimize import OptimizeTaskMixin


class AsyncDecompileWorker(
    DecompileTaskMixin,
    OptimizeTaskMixin,
    FileTaskMixin,
    MatchTaskMixin,
    AutoProcessTaskMixin,
):
    """????????? asyncio ???????? worker?"""

    def __init__(self, event_queue: mp.Queue, command_queue: mp.Queue) -> None:
        """初始化 worker 的进程安全通信队列与任务表。"""
        self.event_queue = event_queue
        self.command_queue = command_queue
        self.running = True
        self.tasks: dict[int, asyncio.Task] = {}
        self.cancel_events: dict[int, threading.Event] = {}

    async def run(self) -> None:
        """运行 worker 命令循环并隔离每个后台任务。"""
        try:
            while self.running:
                await self.process_commands()
                self.cleanup_finished_tasks()
                await asyncio.sleep(0.03)
        except Exception as exc:
            self.emit({"type": "decompile_worker_error", "message": f"反编译进程异常：{exc}"})
        finally:
            await self.cancel_all_tasks()

    def emit(self, event: dict) -> None:
        """向 UI 进程发送反编译或文件浏览事件。"""
        self.event_queue.put(event)

    def event_context(self, applet_id: str = "") -> dict:
        """生成可附加到事件中的小程序上下文字段。"""
        return {"applet_id": applet_id} if applet_id else {}

    async def process_commands(self) -> None:
        """处理 UI 发来的提交、取消和停止命令。"""
        while True:
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                break

            command_type = command.get("type")
            if command_type == "stop":
                self.running = False
                return
            if command_type == "cancel":
                self.cancel_task(int(command.get("task_id") or 0))
                continue
            if command_type == "submit":
                task_id = int(command.get("task_id") or 0)
                operation = str(command.get("operation") or "")
                payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
                if task_id <= 0:
                    self.emit({"type": "decompile_error", "message": "反编译任务编号无效。"})
                    continue
                self.tasks[task_id] = asyncio.create_task(self.run_task(task_id, operation, payload))

    async def run_task(self, task_id: int, operation: str, payload: dict) -> None:
        """执行单个后台任务并把异常转换为 UI 可展示事件。"""
        try:
            if operation == "decompile":
                await self.run_decompile(task_id, payload)
            elif operation == "list_dir":
                await self.run_list_dir(task_id, payload)
            elif operation == "read_file":
                await self.run_read_file(task_id, payload)
            elif operation == "read_binary":
                await self.run_read_binary(task_id, payload)
            elif operation == "optimize":
                await self.run_optimize(task_id, payload)
            elif operation == "scan_matches":
                await self.run_scan_matches(task_id, payload)
            elif operation == "export_matches":
                await self.run_export_matches(task_id, payload)
            elif operation == "auto_process":
                await self.run_auto_process(task_id, payload)
            elif operation == "load_auto_matches":
                await self.run_load_auto_matches(task_id, payload)
            else:
                raise WxapkgError(f"未知反编译操作：{operation}")
        except asyncio.CancelledError:
            self.emit({"type": f"{operation}_cancelled", "task_id": task_id, "operation": operation})
            raise
        except Exception as exc:
            self.emit(
                {
                    "type": f"{operation}_error",
                    "task_id": task_id,
                    "operation": operation,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=3),
                }
            )
    def cancel_task(self, task_id: int) -> None:
        """取消指定的未完成任务。"""
        cancel_event = self.cancel_events.get(task_id)
        if cancel_event is not None:
            cancel_event.set()
        task = self.tasks.get(task_id)
        if task is not None and not task.done():
            task.cancel()
        else:
            self.emit({"type": "decompile_cancelled", "task_id": task_id})

    def cleanup_finished_tasks(self) -> None:
        """清理已经结束的 asyncio 任务引用。"""
        finished_ids = [task_id for task_id, task in self.tasks.items() if task.done()]
        for task_id in finished_ids:
            self.tasks.pop(task_id, None)

    async def cancel_all_tasks(self) -> None:
        """停止 worker 前取消所有仍在运行的任务。"""
        for cancel_event in self.cancel_events.values():
            cancel_event.set()
        pending = [task for task in self.tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self.tasks.clear()
