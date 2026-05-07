"""执行卡片自动处理流水线，包括反编译、优化、扫描和缓存复用。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from package.decompiler.auto_cache import (
    compact_match_summary,
    compact_stage_entry,
    load_auto_match_summary,
    load_legacy_match_summary,
    match_summary_has_results,
    read_auto_process_cache,
    save_auto_process_entry,
)
from package.decompiler.cache_keys import (
    auto_process_cache_path,
    normalized_path_text,
    output_dirs_for_folders,
    output_dirs_have_files,
    output_dirs_exist,
    output_signature,
    rules_signature,
    source_package_signature,
)
from package.decompiler.constants import AUTO_MATCH_CHUNK_SIZE, AUTO_PROCESS_CACHE_VERSION
from package.decompiler.core import WxapkgError, normalize_new_folder_names


class AutoProcessTaskMixin:
    def emit_auto_stage(self, task_id: int, applet_id: str, stage: str, message: str, entry: dict | None = None) -> None:
        """发送自动处理流水线阶段事件。"""
        event = {
            "type": "auto_process_stage",
            "task_id": task_id,
            "applet_id": applet_id,
            "stage": stage,
            "message": message,
        }
        if entry is not None:
            event["entry"] = compact_stage_entry(entry)
        self.emit(event)

    def auto_entry_has_valid_decompile(self, entry: dict, source_signature_value: dict, output_dirs: list[Path]) -> bool:
        """判断按小程序 ID 缓存的反编译结果是否仍可复用。"""
        decompile_entry = entry.get("decompile") if isinstance(entry.get("decompile"), dict) else {}
        summary = decompile_entry.get("summary") if isinstance(decompile_entry.get("summary"), dict) else {}
        if not bool(decompile_entry.get("processed")):
            return False
        if entry.get("source_signature") != source_signature_value:
            return False
        if not output_dirs_exist(output_dirs):
            return False
        output_has_files = output_dirs_have_files(output_dirs)
        if bool(summary.get("errors")) and not output_has_files:
            return False
        if int(summary.get("extracted_count") or 0) > 0 and not output_has_files:
            return False
        return True

    def auto_entry_has_valid_optimize(self, entry: dict, output_signature_value: dict, optimize_enabled: bool) -> bool:
        """判断按小程序 ID 缓存的代码优化结果是否仍可复用。"""
        optimize_entry = entry.get("optimize") if isinstance(entry.get("optimize"), dict) else {}
        if not optimize_enabled:
            return bool(optimize_entry.get("skipped"))
        if not bool(optimize_entry.get("processed")):
            return False
        return optimize_entry.get("output_signature") == output_signature_value

    def auto_entry_has_valid_matches(self, entry: dict, output_signature_value: dict, rules_signature_value: str) -> bool:
        """判断按小程序 ID 缓存的正则匹配结果是否仍可复用。"""
        match_entry = entry.get("matches") if isinstance(entry.get("matches"), dict) else {}
        if not bool(match_entry.get("processed")):
            return False
        return (
            match_entry.get("output_signature") == output_signature_value
            and match_entry.get("rules_signature") == rules_signature_value
        )

    async def run_auto_process(self, task_id: int, payload: dict) -> None:
        """卡片创建时执行反编译、优化和正则扫描的后台流水线。"""
        applet_id = str(payload.get("applet_id") or "").strip()
        if not applet_id:
            raise WxapkgError("自动处理任务缺少小程序 ID。")

        if hasattr(self, "task_cancel_event"):
            self.task_cancel_event(task_id)
        packages_root = Path(str(payload.get("packages_root") or "")).expanduser()
        output_root = Path(str(payload.get("output_root") or "output")).expanduser()
        cache_path = Path(str(payload.get("cache_path") or auto_process_cache_path(output_root))).expanduser()
        new_folders = normalize_new_folder_names(payload.get("new_folders") if isinstance(payload.get("new_folders"), list) else [])
        rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
        optimize_enabled = bool(payload.get("optimize_enabled"))
        output_dirs = output_dirs_for_folders(output_root, new_folders)
        normalized_output_dirs = [normalized_path_text(path) for path in output_dirs]

        self.emit(
            {
                "type": "auto_process_started",
                "task_id": task_id,
                "applet_id": applet_id,
                "message": "自动处理任务已启动",
            }
        )

        if hasattr(self, "raise_if_task_cancelled"):
            self.raise_if_task_cancelled(task_id)
        source_signature_value = await asyncio.to_thread(source_package_signature, packages_root, new_folders)
        if hasattr(self, "raise_if_task_cancelled"):
            self.raise_if_task_cancelled(task_id)
        rules_signature_value = rules_signature(rules)
        cache = await asyncio.to_thread(read_auto_process_cache, cache_path)
        applets = cache.get("applets") if isinstance(cache.get("applets"), dict) else {}
        cached_entry = applets.get(applet_id) if isinstance(applets.get(applet_id), dict) else {}

        base_entry = {
            "version": AUTO_PROCESS_CACHE_VERSION,
            "applet_id": applet_id,
            "status": "running",
            "processed": False,
            "decompile_processed": False,
            "optimize_processed": False,
            "regex_processed": False,
            "source_signature": source_signature_value,
            "rules_signature": rules_signature_value,
            "optimize_enabled": optimize_enabled,
            "new_folders": list(new_folders),
            "output_dirs": normalized_output_dirs,
            "updated_at": time.time(),
        }
        if isinstance(cached_entry, dict) and cached_entry.get("source_signature") == source_signature_value:
            base_entry.update({key: value for key, value in cached_entry.items() if key in {"decompile", "optimize", "matches"}})
        entry = base_entry

        if not new_folders:
            entry.update({"status": "skipped", "message": "未找到绑定的 new_folder", "updated_at": time.time()})
            if hasattr(self, "raise_if_task_cancelled"):
                self.raise_if_task_cancelled(task_id)
            await asyncio.to_thread(save_auto_process_entry, cache_path, applet_id, entry)
            self.emit({"type": "auto_process_result", "task_id": task_id, "applet_id": applet_id, "entry": compact_stage_entry(entry)})
            return

        if self.auto_entry_has_valid_decompile(entry, source_signature_value, output_dirs):
            decompile_entry = entry.get("decompile") if isinstance(entry.get("decompile"), dict) else {}
            decompile_summary = decompile_entry.get("summary") if isinstance(decompile_entry.get("summary"), dict) else {}
            self.emit_auto_stage(task_id, applet_id, "decompile_cached", "已使用缓存反编译结果", entry)
        else:
            self.emit_auto_stage(task_id, applet_id, "decompile", "正在后台反编译")
            decompile_summary = await self.execute_decompile(task_id, packages_root, output_root, new_folders, applet_id)
            if hasattr(self, "raise_if_task_cancelled"):
                self.raise_if_task_cancelled(task_id)
            entry["decompile"] = {
                "processed": True,
                "cached": False,
                "summary": decompile_summary,
                "updated_at": time.time(),
            }
            entry["decompile_result"] = decompile_summary
            entry["decompile_processed"] = True
            entry["updated_at"] = time.time()
            if hasattr(self, "raise_if_task_cancelled"):
                self.raise_if_task_cancelled(task_id)
            await asyncio.to_thread(save_auto_process_entry, cache_path, applet_id, entry)

        entry["decompile_result"] = decompile_summary
        entry["decompile_processed"] = True
        decompile_has_errors = bool(decompile_summary.get("errors"))
        output_has_files = await asyncio.to_thread(output_dirs_have_files, output_dirs)
        if decompile_has_errors and not output_has_files:
            legacy_match_summary = await asyncio.to_thread(load_legacy_match_summary, cache_path, output_dirs, new_folders)
            if match_summary_has_results(legacy_match_summary):
                output_signature_value = await asyncio.to_thread(output_signature, output_dirs)
                entry["matches"] = {
                    "processed": True,
                    "cached": True,
                    "summary": legacy_match_summary,
                    "output_signature": output_signature_value,
                    "rules_signature": rules_signature_value,
                    "updated_at": time.time(),
                }
                entry["regex_result"] = legacy_match_summary
                entry["regex_processed"] = True
            entry.update(
                {
                    "status": "error",
                    "processed": False,
                    "message": (
                        "反编译存在错误，已保留历史正则匹配结果"
                        if match_summary_has_results(legacy_match_summary)
                        else "反编译存在错误，已停止后续自动处理"
                    ),
                    "updated_at": time.time(),
                }
            )
            if hasattr(self, "raise_if_task_cancelled"):
                self.raise_if_task_cancelled(task_id)
            await asyncio.to_thread(save_auto_process_entry, cache_path, applet_id, entry)
            self.emit({"type": "auto_process_result", "task_id": task_id, "applet_id": applet_id, "entry": compact_stage_entry(entry)})
            return
        if not decompile_has_errors:
            self.emit_auto_stage(task_id, applet_id, "decompile_done", "后台反编译已完成", entry)
        if decompile_has_errors:
            self.emit_auto_stage(task_id, applet_id, "decompile_warning", "反编译存在错误，已复用已有输出继续处理", entry)

        output_signature_value = await asyncio.to_thread(output_signature, output_dirs)
        if optimize_enabled:
            if self.auto_entry_has_valid_optimize(entry, output_signature_value, optimize_enabled):
                optimize_entry = entry.get("optimize") if isinstance(entry.get("optimize"), dict) else {}
                optimize_summary = optimize_entry.get("summary") if isinstance(optimize_entry.get("summary"), dict) else {}
                self.emit_auto_stage(task_id, applet_id, "optimize_cached", "已使用缓存代码优化结果", entry)
            else:
                self.emit_auto_stage(task_id, applet_id, "optimize", "正在后台优化代码")
                optimize_summary = await self.optimize_output_dirs(task_id, output_dirs, applet_id)
                if hasattr(self, "raise_if_task_cancelled"):
                    self.raise_if_task_cancelled(task_id)
                output_signature_value = await asyncio.to_thread(output_signature, output_dirs)
                entry["optimize"] = {
                    "processed": True,
                    "cached": False,
                    "summary": optimize_summary,
                    "output_signature": output_signature_value,
                    "updated_at": time.time(),
                }
                entry["optimize_result"] = optimize_summary
                entry["optimize_processed"] = True
                entry["updated_at"] = time.time()
                if hasattr(self, "raise_if_task_cancelled"):
                    self.raise_if_task_cancelled(task_id)
                await asyncio.to_thread(save_auto_process_entry, cache_path, applet_id, entry)
                self.emit_auto_stage(task_id, applet_id, "optimize_done", "后台代码优化已完成", entry)
        else:
            optimize_summary = {}
            entry["optimize"] = {
                "processed": False,
                "skipped": True,
                "summary": optimize_summary,
                "output_signature": output_signature_value,
                "updated_at": time.time(),
            }
            entry["optimize_result"] = optimize_summary
            entry["optimize_processed"] = False

        optimize_entry = entry.get("optimize") if isinstance(entry.get("optimize"), dict) else {}
        entry["optimize_result"] = optimize_summary
        entry["optimize_processed"] = bool(optimize_entry.get("processed"))

        output_signature_value = await asyncio.to_thread(output_signature, output_dirs)
        if self.auto_entry_has_valid_matches(entry, output_signature_value, rules_signature_value):
            match_entry = entry.get("matches") if isinstance(entry.get("matches"), dict) else {}
            match_summary = match_entry.get("summary") if isinstance(match_entry.get("summary"), dict) else {}
            self.emit_auto_stage(task_id, applet_id, "regex_cached", "已使用缓存正则匹配结果", entry)
        else:
            self.emit_auto_stage(task_id, applet_id, "regex", "正在后台正则匹配")
            match_summary = await self.execute_scan_matches(task_id, output_dirs, rules, applet_id)
            if hasattr(self, "raise_if_task_cancelled"):
                self.raise_if_task_cancelled(task_id)
            entry["matches"] = {
                "processed": True,
                "cached": False,
                "summary": match_summary,
                "output_signature": output_signature_value,
                "rules_signature": rules_signature_value,
                "updated_at": time.time(),
            }
            entry["regex_result"] = match_summary
            entry["regex_processed"] = True
            entry["updated_at"] = time.time()
            if hasattr(self, "raise_if_task_cancelled"):
                self.raise_if_task_cancelled(task_id)
            await asyncio.to_thread(save_auto_process_entry, cache_path, applet_id, entry)
            self.emit_auto_stage(task_id, applet_id, "regex_done", "后台正则匹配已完成", entry)

        entry["regex_result"] = match_summary
        entry["regex_processed"] = True
        final_message = "自动处理完成（反编译存在错误，已复用已有输出）" if decompile_has_errors else "自动处理完成"
        entry.update(
            {
                "status": "done",
                "processed": True,
                "message": final_message,
                "updated_at": time.time(),
            }
        )
        if hasattr(self, "raise_if_task_cancelled"):
            self.raise_if_task_cancelled(task_id)
        await asyncio.to_thread(save_auto_process_entry, cache_path, applet_id, entry)
        self.emit({"type": "auto_process_result", "task_id": task_id, "applet_id": applet_id, "entry": compact_stage_entry(entry)})

    async def run_load_auto_matches(self, task_id: int, payload: dict) -> None:
        """按需从自动处理缓存读取完整正则匹配明细。"""
        cache_path = Path(str(payload.get("cache_path") or "")).expanduser()
        applet_id = str(payload.get("applet_id") or "").strip()
        legacy_applet_id = str(payload.get("legacy_applet_id") or "").strip()
        new_folders = payload.get("new_folders") if isinstance(payload.get("new_folders"), list) else []
        raw_dirs = payload.get("output_dirs") if isinstance(payload.get("output_dirs"), list) else []
        output_dirs = [Path(str(path or "")).expanduser() for path in raw_dirs]
        if not applet_id:
            raise WxapkgError("加载匹配结果缺少小程序缓存 ID。")
        summary = await asyncio.to_thread(
            load_auto_match_summary,
            cache_path,
            applet_id,
            legacy_applet_id,
            new_folders,
            output_dirs,
        )
        results = summary.get("results") if isinstance(summary.get("results"), list) else []
        compact_summary = compact_match_summary(summary)
        compact_summary["results_loaded"] = True
        compact_summary["match_count"] = int(compact_summary.get("match_count") or len(results))
        self.emit({"type": "auto_matches_started", "task_id": task_id, "applet_id": applet_id, "summary": compact_summary})
        for start in range(0, len(results), AUTO_MATCH_CHUNK_SIZE):
            await asyncio.sleep(0)
            self.emit(
                {
                    "type": "auto_matches_chunk",
                    "task_id": task_id,
                    "applet_id": applet_id,
                    "results": results[start : start + AUTO_MATCH_CHUNK_SIZE],
                    "loaded_count": min(start + AUTO_MATCH_CHUNK_SIZE, len(results)),
                    "total_count": len(results),
                }
            )
        self.emit({"type": "auto_matches_loaded", "task_id": task_id, "applet_id": applet_id, "summary": compact_summary})
