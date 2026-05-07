"""管理详情页自动反编译、优化、扫描和导出流程。"""

from __future__ import annotations

from package.applet_detail.decompile_support import *


class DecompileProcessingMixin:
    def decompile_enabled(self) -> bool:
        """判断当前记录是否允许自动反编译。"""
        return bool(self.record.get("_decompile_enabled"))

    def optimize_code_enabled(self) -> bool:
        """判断当前记录是否允许优化反编译输出代码。"""
        return bool(self.record.get("_optimize_code_enabled"))

    def regex_rules(self) -> list[dict]:
        """返回当前详情页启用的正则规则列表。"""
        rules = self.record.get("_regex_rules")
        if not isinstance(rules, list):
            return []
        return [dict(rule) for rule in rules if isinstance(rule, dict) and bool(rule.get("enabled", True))]

    def match_scan_signature(self) -> tuple:
        """生成当前匹配扫描输入签名。"""
        rule_parts = tuple(
            (
                str(rule.get("name") or ""),
                str(rule.get("pattern") or ""),
                bool(rule.get("enabled", True)),
            )
            for rule in self.regex_rules()
        )
        return (tuple(self.current_output_dir_payload()), rule_parts)

    def current_output_dir_payload(self) -> list[str]:
        """返回后台优化任务需要处理的输出目录列表。"""
        return [str(path) for path in self.current_folder_output_dirs()]

    def global_search_ready(self) -> bool:
        """判断当前详情页是否允许执行全局搜索。"""
        state = self.processing_state()
        if not self.global_search_output_dirs():
            return False
        if not bool(state.get("decompile_processed")):
            return False
        if self.optimize_code_enabled():
            optimize_summary = self.processing_summary(state, "optimize_result", "optimize")
            return bool(optimize_summary.get("directories"))
        return True

    def reset_tree_root(self, preserve_state: bool = True) -> None:
        """重置左侧文件树根节点并提交首层懒加载任务。"""
        expanded_paths, selected_path = self.capture_tree_state() if preserve_state else (set(), "")
        for task_id in list(self.tree_tasks):
            self.cancel_task(task_id)
        self.tree_tasks.clear()
        self.tree.clear()
        self.match_root_item = QTreeWidgetItem()
        self.match_root_item.setData(0, MATCH_ROOT_ROLE, True)
        self.update_match_root_text()
        self.tree.addTopLevelItem(self.match_root_item)
        self.global_search_root_item = QTreeWidgetItem(["[全局搜索]"])
        self.global_search_root_item.setData(0, PATH_ROLE, "__global_search__")
        self.global_search_root_item.setData(0, IS_DIR_ROLE, False)
        self.global_search_root_item.setData(0, LOADED_ROLE, True)
        self.tree.addTopLevelItem(self.global_search_root_item)
        for folder_dir in self.current_folder_output_dirs():
            root_item = QTreeWidgetItem([output_folder_display_name(self.output_root, folder_dir)])
            root_item.setData(0, PATH_ROLE, str(folder_dir))
            root_item.setData(0, IS_DIR_ROLE, True)
            root_item.setData(0, LOADED_ROLE, False)
            root_item.addChild(create_loading_item())
            self.tree.addTopLevelItem(root_item)
        self.restore_tree_state(expanded_paths, selected_path)

    def capture_tree_state(self) -> tuple[set[str], str]:
        """记录当前文件树展开目录和选中文件路径，避免刷新后折叠。"""
        expanded_paths: set[str] = set()
        selected_item = self.tree.currentItem() if hasattr(self, "tree") else None
        selected_path = self.normalized_tree_path(str(selected_item.data(0, PATH_ROLE) or "")) if selected_item is not None else ""

        def visit(item: QTreeWidgetItem) -> None:
            """递归采集已展开目录路径。"""
            if bool(item.data(0, IS_DIR_ROLE)) and item.isExpanded():
                item_path = self.normalized_tree_path(str(item.data(0, PATH_ROLE) or ""))
                if item_path:
                    expanded_paths.add(item_path)
            for child_index in range(item.childCount()):
                visit(item.child(child_index))

        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item is not None:
                visit(item)
        return expanded_paths, selected_path

    def restore_tree_state(self, expanded_paths: set[str], selected_path: str) -> None:
        """恢复文件树展开和选中状态，目录内容仍通过后台懒加载。"""
        self.pending_tree_expand_paths = set(expanded_paths)
        self.pending_tree_reveal_path = selected_path
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item is not None:
                self.restore_tree_item_state(item)

    def restore_tree_item_state(self, item: QTreeWidgetItem) -> None:
        """恢复单个节点展开状态，并继续后台加载后续子目录。"""
        item_path = self.normalized_tree_path(str(item.data(0, PATH_ROLE) or ""))
        should_expand = item_path in self.pending_tree_expand_paths
        should_reveal = bool(self.pending_tree_reveal_path) and (
            self.pending_tree_reveal_path == item_path or self.pending_tree_reveal_path.startswith(item_path + "/")
        )
        if should_expand or should_reveal:
            self.tree.expandItem(item)
            if bool(item.data(0, IS_DIR_ROLE)) and not bool(item.data(0, LOADED_ROLE)):
                self.load_tree_item(item)
                return
        if bool(item.data(0, LOADED_ROLE)):
            if should_reveal:
                self.continue_tree_reveal(item)
            for child_index in range(item.childCount()):
                self.restore_tree_item_state(item.child(child_index))

    def update_match_root_text(self, running: bool = False) -> None:
        """刷新左侧固定匹配结果节点文本。"""
        if self.match_root_item is None:
            return
        if running:
            text = "[匹配结果] 正在匹配..."
        else:
            text = f"[匹配结果] {max(self.match_result_count, len(self.match_results))}"
        self.match_root_item.setText(0, text)

    def start_initial_processing(self) -> None:
        """首次进入详情页时只同步卡片后台状态，避免重复启动耗时任务。"""
        self.apply_processing_state()

    def start_followup_after_decompile(self, output_dirs: list[str] | None = None, force_match: bool = False) -> None:
        """反编译完成或命中缓存后，继续处理优化和匹配。"""
        if self.optimize_code_enabled() and self.start_optimize_existing_output(output_dirs):
            return
        self.start_match_scan(output_dirs, force=force_match)

    def start_auto_decompile(self) -> bool:
        """在反编译开关开启时自动提交反编译任务。"""
        if self.started_decompile:
            return False
        if not self.decompile_enabled():
            self.status_label.setText("反编译未开启，当前展示已有目录内容")
            return False
        new_folders = record_new_folders(self.record)
        if not new_folders:
            self.status_label.setText("未找到绑定的 new_folder")
            return False
        if self.cached_decompile_entry() is not None:
            self.started_decompile = True
            self.status_label.setText("反编译结果未变化，已跳过重复反编译")
            return False
        self.started_decompile = True
        self.cancel_button.setEnabled(True)
        self.decompile_task_id = self.ensure_runner().submit(
            "decompile",
            {
                "packages_root": str(self.record.get("_packages_root") or ""),
                "output_root": str(self.output_root),
                "new_folders": new_folders,
            },
        )
        return True

    def update_record(self, record: dict) -> None:
        """用最新小程序记录刷新页面，并同步卡片后台处理状态。"""
        old_output_dir = self.app_output_dir
        old_new_folders = record_new_folders(self.record)
        old_processing_state = self.processing_state()
        old_search_state = dict(self.record.get("_global_search_state") or {})
        self.record = dict(record)
        if not self.record.get("_global_search_state"):
            self.record["_global_search_state"] = old_search_state
        self.output_root = self.current_output_root()
        self.app_output_dir = self.output_root
        if not self.decompile_enabled() and self.decompile_task_id is not None:
            self.cancel_task(self.decompile_task_id)
            self.decompile_task_id = None
            self.started_decompile = False
            self.status_label.setText("反编译已关闭，正在取消后台任务")
        if not self.optimize_code_enabled():
            self.pending_optimize_after_decompile = False
            if self.optimize_task_id is not None:
                self.cancel_task(self.optimize_task_id)
                self.optimize_task_id = None
                self.status_label.setText("代码优化已关闭，正在取消后台任务")
        context_changed = old_output_dir != self.app_output_dir or old_new_folders != record_new_folders(self.record)
        if context_changed or self.should_reload_tree_for_processing(old_processing_state, self.processing_state()):
            self.reset_tree_root()
        if context_changed:
            self.started_decompile = False
        self.apply_processing_state()
        self.restore_global_search_state()

    def start_optimize_existing_output(self, output_dirs: list[str] | None = None) -> bool:
        """提交已有反编译输出目录的独立代码优化任务。"""
        if not self.optimize_code_enabled() or self.optimize_task_id is not None:
            return False
        payload_dirs = output_dirs or self.current_output_dir_payload()
        if self.cached_optimize_entry(payload_dirs) is not None:
            self.status_label.setText("代码优化结果未变化，已跳过重复优化")
            return False
        if self.match_scan_task_id is not None:
            self.cancel_task(self.match_scan_task_id)
            self.match_scan_task_id = None
        self.match_results = []
        self.match_result_count = 0
        self.last_match_signature = None
        self.update_match_root_text(running=True)
        self.status_label.setText("正在优化已反编译输出文件")
        self.cancel_button.setEnabled(True)
        self.optimize_task_id = self.ensure_runner().submit(
            "optimize",
            {
                "output_dirs": payload_dirs,
            },
        )
        return True

    def start_match_scan(self, output_dirs: list[str] | None = None, force: bool = False) -> None:
        """提交反编译输出目录正则匹配扫描任务。"""
        rules = self.regex_rules()
        if not rules:
            self.match_results = []
            self.match_result_count = 0
            self.last_match_signature = None
            self.update_match_root_text()
            self.refresh_match_results_view()
            return
        payload_dirs = output_dirs or self.current_output_dir_payload()
        if self.load_cached_match_results(payload_dirs):
            return
        signature = self.match_scan_signature()
        if not force and signature == self.last_match_signature and self.match_results:
            return
        if self.match_scan_task_id is not None:
            self.cancel_task(self.match_scan_task_id)
        self.last_match_signature = signature
        self.match_results = []
        self.match_result_count = 0
        self.update_match_root_text(running=True)
        self.refresh_match_results_view()
        self.status_label.setText("正在匹配中...")
        self.cancel_button.setEnabled(True)
        self.ensure_runner()
        assert self.match_loader is not None
        self.match_scan_task_id = self.match_loader.scan(payload_dirs, rules)

    def export_match_results(self, export_format: str) -> None:
        """把当前匹配结果导出到 JSON 或 TXT 文件。"""
        if not self.match_results:
            self.status_label.setText("当前没有可导出的匹配结果")
            return
        suffix = "json" if export_format == "json" else "txt"
        path, _selected_filter = QFileDialog.getSaveFileName(self, "导出匹配结果", f"matches.{suffix}", f"*.{suffix}")
        if not path:
            return
        if self.export_task_id is not None:
            self.cancel_task(self.export_task_id)
        self.status_label.setText("正在导出匹配结果")
        self.cancel_button.setEnabled(True)
        self.export_task_id = self.ensure_runner().submit(
            "export_matches",
            {
                "path": path,
                "format": suffix,
                "results": self.match_results,
            },
        )

    def show_match_results_panel(self) -> None:
        """切换到匹配结果面板。"""
        self.stop_image_movie()
        self.set_code_highlighter("")
        self.content_title.setText("匹配结果")
        self.preview_stack.setCurrentWidget(self.match_panel)
        match_summary = self.processing_summary(self.processing_state(), "regex_result", "matches")
        results_loaded = bool(match_summary.get("results_loaded")) if isinstance(match_summary, dict) else False
        if self.match_result_count > 0 and (not self.match_results or not results_loaded):
            QTimer.singleShot(0, self.load_auto_match_results)
        self.refresh_match_results_view()
