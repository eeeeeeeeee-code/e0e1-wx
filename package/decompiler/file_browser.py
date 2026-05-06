"""提供目录浏览、文本编码识别和局部文件读取能力。"""

from __future__ import annotations

import codecs
import io
from pathlib import Path


def _printable_text_ratio(text: str) -> float:
    if not text:
        return 0.0
    printable_count = sum(1 for char in text if char in "\t\n\r" or (char.isprintable() and char != "\x00"))
    return printable_count / max(1, len(text))


def _likely_utf16_encoding(sample: bytes) -> str:
    if sample.startswith(codecs.BOM_UTF16_LE):
        return "utf-16-le"
    if sample.startswith(codecs.BOM_UTF16_BE):
        return "utf-16-be"
    if len(sample) < 8:
        return ""

    pair_count = len(sample) // 2
    even_bytes = sample[: pair_count * 2 : 2]
    odd_bytes = sample[1 : pair_count * 2 : 2]
    even_null_ratio = even_bytes.count(0) / max(1, len(even_bytes))
    odd_null_ratio = odd_bytes.count(0) / max(1, len(odd_bytes))

    candidates: list[str] = []
    if odd_null_ratio > 0.30 and even_null_ratio < 0.10:
        candidates.append("utf-16-le")
    if even_null_ratio > 0.30 and odd_null_ratio < 0.10:
        candidates.append("utf-16-be")

    for encoding in candidates:
        try:
            text = sample.decode(encoding)
        except UnicodeDecodeError:
            continue
        if _printable_text_ratio(text) > 0.85:
            return encoding
    return ""


def detect_text_encoding(sample: bytes) -> str:
    """根据文件头与常见编码尝试判断文本编码。"""
    if sample.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    utf16_encoding = _likely_utf16_encoding(sample)
    if utf16_encoding:
        return utf16_encoding
    for encoding in ("utf-8", "gb18030", "gbk", "big5"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def looks_binary(sample: bytes) -> bool:
    """根据采样内容判断文件是否明显为二进制。"""
    if not sample:
        return False
    if _likely_utf16_encoding(sample):
        return False
    if b"\x00" in sample:
        return True
    control_count = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 13})
    return control_count / max(1, len(sample)) > 0.30


def iter_text_files(output_dirs: list[Path]) -> list[Path]:
    """递归收集输出目录下可搜索的文本文件。"""
    files: list[Path] = []
    skipped_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg", ".mp3", ".mp4", ".ttf", ".woff", ".woff2"}
    skipped_parts = {".git", ".e0e1_cache", "__pycache__"}
    for output_dir in output_dirs:
        if not output_dir.is_dir():
            continue
        for path in output_dir.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skipped_parts for part in path.parts):
                continue
            if path.suffix.lower() in skipped_suffixes:
                continue
            try:
                with path.open("rb") as file:
                    sample = file.read(4096)
            except OSError:
                continue
            if looks_binary(sample):
                continue
            files.append(path)
    return files


def read_text_lines(path: Path) -> list[tuple[int, str]]:
    """按 utf-8 优先策略读取文本文件的全部行。"""
    with path.open("rb") as file:
        sample = file.read(4096)
        encoding = detect_text_encoding(sample)
        file.seek(0)
        text_file = io.TextIOWrapper(file, encoding=encoding or "utf-8", errors="replace", newline="")
        try:
            return [(line_number, text) for line_number, text in enumerate(text_file, start=1)]
        finally:
            text_file.detach()


def list_directory_entries(path: Path) -> dict:
    """列出单层目录内容，供文件树懒加载使用。"""
    if not path.exists():
        return {"path": str(path), "exists": False, "entries": []}
    if not path.is_dir():
        return {"path": str(path), "exists": True, "entries": []}

    entries: list[dict] = []
    try:
        children = list(path.iterdir())
    except OSError as exc:
        return {"path": str(path), "exists": True, "error": str(exc), "entries": []}

    for child in children:
        try:
            is_dir = child.is_dir()
            is_file = child.is_file()
            if not is_dir and not is_file:
                continue
            size = 0 if is_dir else child.stat().st_size
            has_children = False
            if is_dir:
                try:
                    has_children = any(child.iterdir())
                except OSError:
                    has_children = False
        except OSError:
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "is_dir": is_dir,
                "size": size,
                "has_children": has_children,
            }
        )
    entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
    return {"path": str(path), "exists": True, "entries": entries}


def read_text_window(path: Path, target_line: int, context_lines: int, max_chars: int) -> dict:
    """在线程中读取目标行附近的文本窗口，避免大文件预览截断导致无法跳转。"""
    with path.open("rb") as file:
        sample = file.read(4096)
        binary = looks_binary(sample)
        encoding = detect_text_encoding(sample)
        if binary:
            return {
                "binary": True,
                "encoding": "hex",
                "text": sample[:4096].hex(" "),
                "line_base": 1,
                "truncated": True,
            }

        start_line = max(1, int(target_line) - max(0, int(context_lines)))
        end_line = max(start_line, int(target_line) + max(0, int(context_lines)))
        lines: list[str] = []
        char_count = 0
        reached_target = False
        truncated = False
        file.seek(0)
        text_file = io.TextIOWrapper(file, encoding=encoding, errors="replace", newline="")
        try:
            for line_number, text in enumerate(text_file, start=1):
                if line_number < start_line:
                    continue
                if line_number > end_line:
                    break
                if line_number == target_line:
                    reached_target = True
                if char_count + len(text) > max_chars:
                    truncated = True
                    break
                lines.append(text)
                char_count += len(text)
        finally:
            text_file.detach()
        return {
            "binary": False,
            "encoding": encoding,
            "text": "".join(lines),
            "line_base": start_line,
            "line_count": len(lines),
            "target_line": target_line,
            "truncated": truncated or not reached_target,
        }
