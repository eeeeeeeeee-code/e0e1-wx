"""运行加解密后台 worker，并向 UI 返回任务进度和结果。"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import queue
import traceback

from package.crypto.core import CryptoError, decrypt_data, derive_aes_key_result, encrypt_data


def execute_crypto_operation(operation: str, payload: dict) -> dict:
    """在子进程中执行一次加密、解密或密钥派生任务。"""
    if operation == "encrypt":
        result = encrypt_data(
            str(payload.get("data", "")),
            str(payload.get("iv_b64", "")),
            str(payload.get("key_b64", "")),
        )
        return {"text": result}
    if operation == "decrypt":
        result = decrypt_data(
            str(payload.get("data", "")),
            str(payload.get("iv_b64", "")),
            str(payload.get("key_b64", "")),
        )
        return {"text": result}
    if operation == "derive_key":
        return derive_aes_key_result(
            str(payload.get("wxid", "")),
            str(payload.get("salt", "")),
            str(payload.get("iv", "")),
        )
    raise CryptoError(f"未知加解密操作：{operation}")


class AsyncCryptoWorker:
    """运行在独立进程中的 asyncio 加密解密 worker。"""

    def __init__(self, event_queue: mp.Queue, command_queue: mp.Queue) -> None:
        """初始化 worker 的进程安全通信队列。"""
        self.event_queue = event_queue
        self.command_queue = command_queue
        self.running = True
        self.tasks: dict[int, asyncio.Task] = {}

    async def run(self) -> None:
        """运行 worker 命令循环并隔离每个后台任务。"""
        try:
            while self.running:
                await self.process_commands()
                self.cleanup_finished_tasks()
                await asyncio.sleep(0.03)
        except Exception as exc:
            self.emit({"type": "crypto_error", "message": f"加解密进程异常：{exc}"})
        finally:
            await self.cancel_all_tasks()

    def emit(self, event: dict) -> None:
        """向 UI 进程发送加解密任务事件。"""
        self.event_queue.put(event)

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
                if task_id <= 0:
                    self.emit({"type": "crypto_error", "message": "加解密任务编号无效。"})
                    continue
                operation = str(command.get("operation", ""))
                payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
                self.tasks[task_id] = asyncio.create_task(self.run_task(task_id, operation, payload))

    async def run_task(self, task_id: int, operation: str, payload: dict) -> None:
        """执行单个任务并把异常转换为 UI 可展示事件。"""
        self.emit({"type": "crypto_started", "task_id": task_id, "operation": operation})
        try:
            await asyncio.sleep(0)
            result = execute_crypto_operation(operation, payload)
            self.emit(
                {
                    "type": "crypto_result",
                    "task_id": task_id,
                    "operation": operation,
                    "result": result,
                }
            )
        except asyncio.CancelledError:
            self.emit({"type": "crypto_cancelled", "task_id": task_id, "operation": operation})
            raise
        except CryptoError as exc:
            self.emit({"type": "crypto_error", "task_id": task_id, "operation": operation, "message": str(exc)})
        except Exception as exc:
            self.emit(
                {
                    "type": "crypto_error",
                    "task_id": task_id,
                    "operation": operation,
                    "message": f"加解密任务失败：{exc}",
                    "traceback": traceback.format_exc(limit=3),
                }
            )

    def cancel_task(self, task_id: int) -> None:
        """取消指定的未完成任务。"""
        task = self.tasks.get(task_id)
        if task is not None and not task.done():
            task.cancel()
        else:
            self.emit({"type": "crypto_cancelled", "task_id": task_id})

    def cleanup_finished_tasks(self) -> None:
        """清理已经结束的 asyncio 任务引用。"""
        finished_ids = [task_id for task_id, task in self.tasks.items() if task.done()]
        for task_id in finished_ids:
            self.tasks.pop(task_id, None)

    async def cancel_all_tasks(self) -> None:
        """停止 worker 前取消所有仍在运行的任务。"""
        pending = [task for task in self.tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self.tasks.clear()


def crypto_worker_main(event_queue: mp.Queue, command_queue: mp.Queue) -> None:
    """加解密 worker 子进程入口。"""
    asyncio.run(AsyncCryptoWorker(event_queue, command_queue).run())


class CryptoTaskRunner:
    """UI 进程中的加解密任务调度器。"""

    def __init__(self) -> None:
        """启动独立加解密进程并准备通信队列。"""
        self.event_queue: mp.Queue = mp.Queue()
        self.command_queue: mp.Queue = mp.Queue()
        self.next_task_id = 1
        self.process = mp.Process(
            target=crypto_worker_main,
            args=(self.event_queue, self.command_queue),
            daemon=True,
            name="crypto-async-worker",
        )
        self.process.start()

    def submit(self, operation: str, payload: dict) -> int:
        """提交一项加密、解密或密钥派生任务并返回任务编号。"""
        task_id = self.next_task_id
        self.next_task_id += 1
        self.command_queue.put(
            {
                "type": "submit",
                "task_id": task_id,
                "operation": operation,
                "payload": payload,
            }
        )
        return task_id

    def cancel(self, task_id: int) -> None:
        """请求取消指定任务。"""
        self.command_queue.put({"type": "cancel", "task_id": task_id})

    def get_event_nowait(self) -> dict:
        """非阻塞获取一个 worker 返回事件。"""
        return self.event_queue.get_nowait()

    def shutdown(self, wait: bool = True) -> None:
        """停止加解密 worker 进程，可选择是否等待进程退出。"""
        if self.process.is_alive():
            self.command_queue.put({"type": "stop"})
        if not wait:
            return
        if self.process.is_alive():
            self.process.join(timeout=1.0)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1.0)
