"""扫描微信小程序窗口并把新增目录绑定到监控记录。"""

from __future__ import annotations

import asyncio

from package.monitor.constants import MATCH_WINDOW_SECONDS, TITLE_RETRY_COUNT, TITLE_RETRY_INTERVAL_SECONDS
from package.monitor.windows import list_wechat_app_windows


class MonitorScanMixin:
    async def scan_once(self) -> None:
        """执行一次窗口和文件夹扫描，并更新数据库。"""
        try:
            current_dirs = await asyncio.to_thread(self.snapshot_dirs)
            previous_keys = {
                self.wxid_identity_key(packages_root, wxid)
                for packages_root, wxid, _created_at in self.flatten_snapshot_dirs(self.previous_dirs)
            }
            new_entries = [
                (packages_root, wxid, created_at)
                for packages_root, wxid, created_at in self.flatten_snapshot_dirs(current_dirs)
                if self.wxid_identity_key(packages_root, wxid) not in previous_keys
            ]
            windows = await self.stable_windows(retry=bool(new_entries))
            new_groups = self.group_new_dir_entries(new_entries)
            self.bind_new_dir_groups(new_groups, windows)
            self.refresh_existing_records(windows, current_dirs=current_dirs)
            self.previous_dirs = current_dirs
            self.publish_records()
        except Exception as exc:
            self.emit({"type": "error", "message": f"小程序扫描失败：{exc}"})

    async def stable_windows(self, retry: bool = False) -> list[dict]:
        """获取窗口列表，并在新增文件夹出现时异步等待标题稳定。"""
        latest_windows: list[dict] = []
        for attempt in range(TITLE_RETRY_COUNT):
            latest_windows = list_wechat_app_windows()
            for window in latest_windows:
                title = str(window.get("title", "")).strip()
                if title:
                    title_key = int(window.get("hwnd") or window["pid"])
                    self.last_titles[title_key] = title
            if latest_windows and all(
                str(window.get("title", "")).strip() or self.last_titles.get(int(window.get("hwnd") or window["pid"]), "")
                for window in latest_windows
            ):
                break
            if not latest_windows and not retry:
                break
            if attempt < TITLE_RETRY_COUNT - 1:
                await asyncio.sleep(TITLE_RETRY_INTERVAL_SECONDS)

        resolved_windows: list[dict] = []
        for window in latest_windows:
            pid = int(window["pid"])
            title_key = int(window.get("hwnd") or pid)
            title = str(window.get("title", "")).strip() or self.last_titles.get(title_key, "")
            if not title:
                continue
            window["title"] = title
            resolved_windows.append(window)
        resolved_windows.sort(
            key=lambda item: (
                item.get("start_time") or 0.0,
                item.get("pid") or 0,
                int(item.get("hwnd") or 0),
            )
        )
        return resolved_windows

    def bind_new_dir_groups(self, new_groups: list[tuple[str, list[str], float]], windows: list[dict]) -> None:
        """把同一批新增 wxid 文件夹绑定到一个小程序窗口。"""
        if not new_groups:
            return
        assert self.conn is not None
        titled_windows = [window for window in windows if str(window.get("title", "")).strip()]
        active_window_keys = {
            (int(row["pid"] or 0), str(row["window_title"] or ""))
            for row in self.conn.execute("SELECT pid, window_title FROM applet WHERE status = 1").fetchall()
        }
        used_window_indexes: set[int] = set()

        for packages_root, wxids, created_at in new_groups:
            candidates = [
                (index, window)
                for index, window in enumerate(titled_windows)
                if index not in used_window_indexes
                and (int(window["pid"]), str(window.get("title", ""))) not in active_window_keys
                and abs(float(window.get("start_time") or 0.0) - created_at) <= MATCH_WINDOW_SECONDS
            ]
            if not candidates:
                candidates = [
                    (index, window)
                    for index, window in enumerate(titled_windows)
                    if index not in used_window_indexes
                    and (int(window["pid"]), str(window.get("title", ""))) not in active_window_keys
                ]
            if not candidates:
                candidates = [
                    (index, window)
                    for index, window in enumerate(titled_windows)
                    if index not in used_window_indexes
                    and abs(float(window.get("start_time") or 0.0) - created_at) <= MATCH_WINDOW_SECONDS
                ]
            if not candidates:
                candidates = [
                    (index, window)
                    for index, window in enumerate(titled_windows)
                    if index not in used_window_indexes
                ]
            if not candidates:
                candidates = [
                    (index, window)
                    for index, window in enumerate(titled_windows)
                    if abs(float(window.get("start_time") or 0.0) - created_at) <= MATCH_WINDOW_SECONDS
                ]
            candidates.sort(key=lambda item: (abs(float(item[1].get("start_time") or 0.0) - created_at), item[0]))

            candidate = candidates[0] if candidates else None
            window = candidate[1] if candidate else None
            if window:
                used_window_indexes.add(candidate[0])
                self.upsert_applet(wxids, window, created_at, packages_root)
