"""处理 UI 发来的删除、隐藏、重绑定和停止监控命令。"""

from __future__ import annotations

import asyncio
import queue
import time
from pathlib import Path


class MonitorCommandMixin:
    async def process_commands(self) -> None:
        """处理 UI 进程发送的删除、隐藏和重新绑定命令。"""
        changed = False
        while True:
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                break
            command_type = command.get("type")
            if command_type == "stop":
                self.running = False
                return
            try:
                if command_type == "delete":
                    await self.delete_record(int(command.get("id", 0)), str(command.get("output_root") or ""))
                    changed = True
                elif command_type == "hide":
                    self.hide_record(int(command.get("id", 0)))
                    changed = True
                elif command_type == "rebind":
                    await self.rebind_record(int(command.get("id", 0)))
                    changed = True
            except Exception as exc:
                self.emit({"type": "error", "message": f"处理监控命令失败：{exc}"})
        if changed:
            self.publish_records(force=True)
    async def delete_record(self, record_id: int, output_root: str = "") -> None:
        """从数据库中删除指定小程序记录，并清理对应反编译输出。"""
        assert self.conn is not None
        row = self.conn.execute("SELECT wxid, wxids FROM applet WHERE id = ?", (record_id,)).fetchone()
        if row is not None and output_root:
            wxids = self.decode_wxids(row["wxids"], str(row["wxid"] or ""))
            deleted_count = await asyncio.to_thread(self.cleanup_output_dirs, wxids, Path(output_root))
            if deleted_count:
                self.emit({"type": "info", "message": f"已删除 {deleted_count} 个 output 输出目录。"})
        self.conn.execute("DELETE FROM applet WHERE id = ?", (record_id,))
        self.conn.commit()

    def hide_record(self, record_id: int) -> None:
        """隐藏指定小程序记录但保留数据库数据。"""
        assert self.conn is not None
        self.conn.execute("UPDATE applet SET hidden = 1 WHERE id = ?", (record_id,))
        self.conn.commit()

    async def rebind_record(self, record_id: int) -> None:
        """把指定记录重新绑定到最近的未使用 wxid 文件夹。"""
        assert self.conn is not None
        existing_wxids = self.existing_wxid_set(exclude_record_id=record_id)
        current_dirs = self.snapshot_dirs()
        available = [(name, created_at) for name, created_at in current_dirs.items() if name not in existing_wxids]
        if not available:
            self.emit({"type": "warning", "message": "未找到可用于重新绑定的新 wxid 文件夹。"})
            return

        latest_group = sorted(self.group_new_dirs(available), key=lambda item: item[1], reverse=True)[0]
        wxids, created_at = latest_group
        normalized_wxids = self.normalize_wxids(wxids)
        primary_wxid = normalized_wxids[0]
        windows = await self.stable_windows(retry=True)
        window = windows[-1] if windows else {"title": "", "pid": 0, "start_time": created_at}
        existing = self.conn.execute(
            "SELECT id, wxid, wxids, name, window_title FROM applet WHERE id = ?",
            (record_id,),
        ).fetchone()
        title = str(window.get("title") or "").strip()
        name = self.choose_record_name(title, existing, normalized_wxids)
        window_title = self.choose_window_title(title, existing, normalized_wxids)
        self.conn.execute(
            """
            UPDATE applet
            SET wxid = ?, wxids = ?, name = ?, window_title = ?, pid = ?, start_time = ?, last_seen = ?, status = ?, created_at = ?, hidden = 0
            WHERE id = ?
            """,
            (
                primary_wxid,
                self.encode_wxids(normalized_wxids),
                name,
                window_title,
                int(window.get("pid") or 0),
                float(window.get("start_time") or created_at),
                time.time(),
                1 if int(window.get("pid") or 0) else 0,
                created_at,
                record_id,
            ),
        )
        self.conn.commit()
