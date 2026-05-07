"""Handle delete, hide, rebind, and stop commands from the UI process."""

from __future__ import annotations

import asyncio
import queue
import time
from pathlib import Path


class MonitorCommandMixin:
    async def process_commands(self) -> None:
        """Handle pending commands sent by the UI process."""
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
        """Delete a record and clean its output, cache, and packages directories."""
        assert self.conn is not None
        row = self.conn.execute(
            "SELECT wxid, wxids, packages_root FROM applet WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is not None:
            raw_wxids = self.decode_wxids(row["wxids"], str(row["wxid"] or ""))
            wxids = list(raw_wxids)
            packages_root = str(row["packages_root"] or "").strip()
            if packages_root and hasattr(self, "normalize_record_wxids"):
                wxids = self.normalize_record_wxids(wxids, packages_root)

            cache_keys: list[str] = []
            for group in (wxids, raw_wxids):
                normalized_group = [str(item).strip() for item in group if str(item).strip()]
                if normalized_group:
                    cache_keys.append("|".join(normalized_group))
                    cache_keys.extend(normalized_group)
            primary_wxid = str(row["wxid"] or "").strip()
            if primary_wxid:
                cache_keys.append(primary_wxid)
            cache_keys.append(str(record_id))

            if output_root:
                deleted_count = await asyncio.to_thread(self.cleanup_output_dirs, wxids, Path(output_root))
                if deleted_count:
                    self.emit({"type": "info", "message": f"已删除 {deleted_count} 个 output 输出目录。"})
                deleted_count = await asyncio.to_thread(self.cleanup_cache_entries, Path(output_root), cache_keys)
                if deleted_count:
                    self.emit({"type": "info", "message": f"已删除 {deleted_count} 个缓存条目。"})

            if packages_root:
                try:
                    deleted_count = await asyncio.to_thread(self.cleanup_packages_dirs, wxids, Path(packages_root))
                except OSError as exc:
                    self.emit({"type": "warning", "message": f"删除小程序包目录失败：{exc}"})
                else:
                    if deleted_count:
                        self.emit({"type": "info", "message": f"已删除 {deleted_count} 个小程序包目录。"})
        self.conn.execute("DELETE FROM applet WHERE id = ?", (record_id,))
        self.conn.commit()

    def hide_record(self, record_id: int) -> None:
        """Hide a record while keeping it in the database."""
        assert self.conn is not None
        self.conn.execute("UPDATE applet SET hidden = 1 WHERE id = ?", (record_id,))
        self.conn.commit()

    async def rebind_record(self, record_id: int) -> None:
        """Rebind a record to the newest available unbound wxid directory."""
        assert self.conn is not None
        existing_wxid_keys = self.existing_wxid_keys(exclude_record_id=record_id)
        current_dirs = await asyncio.to_thread(self.snapshot_dirs)
        available = [
            (packages_root, wxid, created_at)
            for packages_root, wxid, created_at in self.flatten_snapshot_dirs(current_dirs)
            if self.wxid_identity_key(packages_root, wxid) not in existing_wxid_keys
        ]
        if not available:
            self.emit({"type": "warning", "message": "未找到可用于重新绑定的新 wxid 文件夹。"})
            return

        latest_group = sorted(self.group_new_dir_entries(available), key=lambda item: item[2], reverse=True)[0]
        packages_root, wxids, created_at = latest_group
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
            SET wxid = ?, wxids = ?, packages_root = ?, name = ?, window_title = ?, pid = ?, start_time = ?, last_seen = ?, status = ?, created_at = ?, hidden = 0
            WHERE id = ?
            """,
            (
                primary_wxid,
                self.encode_wxids(normalized_wxids),
                self.normalize_packages_root(packages_root),
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
