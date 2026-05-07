"""处理反编译输出目录列表、文本预览和二进制预览任务。"""

from __future__ import annotations

import asyncio
import codecs
from pathlib import Path

from package.decompiler.constants import (
    MAX_BINARY_PREVIEW_BYTES,
    MAX_PREVIEW_BYTES,
    MAX_TARGET_PREVIEW_BYTES,
    READ_CHUNK_BYTES,
    TARGET_PREVIEW_CONTEXT_LINES,
)
from package.decompiler.core import WxapkgError
from package.decompiler.file_browser import detect_text_encoding, list_directory_entries, looks_binary, read_text_window


class FileTaskMixin:
    async def run_list_dir(self, task_id: int, payload: dict) -> None:
        """异步列出目录内容并返回给文件树。"""
        path = Path(str(payload.get("path") or "")).expanduser()
        result = await asyncio.to_thread(list_directory_entries, path)
        self.emit({"type": "tree_loaded", "task_id": task_id, "result": result})

    async def run_read_file(self, task_id: int, payload: dict) -> None:
        """按块读取文本文件内容并持续发送给 UI。"""
        path = Path(str(payload.get("path") or "")).expanduser()
        max_bytes = int(payload.get("max_bytes") or MAX_PREVIEW_BYTES)
        if not await asyncio.to_thread(path.is_file):
            raise WxapkgError(f"文件不存在：{path}")

        target_line = int(payload.get("target_line") or 0)
        if target_line > 0:
            await self.run_read_file_window(task_id, path, target_line)
            return

        size = (await asyncio.to_thread(path.stat)).st_size
        file = await asyncio.to_thread(path.open, "rb")
        read_bytes = 0
        encoding = "utf-8"
        truncated = False
        try:
            first_chunk = await asyncio.to_thread(file.read, READ_CHUNK_BYTES)
            read_bytes += len(first_chunk)
            binary = looks_binary(first_chunk)
            encoding = detect_text_encoding(first_chunk)
            self.emit(
                {
                    "type": "content_started",
                    "task_id": task_id,
                    "path": str(path),
                    "size": size,
                    "encoding": encoding,
                    "binary": binary,
                }
            )
            if binary:
                preview = first_chunk[:4096].hex(" ")
                self.emit({"type": "content_chunk", "task_id": task_id, "path": str(path), "text": preview})
                self.emit({"type": "content_loaded", "task_id": task_id, "path": str(path), "encoding": "hex", "truncated": size > 4096})
                return

            decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
            current = first_chunk
            while current:
                await asyncio.sleep(0)
                text = decoder.decode(current, final=False)
                if text:
                    self.emit({"type": "content_chunk", "task_id": task_id, "path": str(path), "text": text})
                if read_bytes >= max_bytes:
                    truncated = size > read_bytes
                    break
                current = await asyncio.to_thread(file.read, min(READ_CHUNK_BYTES, max_bytes - read_bytes))
                read_bytes += len(current)
            tail = decoder.decode(b"", final=True)
            if tail:
                self.emit({"type": "content_chunk", "task_id": task_id, "path": str(path), "text": tail})
        finally:
            await asyncio.to_thread(file.close)
        self.emit({"type": "content_loaded", "task_id": task_id, "path": str(path), "encoding": encoding, "truncated": truncated})

    async def run_read_file_window(self, task_id: int, path: Path, target_line: int) -> None:
        """读取目标行附近的文本片段并返回给 UI 定位。"""
        size = (await asyncio.to_thread(path.stat)).st_size
        result = await asyncio.to_thread(
            read_text_window,
            path,
            target_line,
            TARGET_PREVIEW_CONTEXT_LINES,
            MAX_TARGET_PREVIEW_BYTES,
        )
        self.emit(
            {
                "type": "content_started",
                "task_id": task_id,
                "path": str(path),
                "size": size,
                "encoding": result.get("encoding"),
                "binary": bool(result.get("binary")),
                "line_base": int(result.get("line_base") or 1),
                "target_line": target_line,
            }
        )
        text = str(result.get("text") or "")
        if text:
            self.emit({"type": "content_chunk", "task_id": task_id, "path": str(path), "text": text})
        self.emit(
            {
                "type": "content_loaded",
                "task_id": task_id,
                "path": str(path),
                "encoding": result.get("encoding"),
                "truncated": bool(result.get("truncated")),
                "line_base": int(result.get("line_base") or 1),
                "target_line": target_line,
                "targeted": True,
            }
        )

    async def run_read_binary(self, task_id: int, payload: dict) -> None:
        """读取图片等二进制预览文件并返回字节数据。"""
        path = Path(str(payload.get("path") or "")).expanduser()
        max_bytes = int(payload.get("max_bytes") or MAX_BINARY_PREVIEW_BYTES)
        if not await asyncio.to_thread(path.is_file):
            raise WxapkgError(f"文件不存在：{path}")

        size = (await asyncio.to_thread(path.stat)).st_size
        if size > max_bytes:
            raise WxapkgError(f"文件过大，无法预览：{path.name}")

        data = await asyncio.to_thread(path.read_bytes)
        self.emit(
            {
                "type": "binary_loaded",
                "task_id": task_id,
                "path": str(path),
                "size": size,
                "data": data,
            }
        )
