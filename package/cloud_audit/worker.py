"""实现云审计静态扫描与导出专用后台 worker。"""

from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import queue
import threading
import traceback
from pathlib import Path

from package.cloud_audit.cache import load_cloud_audit_entry, save_cloud_audit_entry
from package.cloud_audit.models import build_report_payload
from package.cloud_audit.scanner import CloudSourceScanner
from package.decompiler.cache_keys import output_signature


class AsyncCloudAuditWorker:
    """在独立进程中执行静态扫描和报告导出任务。"""

    def __init__(self, event_queue: mp.Queue, command_queue: mp.Queue) -> None:
        """初始化 worker 队列、任务表和取消事件表。"""
        self.event_queue = event_queue
        self.command_queue = command_queue
        self.running = True
        self.tasks: dict[int, asyncio.Task] = {}
        self.cancel_events: dict[int, threading.Event] = {}

    async def run(self) -> None:
        """运行 worker 命令循环，并保证退出时清理所有任务。"""
        try:
            while self.running:
                await self.process_commands()
                self.cleanup_finished_tasks()
                await asyncio.sleep(0.03)
        except Exception as exc:
            self.emit({"type": "cloud_worker_error", "message": f"云审计 worker 异常：{exc}"})
        finally:
            await self.cancel_all_tasks()

    def emit(self, event: dict) -> None:
        """向 UI 进程发送静态扫描或导出事件。"""
        self.event_queue.put(event)

    async def process_commands(self) -> None:
        """以非阻塞方式处理提交、取消和停止命令。"""
        while True:
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                break
            command_type = str(command.get("type") or "")
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
                    continue
                cancel_event = threading.Event()
                self.cancel_events[task_id] = cancel_event
                self.tasks[task_id] = asyncio.create_task(self.run_task(task_id, operation, payload, cancel_event))

    async def run_task(self, task_id: int, operation: str, payload: dict, cancel_event: threading.Event) -> None:
        """执行单个任务，并把异常转为界面可消费的事件。"""
        try:
            if operation == "scan_static":
                await self.run_scan_static(task_id, payload, cancel_event)
            elif operation == "export_report":
                await self.run_export_report(task_id, payload)
            elif operation == "load_cache":
                await self.run_load_cache(task_id, payload)
            elif operation == "save_cache":
                await self.run_save_cache(task_id, payload)
            elif operation == "clear_cache":
                await self.run_clear_cache(task_id, payload)
            else:
                raise ValueError(f"未知云审计操作：{operation}")
        except asyncio.CancelledError:
            self.emit({"type": f"{operation}_cancelled", "task_id": task_id})
            raise
        except Exception as exc:
            self.emit(
                {
                    "type": f"{operation}_error",
                    "task_id": task_id,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=3),
                }
            )

    async def run_scan_static(self, task_id: int, payload: dict, cancel_event: threading.Event) -> None:
        """扫描多个反编译输出目录中的云能力调用特征。"""
        record_id = int(payload.get("record_id") or 0)
        directories = [Path(str(item)).expanduser() for item in payload.get("output_dirs", []) if str(item).strip()]
        cache_path_text = str(payload.get("cache_path") or "").strip()
        cache_path = Path(cache_path_text).expanduser() if cache_path_text else None
        applet_key = str(payload.get("applet_key") or "").strip()
        force = bool(payload.get("force"))
        result = await asyncio.to_thread(
            self.scan_static_with_cache,
            task_id,
            record_id,
            directories,
            cache_path,
            applet_key,
            force,
            cancel_event,
        )
        self.emit(
            {
                "type": "scan_static_result",
                "task_id": task_id,
                "record_id": record_id,
                "results": result.get("results", []),
                "cached": bool(result.get("cached")),
                "cancelled": bool(result.get("cancelled")),
            }
        )

    def scan_static_with_cache(
        self,
        task_id: int,
        record_id: int,
        directories: list[Path],
        cache_path: Path | None,
        applet_key: str,
        force: bool,
        cancel_event: threading.Event,
    ) -> dict:
        """在线程中按输出目录签名复用或刷新文件静态扫描结果。"""
        signature = output_signature(directories)
        if cancel_event.is_set():
            return {"results": [], "cached": False, "cancelled": True}
        cached_entry = load_cloud_audit_entry(cache_path, applet_key) if applet_key and cache_path is not None else {}
        cached_results = cached_entry.get("static_entries") if isinstance(cached_entry.get("static_entries"), list) else []
        if not force and cached_results and cached_entry.get("static_signature") == signature:
            self.emit(
                {
                    "type": "scan_static_progress",
                    "task_id": task_id,
                    "record_id": record_id,
                    "summary": {
                        "directories": [str(path) for path in directories],
                        "total_files": len(signature.get("files", [])) if isinstance(signature, dict) else 0,
                        "scanned_files": 0,
                        "match_count": len(cached_results),
                        "cached": True,
                        "cancelled": False,
                    },
                }
            )
            return {"results": [dict(item) for item in cached_results if isinstance(item, dict)], "cached": True}

        scanner = CloudSourceScanner(
            progress_callback=lambda summary: self.emit(
                {"type": "scan_static_progress", "task_id": task_id, "record_id": record_id, "summary": summary}
            ),
            cancel_event=cancel_event,
        )
        results = scanner.scan_directories(directories)
        if applet_key and cache_path is not None and not cancel_event.is_set():
            save_cloud_audit_entry(
                cache_path,
                applet_key,
                {
                    "static_signature": signature,
                    "static_entries": [dict(item) for item in results if isinstance(item, dict)],
                },
            )
        return {"results": results, "cached": False, "cancelled": cancel_event.is_set()}

    async def run_export_report(self, task_id: int, payload: dict) -> None:
        """把界面上的云审计记录导出为 UTF-8 JSON 报告。"""
        export_path = Path(str(payload.get("path") or "")).expanduser()
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        call_history = payload.get("call_history") if isinstance(payload.get("call_history"), list) else []
        report = build_report_payload(items, call_history)
        await asyncio.to_thread(self.write_report, export_path, report)
        self.emit({"type": "export_report_done", "task_id": task_id, "path": str(export_path)})

    def write_report(self, export_path: Path, report: dict) -> None:
        """在子线程中写入导出 JSON 报告文件。"""
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with export_path.open("w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)

    async def run_load_cache(self, task_id: int, payload: dict) -> None:
        """异步读取指定卡片的云审计缓存。"""
        record_id = int(payload.get("record_id") or 0)
        cache_path_text = str(payload.get("cache_path") or "").strip()
        applet_key = str(payload.get("applet_key") or "").strip()
        entry = {}
        if cache_path_text and applet_key:
            entry = await asyncio.to_thread(
                load_cloud_audit_entry,
                Path(cache_path_text).expanduser(),
                applet_key,
            )
        self.emit({"type": "load_cache_result", "task_id": task_id, "record_id": record_id, "entry": entry})

    async def run_save_cache(self, task_id: int, payload: dict) -> None:
        """异步合并保存指定卡片的云审计缓存。"""
        record_id = int(payload.get("record_id") or 0)
        cache_path_text = str(payload.get("cache_path") or "").strip()
        applet_key = str(payload.get("applet_key") or "").strip()
        entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
        saved_entry = {}
        if cache_path_text and applet_key:
            saved_entry = await asyncio.to_thread(
                save_cloud_audit_entry,
                Path(cache_path_text).expanduser(),
                applet_key,
                entry,
            )
        self.emit({"type": "save_cache_done", "task_id": task_id, "record_id": record_id, "entry": saved_entry})

    async def run_clear_cache(self, task_id: int, payload: dict) -> None:
        """异步清空指定卡片的云审计结果缓存段。"""
        record_id = int(payload.get("record_id") or 0)
        cache_path_text = str(payload.get("cache_path") or "").strip()
        applet_key = str(payload.get("applet_key") or "").strip()
        cleared_entry = {}
        if cache_path_text and applet_key:
            cleared_entry = await asyncio.to_thread(
                save_cloud_audit_entry,
                Path(cache_path_text).expanduser(),
                applet_key,
                {
                    "static_signature": {},
                    "static_entries": [],
                    "runtime_static_entries": [],
                    "dynamic_entries": [],
                    "call_history": [],
                },
            )
        self.emit({"type": "clear_cache_done", "task_id": task_id, "record_id": record_id, "entry": cleared_entry})

    def cancel_task(self, task_id: int) -> None:
        """取消指定任务，并同步触发线程侧取消事件。"""
        cancel_event = self.cancel_events.get(task_id)
        if cancel_event is not None:
            cancel_event.set()
        task = self.tasks.get(task_id)
        if task is not None and not task.done():
            task.cancel()

    def cleanup_finished_tasks(self) -> None:
        """清理已经结束的任务和取消事件。"""
        finished_ids = [task_id for task_id, task in self.tasks.items() if task.done()]
        for task_id in finished_ids:
            self.tasks.pop(task_id, None)
            self.cancel_events.pop(task_id, None)

    async def cancel_all_tasks(self) -> None:
        """在 worker 退出前取消全部未完成任务。"""
        for cancel_event in self.cancel_events.values():
            cancel_event.set()
        pending = [task for task in self.tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self.tasks.clear()
        self.cancel_events.clear()


def cloud_audit_worker_main(event_queue: mp.Queue, command_queue: mp.Queue) -> None:
    """云审计 worker 子进程入口。"""
    asyncio.run(AsyncCloudAuditWorker(event_queue, command_queue).run())
