"""在 UI 进程中管理小程序监控子进程和控制命令。"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
from pathlib import Path

from package.monitor.worker import AsyncMiniProgramMonitorWorker


class MiniProgramMonitor:
    """UI 进程中的监控控制器，负责管理监控子进程。"""

    def __init__(self, root_path: Path, db_path: Path, event_queue: mp.Queue, monitor_id: int) -> None:
        """初始化监控控制器和跨进程命令队列。"""
        self.root_path = root_path
        self.db_path = db_path
        self.event_queue = event_queue
        self.monitor_id = monitor_id
        self.command_queue: mp.Queue = mp.Queue()
        self.process = mp.Process(
            target=monitor_worker_main,
            args=(str(self.root_path), str(self.db_path), self.event_queue, self.command_queue, self.monitor_id),
            daemon=True,
            name=f"mini-program-monitor-{self.monitor_id}",
        )

    def start(self) -> None:
        """启动监控子进程。"""
        self.process.start()

    def stop(self) -> None:
        """请求监控子进程停止。"""
        if self.process.is_alive():
            self.command_queue.put({"type": "stop"})

    def send_command(self, command: dict) -> None:
        """向监控子进程发送卡片操作命令。"""
        if self.process.is_alive():
            self.command_queue.put(command)

    def join(self, timeout: float | None = None) -> None:
        """等待监控子进程结束。"""
        self.process.join(timeout=timeout)

    def is_alive(self) -> bool:
        """返回监控子进程是否仍在运行。"""
        return self.process.is_alive()

    def terminate(self) -> None:
        """强制终止监控子进程。"""
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1.0)


def monitor_worker_main(root_path: str, db_path: str, event_queue: mp.Queue, command_queue: mp.Queue, monitor_id: int) -> None:
    """监控 worker 子进程入口。"""
    worker = AsyncMiniProgramMonitorWorker(Path(root_path), Path(db_path), event_queue, command_queue, monitor_id)
    asyncio.run(worker.run())
