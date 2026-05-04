"""归一化 wxid 列表并选择稳定的小程序名称和窗口标题。"""

from __future__ import annotations

import json
import sqlite3


class MonitorIdentityMixin:
    def normalize_wxids(self, wxids: list[str]) -> list[str]:
        """去重并保持 wxid 原始出现顺序。"""
        normalized: list[str] = []
        seen: set[str] = set()
        for wxid in wxids:
            value = str(wxid).strip()
            if value and value not in seen:
                normalized.append(value)
                seen.add(value)
        return normalized

    def encode_wxids(self, wxids: list[str]) -> str:
        """把 wxid 列表编码为数据库文本。"""
        return json.dumps(self.normalize_wxids(wxids), ensure_ascii=False)

    def decode_wxids(self, value: str | None, fallback: str = "") -> list[str]:
        """从数据库文本还原 wxid 列表，并兼容旧单 wxid 数据。"""
        wxids: list[str] = []
        if value:
            try:
                raw_items = json.loads(value)
                if isinstance(raw_items, list):
                    wxids.extend(str(item).strip() for item in raw_items)
            except json.JSONDecodeError:
                wxids.extend(part.strip() for part in value.split(","))
        if fallback:
            wxids.append(str(fallback).strip())
        return self.normalize_wxids(wxids)

    def existing_wxid_set(self, exclude_record_id: int | None = None) -> set[str]:
        """获取数据库中已绑定的全部 wxid。"""
        assert self.conn is not None
        used: set[str] = set()
        rows = self.conn.execute("SELECT id, wxid, wxids FROM applet").fetchall()
        for row in rows:
            if exclude_record_id is not None and int(row["id"]) == exclude_record_id:
                continue
            used.update(self.decode_wxids(row["wxids"], str(row["wxid"] or "")))
        return used

    def find_record_by_any_wxid(self, wxids: list[str]) -> sqlite3.Row | None:
        """查找已包含任意 wxid 的现有记录。"""
        assert self.conn is not None
        target_wxids = set(self.normalize_wxids(wxids))
        if not target_wxids:
            return None
        rows = self.conn.execute("SELECT id, wxid, wxids, name, window_title FROM applet").fetchall()
        for row in rows:
            current_wxids = set(self.decode_wxids(row["wxids"], str(row["wxid"] or "")))
            if current_wxids & target_wxids:
                return row
        return None

    def is_placeholder_title(self, title: str, wxids: list[str]) -> bool:
        """判断标题是否只是 wxid 或 PID 这类占位内容。"""
        value = str(title or "").strip()
        if not value:
            return True
        if value.upper().startswith("PID "):
            return True
        return value in set(self.normalize_wxids(wxids))

    def choose_record_name(self, new_title: str, existing: sqlite3.Row | None, wxids: list[str]) -> str:
        """优先保留真实小程序名，避免关闭后回退成 wxid。"""
        normalized_wxids = self.normalize_wxids(wxids)
        if not self.is_placeholder_title(new_title, normalized_wxids):
            return str(new_title).strip()
        if existing is not None:
            old_name = str(existing["name"] or "").strip()
            if not self.is_placeholder_title(old_name, normalized_wxids):
                return old_name
            old_title = str(existing["window_title"] or "").strip()
            if not self.is_placeholder_title(old_title, normalized_wxids):
                return old_title
        return ""

    def choose_window_title(self, new_title: str, existing: sqlite3.Row | None, wxids: list[str]) -> str:
        """保留真实窗口标题，避免用 wxid 覆盖已识别标题。"""
        normalized_wxids = self.normalize_wxids(wxids)
        if not self.is_placeholder_title(new_title, normalized_wxids):
            return str(new_title).strip()
        if existing is not None:
            old_title = str(existing["window_title"] or "").strip()
            if not self.is_placeholder_title(old_title, normalized_wxids):
                return old_title
        return "" if self.is_placeholder_title(new_title, normalized_wxids) else str(new_title).strip()
