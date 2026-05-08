"""基于用户规则扫描反编译输出内容并生成匹配摘要。"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Callable


MAX_MATCH_TEXT_LENGTH = 500
READ_LINE_LIMIT_BYTES = 2 * 1024 * 1024
CACHE_DIR_NAME = ".e0e1_cache"
SKIP_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".ico",
    ".mp3",
    ".mp4",
    ".zip",
    ".gz",
    ".br",
    ".wxapkg",
}


class RegexContentScanner:
    """使用配置正则流式扫描文件内容。"""

    def __init__(
        self,
        rules: list[dict],
        progress_callback: Callable[[dict], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """初始化扫描规则、进度回调和取消事件。"""
        self.rules = self.compile_rules(rules)
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event or threading.Event()

    def compile_rules(self, rules: list[dict]) -> list[dict]:
        """编译启用的正则规则，跳过无效规则。"""
        compiled_rules: list[dict] = []
        for index, rule in enumerate(rules or []):
            if not isinstance(rule, dict) or not bool(rule.get("enabled", True)):
                continue
            name = str(rule.get("name") or f"规则 {index + 1}").strip()
            pattern = str(rule.get("pattern") or "").strip()
            if not pattern:
                continue
            try:
                compiled_rules.append(
                    {
                        "name": name,
                        "pattern": pattern,
                        "regex": re.compile(pattern),
                    }
                )
            except re.error:
                continue
        return compiled_rules

    def should_cancel(self) -> bool:
        """判断当前扫描任务是否已被请求取消。"""
        return self.cancel_event.is_set()

    def discover_files(self, directories: list[Path]) -> list[Path]:
        """递归发现需要扫描的普通文件。"""
        files: list[Path] = []
        seen: set[str] = set()
        for directory in directories:
            if self.should_cancel():
                break
            root = Path(directory)
            if not root.exists() or not root.is_dir():
                continue
            for current_root, dir_names, file_names in os.walk(root):
                if self.should_cancel():
                    break
                dir_names[:] = [name for name in dir_names if name != CACHE_DIR_NAME]
                for file_name in file_names:
                    file_path = Path(current_root) / file_name
                    if CACHE_DIR_NAME in file_path.parts:
                        continue
                    if file_path.suffix.lower() in SKIP_EXTENSIONS:
                        continue
                    key = str(file_path.resolve(strict=False))
                    if key in seen:
                        continue
                    files.append(file_path)
                    seen.add(key)
        files.sort(key=lambda item: str(item).lower())
        return files

    def looks_binary(self, sample: bytes) -> bool:
        """根据采样字节判断文件是否明显为二进制。"""
        if not sample:
            return False
        if b"\x00" in sample:
            return True
        control_count = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 13})
        return control_count / max(1, len(sample)) > 0.30

    def emit_progress(self, summary: dict, force: bool = False) -> None:
        """按需发送扫描进度。"""
        if self.progress_callback is None:
            return
        scanned_count = int(summary.get("scanned_count") or 0)
        if force or scanned_count % 20 == 0:
            self.progress_callback(dict(summary))

    def scan(self, directories: list[Path]) -> dict:
        """扫描目录并返回匹配结果汇总。"""
        summary = {
            "directories": [str(path) for path in directories],
            "total_files": 0,
            "scanned_count": 0,
            "match_count": 0,
            "error_count": 0,
            "cancelled": False,
            "results": [],
        }
        if not self.rules:
            return summary

        files = self.discover_files(directories)
        summary["total_files"] = len(files)
        self.emit_progress(summary, force=True)
        for file_path in files:
            if self.should_cancel():
                summary["cancelled"] = True
                break
            try:
                matches = self.scan_file(file_path)
                summary["results"].extend(matches)
                summary["match_count"] = int(summary["match_count"]) + len(matches)
            except OSError:
                summary["error_count"] = int(summary["error_count"]) + 1
            finally:
                summary["scanned_count"] = int(summary["scanned_count"]) + 1
                self.emit_progress(summary)
        self.emit_progress(summary, force=True)
        return summary

    def scan_file(self, file_path: Path) -> list[dict]:
        """流式扫描单个文件并返回匹配结果。"""
        results: list[dict] = []
        with file_path.open("rb") as file:
            sample = file.read(4096)
            if self.looks_binary(sample):
                return results
            file.seek(0)
            for line_number, raw_line in enumerate(file, start=1):
                if self.should_cancel():
                    break
                if len(raw_line) > READ_LINE_LIMIT_BYTES:
                    continue
                line = raw_line.decode("utf-8", errors="ignore").rstrip("\r\n")
                if not line:
                    continue
                for rule in self.rules:
                    regex = rule["regex"]
                    for match in regex.finditer(line):
                        match_text = match.group(0)
                        if len(match_text) > MAX_MATCH_TEXT_LENGTH:
                            match_text = match_text[:MAX_MATCH_TEXT_LENGTH] + "..."
                        results.append(
                            {
                                "match_text": match_text,
                                "file_path": str(file_path),
                                "line_number": line_number,
                                "rule_name": str(rule["name"]),
                                "match_start": match.start(),
                                "match_end": match.end(),
                            }
                        )
        return results
