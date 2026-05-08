"""处理主窗口监控卡片列表、分页、UI 事件和详情窗口联动。"""

from __future__ import annotations

import queue

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QGridLayout, QLabel, QMessageBox

from package.applet_detail import AppletDetailWindow
from package.applet_detail.decompile_search_state import normalize_global_search_state
from package.applet_logs import LogEntry, log_entry_from_state, log_record_key, normalize_log_settings
from package.config.defaults import (
    DEFAULT_DEVTOOLS_CDP_PORT,
    DEFAULT_MINIAPP_DEBUG_PORT,
    normalize_cloud_call_timeout,
    normalize_devtools_port,
    normalize_route_traverse_interval,
)
from package.monitor import MiniProgramMonitor, PAGE_SIZE
from package.ui.constants import CARD_COLUMNS, CARD_COLUMN_SPACING, UI_EVENT_BATCH_LIMIT
from package.ui.paths import wxid_db_path
from package.ui.widgets import MiniProgramCard


class MainWindowMonitorMixin:
    def clear_layout(self, layout: QGridLayout) -> None:
        """清空网格布局中的旧控件。"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh_monitor_cards(self) -> None:
        """根据监控记录刷新小程序卡片列表。"""
        self.clear_layout(self.cards_layout)
        records = self.monitor_records
        total_pages = max(1, (len(records) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1

        if not records:
            empty = QLabel("当前未检测到小程序实例")
            empty.setObjectName("MutedLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(180)
            self.cards_layout.addWidget(empty, 0, 0)
            self.update_pagination_controls()
            self.refresh_state_hint()
            return

        page_start = self.current_page * PAGE_SIZE
        page_records = records[page_start : page_start + PAGE_SIZE]
        card_width = self.monitor_card_width()

        for index, record in enumerate(page_records):
            self.schedule_card_auto_processing(record)
            card = MiniProgramCard(record)
            card.set_equal_width(card_width)
            card.delete_requested.connect(self.delete_monitor_record)
            card.rebind_requested.connect(self.rebind_monitor_record)
            card.detail_requested.connect(self.open_applet_detail)
            row = index // CARD_COLUMNS
            column = index % CARD_COLUMNS
            self.cards_layout.addWidget(card, row, column)

        for column in range(CARD_COLUMNS):
            self.cards_layout.setColumnStretch(column, 1)
        self.cards_layout.setRowStretch((len(page_records) + CARD_COLUMNS - 1) // CARD_COLUMNS, 1)
        self.update_pagination_controls()
        self.refresh_state_hint()

    def monitor_card_width(self) -> int:
        """根据监控区域可用宽度计算每张卡片的平均宽度。"""
        available_width = max(1, self.scroll_area.viewport().width())
        total_spacing = CARD_COLUMN_SPACING * (CARD_COLUMNS - 1)
        return max(1, (available_width - total_spacing) // CARD_COLUMNS)

    def resize_monitor_cards(self) -> None:
        """窗口尺寸变化时强制同步所有卡片为平均宽度。"""
        if not hasattr(self, "scroll_area"):
            return
        card_width = self.monitor_card_width()
        for card in self.card_container.findChildren(MiniProgramCard):
            card.set_equal_width(card_width)

    def resizeEvent(self, event) -> None:
        """主窗口尺寸变化时重新平均卡片宽度。"""
        super().resizeEvent(event)
        QTimer.singleShot(0, self.resize_monitor_cards)

    def update_pagination_controls(self) -> None:
        """刷新分页按钮和页码状态。"""
        total_pages = max(1, (len(self.monitor_records) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page_label.setText(f"{self.current_page + 1} / {total_pages}")
        self.prev_page_button.setEnabled(self.current_page > 0)
        self.next_page_button.setEnabled(self.current_page < total_pages - 1)

    def previous_page(self) -> None:
        """切换到上一页小程序卡片。"""
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh_monitor_cards()

    def next_page(self) -> None:
        """切换到下一页小程序卡片。"""
        total_pages = max(1, (len(self.monitor_records) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.refresh_monitor_cards()

    def process_ui_events(self) -> None:
        """从进程安全队列中消费后台事件并更新 UI。"""
        for _index in range(UI_EVENT_BATCH_LIMIT):
            try:
                event = self.ui_events.get_nowait()
            except queue.Empty:
                break
            event_type = event.get("type")
            if event_type == "state_loaded":
                self.store.handle_event(event)
                self.refresh_module_buttons()
                self.refresh_state_hint()
                self.restart_monitor()
            elif event_type == "monitor_records":
                if event.get("monitor_id") != self.monitor_id:
                    continue
                records = event.get("records", [])
                if records == self.monitor_records:
                    continue
                self.monitor_records = records
                self.refresh_monitor_cards()
                self.refresh_open_detail_record()
            elif event_type in {"warning", "error"}:
                if "monitor_id" in event and event.get("monitor_id") != self.monitor_id:
                    continue
                message = str(event.get("message", ""))
                if hasattr(self, "monitor_status_label"):
                    self.monitor_status_label.setText(message)
            elif event_type == "info":
                if hasattr(self, "monitor_status_label"):
                    self.monitor_status_label.setText(str(event.get("message", "")))

    def start_monitor(self) -> None:
        """启动或复用小程序后台监控进程。"""
        root_path = self.applet_packages_path()
        if self.monitor is not None and self.monitor_root_path == root_path:
            return
        self.stop_monitor(wait=False)
        self.monitor_root_path = root_path
        self.monitor_id += 1
        self.monitor = MiniProgramMonitor(root_path, wxid_db_path(), self.ui_events, self.monitor_id)
        self.monitor.start()
        if hasattr(self, "monitor_status_label"):
            self.monitor_status_label.setText("监控运行中")

    def stop_monitor(self, wait: bool = False) -> None:
        """请求停止当前小程序后台监控进程。"""
        if self.monitor is not None:
            self.monitor.stop()
            if wait:
                self.monitor.join(timeout=1.5)
                if self.monitor.is_alive():
                    self.monitor.terminate()
            self.monitor = None

    def restart_monitor(self) -> None:
        """重启小程序后台监控进程。"""
        self.start_monitor()

    def send_monitor_command(self, command_type: str, record_id: int, payload: dict | None = None) -> None:
        """向后台监控进程发送卡片操作命令。"""
        if self.monitor is None:
            return
        command = {"type": command_type, "id": record_id}
        if payload:
            command.update(payload)
        self.monitor.send_command(command)

    def delete_monitor_record(self, record_id: int) -> None:
        """确认后删除指定小程序数据库记录。"""
        reply = QMessageBox.question(
            self,
            "删除记录",
            "确认删除这条小程序记录？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            window = self.detail_windows.get(record_id)
            if window is not None:
                window.close()
            if hasattr(self, "auto_processor"):
                record = next((item for item in self.monitor_records if int(item.get("id") or 0) == record_id), None)
                if record is not None and hasattr(self.auto_processor, "delete_record"):
                    self.auto_processor.delete_record(self.prepare_detail_record(record))
                else:
                    self.auto_processor.cancel_record(record_id)
            self.send_monitor_command("delete", record_id, {"output_root": str(self.output_root_path())})

    def hide_monitor_record(self, record_id: int) -> None:
        """隐藏指定小程序卡片。"""
        self.send_monitor_command("hide", record_id)

    def rebind_monitor_record(self, record_id: int) -> None:
        """请求后台重新绑定指定小程序记录。"""
        self.send_monitor_command("rebind", record_id)

    def open_applet_detail(self, record: dict) -> None:
        """为指定小程序卡片打开独立功能详情窗口。"""
        record_id = int(record.get("id") or 0)
        detail_record = self.prepare_detail_record(record)
        if record_id > 0 and record_id in self.detail_windows:
            window = self.detail_windows[record_id]
            window.update_record(detail_record)
            window.show()
            window.raise_()
            window.activateWindow()
            return

        window = AppletDetailWindow(
            detail_record,
            self,
            devtools_service=getattr(self, "devtools_service", None),
            route_service=getattr(self, "route_service", None),
            log_store=getattr(self, "log_store", None),
            on_log_settings_changed=lambda settings, key=detail_record.get("_log_record_key", ""): self.update_log_settings(
                str(key), settings
            ),
            on_global_search_state_changed=lambda state, key=detail_record.get("_log_record_key", ""): self.update_global_search_state(
                str(key), state
            ),
        )
        window.closed.connect(self.remove_detail_window)
        if record_id > 0:
            self.detail_windows[record_id] = window
        window.show()

    def remove_detail_window(self, record_id: int) -> None:
        """详情窗口关闭后移除主窗口保存的引用。"""
        if record_id > 0:
            self.detail_windows.pop(record_id, None)

    def refresh_open_detail_record(self) -> None:
        """监控数据刷新时同步所有已打开的独立详情窗口。"""
        if not self.detail_windows:
            return
        records_by_id = {int(record.get("id") or 0): record for record in self.monitor_records}
        for record_id, window in list(self.detail_windows.items()):
            record = records_by_id.get(record_id)
            if record is not None:
                window.update_record(self.prepare_detail_record(record))

    def schedule_card_auto_processing(self, record: dict) -> None:
        """在小程序卡片生成时提交自动反编译流水线任务。"""
        self.auto_processor.ensure_record(self.prepare_detail_record(record))

    def schedule_visible_auto_processing(self) -> None:
        """重新调度当前可见卡片对应的自动处理任务。"""
        page_start = self.current_page * PAGE_SIZE
        for record in self.monitor_records[page_start : page_start + PAGE_SIZE]:
            self.schedule_card_auto_processing(record)

    def on_auto_processing_updated(self, record_id: int, _state: dict) -> None:
        """后台自动处理状态变化时刷新已打开详情页。"""
        state = dict(_state or {})
        state["record_id"] = int(record_id or state.get("record_id") or 0)
        self.append_feature_state_log("decompile_folder", state, "后台自动处理状态更新")
        window = self.detail_windows.get(int(record_id or 0))
        if window is None:
            return
        for record in self.monitor_records:
            if int(record.get("id") or 0) == int(record_id or 0):
                window.update_record(self.prepare_detail_record(record))
                return

    def prepare_detail_record(self, record: dict) -> dict:
        """为详情页补充反编译、代码优化、正则规则和输出路径。"""
        detail_record = dict(record)
        state = self.store.state
        toggles = state.get("toggles", {})
        detail_record["_decompile_enabled"] = bool(toggles.get("decompile", False))
        detail_record["_optimize_code_enabled"] = bool(toggles.get("optimize_code", False))
        detail_record["_cloud_enabled"] = bool(toggles.get("cloud", False))
        detail_record["_regex_rules"] = [dict(rule) for rule in state.get("rules", []) if isinstance(rule, dict)]
        detail_record["_packages_root"] = str(detail_record.get("packages_root") or "").strip() or str(self.applet_packages_path())
        detail_record["_output_root"] = str(self.output_root_path())
        detail_record["_cloud_call_timeout_seconds"] = normalize_cloud_call_timeout(
            state.get("config", {}).get("cloud_call_timeout_seconds")
        )
        detail_record["_route_traverse_interval_seconds"] = normalize_route_traverse_interval(
            state.get("config", {}).get("route_traverse_interval_seconds")
        )
        detail_record["_miniapp_debug_port"] = normalize_devtools_port(
            state.get("config", {}).get("miniapp_debug_port"),
            DEFAULT_MINIAPP_DEBUG_PORT,
        )
        detail_record["_devtools_cdp_port"] = normalize_devtools_port(
            state.get("config", {}).get("devtools_cdp_port"),
            DEFAULT_DEVTOOLS_CDP_PORT,
        )
        detail_record["_processing_state"] = self.auto_processor.snapshot(int(detail_record.get("id") or 0))
        log_key = log_record_key(detail_record)
        detail_record["_log_record_key"] = log_key
        detail_record["_log_settings"] = normalize_log_settings(
            state.get("log_settings", {}).get("records", {}).get(log_key, {})
        )
        detail_record["_global_search_state"] = normalize_global_search_state(
            state.get("global_search", {}).get("records", {}).get(log_key, {})
        )
        return detail_record

    def update_log_settings(self, record_key: str, settings: dict) -> None:
        """保存指定小程序卡片的日志筛选设置。"""
        self.store.update_log_settings(record_key, settings)
        for record in self.monitor_records:
            detail_key = log_record_key(record)
            if detail_key == str(record_key):
                prepared = self.prepare_detail_record(record)
                window = self.detail_windows.get(int(prepared.get("id") or 0))
                if window is not None:
                    window.update_record(prepared)
                break

    def update_global_search_state(self, record_key: str, state: dict) -> None:
        """保存指定小程序卡片的全局搜索状态。"""
        self.store.update_global_search_state(record_key, state)
        for record in self.monitor_records:
            detail_key = log_record_key(record)
            if detail_key != str(record_key):
                continue
            prepared = self.prepare_detail_record(record)
            window = self.detail_windows.get(int(prepared.get("id") or 0))
            if window is not None:
                window.update_record(prepared)
            break

    def append_feature_state_log(self, source: str, state: dict, fallback_message: str = "", record_key: str | None = None) -> None:
        """把功能状态事件转换成日志并写入共享日志缓冲。"""
        entry = log_entry_from_state(source, state, fallback_message=fallback_message, record_key=record_key)
        if entry is None:
            return
        self.append_feature_log_entry(entry)

    def append_feature_log(self, record_key: str | int, source: str, level: str, message: str) -> None:
        """直接写入一条指定功能点的小程序日志。"""
        key = str(record_key or "").strip()
        text = str(message or "").strip()
        if not key or key == "0" or not text:
            return
        self.append_feature_log_entry(LogEntry(record_key=key, source=source, level=level, message=text))

    def append_feature_log_entry(self, entry: LogEntry) -> None:
        """保存日志条目并刷新当前打开的日志页。"""
        store = getattr(self, "log_store", None)
        if store is None:
            return
        store.append(entry)
        self.refresh_open_log_pages(entry.record_key)

    def refresh_open_log_pages(self, record_key: str) -> None:
        """刷新当前打开且属于指定小程序的日志 Tab。"""
        for window in list(getattr(self, "detail_windows", {}).values()):
            page = getattr(window, "page", None)
            if page is None:
                continue
            page_record_key = str(getattr(page, "record", {}).get("_log_record_key") or log_record_key(getattr(page, "record", {})))
            if page_record_key != str(record_key):
                continue
            logs_index = page.tab_index("logs") if hasattr(page, "tab_index") else -1
            if logs_index < 0 or page.tabs.currentIndex() != logs_index:
                continue
            host = page.tab_hosts.get(logs_index)
            layout = host.layout() if host is not None else None
            widget = layout.itemAt(0).widget() if layout is not None and layout.count() else None
            if widget is not None and hasattr(widget, "refresh_logs"):
                widget.refresh_logs()

    def on_devtools_state_logged(self, state: dict) -> None:
        """记录 devtools-cdp 状态变化日志。"""
        self.append_feature_state_log("devtools_cdp", state, "devtools-cdp 状态更新")

    def on_route_state_logged(self, record_id: int, state: dict) -> None:
        """记录小程序路由状态变化日志。"""
        route_state = dict(state or {})
        route_state["record_id"] = int(record_id or route_state.get("record_id") or 0)
        self.append_feature_state_log("routes", route_state, "路由状态更新")

    def on_miniapp_jump_state_logged(self, record_id: int, state: dict) -> None:
        """记录跨小程序跳转状态变化日志。"""
        jump_state = dict(state or {})
        jump_state["record_id"] = int(record_id or jump_state.get("record_id") or 0)
        self.append_feature_state_log("miniapp_jump", jump_state, "跨小程序跳转状态更新")

    def on_debug_toggle_log_logged(self, payload: dict) -> None:
        """记录调试开关详细链路日志。"""
        if not isinstance(payload, dict):
            return
        record_key = str(payload.get("record_id") or payload.get("owner_key") or "").strip()
        if not record_key or record_key == "0":
            return
        message = str(payload.get("message") or "").strip()
        if not message:
            return
        action_labels = {
            "detect": "检测调试状态",
            "enable": "开启调试",
            "disable": "关闭调试",
        }
        stage_labels = {
            "command_received": "收到命令",
            "prepare_runtime": "准备会话",
            "runtime_ready": "运行时就绪",
            "detect_result": "检测结果",
            "detect_failed": "检测失败",
            "set_enable_debug": "设置成功",
            "set_enable_debug_failed": "设置失败",
            "cancelled": "任务取消",
        }
        action_label = action_labels.get(str(payload.get("action") or "").strip(), "")
        stage_label = stage_labels.get(str(payload.get("stage") or "").strip(), "")
        prefix_parts = [part for part in (action_label, stage_label) if part]
        if prefix_parts:
            message = f"{' / '.join(prefix_parts)}：{message}"
        self.append_feature_log(record_key, "debug_toggle", str(payload.get("level") or "INFO"), message)

    def on_cloud_state_logged(self, state: dict) -> None:
        """记录云函数状态变化日志。"""
        self.append_feature_state_log("cloud_functions", state, "云函数状态更新")

    def on_cloud_calls_logged(self, calls: list) -> None:
        """记录动态云函数捕获数量变化日志。"""
        state = getattr(getattr(self, "devtools_service", None), "cloud_state", {})
        record_id = int(state.get("record_id") or 0) if isinstance(state, dict) else 0
        if record_id <= 0 or not calls:
            return
        self.append_feature_log(record_id, "cloud_functions", "INFO", f"动态捕获云调用 {len(calls)} 条")

    def on_cloud_call_completed_logged(self, result: dict) -> None:
        """记录手动云函数调用结果日志。"""
        if not isinstance(result, dict):
            return
        record_id = int(result.get("record_id") or 0)
        name = str(result.get("name") or "云函数").strip()
        ok = bool(result.get("ok", result.get("status") == "success"))
        reason = str(result.get("reason") or result.get("error") or "").strip()
        if ok:
            self.append_feature_log(record_id, "cloud_functions", "INFO", f"手动调用 {name} 完成")
        else:
            message = f"手动调用 {name} 失败"
            if reason:
                message = f"{message}：{reason}"
            self.append_feature_log(record_id, "cloud_functions", "ERROR", message)

    def on_cloud_static_scan_completed_logged(self, record_id: int, results: list) -> None:
        """记录运行时云函数静态扫描完成日志。"""
        count = len(results) if isinstance(results, list) else 0
        self.append_feature_log(record_id, "cloud_functions", "INFO", f"运行时静态扫描完成，发现 {count} 项")

    def on_cloud_static_scan_failed_logged(self, record_id: int, message: str) -> None:
        """记录运行时云函数静态扫描失败日志。"""
        self.append_feature_log(record_id, "cloud_functions", "ERROR", str(message or "运行时静态扫描失败"))
