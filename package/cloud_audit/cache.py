"""读写云审计扫描结果缓存，供后台 worker 进程调用。"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path


CLOUD_AUDIT_CACHE_DIR_NAME = ".e0e1_cache"
CLOUD_AUDIT_CACHE_FILE_NAME = "cloud_audit_state.json"
CLOUD_AUDIT_CACHE_VERSION = 1


def cloud_audit_cache_path(output_root: Path) -> Path:
    """根据输出根目录生成云审计缓存文件路径。"""
    return Path(output_root).expanduser() / CLOUD_AUDIT_CACHE_DIR_NAME / CLOUD_AUDIT_CACHE_FILE_NAME


def empty_cloud_audit_cache() -> dict:
    """创建新的云审计缓存根对象。"""
    return {"version": CLOUD_AUDIT_CACHE_VERSION, "applets": {}}


def read_cloud_audit_cache(cache_path: Path) -> dict:
    """在 worker 进程中读取 UTF-8 云审计缓存文件。"""
    path = Path(cache_path).expanduser()
    if not path.is_file():
        return empty_cloud_audit_cache()
    try:
        raw_cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_cloud_audit_cache()
    if not isinstance(raw_cache, dict):
        return empty_cloud_audit_cache()
    applets = raw_cache.get("applets")
    if not isinstance(applets, dict):
        raw_cache["applets"] = {}
    raw_cache["version"] = CLOUD_AUDIT_CACHE_VERSION
    return raw_cache


def write_cloud_audit_cache(cache_path: Path, cache: dict) -> None:
    """在 worker 进程中原子写入 UTF-8 云审计缓存文件。"""
    path = Path(cache_path).expanduser()
    applets = cache.get("applets") if isinstance(cache.get("applets"), dict) else {}
    payload = {
        "version": CLOUD_AUDIT_CACHE_VERSION,
        "applets": applets,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_cloud_audit_entry(cache_path: Path, applet_key: str) -> dict:
    """读取指定小程序的云审计缓存条目。"""
    key = str(applet_key or "").strip()
    if not key:
        return {}
    cache = read_cloud_audit_cache(cache_path)
    applets = cache.get("applets") if isinstance(cache.get("applets"), dict) else {}
    entry = applets.get(key)
    return copy.deepcopy(entry) if isinstance(entry, dict) else {}


def save_cloud_audit_entry(cache_path: Path, applet_key: str, entry: dict) -> dict:
    """合并保存指定小程序的云审计缓存条目并返回保存后的条目。"""
    key = str(applet_key or "").strip()
    if not key or not isinstance(entry, dict):
        return {}
    cache = read_cloud_audit_cache(cache_path)
    applets = cache.setdefault("applets", {})
    previous = applets.get(key) if isinstance(applets.get(key), dict) else {}
    merged = copy.deepcopy(previous)
    for field, value in entry.items():
        merged[str(field)] = copy.deepcopy(value)
    merged["applet_key"] = key
    merged["updated_at"] = time.time()
    applets[key] = merged
    write_cloud_audit_cache(cache_path, cache)
    return copy.deepcopy(merged)
