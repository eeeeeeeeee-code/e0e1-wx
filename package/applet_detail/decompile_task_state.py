"""维护详情页任务取消、按钮状态和 worker 生命周期。"""

from __future__ import annotations

from package.applet_detail.decompile_support import *


class DecompileTaskStateMixin:
    def mark_task_cancelled(self, event: dict) -> None:
        """根据取消事件清理本地任务状态。"""
        task_id = int(event.get("task_id") or 0)
        matched = False
        rescan_after_cancel = False
        if task_id == self.decompile_task_id:
            self.decompile_task_id = None
            self.pending_optimize_after_decompile = False
            matched = True
        if task_id == self.optimize_task_id:
            self.optimize_task_id = None
            rescan_after_cancel = True
            matched = True
        if task_id == self.match_scan_task_id:
            self.match_scan_task_id = None
            self.update_match_root_text()
            matched = True
        if task_id == self.export_task_id:
            self.export_task_id = None
            matched = True
        if task_id == self.read_task_id:
            self.read_task_id = None
            matched = True
        if task_id == self.image_task_id:
            self.image_task_id = None
            matched = True
        if task_id == self.auto_matches_task_id:
            self.auto_matches_task_id = None
            matched = True
        if not matched:
            return
        if rescan_after_cancel:
            self.start_match_scan(force=True)
        else:
            self.status_label.setText("任务已取消")
        self.update_cancel_button()

    def update_cancel_button(self) -> None:
        """根据当前活动任务刷新取消按钮状态。"""
        has_task = any(
            task_id is not None
            for task_id in (
                self.decompile_task_id,
                self.optimize_task_id,
                self.match_scan_task_id,
                self.export_task_id,
                self.read_task_id,
                self.image_task_id,
                self.auto_matches_task_id,
            )
        )
        self.cancel_button.setEnabled(has_task)

    def shutdown_worker(self) -> None:
        """页面销毁时停止后台 worker 进程。"""
        if self.worker_closed:
            return
        self.worker_closed = True
        if hasattr(self, "event_timer"):
            self.event_timer.stop()
        for task_id in (
            self.decompile_task_id,
            self.optimize_task_id,
            self.match_scan_task_id,
            self.export_task_id,
            self.read_task_id,
            self.image_task_id,
            self.auto_matches_task_id,
        ):
            self.cancel_task(task_id)
        self.stop_image_movie()
        if self.match_render_timer is not None:
            self.match_render_timer.stop()
        if self.runner is not None:
            self.runner.shutdown(wait=False)
            self.runner = None
