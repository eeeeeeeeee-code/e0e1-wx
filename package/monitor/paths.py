"""提供多监控根目录解析和安全清理工具。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from package.monitor.utils import is_safe_applet_packages_dir


_MD5_DIR_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def default_applet_packages_root(home_dir: Path | None = None) -> Path:
    """返回默认的微信小程序 Applet packages 目录。"""
    home = Path(home_dir) if home_dir is not None else Path.home()
    return home / "AppData" / "Roaming" / "Tencent" / "xwechat" / "radium" / "Applet" / "packages"


def default_users_root(home_dir: Path | None = None) -> Path:
    """返回默认的微信 users 根目录。"""
    home = Path(home_dir) if home_dir is not None else Path.home()
    return home / "AppData" / "Roaming" / "Tencent" / "xwechat" / "radium" / "users"


def build_monitor_scan_roots(configured_root: Path | str, home_dir: Path | None = None) -> list[Path]:
    """生成监控 worker 需要检查的扫描根目录列表。"""
    configured_path = Path(str(configured_root or "")).expanduser()
    candidates = [
        configured_path,
        default_applet_packages_root(home_dir=home_dir),
        default_users_root(home_dir=home_dir),
    ]
    roots: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        roots.append(path)
    return roots


def is_md5_user_dir_name(name: str) -> bool:
    """判断目录名是否为微信 users 目录下的 32 位 md5。"""
    return bool(_MD5_DIR_PATTERN.fullmatch(str(name or "").strip()))


def resolve_packages_roots(scan_root: Path | str) -> list[Path]:
    """把扫描根目录解析为一个或多个真实的 packages 根目录。"""
    root = Path(scan_root).expanduser()
    if is_safe_applet_packages_dir(root):
        return [root]

    if root.name.lower() != "users":
        return []

    resolved: list[Path] = []
    if not root.exists() or not root.is_dir():
        return resolved

    try:
        children = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return resolved

    for child in children:
        try:
            if not child.is_dir() or not is_md5_user_dir_name(child.name):
                continue
        except OSError:
            continue
        packages_root = child / "applet" / "packages"
        if packages_root not in resolved:
            resolved.append(packages_root)
    return resolved


def cleanup_wx_directories(packages_root: Path | str) -> int:
    """安全清理 packages 根目录下一层名称以 wx 开头的目录。"""
    root = Path(packages_root).expanduser()
    if not is_safe_applet_packages_dir(root):
        return 0
    if not root.exists() or not root.is_dir():
        return 0

    deleted_count = 0
    try:
        children = list(root.iterdir())
    except OSError:
        return 0

    for child in children:
        try:
            if not child.is_dir() or not child.name.lower().startswith("wx"):
                continue
            shutil.rmtree(child)
            deleted_count += 1
        except OSError:
            continue
    return deleted_count
