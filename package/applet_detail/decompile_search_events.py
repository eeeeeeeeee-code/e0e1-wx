"""处理全局搜索后台事件并刷新反编译详情页 UI。"""

from __future__ import annotations


class DecompileSearchEventMixin:
    def is_current_search_event(self, event: dict) -> bool:
        """忽略已经取消或被新任务替换的旧搜索事件。"""
        task_id = int(event.get("task_id") or 0)
        return self.search_task_id is not None and task_id == self.search_task_id

    def handle_search_event(self, event_type: str, event: dict) -> None:
        """分发全局搜索任务事件。"""
        if event_type == "search_text_error":
            if self.search_task_id is not None and int(event.get("task_id") or 0) == self.search_task_id:
                self.search_task_id = None
            self.global_search_status_label.setText(str(event.get("message") or "搜索失败"))
            self.refresh_global_search_controls()
            self.persist_global_search_state()
            self.update_cancel_button()
            return
        if not self.is_current_search_event(event):
            return
        if event_type == "search_started":
            self.global_search_results = []
            self.global_search_result_count = 0
            self.global_search_status_label.setText("正在搜索...")
            self.refresh_global_search_results_view()
        elif event_type == "search_progress":
            scanned_count = int(event.get("scanned_count") or 0)
            result_count = int(event.get("result_count") or len(self.global_search_results))
            self.global_search_status_label.setText(f"正在搜索... 已扫描 {scanned_count} 个文件，命中 {result_count} 条")
        elif event_type == "search_chunk":
            chunk = event.get("results") if isinstance(event.get("results"), list) else []
            self.global_search_results.extend(dict(item) for item in chunk if isinstance(item, dict))
            self.global_search_result_count = len(self.global_search_results)
            self.refresh_global_search_results_view()
        elif event_type == "search_done":
            self.search_task_id = None
            summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
            self.global_search_result_count = int(summary.get("result_count") or len(self.global_search_results))
            self.global_search_status_label.setText(f"搜索完成，命中 {self.global_search_result_count} 条")
            self.refresh_global_search_results_view()
            self.persist_global_search_state()
            self.update_cancel_button()
        elif event_type == "search_cancelled":
            self.search_task_id = None
            self.global_search_status_label.setText("搜索已取消")
            self.persist_global_search_state()
            self.update_cancel_button()
        self.refresh_global_search_controls()
