"""生成自动处理缓存所需的路径、规则和输入输出签名。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from package.decompiler.constants import AUTO_PROCESS_CACHE_DIR_NAME, AUTO_PROCESS_CACHE_FILE_NAME
from package.decompiler.core import safe_output_folder_path


def normalized_path_text(path: Path) -> str:
    """返回不要求目标存在的规范化路径文本。"""
    return str(Path(path).expanduser().resolve(strict=False))


def auto_process_cache_path(output_root: Path) -> Path:
    """生成自动处理流水线的共享缓存文件路径。"""
    return output_root / AUTO_PROCESS_CACHE_DIR_NAME / AUTO_PROCESS_CACHE_FILE_NAME


def output_dirs_for_folders(output_root: Path, new_folders: list[str]) -> list[Path]:
    """根据 new_folder 列表生成对应反编译输出目录。"""
    return [safe_output_folder_path(output_root, new_folder, "new_folder") for new_folder in new_folders]


def is_auto_cache_path(path: Path) -> bool:
    """判断路径是否位于自动处理缓存目录中。"""
    return AUTO_PROCESS_CACHE_DIR_NAME in Path(path).parts


def rules_signature(rules: list[dict]) -> str:
    """为启用的正则规则生成稳定签名。"""
    rule_parts = [
        {
            "name": str(rule.get("name") or ""),
            "pattern": str(rule.get("pattern") or ""),
            "enabled": bool(rule.get("enabled", True)),
        }
        for rule in rules
        if isinstance(rule, dict) and bool(rule.get("enabled", True))
    ]
    payload = json.dumps(rule_parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_package_signature(packages_root: Path, new_folders: list[str]) -> dict:
    """扫描输入 wxapkg 文件并生成用于缓存校验的轻量签名。"""
    folders = []
    for new_folder in new_folders:
        source_dir = packages_root / new_folder
        folder_info = {
            "folder": new_folder,
            "path": normalized_path_text(source_dir),
            "exists": source_dir.is_dir(),
            "files": [],
        }
        if source_dir.is_dir():
            files = []
            try:
                for wxapkg_path in source_dir.rglob("*.wxapkg"):
                    try:
                        if not wxapkg_path.is_file():
                            continue
                        stat = wxapkg_path.stat()
                        relative_path = wxapkg_path.relative_to(source_dir).as_posix()
                    except (OSError, ValueError):
                        continue
                    files.append(
                        {
                            "path": relative_path,
                            "size": stat.st_size,
                            "mtime_ns": stat.st_mtime_ns,
                        }
                    )
            except OSError:
                files = []
            folder_info["files"] = sorted(files, key=lambda item: item["path"].lower())
        folders.append(folder_info)
    return {"packages_root": normalized_path_text(packages_root), "folders": folders}


def output_signature(output_dirs: list[Path]) -> dict:
    """扫描输出目录文件状态，用于判断优化和匹配缓存是否可复用。"""
    entries = []
    directories = []
    for output_dir in output_dirs:
        root = Path(output_dir).expanduser()
        root_text = normalized_path_text(root)
        root_exists = root.is_dir()
        directories.append({"path": root_text, "exists": root_exists})
        if not root_exists:
            continue
        try:
            for file_path in root.rglob("*"):
                if is_auto_cache_path(file_path):
                    continue
                try:
                    if not file_path.is_file():
                        continue
                    stat = file_path.stat()
                    relative_path = file_path.relative_to(root).as_posix()
                except (OSError, ValueError):
                    continue
                entries.append(
                    {
                        "root": root_text,
                        "path": relative_path,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )
        except OSError:
            continue
    entries.sort(key=lambda item: (item["root"].lower(), item["path"].lower()))
    return {"directories": directories, "files": entries}


def output_dirs_exist(output_dirs: list[Path]) -> bool:
    """判断全部输出目录是否存在。"""
    return all(Path(path).expanduser().is_dir() for path in output_dirs)


def output_dirs_have_files(output_dirs: list[Path]) -> bool:
    """判断输出目录内是否存在非缓存文件。"""
    for output_dir in output_dirs:
        root = Path(output_dir).expanduser()
        if not root.is_dir():
            continue
        try:
            for file_path in root.rglob("*"):
                if is_auto_cache_path(file_path):
                    continue
                try:
                    if file_path.is_file():
                        return True
                except OSError:
                    continue
        except OSError:
            continue
    return False
