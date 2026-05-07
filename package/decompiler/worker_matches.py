"""执行正则匹配扫描和匹配结果文件导出。"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from package.content_scanner import RegexContentScanner


class MatchTaskMixin:
    async def run_scan_matches(self, task_id: int, payload: dict) -> None:
        """执行反编译输出目录正则匹配扫描任务。"""
        raw_dirs = payload.get("output_dirs") if isinstance(payload.get("output_dirs"), list) else []
        output_dirs = [Path(str(path or "")).expanduser() for path in raw_dirs]
        rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
        summary = await self.execute_scan_matches(task_id, output_dirs, rules)
        self.emit({"type": "match_scan_result", "task_id": task_id, "summary": summary})

    async def execute_scan_matches(self, task_id: int, output_dirs: list[Path], rules: list[dict], applet_id: str = "") -> dict:
        """执行正则匹配扫描核心流程并返回汇总结果。"""
        context = self.event_context(applet_id)
        cancel_event = self.cancel_events.get(task_id)
        if cancel_event is None:
            cancel_event = threading.Event()
            self.cancel_events[task_id] = cancel_event

        def progress_callback(summary: dict) -> None:
            """从扫描线程向 UI 发送进度事件。"""
            self.emit({"type": "match_scan_progress", "task_id": task_id, "summary": summary, **context})

        try:
            scanner = RegexContentScanner(rules, progress_callback=progress_callback, cancel_event=cancel_event)
            self.emit(
                {
                    "type": "match_scan_started",
                    "task_id": task_id,
                    "rule_count": len(scanner.rules),
                    "output_dirs": [str(path) for path in output_dirs],
                    **context,
                }
            )
            return await asyncio.to_thread(scanner.scan, output_dirs)
        finally:
            self.cancel_events.pop(task_id, None)
    async def run_export_matches(self, task_id: int, payload: dict) -> None:
        """导出匹配结果到 JSON 或 TXT 文件。"""
        output_path = Path(str(payload.get("path") or "")).expanduser()
        export_format = str(payload.get("format") or "json").lower()
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        await asyncio.to_thread(self.export_match_results, output_path, export_format, results)
        self.emit({"type": "export_matches_result", "task_id": task_id, "path": str(output_path), "count": len(results)})

    def export_match_results(self, output_path: Path, export_format: str, results: list[dict]) -> None:
        """在后台线程中写出匹配结果文件。"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if export_format == "txt":
            lines = []
            for result in results:
                lines.append(
                    f"[{result.get('rule_name') or '-'}] "
                    f"{result.get('file_path') or ''}:{int(result.get('line_number') or 0)} "
                    f"{result.get('match_text') or ''}"
                )
            output_path.write_text("\n".join(lines), encoding="utf-8")
            return
        output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
