"""分发反编译 worker 事件并更新详情页状态与内容。"""

from __future__ import annotations

from package.applet_detail.decompile_support import *


class DecompileEventMixin:
    def cancel_active_tasks(self) -> None:
        """取消当前页面可取消的后台任务。"""
        for task_id in (
            self.decompile_task_id,
            self.optimize_task_id,
            self.match_scan_task_id,
            self.search_task_id,
            self.export_task_id,
            self.read_task_id,
            self.image_task_id,
            self.auto_matches_task_id,
        ):
            self.cancel_task(task_id)
        self.status_label.setText("已请求取消任务")
        self.cancel_button.setEnabled(False)

    def process_worker_events(self) -> None:
        """从 worker 队列消费事件并刷新 UI。"""
        if self.runner is None:
            return
        for _index in range(WORKER_EVENT_BATCH_LIMIT):
            try:
                event = self.runner.get_event_nowait()
            except queue.Empty:
                break
            self.handle_worker_event(event)

    def handle_worker_event(self, event: dict) -> None:
        """按事件类型分发 worker 返回的数据。"""
        event_type = str(event.get("type") or "")
        if event_type == "tree_loaded":
            self.handle_tree_loaded(event)
        elif event_type in {"decompile_started", "decompile_folder_started", "decompile_progress", "decompile_folder_done", "decompile_result"}:
            self.handle_decompile_event(event_type, event)
        elif event_type in {"optimize_started", "optimize_progress", "optimize_result", "optimize_error"}:
            self.handle_optimize_event(event_type, event)
        elif event_type in {"match_scan_started", "match_scan_progress", "match_scan_result", "scan_matches_error"}:
            self.handle_match_scan_event(event_type, event)
        elif event_type in {"search_started", "search_progress", "search_chunk", "search_done", "search_cancelled", "search_text_error"}:
            self.handle_search_event(event_type, event)
        elif event_type in {"export_matches_result", "export_matches_error"}:
            self.handle_export_event(event_type, event)
        elif event_type in {"auto_matches_started", "auto_matches_chunk", "auto_matches_loaded", "load_auto_matches_error"}:
            self.handle_auto_matches_event(event_type, event)
        elif event_type in {"decompile_folder_error", "decompile_file_error", "decompile_error", "decompile_worker_error"}:
            self.status_label.setText(str(event.get("message") or "反编译任务失败"))
        elif event_type == "content_started":
            if not self.is_current_read_event(event):
                return
            self.content_line_base = int(event.get("line_base") or 1)
            self.content_editor.clear()
            self.move_content_to_top()
            self.status_label.setText(f"正在读取：{Path(str(event.get('path') or '')).name}")
        elif event_type == "content_chunk":
            if not self.is_current_read_event(event):
                return
            self.append_content(str(event.get("text") or ""))
        elif event_type == "content_loaded":
            if not self.is_current_read_event(event):
                return
            self.read_task_id = None
            self.content_line_base = int(event.get("line_base") or self.content_line_base or 1)
            truncated = "，已截断预览" if event.get("truncated") else ""
            self.status_label.setText(f"读取完成，编码：{event.get('encoding')}{truncated}")
            if not self.apply_pending_jump(str(event.get("path") or "")):
                self.move_content_to_top()
            self.update_cancel_button()
        elif event_type == "binary_loaded":
            if not self.is_current_image_event(event):
                return
            self.image_task_id = None
            path = Path(str(event.get("path") or ""))
            data = event.get("data") if isinstance(event.get("data"), bytes) else b""
            self.show_image_content(path, data)
        elif event_type == "read_binary_error":
            if not self.is_current_image_event(event):
                return
            self.image_task_id = None
            self.status_label.setText(str(event.get("message") or "读取图片失败"))
            self.update_cancel_button()
        elif event_type == "read_file_error":
            if not self.is_current_read_event(event):
                return
            self.read_task_id = None
            self.status_label.setText(str(event.get("message") or "读取文件失败"))
            self.update_cancel_button()
        elif event_type.endswith("_cancelled"):
            self.mark_task_cancelled(event)

    def is_current_optimize_event(self, event: dict) -> bool:
        """忽略已过期的代码优化任务事件。"""
        task_id = int(event.get("task_id") or 0)
        return task_id in {self.decompile_task_id, self.optimize_task_id}

    def is_current_read_event(self, event: dict) -> bool:
        """忽略已经取消或被新文件替换的旧读取事件。"""
        task_id = int(event.get("task_id") or 0)
        return self.read_task_id is not None and task_id == self.read_task_id

    def is_current_image_event(self, event: dict) -> bool:
        """忽略已经取消或被新图片替换的旧图片事件。"""
        task_id = int(event.get("task_id") or 0)
        return self.image_task_id is not None and task_id == self.image_task_id

    def is_current_match_scan_event(self, event: dict) -> bool:
        """忽略已经取消或被新扫描替换的旧匹配事件。"""
        task_id = int(event.get("task_id") or 0)
        return self.match_scan_task_id is not None and task_id == self.match_scan_task_id

    def is_current_export_event(self, event: dict) -> bool:
        """忽略已经取消或被新导出替换的旧导出事件。"""
        task_id = int(event.get("task_id") or 0)
        return self.export_task_id is not None and task_id == self.export_task_id

    def is_current_auto_matches_event(self, event: dict) -> bool:
        """忽略已经取消或过期的匹配结果加载事件。"""
        task_id = int(event.get("task_id") or 0)
        return self.auto_matches_task_id is not None and task_id == self.auto_matches_task_id

    def handle_tree_loaded(self, event: dict) -> None:
        """把目录加载结果填充到对应树节点。"""
        task_id = int(event.get("task_id") or 0)
        item = self.tree_tasks.pop(task_id, None)
        if item is None:
            return
        result = event.get("result") if isinstance(event.get("result"), dict) else {}
        item.takeChildren()
        item.setData(0, LOADED_ROLE, True)
        if not result.get("exists", True):
            self.status_label.setText("目录尚不存在")
            return
        for entry in result.get("entries", []):
            child = QTreeWidgetItem([str(entry.get("name") or "")])
            child.setData(0, PATH_ROLE, str(entry.get("path") or ""))
            child.setData(0, IS_DIR_ROLE, bool(entry.get("is_dir")))
            child.setData(0, LOADED_ROLE, False)
            if bool(entry.get("is_dir")) and bool(entry.get("has_children")):
                child.addChild(create_loading_item())
            item.addChild(child)
        self.restore_tree_item_state(item)
        self.continue_tree_reveal(item)

    def handle_decompile_event(self, event_type: str, event: dict) -> None:
        """处理反编译进度与完成事件。"""
        if event_type == "decompile_started":
            self.status_label.setText("反编译任务已启动")
        elif event_type == "decompile_folder_started":
            self.status_label.setText(f"正在处理：{event.get('new_folder')}，共 {int(event.get('package_count') or 0)} 个 wxapkg")
        elif event_type == "decompile_progress":
            self.status_label.setText(
                f"{event.get('new_folder')}：{int(event.get('index') or 0)} / {int(event.get('total') or 0)}，"
                f"提取 {int(event.get('file_count') or 0)} 个文件"
            )
        elif event_type == "decompile_folder_done":
            self.status_label.setText(f"{event.get('new_folder')} 处理完成")
        elif event_type == "decompile_result":
            summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
            self.decompile_task_id = None
            self.save_decompile_cache(summary)
            self.status_label.setText(
                f"反编译完成：{int(summary.get('package_count') or 0)} 个 wxapkg，"
                f"{int(summary.get('extracted_count') or 0)} 个文件"
            )
            self.reset_tree_root()
            output_dirs = [str(path) for path in summary.get("output_dirs", [])] if isinstance(summary.get("output_dirs"), list) else []
            if self.optimize_code_enabled():
                if self.match_scan_task_id is not None:
                    self.cancel_task(self.match_scan_task_id)
                    self.match_scan_task_id = None
                self.match_results = []
                self.match_result_count = 0
                self.last_match_signature = None
                self.update_match_root_text(running=True)
                self.pending_optimize_after_decompile = False
                if not self.start_optimize_existing_output(output_dirs):
                    self.start_match_scan(output_dirs, force=True)
            else:
                self.start_match_scan(output_dirs, force=True)
                self.update_cancel_button()

    def handle_optimize_event(self, event_type: str, event: dict) -> None:
        """处理代码优化进度与完成事件。"""
        if not self.is_current_optimize_event(event):
            return
        summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
        total_files = int(summary.get("total_files") or 0)
        processed_count = int(summary.get("processed_count") or 0)
        if event_type == "optimize_started":
            self.status_label.setText(f"代码优化已启动：{total_files} 个可处理文件")
        elif event_type == "optimize_progress":
            self.status_label.setText(
                f"代码优化进度：{processed_count} / {total_files}，"
                f"成功 {int(summary.get('success_count') or 0)}，"
                f"跳过 {int(summary.get('skip_count') or 0)}，"
                f"失败 {int(summary.get('error_count') or 0)}"
            )
        elif event_type == "optimize_result":
            if int(event.get("task_id") or 0) == self.optimize_task_id:
                self.optimize_task_id = None
            self.save_optimize_cache(summary)
            self.status_label.setText(
                f"代码优化完成：成功 {int(summary.get('success_count') or 0)} 个，"
                f"跳过 {int(summary.get('skip_count') or 0)} 个，"
                f"失败 {int(summary.get('error_count') or 0)} 个"
            )
            self.reset_tree_root()
            output_dirs = [str(path) for path in summary.get("directories", [])] if isinstance(summary.get("directories"), list) else []
            self.start_match_scan(output_dirs, force=True)
            self.update_cancel_button()
        elif event_type == "optimize_error":
            if int(event.get("task_id") or 0) == self.optimize_task_id:
                self.optimize_task_id = None
            self.status_label.setText(str(event.get("message") or "代码优化失败"))
            self.start_match_scan(force=True)
            self.update_cancel_button()

    def handle_match_scan_event(self, event_type: str, event: dict) -> None:
        """处理正则匹配扫描进度与结果事件。"""
        if not self.is_current_match_scan_event(event):
            return
        summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
        if event_type == "match_scan_started":
            rule_count = int(event.get("rule_count") or 0)
            self.status_label.setText(f"正在匹配中... 共 {rule_count} 条规则")
            self.update_match_root_text(running=True)
        elif event_type == "match_scan_progress":
            scanned_count = int(summary.get("scanned_count") or 0)
            total_files = int(summary.get("total_files") or 0)
            match_count = int(summary.get("match_count") or 0)
            self.status_label.setText(f"正在匹配中... {scanned_count} / {total_files}，命中 {match_count} 条")
            self.update_match_root_text(running=True)
        elif event_type == "match_scan_result":
            self.match_scan_task_id = None
            self.match_results = list(summary.get("results") or []) if isinstance(summary.get("results"), list) else []
            self.match_result_count = int(summary.get("match_count") or len(self.match_results))
            self.save_match_cache(summary)
            self.status_label.setText(
                f"匹配完成：扫描 {int(summary.get('scanned_count') or 0)} 个文件，"
                f"命中 {len(self.match_results)} 条"
            )
            self.update_match_root_text()
            self.refresh_match_results_view()
            self.update_cancel_button()
        elif event_type == "scan_matches_error":
            self.match_scan_task_id = None
            self.status_label.setText(str(event.get("message") or "正则匹配失败"))
            self.update_match_root_text()
            self.update_cancel_button()

    def handle_export_event(self, event_type: str, event: dict) -> None:
        """处理匹配结果导出事件。"""
        if not self.is_current_export_event(event):
            return
        self.export_task_id = None
        if event_type == "export_matches_result":
            self.status_label.setText(f"匹配结果已导出：{event.get('path')}")
        else:
            self.status_label.setText(str(event.get("message") or "导出匹配结果失败"))
        self.update_cancel_button()

    def handle_auto_matches_event(self, event_type: str, event: dict) -> None:
        """处理自动处理缓存中的完整匹配结果加载事件。"""
        if not self.is_current_auto_matches_event(event):
            return
        if event_type == "auto_matches_started":
            summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
            self.match_results = []
            self.match_result_count = int(summary.get("match_count") or 0)
            self.update_match_root_text()
            self.status_label.setText(f"正在加载匹配结果：0 / {self.match_result_count}")
            self.refresh_match_results_view()
        elif event_type == "auto_matches_chunk":
            chunk = event.get("results") if isinstance(event.get("results"), list) else []
            self.match_results.extend(chunk)
            loaded_count = int(event.get("loaded_count") or len(self.match_results))
            total_count = int(event.get("total_count") or self.match_result_count)
            self.match_result_count = max(self.match_result_count, total_count)
            self.status_label.setText(f"正在加载匹配结果：{loaded_count} / {total_count}")
        elif event_type == "auto_matches_loaded":
            summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
            self.auto_matches_task_id = None
            self.match_result_count = int(summary.get("match_count") or len(self.match_results))
            self.update_match_root_text()
            if self.match_result_count > 0:
                self.status_label.setText(f"已加载保存的匹配结果：{self.match_result_count} 条")
            elif self.decompile_enabled():
                self.status_label.setText(self.processing_status_message(self.processing_state()))
            self.refresh_match_results_view()
        else:
            self.auto_matches_task_id = None
            self.status_label.setText(str(event.get("message") or "加载匹配结果失败"))
        self.update_cancel_button()
