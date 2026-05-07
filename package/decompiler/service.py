"""反编译服务兼容导出入口，保持旧导入路径稳定。"""

from package.decompiler.auto_cache import (
    compact_match_summary,
    compact_signature,
    compact_stage_entry,
    legacy_entry_matches_output,
    load_auto_match_summary,
    load_legacy_match_summary,
    match_summary_has_results,
    path_leaf_names,
    read_auto_process_cache,
    remap_legacy_match_summary,
    remap_legacy_result_path,
    save_auto_process_entry,
    write_auto_process_cache,
)
from package.decompiler.cache_keys import (
    auto_process_cache_path,
    is_auto_cache_path,
    normalized_path_text,
    output_dirs_exist,
    output_dirs_for_folders,
    output_dirs_have_files,
    output_signature,
    rules_signature,
    source_package_signature,
)
from package.decompiler.constants import *
from package.decompiler.file_browser import detect_text_encoding, list_directory_entries, looks_binary, read_text_window
from package.decompiler.runner import DecompileTaskRunner, decompile_worker_main
from package.decompiler.worker import AsyncDecompileWorker

__all__ = [
    "AsyncDecompileWorker",
    "DecompileTaskRunner",
    "auto_process_cache_path",
    "compact_match_summary",
    "compact_signature",
    "compact_stage_entry",
    "decompile_worker_main",
    "detect_text_encoding",
    "is_auto_cache_path",
    "legacy_entry_matches_output",
    "list_directory_entries",
    "load_auto_match_summary",
    "load_legacy_match_summary",
    "looks_binary",
    "match_summary_has_results",
    "normalized_path_text",
    "output_dirs_exist",
    "output_dirs_for_folders",
    "output_dirs_have_files",
    "output_signature",
    "path_leaf_names",
    "read_auto_process_cache",
    "read_text_window",
    "remap_legacy_match_summary",
    "remap_legacy_result_path",
    "rules_signature",
    "save_auto_process_entry",
    "source_package_signature",
    "write_auto_process_cache",
]
