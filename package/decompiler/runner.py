"""在 UI 进程中管理反编译 worker 子进程和任务队列。"""

from __future__ import annotations

import asyncio
import multiprocessing as mp

from package.decompiler.worker import AsyncDecompileWorker


def decompile_worker_main(event_queue: mp.Queue, command_queue: mp.Queue) -> None:
    """反编译 worker 子进程入口。"""
    asyncio.run(AsyncDecompileWorker(event_queue, command_queue).run())


class DecompileTaskRunner:
    """UI 进程中的反编译与文件浏览任务调度器。"""

    def __init__(self) -> None:
        """启动独立反编译进程并准备通信队列。"""
        self.event_queue: mp.Queue = mp.Queue()
        self.command_queue: mp.Queue = mp.Queue()
        self.next_task_id = 1
        self.process = mp.Process(
            target=decompile_worker_main,
            args=(self.event_queue, self.command_queue),
            daemon=True,
            name="decompile-async-worker",
        )
        self.process.start()

    def submit(self, operation: str, payload: dict) -> int:
        """提交一项反编译、目录加载或文件读取任务。"""
        task_id = self.next_task_id
        self.next_task_id += 1
        self.command_queue.put({"type": "submit", "task_id": task_id, "operation": operation, "payload": payload})
        return task_id

    def cancel(self, task_id: int) -> None:
        """请求取消指定任务。"""
        self.command_queue.put({"type": "cancel", "task_id": task_id})

    def get_event_nowait(self) -> dict:
        """非阻塞获取一个 worker 返回事件。"""
        return self.event_queue.get_nowait()

    def shutdown(self, wait: bool = True) -> None:
        """停止反编译 worker 进程，可选择是否等待进程退出。"""
        if self.process.is_alive():
            self.command_queue.put({"type": "stop"})
        if not wait:
            return
        if self.process.is_alive():
            self.process.join(timeout=1.0)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1.0)
