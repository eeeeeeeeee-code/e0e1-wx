"""提供基于反编译输出目录的静态云函数扫描能力。"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Callable


MAX_FILE_BYTES = 50 * 1024 * 1024
WINDOW_SCAN_LENGTH = 2000
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
    ".db",
    ".exe",
    ".dll",
}
SUPPORTED_EXTENSIONS = {
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".jsx",
    ".tsx",
    ".wxs",
    ".json",
    ".html",
    ".wxml",
    ".wxss",
    ".fpcssb",
    ".fpiib",
}
DATABASE_OPERATIONS = ("add", "get", "update", "remove", "count", "aggregate", "doc", "where", "set")
STORAGE_METHODS = ("uploadFile", "downloadFile", "deleteFile", "getTempFileURL")
FUNCTION_NAME_RE = re.compile(r'(?<![\w$])["\']?name["\']?\s*:\s*["\']([^"\']+)["\']', re.S)
FIELD_RE = re.compile(r'(?<![\w$])(?:["\']([^"\']+)["\']|([A-Za-z_$][\w$]*))\s*:', re.S)
COLLECTION_RE = re.compile(r'\.collection\s*\(\s*["\']([^"\']+)["\']\s*\)', re.S)
JS_HEX_ESCAPE_RE = re.compile(r"\\x([0-9a-fA-F]{2})")
JS_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


class CloudSourceScanner:
    """扫描本地反编译源码中的云函数、数据库与云存储特征。"""

    def __init__(
        self,
        progress_callback: Callable[[dict], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """初始化扫描器的进度回调与取消事件。"""
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event or threading.Event()

    def should_cancel(self) -> bool:
        """判断当前任务是否已经收到取消请求。"""
        return self.cancel_event.is_set()

    def emit_progress(self, payload: dict, force: bool = False) -> None:
        """按需向上层发送扫描进度事件。"""
        if self.progress_callback is None:
            return
        scanned_files = int(payload.get("scanned_files") or 0)
        if force or scanned_files % 20 == 0:
            self.progress_callback(dict(payload))

    def discover_files(self, directories: list[Path]) -> list[Path]:
        """递归收集需要执行静态扫描的文本文件。"""
        discovered: list[Path] = []
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
                dir_names[:] = [name for name in dir_names if name != ".e0e1_cache"]
                for file_name in file_names:
                    path = Path(current_root) / file_name
                    suffix = path.suffix.lower()
                    if suffix in SKIP_EXTENSIONS:
                        continue
                    if suffix and suffix not in SUPPORTED_EXTENSIONS:
                        continue
                    resolved_text = str(path.resolve(strict=False))
                    if resolved_text in seen:
                        continue
                    seen.add(resolved_text)
                    discovered.append(path)
        discovered.sort(key=lambda item: str(item).lower())
        return discovered

    def scan_directories(self, directories: list[Path]) -> list[dict]:
        """扫描多个输出目录并返回统一的静态云审计结果。"""
        summary = {
            "directories": [str(path) for path in directories],
            "total_files": 0,
            "scanned_files": 0,
            "match_count": 0,
            "cancelled": False,
        }
        found: dict[str, dict] = {}
        files = self.discover_files(directories)
        summary["total_files"] = len(files)
        self.emit_progress(summary, force=True)

        for file_path in files:
            if self.should_cancel():
                summary["cancelled"] = True
                break
            self.scan_file(file_path, found)
            summary["scanned_files"] = int(summary["scanned_files"]) + 1
            summary["match_count"] = len(found)
            self.emit_progress(summary)

        self.emit_progress(summary, force=True)
        return self.build_results(found)

    def scan_sources(self, sources: list[dict] | list[tuple[str, str]]) -> list[dict]:
        """扫描内存中的源码片段，例如运行时的 `__wxAppCode__`。"""
        summary = {
            "directories": [],
            "total_files": len(sources),
            "scanned_files": 0,
            "match_count": 0,
            "cancelled": False,
        }
        found: dict[str, dict] = {}
        self.emit_progress(summary, force=True)
        for index, source_item in enumerate(sources):
            if self.should_cancel():
                summary["cancelled"] = True
                break
            if isinstance(source_item, dict):
                source_name = str(source_item.get("name") or source_item.get("path") or f"runtime:{index}")
                source_text = str(source_item.get("source") or "")
            else:
                source_name = str(source_item[0] or f"runtime:{index}")
                source_text = str(source_item[1] or "")
            if not source_text:
                continue
            self.scan_source_text(source_text, source_name, found)
            summary["scanned_files"] = int(summary["scanned_files"]) + 1
            summary["match_count"] = len(found)
            self.emit_progress(summary)
        self.emit_progress(summary, force=True)
        return self.build_results(found)

    def scan_file(self, file_path: Path, found: dict[str, dict]) -> None:
        """扫描单个源码文件，并把结果累计到 found 映射中。"""
        try:
            if file_path.stat().st_size > MAX_FILE_BYTES:
                return
            source = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        if not source:
            return
        self.scan_source_text(source, str(file_path), found)

    def scan_source_text(self, source: str, source_name: str, found: dict[str, dict]) -> None:
        """扫描一段源码文本并把结果累计到 found 映射中。"""
        normalized_source = self.decode_js_escapes(source)
        self.extract_function_calls(normalized_source, source_name, found)
        self.extract_database_ops(normalized_source, source_name, found)
        self.extract_storage_ops(normalized_source, source_name, found)

    def decode_js_escapes(self, source: str) -> str:
        """还原源码中的常见 JS 十六进制和 Unicode 转义，兼容未优化包。"""
        if "\\" not in source:
            return source

        def replace_hex(match: re.Match) -> str:
            """把 \\xNN 转义还原成字符。"""
            try:
                return chr(int(match.group(1), 16))
            except (TypeError, ValueError):
                return match.group(0)

        def replace_unicode(match: re.Match) -> str:
            """把 \\uNNNN 转义还原成字符。"""
            try:
                return chr(int(match.group(1), 16))
            except (TypeError, ValueError):
                return match.group(0)

        decoded = JS_HEX_ESCAPE_RE.sub(replace_hex, source)
        return JS_UNICODE_ESCAPE_RE.sub(replace_unicode, decoded)

    def extract_function_calls(self, source: str, source_name: str, found: dict[str, dict]) -> None:
        """提取源码中显式声明的云函数调用及其参数名。"""
        cursor = 0
        while True:
            if self.should_cancel():
                return
            index = source.find("callFunction", cursor)
            if index < 0:
                break
            window = source[index : index + WINDOW_SCAN_LENGTH]
            name_match = FUNCTION_NAME_RE.search(window)
            if name_match is None:
                cursor = index + len("callFunction")
                continue
            function_name = str(name_match.group(1) or "").strip()
            if function_name:
                entry = self.ensure_entry(found, f"function:{function_name}", "function", function_name)
                entry["count"] += 1
                entry["files"].add(str(source_name))
                for field_name in self.extract_data_fields(window):
                    entry["params"].add(field_name)
            cursor = index + len("callFunction")

    def extract_database_ops(self, source: str, source_name: str, found: dict[str, dict]) -> None:
        """提取源码中的云数据库集合和常见数据库操作。"""
        for match in COLLECTION_RE.finditer(source):
            if self.should_cancel():
                return
            collection_name = str(match.group(1) or "").strip()
            if not collection_name:
                continue
            entry = self.ensure_entry(found, f"database:{collection_name}", "database", collection_name)
            entry["count"] += 1
            entry["files"].add(str(source_name))
            after = source[match.end() : match.end() + 300]
            for operation in DATABASE_OPERATIONS:
                if f".{operation}(" in after:
                    entry["params"].add(operation)

    def extract_storage_ops(self, source: str, source_name: str, found: dict[str, dict]) -> None:
        """提取源码中的云存储 API 调用。"""
        for method_name in STORAGE_METHODS:
            count = source.count(method_name)
            if count <= 0:
                continue
            entry = self.ensure_entry(found, f"storage:{method_name}", "storage", method_name)
            entry["count"] += count
            entry["files"].add(str(source_name))

    def extract_data_fields(self, window: str) -> list[str]:
        """从 `data: {}` 片段中提取一级字段名。"""
        marker = window.find("data")
        if marker < 0:
            return []
        brace_index = window.find("{", marker)
        if brace_index < 0:
            return []
        block = self.extract_balanced_block(window, brace_index)
        if not block:
            return []
        ignored_names = {"name", "success", "fail", "complete", "config", "env", "data"}
        results: list[str] = []
        seen: set[str] = set()
        for match in FIELD_RE.finditer(block[1:-1]):
            field_name = str(match.group(1) or match.group(2) or "").strip()
            if not field_name or field_name in ignored_names or field_name in seen:
                continue
            seen.add(field_name)
            results.append(field_name)
        return results

    def extract_balanced_block(self, text: str, start_index: int) -> str:
        """提取起始大括号对应的平衡代码块。"""
        depth = 0
        in_string = ""
        escaped = False
        for index in range(start_index, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == in_string:
                    in_string = ""
                continue
            if char in {"'", '"', "`"}:
                in_string = char
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start_index : index + 1]
        return ""

    def ensure_entry(self, found: dict[str, dict], key: str, entry_type: str, name: str) -> dict:
        """创建或复用一条静态扫描结果。"""
        if key not in found:
            found[key] = {
                "type": entry_type,
                "name": name,
                "params": set(),
                "count": 0,
                "files": set(),
            }
        return found[key]

    def build_results(self, found: dict[str, dict]) -> list[dict]:
        """把内部 set 结构转换为可序列化的结果列表。"""
        results: list[dict] = []
        for entry in found.values():
            results.append(
                {
                    "source": "static",
                    "type": str(entry.get("type") or ""),
                    "name": str(entry.get("name") or ""),
                    "params": sorted(str(name) for name in entry.get("params", set())),
                    "count": int(entry.get("count") or 0),
                    "files": sorted(str(path) for path in entry.get("files", set())),
                }
            )
        results.sort(key=lambda item: (str(item.get("type") or ""), str(item.get("name") or "")))
        return results
