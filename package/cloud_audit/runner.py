"""封装云审计静态扫描 worker 的 UI 进程调度入口。"""

from __future__ import annotations

import multiprocessing as mp

from package.cloud_audit.worker import cloud_audit_worker_main


class CloudAuditTaskRunner:
    """在 UI 进程中管理云审计静态扫描子进程与队列。"""

    def __init__(self) -> None:
        """启动静态扫描 worker，并准备任务编号。"""
        self.event_queue: mp.Queue = mp.Queue()
        self.command_queue: mp.Queue = mp.Queue()
        self.next_task_id = 1
        self.process = mp.Process(
            target=cloud_audit_worker_main,
            args=(self.event_queue, self.command_queue),
            daemon=True,
            name="cloud-audit-worker",
        )
        self.process.start()

    def submit(self, operation: str, payload: dict) -> int:
        """提交静态扫描或导出任务，并返回任务编号。"""
        task_id = self.next_task_id
        self.next_task_id += 1
        self.command_queue.put({"type": "submit", "task_id": task_id, "operation": operation, "payload": payload})
        return task_id

    def cancel(self, task_id: int) -> None:
        """取消指定任务。"""
        self.command_queue.put({"type": "cancel", "task_id": int(task_id or 0)})

    def get_event_nowait(self) -> dict:
        """非阻塞获取一个 worker 事件。"""
        return self.event_queue.get_nowait()

    def shutdown(self, wait: bool = True) -> None:
        """停止静态扫描 worker，可选是否等待退出。"""
        if self.process.is_alive():
            self.command_queue.put({"type": "stop"})
        if not wait:
            return
        if self.process.is_alive():
            self.process.join(timeout=1.0)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1.0)
