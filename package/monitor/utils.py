"""提供小程序 packages 目录安全识别工具。"""

from __future__ import annotations

from pathlib import Path


def is_safe_applet_packages_dir(path: Path) -> bool:
    """判断目录是否像微信小程序 packages 目录，避免误删其他路径。"""
    parts = {part.lower() for part in path.parts}
    return path.name.lower() == "packages" and "xwechat" in parts and "applet" in parts
