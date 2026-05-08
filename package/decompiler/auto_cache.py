"""读写自动处理缓存，并兼容旧版详情页匹配缓存。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from package.decompiler.cache_keys import output_signature
from package.decompiler.constants import AUTO_PROCESS_CACHE_LIMIT, AUTO_PROCESS_CACHE_VERSION, LEGACY_PAGE_CACHE_FILE_NAME
from package.decompiler.core import safe_output_folder_name


def read_auto_process_cache(cache_path: Path) -> dict:
    """在 worker 进程中读取自动处理缓存文件。"""
    try:
        if not cache_path.is_file():
            return {"version": AUTO_PROCESS_CACHE_VERSION, "applets": {}}
        raw_cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": AUTO_PROCESS_CACHE_VERSION, "applets": {}}
    if not isinstance(raw_cache, dict):
        return {"version": AUTO_PROCESS_CACHE_VERSION, "applets": {}}
    applets = raw_cache.get("applets")
    if not isinstance(applets, dict):
        applets = {}
    return {"version": AUTO_PROCESS_CACHE_VERSION, "applets": applets}


def write_auto_process_cache(cache_path: Path, cache: dict) -> None:
    """在 worker 进程中原子写入自动处理缓存文件。"""
    applets = cache.get("applets") if isinstance(cache.get("applets"), dict) else {}
    if len(applets) > AUTO_PROCESS_CACHE_LIMIT:
        ordered = sorted(
            applets.items(),
            key=lambda item: float(item[1].get("updated_at") or 0) if isinstance(item[1], dict) else 0.0,
            reverse=True,
        )
        applets = dict(ordered[:AUTO_PROCESS_CACHE_LIMIT])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps({"version": AUTO_PROCESS_CACHE_VERSION, "applets": applets}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(cache_path)


def save_auto_process_entry(cache_path: Path, applet_id: str, entry: dict) -> None:
    """按小程序 ID 保存自动处理流水线缓存。"""
    cache = read_auto_process_cache(cache_path)
    applets = cache.setdefault("applets", {})
    applets[str(applet_id)] = entry
    write_auto_process_cache(cache_path, cache)


def delete_auto_process_entries(cache_path: Path, applet_ids: list[str] | tuple[str, ...] | set[str]) -> int:
    """Delete matching applet entries from the shared auto-process cache."""
    keys = {str(item).strip() for item in applet_ids if str(item).strip()}
    path = Path(cache_path).expanduser()
    if not keys or not path.is_file():
        return 0

    cache = read_auto_process_cache(path)
    applets = cache.get("applets") if isinstance(cache.get("applets"), dict) else {}
    removed = 0
    for key in keys:
        if key in applets:
            applets.pop(key, None)
            removed += 1
    if not removed:
        return 0
    write_auto_process_cache(path, cache)
    return removed


def compact_signature(value: dict) -> dict:
    """压缩文件签名，避免把大量文件清单传回 UI 进程。"""
    if not isinstance(value, dict):
        return {}
    compact = {key: item for key, item in value.items() if key != "files"}
    files = value.get("files")
    if isinstance(files, list):
        compact["file_count"] = len(files)
    folders = compact.get("folders")
    if isinstance(folders, list):
        compact_folders = []
        for folder in folders:
            if not isinstance(folder, dict):
                continue
            compact_folder = {key: item for key, item in folder.items() if key != "files"}
            folder_files = folder.get("files")
            if isinstance(folder_files, list):
                compact_folder["file_count"] = len(folder_files)
            compact_folders.append(compact_folder)
        compact["folders"] = compact_folders
    return compact


def compact_match_summary(summary: dict) -> dict:
    """移除正则命中明细，仅保留 UI 状态所需统计信息。"""
    if not isinstance(summary, dict):
        return {}
    compact = {key: value for key, value in summary.items() if key != "results"}
    results = summary.get("results")
    if isinstance(results, list):
        compact["match_count"] = int(summary.get("match_count") or len(results))
        compact["preview_results"] = [dict(item) for item in results[:20] if isinstance(item, dict)]
        compact["results_loaded"] = False
    elif isinstance(summary.get("preview_results"), list):
        compact["preview_results"] = [dict(item) for item in summary.get("preview_results", []) if isinstance(item, dict)]
        compact["results_loaded"] = bool(summary.get("results_loaded"))
    return compact


def compact_stage_entry(entry: dict) -> dict:
    """压缩自动处理缓存记录，防止主线程接收和深拷贝大对象。"""
    if not isinstance(entry, dict):
        return {}
    compact = {}
    for key, value in entry.items():
        if key == "source_signature":
            compact[key] = compact_signature(value if isinstance(value, dict) else {})
        elif key in {"decompile_result", "optimize_result"} and isinstance(value, dict):
            compact[key] = dict(value)
        elif key == "regex_result":
            compact[key] = compact_match_summary(value if isinstance(value, dict) else {})
        elif key in {"decompile", "optimize", "matches"} and isinstance(value, dict):
            section = dict(value)
            if isinstance(section.get("summary"), dict):
                if key == "matches":
                    section["summary"] = compact_match_summary(section["summary"])
                else:
                    section["summary"] = dict(section["summary"])
            if isinstance(section.get("output_signature"), dict):
                section["output_signature"] = compact_signature(section["output_signature"])
            compact[key] = section
        else:
            compact[key] = value
    return compact


def load_auto_match_summary(
    cache_path: Path,
    applet_id: str,
    legacy_applet_id: str = "",
    new_folders: list[str] | None = None,
    output_dirs: list[Path] | None = None,
) -> dict:
    """从自动处理缓存读取完整正则匹配结果。"""
    cache = read_auto_process_cache(cache_path)
    applets = cache.get("applets") if isinstance(cache.get("applets"), dict) else {}
    entry = applets.get(str(applet_id)) if isinstance(applets.get(str(applet_id)), dict) else {}
    if not entry and legacy_applet_id:
        entry = applets.get(str(legacy_applet_id)) if isinstance(applets.get(str(legacy_applet_id)), dict) else {}
    if not entry and new_folders:
        target_folders = [str(item) for item in new_folders]
        for cached_entry in applets.values():
            if not isinstance(cached_entry, dict):
                continue
            cached_folders = cached_entry.get("new_folders")
            if isinstance(cached_folders, list) and [str(item) for item in cached_folders] == target_folders:
                entry = cached_entry
                break
    matches = entry.get("matches") if isinstance(entry.get("matches"), dict) else {}
    summary = matches.get("summary") if isinstance(matches.get("summary"), dict) else {}
    if not summary and isinstance(entry.get("regex_result"), dict):
        summary = entry["regex_result"]
    if isinstance(summary, dict) and match_summary_has_results(summary):
        return summary
    return load_legacy_match_summary(cache_path, output_dirs or [], new_folders or [])


def match_summary_has_results(summary: dict) -> bool:
    """判断匹配汇总是否包含可展示的命中结果或命中数量。"""
    if not isinstance(summary, dict):
        return False
    results = summary.get("results")
    if isinstance(results, list) and results:
        return True
    try:
        return int(summary.get("match_count") or 0) > 0
    except (TypeError, ValueError):
        return False


def path_leaf_names(paths: list[Path] | list[str] | None) -> set[str]:
    """提取路径最后一级目录名，用于跨工作目录匹配旧缓存。"""
    names: set[str] = set()
    for raw_path in paths or []:
        name = Path(str(raw_path or "")).name.strip().lower()
        if name:
            names.add(name)
    return names


def legacy_entry_matches_output(entry: dict, output_dirs: list[Path], new_folders: list[str]) -> bool:
    """判断旧详情页缓存条目是否属于当前小程序输出目录。"""
    target_names = path_leaf_names(output_dirs)
    target_names.update(safe_output_folder_name(folder, "new_folder").lower() for folder in new_folders)
    if not target_names:
        return False

    raw_dirs = entry.get("output_dirs") if isinstance(entry.get("output_dirs"), list) else []
    summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
    if not raw_dirs and isinstance(summary.get("directories"), list):
        raw_dirs = summary["directories"]
    if path_leaf_names(raw_dirs) & target_names:
        return True

    results = summary.get("results") if isinstance(summary.get("results"), list) else []
    for result in results[:50]:
        file_path = str(result.get("file_path") or "") if isinstance(result, dict) else ""
        parts = [part.lower() for part in Path(file_path).parts]
        if any(name in parts for name in target_names):
            return True
    return False


def remap_legacy_result_path(file_path: str, output_dirs: list[Path]) -> str:
    """把旧缓存中的历史工作目录路径映射到当前输出目录。"""
    if not file_path:
        return file_path
    parts = list(Path(file_path).parts)
    lower_parts = [part.lower() for part in parts]
    dirs_by_name = {Path(path).name.lower(): Path(path) for path in output_dirs}
    for name, output_dir in dirs_by_name.items():
        if name not in lower_parts:
            continue
        index = len(lower_parts) - 1 - list(reversed(lower_parts)).index(name)
        relative_parts = parts[index + 1 :]
        return str(Path(output_dir).joinpath(*relative_parts)) if relative_parts else str(output_dir)
    return file_path


def remap_legacy_match_summary(summary: dict, output_dirs: list[Path]) -> dict:
    """复制旧缓存匹配结果，并修正其中的输出目录和文件路径。"""
    if not isinstance(summary, dict):
        return {}
    remapped = dict(summary)
    remapped["directories"] = [str(path) for path in output_dirs]
    results = summary.get("results")
    if isinstance(results, list):
        remapped_results = []
        for result in results:
            if not isinstance(result, dict):
                continue
            item = dict(result)
            item["file_path"] = remap_legacy_result_path(str(item.get("file_path") or ""), output_dirs)
            remapped_results.append(item)
        remapped["results"] = remapped_results
        remapped["match_count"] = int(remapped.get("match_count") or len(remapped_results))
    return remapped


def load_legacy_match_summary(cache_path: Path, output_dirs: list[Path], new_folders: list[str] | None = None) -> dict:
    """从旧版详情页缓存中兜底读取正则匹配结果。"""
    legacy_path = cache_path.with_name(LEGACY_PAGE_CACHE_FILE_NAME)
    try:
        raw_cache = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = raw_cache.get("matches") if isinstance(raw_cache.get("matches"), dict) else {}
    candidates: list[tuple[float, dict]] = []
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        if not legacy_entry_matches_output(entry, output_dirs, new_folders or []):
            continue
        summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
        if not match_summary_has_results(summary):
            continue
        candidates.append((float(entry.get("updated_at") or 0.0), summary))
    if not candidates:
        return {}
    _updated_at, summary = max(candidates, key=lambda item: item[0])
    return remap_legacy_match_summary(summary, output_dirs)
