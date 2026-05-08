"""Discover monitor package roots and clean matching output folders safely."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from package.cloud_audit.cache import cloud_audit_cache_path, delete_cloud_audit_entries
from package.decompiler.auto_cache import delete_auto_process_entries
from package.decompiler.cache_keys import auto_process_cache_path
from package.decompiler.core import path_inside_root, safe_output_folder_path
from package.monitor.constants import FOLDER_GROUP_TOLERANCE_SECONDS
from package.monitor.paths import build_monitor_scan_roots, cleanup_wx_directories, resolve_packages_roots
from package.monitor.utils import is_safe_applet_packages_dir


class MonitorFileMixin:
    def configured_packages_root(self) -> Path:
        """Return the configured primary packages root."""
        return Path(self.root_path).expanduser()

    def monitor_scan_roots(self) -> list[Path]:
        """Return candidate roots that may contain WeChat applet packages."""
        home_dir = getattr(self, "home_dir", None)
        return build_monitor_scan_roots(self.configured_packages_root(), home_dir=home_dir)

    def packages_roots(self, create_missing: bool = False) -> list[Path]:
        """Resolve candidate roots into real packages roots."""
        roots: list[Path] = []
        seen: set[str] = set()
        for index, scan_root in enumerate(self.monitor_scan_roots()):
            root = Path(scan_root).expanduser()
            candidates: list[Path] = []
            if index == 0:
                if create_missing:
                    root.mkdir(parents=True, exist_ok=True)
                if root.exists():
                    candidates = [root]
            elif is_safe_applet_packages_dir(root):
                if create_missing:
                    root.mkdir(parents=True, exist_ok=True)
                if root.exists():
                    candidates = [root]
            else:
                candidates = resolve_packages_roots(root)
            for candidate in candidates:
                key = str(candidate).casefold()
                if key in seen:
                    continue
                seen.add(key)
                roots.append(candidate)
        return roots

    def discover_package_dirs(self, base: Path | None = None, *, packages_root: Path | None = None) -> dict[str, float]:
        """Return relative directories that directly contain wxapkg files."""
        root = Path(base or self.root_path).expanduser()
        base_root = Path(packages_root or self.root_path).expanduser()
        if not root.exists():
            return {}

        discovered: dict[str, float] = {}
        try:
            entries = sorted(root.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            return {}

        has_wxapkg = False
        child_dirs: list[Path] = []
        for child in entries:
            try:
                if child.is_file() and child.suffix.lower() == ".wxapkg":
                    has_wxapkg = True
                elif child.is_dir():
                    child_dirs.append(child)
            except OSError:
                continue

        if has_wxapkg:
            try:
                rel_path = root.relative_to(base_root).as_posix()
                discovered[rel_path] = root.stat().st_ctime
            except (OSError, ValueError):
                return discovered
            return discovered

        for child in child_dirs:
            discovered.update(self.discover_package_dirs(child, packages_root=base_root))
        return discovered

    def prepare_root_path(self) -> None:
        """启动监控前静默清理 packages 根目录下旧的顶层 wx 目录。"""
        for packages_root in self.packages_roots(create_missing=True):
            cleanup_wx_directories(packages_root)

    def snapshot_dirs(self) -> dict[str, dict[str, float]]:
        """Return the current snapshot for every monitored packages root."""
        snapshot: dict[str, dict[str, float]] = {}
        for packages_root in self.packages_roots():
            discovered = self.discover_package_dirs(packages_root, packages_root=packages_root)
            if discovered:
                snapshot[str(packages_root)] = discovered
        return snapshot

    def flatten_snapshot_dirs(self, snapshot: dict[str, dict[str, float]]) -> list[tuple[str, str, float]]:
        """Flatten snapshots into comparable packages_root + wxid entries."""
        flattened: list[tuple[str, str, float]] = []
        for packages_root, wxids in snapshot.items():
            normalized_root = str(Path(packages_root).expanduser())
            for wxid, created_at in wxids.items():
                flattened.append((normalized_root, str(wxid), float(created_at or 0.0)))
        flattened.sort(key=lambda item: (item[2], item[0].casefold(), item[1]))
        return flattened

    def group_new_dir_entries(self, entries: list[tuple[str, str, float]]) -> list[tuple[str, list[str], float]]:
        """Group newly discovered directories by packages root and creation time."""
        grouped: list[tuple[str, list[str], float]] = []
        entries_by_root: dict[str, list[tuple[str, float]]] = {}
        for packages_root, wxid, created_at in entries:
            entries_by_root.setdefault(packages_root, []).append((wxid, created_at))
        for packages_root, root_entries in entries_by_root.items():
            for wxids, created_at in self.group_new_dirs(root_entries):
                grouped.append((packages_root, wxids, created_at))
        grouped.sort(key=lambda item: (item[2], item[0].casefold(), ",".join(item[1])))
        return grouped

    def normalize_record_wxids(self, wxids: list[str], packages_root: str = "") -> list[str]:
        """Restore real package-relative directories for a stored record."""
        normalized: list[str] = []
        root = Path(str(packages_root or self.root_path)).expanduser()
        for wxid in self.normalize_wxids(wxids):
            discovered = self.discover_package_dirs(root / wxid, packages_root=root)
            if discovered:
                for rel_path in discovered:
                    if rel_path not in normalized:
                        normalized.append(rel_path)
                continue
            if wxid not in normalized:
                normalized.append(wxid)
        return normalized

    def group_new_dirs(self, new_dirs: list[tuple[str, float]]) -> list[tuple[list[str], float]]:
        """Group directories whose creation times are close enough."""
        groups: list[tuple[list[str], float]] = []
        last_created_at: float | None = None
        for wxid, created_at in sorted(new_dirs, key=lambda item: item[1]):
            if (
                groups
                and last_created_at is not None
                and abs(last_created_at - created_at) <= FOLDER_GROUP_TOLERANCE_SECONDS
            ):
                groups[-1][0].append(wxid)
                groups[-1] = (groups[-1][0], min(groups[-1][1], created_at))
            else:
                groups.append(([wxid], created_at))
            last_created_at = created_at
        return groups

    def cleanup_output_dirs(self, wxids: list[str], output_root: Path) -> int:
        """Delete decompile output directories for a record."""
        if not wxids:
            return 0
        root = output_root.expanduser()
        deleted_count = 0
        for wxid in wxids:
            folder = safe_output_folder_path(root, wxid, "new_folder")
            try:
                if not path_inside_root(root, folder) or not folder.is_dir():
                    continue
                shutil.rmtree(folder)
                parent = folder.parent
                while parent != root and path_inside_root(root, parent):
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
                deleted_count += 1
            except OSError as exc:
                self.emit({"type": "warning", "message": f"删除输出目录失败：{folder}，{exc}"})
        return deleted_count

    def cleanup_packages_dirs(self, wxids: list[str], packages_root: Path | str) -> int:
        """Delete record-bound directories under a safe packages root."""
        if not wxids:
            return 0
        root = Path(packages_root).expanduser()
        if not is_safe_applet_packages_dir(root):
            return 0
        if not root.exists() or not root.is_dir():
            return 0

        deleted_count = 0
        for wxid in self.normalize_wxids(wxids):
            raw_path = str(wxid or "").strip().replace("\\", "/").lstrip("/")
            if not raw_path:
                continue
            parts = [part for part in PurePosixPath(raw_path).parts if part not in {"", "."}]
            if not parts or any(part == ".." for part in parts):
                continue
            folder = root.joinpath(*parts)
            try:
                if folder == root or not path_inside_root(root, folder) or not folder.is_dir():
                    continue
                shutil.rmtree(folder)
                parent = folder.parent
                while parent != root and path_inside_root(root, parent):
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
                deleted_count += 1
            except OSError as exc:
                self.emit({"type": "warning", "message": f"删除小程序包目录失败：{folder}，{exc}"})
        return deleted_count

    def cleanup_cache_entries(self, output_root: Path | str, cache_keys: list[str]) -> int:
        """Delete record-bound entries from shared cache files under output/.e0e1_cache."""
        root = Path(output_root).expanduser()
        normalized_keys: list[str] = []
        seen: set[str] = set()
        for item in cache_keys:
            text = str(item or "").strip()
            if text and text not in seen:
                seen.add(text)
                normalized_keys.append(text)
        if not normalized_keys:
            return 0

        deleted_count = 0
        deleted_count += delete_auto_process_entries(auto_process_cache_path(root), normalized_keys)
        deleted_count += delete_cloud_audit_entries(cloud_audit_cache_path(root), normalized_keys)
        return deleted_count
