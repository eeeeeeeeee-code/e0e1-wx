"""Discover packages directories and clean matching output folders safely."""

from __future__ import annotations

import shutil
from pathlib import Path

from package.decompiler.core import path_inside_root, safe_output_folder_path
from package.monitor.constants import FOLDER_GROUP_TOLERANCE_SECONDS
from package.monitor.utils import is_safe_applet_packages_dir


class MonitorFileMixin:
    def discover_package_dirs(self, base: Path | None = None) -> dict[str, float]:
        """Return package directories that directly contain wxapkg files."""
        root = Path(base or self.root_path).expanduser()
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
                rel_path = root.relative_to(self.root_path).as_posix()
                discovered[rel_path] = root.stat().st_ctime
            except (OSError, ValueError):
                return discovered
            return discovered

        for child in child_dirs:
            discovered.update(self.discover_package_dirs(child))
        return discovered

    def prepare_root_path(self) -> None:
        """Prepare the monitored root and clear it only for a safe packages path."""
        self.root_path.mkdir(parents=True, exist_ok=True)
        if not is_safe_applet_packages_dir(self.root_path):
            self.emit(
                {
                    "type": "warning",
                    "message": f"已跳过启动清理：路径不像微信小程序 packages 目录：{self.root_path}",
                }
            )
            return

        for child in self.root_path.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
            except OSError as exc:
                self.emit({"type": "warning", "message": f"清理失败：{child}：{exc}"})

    def snapshot_dirs(self) -> dict[str, float]:
        """Return the current set of package-bearing directories under the root."""
        return self.discover_package_dirs(self.root_path)

    def normalize_record_wxids(self, wxids: list[str]) -> list[str]:
        """Normalize container wxids to the actual package directories."""
        normalized: list[str] = []
        for wxid in self.normalize_wxids(wxids):
            discovered = self.discover_package_dirs(self.root_path / wxid)
            if discovered:
                for rel_path in discovered:
                    if rel_path not in normalized:
                        normalized.append(rel_path)
                continue
            if wxid not in normalized:
                normalized.append(wxid)
        return normalized

    def group_new_dirs(self, new_dirs: list[tuple[str, float]]) -> list[tuple[list[str], float]]:
        """Group newly discovered directories by close creation time."""
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
        """Delete output folders bound to a record and return the deletion count."""
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
                self.emit({"type": "warning", "message": f"删除 output 目录失败：{folder}：{exc}"})
        return deleted_count
