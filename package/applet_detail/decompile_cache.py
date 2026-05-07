"""封装反编译详情页的本地缓存、签名和处理状态判断。"""

from __future__ import annotations

from package.applet_detail.decompile_support import *
from package.decompiler.cache_keys import output_dirs_for_folders


class DecompileCacheMixin:
    def processing_applet_id(self) -> str:
        """生成与卡片自动处理缓存一致的小程序 ID。"""
        state = self.processing_state()
        state_applet_id = str(state.get("applet_id") or "").strip()
        if state_applet_id:
            return state_applet_id
        new_folders = record_new_folders(self.record)
        if new_folders:
            return "|".join(new_folders)
        return str(int(self.record.get("id") or 0))

    def processing_cache_path(self) -> Path:
        """返回自动处理缓存文件路径。"""
        state = self.processing_state()
        raw_path = str(state.get("cache_path") or "").strip()
        if raw_path:
            return Path(raw_path).expanduser()
        return self.output_root / CACHE_DIR_NAME / "applet_processing_state.json"

    def current_output_root(self) -> Path:
        """返回当前记录指定的 output 根目录。"""
        raw_path = str(self.record.get("_output_root") or "output").strip()
        return Path(raw_path or "output").expanduser()

    def current_folder_output_dirs(self) -> list[Path]:
        """返回当前记录对应的 new_folder 输出目录列表。"""
        processing_dirs = self.processing_output_dirs()
        if processing_dirs:
            return processing_dirs
        new_folders = record_new_folders(self.record)
        if not new_folders:
            return [self.app_output_dir]
        return output_dirs_for_folders(self.output_root, new_folders)

    def processing_state(self) -> dict:
        """返回卡片创建时后台自动处理任务的最新状态。"""
        state = self.record.get("_processing_state")
        return dict(state) if isinstance(state, dict) else {}

    def processing_output_dirs(self) -> list[Path]:
        """从自动处理状态中提取输出目录，避免详情页重新计算任务结果。"""
        state = self.processing_state()
        raw_dirs = state.get("output_dirs") if isinstance(state.get("output_dirs"), list) else []
        output_dirs: list[Path] = []
        for raw_path in raw_dirs:
            text = str(raw_path or "").strip()
            if text:
                output_dirs.append(Path(text).expanduser())
        return output_dirs

    def cache_file_path(self) -> Path:
        """返回当前 output 根目录下的反编译页面缓存文件。"""
        return self.output_root / CACHE_DIR_NAME / CACHE_FILE_NAME

    def empty_cache(self) -> dict:
        """创建缓存文件的基础结构。"""
        return {"version": CACHE_VERSION, "decompile": {}, "optimize": {}, "matches": {}}

    def load_cache(self) -> dict:
        """返回空页面缓存，实际结果缓存统一由卡片后台 worker 管理。"""
        return self.empty_cache()

    def save_cache_entry(self, section: str, key: str, entry: dict) -> None:
        """忽略详情页本地缓存写入，避免 UI 线程执行文件 IO。"""
        return

    def cache_key(self, payload: dict) -> str:
        """根据稳定 JSON 生成缓存键。"""
        raw_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

    def normalized_path_text(self, path: Path) -> str:
        """返回不要求目标存在的规范化路径文本。"""
        return str(Path(path).expanduser().resolve(strict=False))

    def source_package_signature(self) -> dict:
        """生成不触发文件扫描的输入标识，完整校验由后台 worker 完成。"""
        packages_root = Path(str(self.record.get("_packages_root") or "")).expanduser()
        folders = [
            {
                "folder": new_folder,
                "path": self.normalized_path_text(packages_root / new_folder),
            }
            for new_folder in record_new_folders(self.record)
        ]
        return {"packages_root": self.normalized_path_text(packages_root), "folders": folders}

    def is_cache_path(self, path: Path) -> bool:
        """判断路径是否位于页面缓存目录中。"""
        return CACHE_DIR_NAME in Path(path).parts

    def output_signature(self, output_dirs: list[str] | None = None) -> dict:
        """生成不扫描文件系统的输出目录标识，避免详情页阻塞 UI。"""
        directories = []
        for raw_path in output_dirs or self.current_output_dir_payload():
            root = Path(str(raw_path or "")).expanduser()
            root_text = self.normalized_path_text(root)
            directories.append({"path": root_text})
        return {"directories": directories, "files": []}

    def output_dirs_exist(self, output_dirs: list[str] | None = None) -> bool:
        """避免在 UI 线程检查目录存在性。"""
        payload_dirs = output_dirs or self.current_output_dir_payload()
        return bool(payload_dirs)

    def output_dirs_have_files(self, output_dirs: list[str] | None = None) -> bool:
        """避免在 UI 线程扫描输出目录文件。"""
        return False

    def decompile_cache_payload(self) -> dict:
        """生成反编译缓存输入。"""
        return {
            "source": self.source_package_signature(),
            "output_root": self.normalized_path_text(self.output_root),
            "output_dirs": [self.normalized_path_text(Path(path)) for path in self.current_output_dir_payload()],
        }

    def optimize_cache_payload(self, output_dirs: list[str] | None = None) -> dict:
        """生成代码优化缓存输入。"""
        return {
            "output_dirs": [self.normalized_path_text(Path(path)) for path in (output_dirs or self.current_output_dir_payload())],
            "version": CACHE_VERSION,
        }

    def match_cache_payload(self, output_dirs: list[str] | None = None) -> dict:
        """生成正则匹配缓存输入。"""
        return {
            "output_dirs": [self.normalized_path_text(Path(path)) for path in (output_dirs or self.current_output_dir_payload())],
            "rules": self.match_scan_signature()[1],
            "version": CACHE_VERSION,
        }

    def cached_decompile_entry(self) -> dict | None:
        """详情页不直接读取缓存，由卡片后台任务返回缓存状态。"""
        return None

    def cached_optimize_entry(self, output_dirs: list[str] | None = None) -> dict | None:
        """详情页不直接读取优化缓存，由后台自动处理状态驱动展示。"""
        return None

    def cached_match_entry(self, output_dirs: list[str] | None = None) -> dict | None:
        """详情页不直接读取匹配缓存，由后台自动处理状态驱动展示。"""
        return None

    def save_decompile_cache(self, summary: dict) -> None:
        """详情页不写反编译缓存，结果由后台自动处理缓存保存。"""
        return

    def save_optimize_cache(self, summary: dict) -> None:
        """详情页不写优化缓存，结果由后台自动处理缓存保存。"""
        return

    def save_match_cache(self, summary: dict) -> None:
        """详情页不写匹配缓存，结果由后台自动处理缓存保存。"""
        return

    def load_cached_match_results(self, output_dirs: list[str] | None = None) -> bool:
        """详情页不直接加载缓存，统一等待卡片后台状态同步。"""
        return False

    def processing_summary(self, state: dict, result_key: str, section_key: str) -> dict:
        """从自动处理状态中提取指定阶段的汇总结果。"""
        direct_summary = state.get(result_key)
        if isinstance(direct_summary, dict):
            return direct_summary
        section = state.get(section_key)
        if isinstance(section, dict) and isinstance(section.get("summary"), dict):
            return section["summary"]
        return {}

    def apply_processing_matches(self, state: dict) -> None:
        """把卡片后台正则结果同步到详情页匹配结果面板。"""
        match_summary = self.processing_summary(state, "regex_result", "matches")
        if not match_summary:
            self.match_results = []
            self.match_result_count = 0
            self.last_match_signature = None
            if str(state.get("stage") or "").startswith("regex") and str(state.get("status") or "") == "running":
                self.update_match_root_text(running=True)
            else:
                self.update_match_root_text()
            self.refresh_match_results_view()
            return
        raw_results = match_summary.get("results")
        if isinstance(raw_results, list):
            self.match_results = list(raw_results)
        elif isinstance(match_summary.get("preview_results"), list):
            self.match_results = [dict(item) for item in match_summary.get("preview_results", []) if isinstance(item, dict)]
        else:
            self.match_results = []
        self.match_result_count = int(match_summary.get("match_count") or len(self.match_results))
        self.last_match_signature = None
        self.update_match_root_text()
        self.refresh_match_results_view()

    def processing_status_message(self, state: dict) -> str:
        """生成详情页展示的自动处理状态文案。"""
        if not state:
            if self.decompile_enabled():
                return "等待卡片后台自动处理状态同步"
            return "反编译未开启，当前展示已有目录内容"

        status = str(state.get("status") or "")
        message = str(state.get("message") or "").strip()
        if status == "done":
            decompile_summary = self.processing_summary(state, "decompile_result", "decompile")
            optimize_summary = self.processing_summary(state, "optimize_result", "optimize")
            match_summary = self.processing_summary(state, "regex_result", "matches")
            package_count = int(decompile_summary.get("package_count") or 0)
            extracted_count = int(decompile_summary.get("extracted_count") or 0)
            match_count = int(match_summary.get("match_count") or len(self.match_results))
            optimize_count = int(optimize_summary.get("processed_count") or 0)
            return f"自动处理完成：反编译 {package_count} 个包 / {extracted_count} 个文件，优化 {optimize_count} 个文件，命中 {match_count} 条"
        if status == "running":
            return message or "卡片后台自动处理中"
        if status == "skipped":
            return message or "自动处理已跳过"
        if status == "cancelled":
            return message or "自动处理已取消"
        if status == "error":
            return message or "自动处理失败"
        return message or "等待卡片后台自动处理"

    def processing_tree_key(self, state: dict) -> tuple:
        """生成判断文件树是否需要重载的自动处理状态键。"""
        output_dirs = tuple(str(path) for path in state.get("output_dirs", []) if str(path or "").strip()) if isinstance(state.get("output_dirs"), list) else ()
        decompile_summary = self.processing_summary(state, "decompile_result", "decompile")
        return (
            bool(state.get("decompile_processed")),
            int(decompile_summary.get("package_count") or 0),
            int(decompile_summary.get("extracted_count") or 0),
            output_dirs,
        )

    def should_reload_tree_for_processing(self, old_state: dict, new_state: dict) -> bool:
        """判断自动处理进度变化后是否需要重载文件树。"""
        if not new_state:
            return False
        old_dirs = tuple(str(path) for path in old_state.get("output_dirs", []) if str(path or "").strip()) if isinstance(old_state.get("output_dirs"), list) else ()
        new_dirs = tuple(str(path) for path in new_state.get("output_dirs", []) if str(path or "").strip()) if isinstance(new_state.get("output_dirs"), list) else ()
        if old_dirs != new_dirs:
            return True
        old_processed = bool(old_state.get("decompile_processed"))
        new_processed = bool(new_state.get("decompile_processed"))
        if not old_processed and new_processed:
            return True
        old_summary = self.processing_summary(old_state, "decompile_result", "decompile")
        new_summary = self.processing_summary(new_state, "decompile_result", "decompile")
        return old_processed and new_processed and (
            int(old_summary.get("package_count") or 0) != int(new_summary.get("package_count") or 0)
            or int(old_summary.get("extracted_count") or 0) != int(new_summary.get("extracted_count") or 0)
        )

    def apply_processing_state(self) -> None:
        """只展示卡片创建时触发的后台处理状态，不在详情页启动耗时任务。"""
        state = self.processing_state()
        self.apply_processing_matches(state)
        self.status_label.setText(self.processing_status_message(state))
        self.update_cancel_button()
        self.maybe_load_saved_match_results()
        if hasattr(self, "refresh_global_search_controls"):
            self.refresh_global_search_controls()

    def maybe_load_saved_match_results(self) -> None:
        """打开详情页或状态刷新后，后台加载已保存的正则匹配结果。"""
        if self.saved_matches_load_attempted:
            return
        if not self.decompile_enabled():
            return
        if self.match_results:
            return
        if self.auto_matches_task_id is not None:
            return
        self.saved_matches_load_attempted = True
        QTimer.singleShot(0, self.load_auto_match_results)
