"""并发格式化反编译输出源码并上报优化进度。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from package.code_optimizer import CodeFormatter
from package.decompiler.constants import FORMATTER_PROGRESS_INTERVAL, FORMATTER_WORKER_COUNT


class OptimizeTaskMixin:
    async def run_optimize(self, task_id: int, payload: dict) -> None:
        """执行独立的反编译输出代码优化任务。"""
        raw_dirs = payload.get("output_dirs") if isinstance(payload.get("output_dirs"), list) else []
        output_dirs = [Path(str(path or "")).expanduser() for path in raw_dirs]
        summary = await self.optimize_output_dirs(task_id, output_dirs)
        self.emit({"type": "optimize_result", "task_id": task_id, "summary": summary})

    async def optimize_output_dirs(self, task_id: int, output_dirs: list[Path], applet_id: str = "") -> dict:
        """异步扫描并多线程格式化反编译输出目录。"""
        formatter = CodeFormatter()
        context = self.event_context(applet_id)
        unique_dirs: list[Path] = []
        seen_dirs: set[str] = set()
        for output_dir in output_dirs:
            key = str(output_dir.resolve(strict=False))
            if key in seen_dirs:
                continue
            unique_dirs.append(output_dir)
            seen_dirs.add(key)

        file_paths: list[Path] = []
        for output_dir in unique_dirs:
            await asyncio.sleep(0)
            if hasattr(self, "raise_if_task_cancelled"):
                self.raise_if_task_cancelled(task_id)
            file_paths.extend(await asyncio.to_thread(formatter.discover_files, output_dir))

        unique_files: list[Path] = []
        seen_files: set[str] = set()
        for file_path in file_paths:
            key = str(file_path.resolve(strict=False))
            if key in seen_files:
                continue
            unique_files.append(file_path)
            seen_files.add(key)

        total_files = len(unique_files)
        summary = {
            "directories": [str(path) for path in unique_dirs],
            "total_files": total_files,
            "processed_count": 0,
            "success_count": 0,
            "skip_count": 0,
            "error_count": 0,
        }
        self.emit({"type": "optimize_started", "task_id": task_id, "summary": summary, **context})
        if total_files == 0:
            return summary

        file_queue: asyncio.Queue[Path] = asyncio.Queue()
        for file_path in unique_files:
            file_queue.put_nowait(file_path)

        async def format_worker() -> None:
            """从异步队列取文件并交给线程执行格式化。"""
            nonlocal summary
            while True:
                if hasattr(self, "raise_if_task_cancelled"):
                    self.raise_if_task_cancelled(task_id)
                try:
                    file_path = file_queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                result = await asyncio.to_thread(formatter.format_file, file_path)
                if hasattr(self, "raise_if_task_cancelled"):
                    self.raise_if_task_cancelled(task_id)
                status = str(result.get("status") or "")
                summary["processed_count"] = int(summary["processed_count"]) + 1
                if status == "success":
                    summary["success_count"] = int(summary["success_count"]) + 1
                elif status == "error":
                    summary["error_count"] = int(summary["error_count"]) + 1
                else:
                    summary["skip_count"] = int(summary["skip_count"]) + 1

                processed = int(summary["processed_count"])
                if processed % FORMATTER_PROGRESS_INTERVAL == 0 or processed == total_files:
                    self.emit(
                        {
                            "type": "optimize_progress",
                            "task_id": task_id,
                            "summary": dict(summary),
                            "last_file": result,
                            **context,
                        }
                    )

        workers = [asyncio.create_task(format_worker()) for _ in range(min(FORMATTER_WORKER_COUNT, total_files))]
        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            raise
        return summary
