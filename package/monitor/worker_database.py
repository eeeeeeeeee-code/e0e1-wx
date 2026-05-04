"""Maintain the wxid database and publish visible records."""

from __future__ import annotations

import json
import sqlite3
import time

from package.monitor.constants import MONITOR_INTERVAL_SECONDS
from package.monitor.windows import pid_is_running


class MonitorDatabaseMixin:
    def ensure_schema(self) -> None:
        """Create or upgrade the applet table."""
        assert self.conn is not None
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applet (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wxid TEXT,
                wxids TEXT,
                name TEXT,
                window_title TEXT,
                pid INTEGER,
                start_time REAL,
                last_seen REAL,
                status INTEGER,
                created_at REAL
            )
            """
        )
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(applet)").fetchall()}
        if "wxids" not in columns:
            self.conn.execute("ALTER TABLE applet ADD COLUMN wxids TEXT")
            for row in self.conn.execute("SELECT id, wxid FROM applet").fetchall():
                wxid = str(row["wxid"] or "").strip()
                wxids = json.dumps([wxid] if wxid else [], ensure_ascii=False)
                self.conn.execute("UPDATE applet SET wxids = ? WHERE id = ?", (wxids, int(row["id"])))
        if "hidden" not in columns:
            self.conn.execute("ALTER TABLE applet ADD COLUMN hidden INTEGER DEFAULT 0")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_applet_wxid ON applet(wxid)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_applet_pid ON applet(pid)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_applet_sort ON applet(status, start_time)")
        self.conn.commit()

    def upsert_applet(self, wxids: list[str], window: dict, created_at: float, status: int = 1) -> None:
        """Insert or update a record with one or more wxid paths."""
        assert self.conn is not None
        normalized_wxids = self.normalize_wxids(wxids)
        if not normalized_wxids:
            return
        now = time.time()
        title = str(window.get("title", "")).strip()
        primary_wxid = normalized_wxids[0]
        pid = int(window.get("pid") or 0)
        start_time = float(window.get("start_time") or created_at or now)
        existing = self.find_record_by_exact_wxids(normalized_wxids)
        if existing is None:
            existing = self.find_record_by_display_name(title, normalized_wxids)
        if existing is None:
            self.detach_wxids_from_records(normalized_wxids)
        else:
            self.detach_wxids_from_records(normalized_wxids, exclude_record_id=int(existing["id"]))
            existing_wxids = self.decode_wxids(existing["wxids"], str(existing["wxid"] or ""))
            normalized_wxids = self.normalize_wxids(existing_wxids + normalized_wxids)
            primary_wxid = normalized_wxids[0]
        name = self.choose_record_name(title, existing, normalized_wxids)
        window_title = self.choose_window_title(title, existing, normalized_wxids)
        if existing:
            self.conn.execute(
                """
                UPDATE applet
                SET wxid = ?, wxids = ?, name = ?, window_title = ?, pid = ?, start_time = ?, last_seen = ?, status = ?, hidden = 0
                WHERE id = ?
                """,
                (primary_wxid, self.encode_wxids(normalized_wxids), name, window_title, pid, start_time, now, status, int(existing["id"])),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO applet (wxid, wxids, name, window_title, pid, start_time, last_seen, status, created_at, hidden)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (primary_wxid, self.encode_wxids(normalized_wxids), name, window_title, pid, start_time, now, status, created_at or now),
            )
        self.conn.commit()

    def find_record_by_exact_wxids(self, wxids: list[str]) -> sqlite3.Row | None:
        """Find a record whose wxid set exactly matches the incoming group."""
        assert self.conn is not None
        target_wxids = self.normalize_wxids(wxids)
        if not target_wxids:
            return None
        rows = self.conn.execute("SELECT id, wxid, wxids, name, window_title FROM applet").fetchall()
        for row in rows:
            current_wxids = self.decode_wxids(row["wxids"], str(row["wxid"] or ""))
            if current_wxids == target_wxids:
                return row
        return None

    def find_record_by_display_name(self, title: str, wxids: list[str]) -> sqlite3.Row | None:
        """Find an existing record with the same real mini program display name."""
        assert self.conn is not None
        target_key = self.display_name_key(title, title, wxids)
        if not target_key:
            return None
        rows = self.conn.execute(
            """
            SELECT id, wxid, wxids, name, window_title, status, last_seen, hidden
            FROM applet
            ORDER BY COALESCE(hidden, 0) ASC, status DESC, last_seen DESC, id DESC
            """
        ).fetchall()
        for row in rows:
            row_wxids = self.decode_wxids(row["wxids"], str(row["wxid"] or ""))
            if self.display_name_key(str(row["name"] or ""), str(row["window_title"] or ""), row_wxids) == target_key:
                return row
        return None

    def display_name_key(self, name: str, window_title: str, wxids: list[str]) -> str:
        """Return the stable uniqueness key for a real mini program name."""
        normalized_wxids = self.normalize_wxids(wxids)
        for value in (str(name or "").strip(), str(window_title or "").strip()):
            if not self.is_placeholder_title(value, normalized_wxids):
                return value.casefold()
        return ""

    def detach_wxids_from_records(self, wxids: list[str], exclude_record_id: int | None = None) -> None:
        """Remove incoming wxids from older mixed records before inserting a new card."""
        assert self.conn is not None
        moving = set(self.normalize_wxids(wxids))
        if not moving:
            return
        rows = self.conn.execute("SELECT id, wxid, wxids FROM applet").fetchall()
        for row in rows:
            if exclude_record_id is not None and int(row["id"]) == int(exclude_record_id):
                continue
            current_wxids = self.decode_wxids(row["wxids"], str(row["wxid"] or ""))
            remaining_wxids = [wxid for wxid in current_wxids if wxid not in moving]
            if len(remaining_wxids) == len(current_wxids):
                continue
            if remaining_wxids:
                self.conn.execute(
                    "UPDATE applet SET wxid = ?, wxids = ? WHERE id = ?",
                    (remaining_wxids[0], self.encode_wxids(remaining_wxids), int(row["id"])),
                )
            else:
                self.conn.execute("DELETE FROM applet WHERE id = ?", (int(row["id"]),))

    def rebind_wxids_to_window(self, wxids: list[str], window: dict, created_at: float) -> None:
        """Move package directories out of a stale record and bind them to a visible window."""
        assert self.conn is not None
        normalized_wxids = self.normalize_wxids(wxids)
        if not normalized_wxids:
            return
        existing = self.find_record_by_any_wxid(normalized_wxids)
        if existing is not None:
            existing_wxids = self.decode_wxids(existing["wxids"], str(existing["wxid"] or ""))
            moving = set(normalized_wxids)
            remaining_wxids = [wxid for wxid in existing_wxids if wxid not in moving]
            if remaining_wxids and len(remaining_wxids) != len(existing_wxids):
                self.conn.execute(
                    "UPDATE applet SET wxid = ?, wxids = ? WHERE id = ?",
                    (remaining_wxids[0], self.encode_wxids(remaining_wxids), int(existing["id"])),
                )
                self.conn.commit()
            elif not remaining_wxids:
                self.conn.execute("DELETE FROM applet WHERE id = ?", (int(existing["id"]),))
                self.conn.commit()
        self.upsert_applet(normalized_wxids, window, created_at, status=1)

    def refresh_existing_records(self, windows: list[dict], current_dirs: dict[str, float] | None = None) -> None:
        """Refresh existing records based on the current process window list."""
        assert self.conn is not None
        now = time.time()
        current_window_keys = {(int(window["pid"]), str(window.get("title", ""))) for window in windows}
        matched_window_keys: set[tuple[int, str]] = set()
        for window in windows:
            pid = int(window["pid"])
            title = str(window.get("title", "")).strip()
            existing = self.conn.execute(
                "SELECT id, wxid, wxids, name, window_title FROM applet WHERE pid = ? AND window_title = ? ORDER BY id DESC LIMIT 1",
                (pid, title),
            ).fetchone()
            if not existing:
                continue
            wxids = self.decode_wxids(existing["wxids"], str(existing["wxid"] or ""))
            name = self.choose_record_name(title, existing, wxids)
            window_title = self.choose_window_title(title, existing, wxids)
            self.conn.execute(
                """
                UPDATE applet
                SET name = ?, window_title = ?, start_time = ?, last_seen = ?, status = 1
                WHERE id = ?
                """,
                (name, window_title, float(window.get("start_time") or now), now, int(existing["id"])),
            )
            matched_window_keys.add((pid, title))

        if current_dirs:
            rows = self.conn.execute("SELECT id, wxid, wxids, window_title FROM applet").fetchall()
            record_by_wxid: dict[str, sqlite3.Row] = {}
            for row in rows:
                for wxid in self.decode_wxids(row["wxids"], str(row["wxid"] or "")):
                    record_by_wxid[wxid] = row

            def unowned_wxids(wxids: list[str]) -> list[str]:
                return [wxid for wxid in wxids if wxid not in record_by_wxid]

            used_wxids: set[str] = set()
            sorted_dir_groups = [
                (available_wxids, created_at)
                for wxids, created_at in sorted(self.group_new_dirs(list(current_dirs.items())), key=lambda item: item[1], reverse=True)
                if (available_wxids := unowned_wxids(wxids))
            ]
            for window in windows:
                pid = int(window["pid"])
                title = str(window.get("title", "")).strip()
                if not title or (pid, title) in matched_window_keys:
                    continue
                candidate: tuple[list[str], float] | None = None
                for wxids, created_at in sorted_dir_groups:
                    if any(wxid in used_wxids for wxid in wxids):
                        continue
                    candidate = (wxids, created_at)
                    break
                if candidate is None:
                    continue
                wxids, created_at = candidate
                used_wxids.update(wxids)
                self.upsert_applet(wxids, window, created_at)
                matched_window_keys.add((pid, title))

        active_rows = self.conn.execute("SELECT id, pid, window_title, last_seen FROM applet WHERE status = 1").fetchall()
        for row in active_rows:
            pid = int(row["pid"] or 0)
            window_key = (pid, str(row["window_title"] or ""))
            last_seen = float(row["last_seen"] or 0.0)
            if window_key not in current_window_keys and (not pid_is_running(pid) or now - last_seen > MONITOR_INTERVAL_SECONDS * 4):
                self.conn.execute("UPDATE applet SET status = 0, last_seen = ? WHERE id = ?", (now, int(row["id"])))
        self.conn.commit()

    def publish_records(self, force: bool = False) -> None:
        """Load visible records, normalize package paths, and emit them to the UI."""
        assert self.conn is not None
        self.consolidate_duplicate_display_name_records()
        rows = self.conn.execute(
            """
            SELECT id, wxid, wxids, name, window_title, pid, start_time, last_seen, status, created_at, hidden
            FROM applet
            WHERE COALESCE(hidden, 0) = 0
            ORDER BY status DESC, start_time DESC, id DESC
            """
        ).fetchall()
        records = []
        dirty_rows: list[tuple[int, str, str]] = []

        for row in rows:
            record = dict(row)
            wxids = self.decode_wxids(record.get("wxids"), str(record.get("wxid") or ""))
            normalized_wxids = self.normalize_record_wxids(wxids)
            if normalized_wxids != wxids:
                dirty_rows.append((int(record["id"]), normalized_wxids[0] if normalized_wxids else "", self.encode_wxids(normalized_wxids)))
                wxids = normalized_wxids
                record["wxid"] = normalized_wxids[0] if normalized_wxids else record.get("wxid")
                record["wxids"] = self.encode_wxids(normalized_wxids)

            name = str(record.get("name") or "").strip()
            window_title = str(record.get("window_title") or "").strip()
            if self.is_placeholder_title(name, wxids) and not self.is_placeholder_title(window_title, wxids):
                record["name"] = window_title
            elif self.is_placeholder_title(name, wxids):
                record["name"] = ""
            if self.is_placeholder_title(window_title, wxids):
                record["window_title"] = ""
            if int(record.get("status") or 0) == 0 and not record["name"] and not record["window_title"]:
                continue
            record["wxids_list"] = wxids
            record["wxids_display"] = ", ".join(wxids)
            records.append(record)

        if dirty_rows:
            for record_id, wxid, wxids_json in dirty_rows:
                self.conn.execute("UPDATE applet SET wxid = ?, wxids = ? WHERE id = ?", (wxid, wxids_json, record_id))
            self.conn.commit()

        signature = tuple(
            (
                record.get("id"),
                record.get("wxids_display"),
                record.get("name"),
                record.get("window_title"),
                record.get("pid"),
                record.get("status"),
                record.get("hidden"),
            )
            for record in records
        )
        if not force and signature == self.last_records_signature:
            return
        self.last_records_signature = signature
        self.emit({"type": "monitor_records", "records": records})

    def consolidate_duplicate_display_name_records(self) -> None:
        """Merge historical duplicate rows that have the same mini program name."""
        assert self.conn is not None
        rows = self.conn.execute(
            """
            SELECT id, wxid, wxids, name, window_title, pid, start_time, last_seen, status, created_at, hidden
            FROM applet
            ORDER BY COALESCE(hidden, 0) ASC, status DESC, last_seen DESC, id DESC
            """
        ).fetchall()
        groups: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            wxids = self.decode_wxids(row["wxids"], str(row["wxid"] or ""))
            key = self.display_name_key(str(row["name"] or ""), str(row["window_title"] or ""), wxids)
            if key:
                groups.setdefault(key, []).append(row)

        changed = False
        for group_rows in groups.values():
            if len(group_rows) <= 1:
                continue
            primary = group_rows[0]
            merged_wxids: list[str] = []
            for row in group_rows:
                merged_wxids.extend(self.decode_wxids(row["wxids"], str(row["wxid"] or "")))
            merged_wxids = self.normalize_wxids(merged_wxids)
            if not merged_wxids:
                continue

            name = self.choose_record_name(str(primary["name"] or primary["window_title"] or ""), primary, merged_wxids)
            window_title = self.choose_window_title(str(primary["window_title"] or primary["name"] or ""), primary, merged_wxids)
            status = 1 if any(int(row["status"] or 0) == 1 for row in group_rows) else int(primary["status"] or 0)
            hidden = 1 if all(int(row["hidden"] or 0) == 1 for row in group_rows) else 0
            self.conn.execute(
                """
                UPDATE applet
                SET wxid = ?, wxids = ?, name = ?, window_title = ?, status = ?, hidden = ?
                WHERE id = ?
                """,
                (merged_wxids[0], self.encode_wxids(merged_wxids), name, window_title, status, hidden, int(primary["id"])),
            )
            duplicate_ids = [int(row["id"]) for row in group_rows[1:]]
            self.conn.executemany("DELETE FROM applet WHERE id = ?", [(record_id,) for record_id in duplicate_ids])
            changed = True

        if changed:
            self.conn.commit()
