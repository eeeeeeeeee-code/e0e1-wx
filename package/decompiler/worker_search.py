"""提供反编译输出目录的全局文本搜索后台任务。"""

from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path

from package.decompiler.file_browser import iter_text_files, read_text_lines


SEARCH_CHUNK_SIZE = 100


class SearchTaskMixin:
    async def run_search_text(self, task_id: int, payload: dict) -> None:
        """执行普通文本或正则的全局搜索任务。"""
        raw_dirs = payload.get("output_dirs") if isinstance(payload.get("output_dirs"), list) else []
        output_dirs = [Path(str(path or "")).expanduser() for path in raw_dirs]
        query = str(payload.get("query") or "")
        regex_enabled = bool(payload.get("regex_enabled"))
        summary = await self.execute_search_text(task_id, output_dirs, query, regex_enabled)
        if summary is None:
            return
        self.emit({"type": "search_done", "task_id": task_id, "summary": summary})

    async def execute_search_text(self, task_id: int, output_dirs: list[Path], query: str, regex_enabled: bool) -> dict | None:
        """扫描输出目录并分批回传命中文本结果。"""
        cancel_event = self.cancel_events.get(task_id)
        if cancel_event is None:
            cancel_event = threading.Event()
            self.cancel_events[task_id] = cancel_event
        try:
            pattern = None
            if regex_enabled:
                try:
                    pattern = re.compile(query)
                except re.error as exc:
                    self.emit(
                        {
                            "type": "search_text_error",
                            "task_id": task_id,
                            "message": f"正则表达式无效：{exc}",
                        }
                    )
                    return None

            files = await asyncio.to_thread(iter_text_files, output_dirs)
            results: list[dict] = []
            chunk: list[dict] = []
            scanned_count = 0
            self.emit(
                {
                    "type": "search_started",
                    "task_id": task_id,
                    "query": query,
                    "regex_enabled": regex_enabled,
                    "file_count": len(files),
                }
            )

            for file_path in files:
                if cancel_event.is_set():
                    raise asyncio.CancelledError
                matches = await asyncio.to_thread(self.search_file_matches, file_path, output_dirs, query, pattern)
                scanned_count += 1
                if matches:
                    results.extend(matches)
                    chunk.extend(matches)
                self.emit(
                    {
                        "type": "search_progress",
                        "task_id": task_id,
                        "scanned_count": scanned_count,
                        "result_count": len(results),
                    }
                )
                if len(chunk) >= SEARCH_CHUNK_SIZE:
                    self.emit(
                        {
                            "type": "search_chunk",
                            "task_id": task_id,
                            "results": [dict(item) for item in chunk],
                            "loaded_count": len(results),
                            "scanned_count": scanned_count,
                        }
                    )
                    chunk = []
                await asyncio.sleep(0)

            if chunk:
                self.emit(
                    {
                        "type": "search_chunk",
                        "task_id": task_id,
                        "results": [dict(item) for item in chunk],
                        "loaded_count": len(results),
                        "scanned_count": scanned_count,
                    }
                )

            return {
                "query": query,
                "regex_enabled": regex_enabled,
                "results": results,
                "result_count": len(results),
                "scanned_count": scanned_count,
                "output_dirs": [str(path) for path in output_dirs],
            }
        finally:
            self.cancel_events.pop(task_id, None)

    def search_file_matches(
        self,
        file_path: Path,
        output_dirs: list[Path],
        query: str,
        pattern: re.Pattern | None,
    ) -> list[dict]:
        """扫描单个文件并返回行级搜索结果。"""
        relative_path = self.build_relative_path(file_path, output_dirs)
        results: list[dict] = []
        for line_number, line_text in read_text_lines(file_path):
            if pattern is not None:
                for match in pattern.finditer(line_text):
                    results.append(
                        {
                            "file_path": str(file_path),
                            "relative_path": relative_path,
                            "line_number": line_number,
                            "line_text": line_text.rstrip("\r\n"),
                            "match_text": match.group(0),
                            "match_start": int(match.start()),
                            "match_end": int(match.end()),
                        }
                    )
            else:
                match_start = line_text.find(query)
                if match_start < 0:
                    continue
                results.append(
                    {
                        "file_path": str(file_path),
                        "relative_path": relative_path,
                        "line_number": line_number,
                        "line_text": line_text.rstrip("\r\n"),
                        "match_text": query,
                        "match_start": int(match_start),
                        "match_end": int(match_start + len(query)),
                    }
                )
        return results

    def build_relative_path(self, file_path: Path, output_dirs: list[Path]) -> str:
        """基于输出根目录生成展示用相对路径。"""
        for output_dir in output_dirs:
            try:
                return str(file_path.relative_to(output_dir)).replace("\\", "/")
            except ValueError:
                continue
        return file_path.name
