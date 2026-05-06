"""云函数详情页，负责静态/动态结果展示与手动调用入口。"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from package.cloud_audit import (
    CloudAuditTaskRunner,
    cloud_audit_cache_path,
    entry_template,
    format_json_text,
    normalize_dynamic_call,
    normalize_static_entry,
)
from package.applet_detail.reconnect_hint import service_needs_miniapp_reconnect_hint, show_miniapp_reconnect_hint
from package.decompiler.cache_keys import output_dirs_for_folders
from package.devtools.identity import record_new_folders, record_owner_key
from package.ui.paths import output_root_path


class CloudFunctionsPage(QWidget):
    """在同一页面内展示云函数扫描结果和手动调用面板。"""

    def __init__(self, record: dict, devtools_service=None, parent: QWidget | None = None) -> None:
        """初始化云函数详情页、任务 runner 和信号连接。"""
        super().__init__(parent)
        self.record = dict(record)
        self.devtools_service = devtools_service
        self.runner: CloudAuditTaskRunner | None = None
        self.static_task_id: int | None = None
        self.export_task_id: int | None = None
        self.cache_task_id: int | None = None
        self.save_cache_task_id: int | None = None
        self.dynamic_entries: list[dict] = []
        self.static_entries: list[dict] = []
        self.runtime_static_entries: list[dict] = []
        self.cached_call_history: list[dict] = []
        self.selected_entry: dict | None = None
        self.last_result_entry: dict | None = None
        self.last_filter_text = ""
        self.worker_closed = False
        self.pending_static_scans = 0
        self.pending_call_name = ""
        self.pending_call_data: dict = {}
        self.pending_call_timeout_seconds = 0.0
        self.manual_call_timeout_timer = QTimer(self)
        self.manual_call_timeout_timer.setSingleShot(True)
        self.manual_call_timeout_timer.timeout.connect(self.handle_manual_call_timeout)

        self.build_ui()
        self.bind_service_signals()
        self.sync_service_snapshot()
        self.refresh_state()

        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self.process_worker_events)
        self.event_timer.start(120)
        QTimer.singleShot(0, self.load_cached_results)

        if self.cloud_enabled():
            QTimer.singleShot(0, self.start_dynamic_audit)

    def build_ui(self) -> None:
        """构建云函数页顶部工具栏、结果列表和调用面板。"""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.start_button = QPushButton("开启动态捕获")
        self.start_button.clicked.connect(self.start_dynamic_audit)
        toolbar.addWidget(self.start_button)
        self.stop_button = QPushButton("停止动态捕获")
        self.stop_button.clicked.connect(self.stop_dynamic_audit)
        toolbar.addWidget(self.stop_button)
        self.scan_button = QPushButton("静态扫描")
        self.scan_button.clicked.connect(self.start_static_scan)
        toolbar.addWidget(self.scan_button)
        self.clear_button = QPushButton("清空结果")
        self.clear_button.clicked.connect(self.clear_results)
        toolbar.addWidget(self.clear_button)
        self.export_button = QPushButton("导出报告")
        self.export_button.clicked.connect(self.export_report)
        toolbar.addWidget(self.export_button)
        self.switch_call_button = QPushButton("切到手动调用")
        self.switch_call_button.clicked.connect(lambda: self.tab_widget.setCurrentIndex(1))
        toolbar.addWidget(self.switch_call_button)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索来源、类型、名称、参数或 AppID")
        self.search_input.textChanged.connect(self.refresh_scan_table)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toolbar.addWidget(self.search_input, 1)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.state_label = QLabel()
        self.state_label.setObjectName("MutedLabel")
        root.addWidget(self.state_label)

        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        root.addWidget(self.tab_widget, 1)

        self.scan_tab = QWidget()
        self.build_scan_tab(self.scan_tab)
        self.tab_widget.addTab(self.scan_tab, "扫描结果")

        self.call_tab = QWidget()
        self.build_call_tab(self.call_tab)
        self.tab_widget.addTab(self.call_tab, "手动调用")

    def build_scan_tab(self, widget: QWidget) -> None:
        """构建扫描结果列表区域。"""
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.scan_summary = QLabel()
        self.scan_summary.setObjectName("MutedLabel")
        layout.addWidget(self.scan_summary)

        self.scan_tree = QTreeWidget()
        self.scan_tree.setColumnCount(7)
        self.scan_tree.setHeaderLabels(["来源", "AppID", "类型", "名称", "参数", "状态", "时间"])
        self.scan_tree.itemSelectionChanged.connect(self.on_scan_selection_changed)
        self.scan_tree.itemDoubleClicked.connect(self.fill_call_form_from_selected)
        layout.addWidget(self.scan_tree, 1)

    def build_call_tab(self, widget: QWidget) -> None:
        """构建手动调用输入区和结果展示区。"""
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        info_row = QGridLayout()
        info_row.setHorizontalSpacing(12)
        info_row.setVerticalSpacing(8)
        self.call_source_label = self.add_call_row(info_row, 0, "选中来源")
        self.call_type_label = self.add_call_row(info_row, 1, "函数类型")
        self.call_hint_label = self.add_call_row(info_row, 2, "模板提示")
        layout.addLayout(info_row)

        form_row = QHBoxLayout()
        form_row.setSpacing(8)
        name_label = QLabel("云函数名")
        form_row.addWidget(name_label)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("请输入云函数名")
        form_row.addWidget(self.name_input, 1)
        self.fill_button = QPushButton("填充选中项")
        self.fill_button.clicked.connect(self.fill_call_form_from_selected)
        form_row.addWidget(self.fill_button)
        self.call_button = QPushButton("执行调用")
        self.call_button.clicked.connect(self.call_selected_function)
        form_row.addWidget(self.call_button)
        layout.addLayout(form_row)

        self.data_input = QPlainTextEdit()
        self.data_input.setObjectName("CodePreview")
        self.data_input.setPlaceholderText("请输入 JSON 参数")
        self.data_input.setMinimumHeight(180)
        layout.addWidget(self.data_input, 1)

        result_label = QLabel("调用结果")
        result_label.setObjectName("SectionTitle")
        layout.addWidget(result_label)
        self.result_view = QPlainTextEdit()
        self.result_view.setObjectName("CodePreview")
        self.result_view.setReadOnly(True)
        self.result_view.setMinimumHeight(180)
        layout.addWidget(self.result_view, 1)

    def add_call_row(self, grid: QGridLayout, row: int, title: str) -> QLabel:
        """在手动调用信息区新增一行只读状态标签。"""
        label = QLabel(title)
        label.setObjectName("MutedLabel")
        value = QLabel("-")
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(label, row, 0)
        grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        return value

    def bind_service_signals(self) -> None:
        """连接 DevTools 云审计信号到当前页面。"""
        service = self.devtools_service
        if service is None:
            return
        if hasattr(service, "cloud_state_changed"):
            service.cloud_state_changed.connect(self.handle_cloud_state_changed)
        if hasattr(service, "cloud_calls_changed"):
            service.cloud_calls_changed.connect(self.handle_cloud_calls_changed)
        if hasattr(service, "cloud_call_completed"):
            service.cloud_call_completed.connect(self.handle_call_completed)
        if hasattr(service, "cloud_static_scan_completed"):
            service.cloud_static_scan_completed.connect(self.handle_runtime_static_results)
        if hasattr(service, "cloud_static_scan_failed"):
            service.cloud_static_scan_failed.connect(self.handle_runtime_static_scan_failed)

    def sync_service_snapshot(self) -> None:
        """把共享 DevTools 服务中已有的动态结果同步到当前页面。"""
        service = self.devtools_service
        if service is None or not hasattr(service, "cloud_calls_for_record"):
            return
        self.dynamic_entries = [normalize_dynamic_call(item) for item in service.cloud_calls_for_record(self.record) if isinstance(item, dict)]
        if self.selected_entry is None and self.dynamic_entries:
            self.selected_entry = dict(self.dynamic_entries[-1])
            self.update_call_hints(self.selected_entry)
            self.fill_call_form(self.selected_entry)

    def cloud_enabled(self) -> bool:
        """判断当前记录是否开启了自动云函数开关。"""
        return bool(self.record.get("_cloud_enabled"))

    def current_state(self) -> dict:
        """返回当前记录对应的云审计状态。"""
        if self.devtools_service is not None and hasattr(self.devtools_service, "cloud_state_for_record"):
            return self.devtools_service.cloud_state_for_record(self.record)
        state = dict(self.record.get("_cloud_state") or {})
        state["current_record"] = True
        return state

    def current_call_history(self) -> list[dict]:
        """返回当前记录对应的云函数调用历史。"""
        history = [dict(item) for item in self.cached_call_history if isinstance(item, dict)]
        if self.devtools_service is not None and hasattr(self.devtools_service, "cloud_call_history_for_record"):
            return self.merge_call_history(history, self.devtools_service.cloud_call_history_for_record(self.record))
        return self.merge_call_history(history, self.record.get("_cloud_call_history", []))

    def current_output_dirs(self) -> list[Path]:
        """计算当前小程序的反编译输出目录。"""
        folders = record_new_folders(self.record)
        root = Path(str(self.record.get("_output_root") or output_root_path())).expanduser()
        return output_dirs_for_folders(root, folders)

    def current_cache_path(self) -> Path:
        """返回当前小程序云审计缓存文件路径，不在主线程执行文件 IO。"""
        root = Path(str(self.record.get("_output_root") or output_root_path())).expanduser()
        return cloud_audit_cache_path(root)

    def current_cache_key(self) -> str:
        """返回当前小程序用于缓存复用的稳定键。"""
        return record_owner_key(self.record)

    def ensure_runner(self) -> CloudAuditTaskRunner:
        """按需启动云审计 worker，仅由页面提交后台任务使用。"""
        if self.runner is None:
            self.runner = CloudAuditTaskRunner()
        return self.runner

    def cache_request_payload(self) -> dict:
        """生成加载或保存缓存时传给 worker 的基础 payload。"""
        return {
            "record_id": self.current_record_id(),
            "applet_key": self.current_cache_key(),
            "cache_path": str(self.current_cache_path()),
        }

    def load_cached_results(self) -> None:
        """异步加载当前卡片缓存的云审计结果。"""
        if self.worker_closed or not self.current_cache_key():
            return
        self.cache_task_id = self.ensure_runner().submit("load_cache", self.cache_request_payload())

    def save_cache_snapshot(self) -> None:
        """把当前云审计结果快照提交给 worker 异步保存。"""
        if self.worker_closed or not self.current_cache_key():
            return
        payload = self.cache_request_payload()
        payload["entry"] = self.cache_entry_payload()
        self.save_cache_task_id = self.ensure_runner().submit("save_cache", payload)

    def clear_cached_results(self) -> None:
        """请求 worker 清空当前卡片的云审计结果缓存。"""
        if self.worker_closed or not self.current_cache_key():
            return
        self.ensure_runner().submit("clear_cache", self.cache_request_payload())

    def cache_entry_payload(self) -> dict:
        """把页面内存结果转换为可持久化的缓存条目。"""
        return {
            "static_entries": self.raw_entry_list(self.static_entries),
            "runtime_static_entries": self.raw_entry_list(self.runtime_static_entries),
            "dynamic_entries": [dict(item) for item in self.dynamic_entries if isinstance(item, dict)],
            "call_history": self.current_call_history(),
        }

    def raw_entry_list(self, entries: list[dict]) -> list[dict]:
        """提取归一化扫描结果中的原始记录用于缓存保存。"""
        results: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw_entry = entry.get("raw") if isinstance(entry.get("raw"), dict) else entry
            results.append(dict(raw_entry))
        return results

    def current_records(self) -> list[dict]:
        """合并当前页面的动态和静态云审计结果。"""
        rows = [dict(item) for item in self.dynamic_entries if isinstance(item, dict)]
        rows.extend(dict(item) for item in self.static_entries if isinstance(item, dict))
        rows.extend(dict(item) for item in self.runtime_static_entries if isinstance(item, dict))
        rows.sort(key=self.sort_key)
        return rows

    def merge_entries(self, base_entries: list[dict], update_entries: list[dict]) -> list[dict]:
        """按记录身份合并扫描结果，后传入的记录覆盖同身份旧记录。"""
        merged: dict[tuple, dict] = {}
        for entry in [*base_entries, *update_entries]:
            if not isinstance(entry, dict):
                continue
            key = self.entry_identity(entry)
            if not key:
                continue
            merged[key] = dict(entry)
        return list(merged.values())

    def merge_call_history(self, base_history: list | None, update_history: list | None) -> list[dict]:
        """按 JSON 内容合并云函数调用历史，避免缓存和实时服务重复展示。"""
        merged: dict[str, dict] = {}
        for item in [*(base_history or []), *(update_history or [])]:
            if not isinstance(item, dict):
                continue
            key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            merged[key] = dict(item)
        return list(merged.values())[-200:]

    def sort_key(self, entry: dict) -> tuple:
        """按来源和时间排序云审计结果。"""
        source_rank_map = {"dynamic": 0, "static": 1, "runtime_static": 2}
        source_rank = source_rank_map.get(str(entry.get("source") or ""), 1)
        timestamp = str(entry.get("timestamp") or "")
        count = int(entry.get("count") or 0)
        return (source_rank, -count, timestamp, str(entry.get("name") or ""))

    def refresh_state(self) -> None:
        """刷新按钮、状态栏和结果摘要。"""
        state = self.current_state()
        status = str(state.get("status") or "stopped")
        current_record = bool(state.get("current_record"))
        enabled = bool(state.get("enabled"))
        self.state_label.setText(
            f"状态: {status}    捕获: {int(state.get('captured_count') or 0)}    "
            f"当前: {'是' if current_record else '否'}"
        )
        if current_record and enabled:
            self.start_button.setText("动态捕获中")
            self.start_button.setEnabled(False)
        elif enabled and not current_record:
            self.start_button.setText("切换到当前记录并捕获")
            self.start_button.setEnabled(self.devtools_service is not None)
        else:
            self.start_button.setText("开启动态捕获")
            self.start_button.setEnabled(self.devtools_service is not None)
        self.stop_button.setEnabled(self.devtools_service is not None and bool(state.get("worker_alive")) and enabled)
        has_records = bool(self.current_records())
        self.clear_button.setEnabled(has_records)
        self.export_button.setEnabled(has_records)
        self.scan_summary.setText(self.summary_text())
        self.refresh_scan_table()

    def summary_text(self) -> str:
        """生成扫描结果汇总文案。"""
        dynamic_count = len(self.dynamic_entries)
        static_count = len(self.static_entries) + len(self.runtime_static_entries)
        total = dynamic_count + static_count
        return f"动态 {dynamic_count} 条，静态 {static_count} 条，共 {total} 条"

    def refresh_scan_table(self) -> None:
        """刷新扫描结果表格，并应用当前搜索过滤。"""
        selected_key = self.entry_identity(self.selected_entry)
        selected_item: QTreeWidgetItem | None = None
        blocker = QSignalBlocker(self.scan_tree)
        self.scan_tree.clear()
        keyword = self.search_input.text().strip().lower()
        self.last_filter_text = keyword
        for entry in self.current_records():
            row_values = self.entry_row_values(entry)
            if keyword and not any(keyword in str(value).lower() for value in row_values):
                continue
            item = QTreeWidgetItem([str(value) for value in row_values])
            item.setData(0, Qt.ItemDataRole.UserRole, dict(entry))
            self.scan_tree.addTopLevelItem(item)
            if selected_key and self.entry_identity(entry) == selected_key:
                selected_item = item
        if selected_item is not None:
            self.scan_tree.setCurrentItem(selected_item)
            selected_item.setSelected(True)
        del blocker
        self.scan_tree.resizeColumnToContents(0)

    def entry_identity(self, entry: dict | None) -> tuple:
        """生成扫描记录的稳定身份，用于刷新表格后恢复选中项。"""
        if not isinstance(entry, dict):
            return ()
        return (
            str(entry.get("source") or ""),
            str(entry.get("type") or ""),
            str(entry.get("name") or ""),
            str(entry.get("app_id") or ""),
            str(entry.get("timestamp") or ""),
            str(entry.get("status") or ""),
            int(entry.get("count") or 0),
            json.dumps(entry.get("params") or [], ensure_ascii=False, sort_keys=True, default=str),
            json.dumps(entry.get("files") or [], ensure_ascii=False, sort_keys=True, default=str),
        )

    def entry_row_values(self, entry: dict) -> tuple[str, str, str, str, str, str, str]:
        """把结果记录转换成表格行文本。"""
        params_text = format_json_text(entry.get("data") or entry.get("params") or {})
        if len(params_text) > 160:
            params_text = params_text[:157] + "..."
        return (
            str(entry.get("source_label") or entry.get("source") or "-"),
            str(entry.get("app_id") or ""),
            str(entry.get("type_label") or entry.get("type") or "-"),
            str(entry.get("name") or ""),
            params_text,
            str(entry.get("status") or ""),
            str(entry.get("timestamp") or ""),
        )

    def process_worker_events(self) -> None:
        """从静态扫描 worker 的事件队列非阻塞拉取结果。"""
        if self.runner is None:
            return
        for _index in range(60):
            try:
                event = self.runner.get_event_nowait()
            except Exception:
                break
            self.handle_worker_event(event)

    def handle_worker_event(self, event: dict) -> None:
        """处理静态扫描 worker 返回的事件。"""
        event_type = str(event.get("type") or "")
        record_id = int(event.get("record_id") or 0)
        if record_id and record_id != self.current_record_id():
            return
        if event_type == "scan_static_progress":
            summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
            if summary.get("cached"):
                self.scan_summary.setText(f"已使用静态扫描缓存，发现 {int(summary.get('match_count') or 0)} 条")
            else:
                self.scan_summary.setText(
                    f"正在扫描 {int(summary.get('scanned_files') or 0)} / {int(summary.get('total_files') or 0)} "
                    f"文件，发现 {int(summary.get('match_count') or 0)} 条"
                )
            return
        if event_type == "scan_static_result":
            results = event.get("results") if isinstance(event.get("results"), list) else []
            self.handle_static_results(results)
            return
        if event_type == "load_cache_result":
            entry = event.get("entry") if isinstance(event.get("entry"), dict) else {}
            self.handle_cache_loaded(record_id, entry)
            return
        if event_type in {"save_cache_done", "clear_cache_done"}:
            return
        if event_type == "scan_static_error":
            self.result_view.setPlainText(str(event.get("message") or "任务失败"))
            self._complete_static_scan_step()
            return
        if event_type == "export_report_done":
            self.result_view.setPlainText(f"报告已导出：{event.get('path')}")
            self.export_button.setEnabled(True)
            return
        if event_type.endswith("_error"):
            self.result_view.setPlainText(str(event.get("message") or "任务失败"))
            self.export_button.setEnabled(True)
            self.scan_button.setEnabled(True)

    def handle_static_results(self, results: list[dict]) -> None:
        """把静态扫描结果加入当前结果集合。"""
        self.static_entries = [normalize_static_entry(item) for item in results if isinstance(item, dict)]
        self.scan_summary.setText(self.summary_text())
        self.refresh_scan_table()
        if self.selected_entry is None and self.static_entries:
            self.select_entry(self.static_entries[-1])
        self.save_cache_snapshot()
        self._complete_static_scan_step()

    def handle_runtime_static_results(self, record_id: int, results: list[dict]) -> None:
        """把运行时补充的静态结果并入当前结果集合。"""
        if int(record_id or 0) and int(record_id or 0) != self.current_record_id():
            return
        self.runtime_static_entries = [self.normalize_runtime_static_entry(item) for item in results if isinstance(item, dict)]
        self.scan_summary.setText(self.summary_text())
        self.refresh_scan_table()
        if self.selected_entry is None and self.runtime_static_entries:
            self.select_entry(self.runtime_static_entries[-1])
        self.save_cache_snapshot()
        self._complete_static_scan_step()

    def handle_cache_loaded(self, record_id: int, entry: dict) -> None:
        """把 worker 异步读取到的缓存结果恢复到当前页面。"""
        if int(record_id or 0) and int(record_id or 0) != self.current_record_id():
            return
        if not isinstance(entry, dict) or not entry:
            return
        loaded_static = [
            normalize_static_entry(item)
            for item in entry.get("static_entries", [])
            if isinstance(item, dict)
        ]
        loaded_runtime_static = [
            self.normalize_runtime_static_entry(item)
            for item in entry.get("runtime_static_entries", [])
            if isinstance(item, dict)
        ]
        loaded_dynamic = [
            dict(item)
            for item in entry.get("dynamic_entries", [])
            if isinstance(item, dict)
        ]
        self.static_entries = self.merge_entries(loaded_static, self.static_entries)
        self.runtime_static_entries = self.merge_entries(loaded_runtime_static, self.runtime_static_entries)
        self.dynamic_entries = self.merge_entries(loaded_dynamic, self.dynamic_entries)
        self.cached_call_history = self.merge_call_history(
            self.cached_call_history,
            entry.get("call_history") if isinstance(entry.get("call_history"), list) else [],
        )
        self.scan_summary.setText(self.summary_text())
        self.refresh_scan_table()
        if self.selected_entry is None:
            if self.dynamic_entries:
                self.select_entry(self.dynamic_entries[-1])
            elif self.static_entries:
                self.select_entry(self.static_entries[-1])
            elif self.runtime_static_entries:
                self.select_entry(self.runtime_static_entries[-1])
        self.refresh_state()

    def handle_runtime_static_scan_failed(self, record_id: int, message: str) -> None:
        """显示运行时静态扫描失败信息。"""
        if int(record_id or 0) and int(record_id or 0) != self.current_record_id():
            return
        self.result_view.setPlainText(str(message or "任务失败"))
        self._complete_static_scan_step()

    def handle_cloud_state_changed(self, _state: dict) -> None:
        """响应共享 DevTools 中的云审计状态变化。"""
        self.refresh_state()

    def handle_cloud_calls_changed(self, calls: list) -> None:
        """响应动态云函数捕获记录变化。"""
        self.dynamic_entries = [normalize_dynamic_call(item) for item in calls if isinstance(item, dict)]
        self.scan_summary.setText(self.summary_text())
        self.refresh_scan_table()
        if self.selected_entry is None and self.dynamic_entries:
            self.select_entry(self.dynamic_entries[-1])
        self.save_cache_snapshot()

    def handle_call_completed(self, result: dict) -> None:
        """显示最新一次手动调用的返回结果。"""
        self.clear_manual_call_timeout()
        self.last_result_entry = dict(result)
        self.cached_call_history = self.merge_call_history(self.cached_call_history, [self.last_result_entry])
        self.result_view.setPlainText(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        self.refresh_state()
        self.save_cache_snapshot()

    def start_dynamic_audit(self) -> None:
        """请求共享 DevTools 服务启动动态云函数捕获。"""
        if self.devtools_service is None or not hasattr(self.devtools_service, "start_cloud_audit"):
            self.result_view.setPlainText("当前没有可用的 DevTools 服务")
            return
        if not self.ensure_miniapp_connected():
            return
        self.result_view.setPlainText("正在启动动态捕获...")
        self.devtools_service.start_cloud_audit(self.record)
        self.refresh_state()

    def stop_dynamic_audit(self) -> None:
        """请求共享 DevTools 服务停止动态云函数捕获。"""
        if self.devtools_service is None or not hasattr(self.devtools_service, "stop_cloud_audit"):
            return
        self.devtools_service.stop_cloud_audit()
        self.refresh_state()

    def clear_results(self) -> None:
        """清空当前页面的静态和动态扫描结果。"""
        self.stop_manual_call_timeout()
        self.dynamic_entries = []
        self.static_entries = []
        self.runtime_static_entries = []
        self.cached_call_history = []
        self.selected_entry = None
        self.pending_static_scans = 0
        self.update_call_hints(None)
        self.name_input.clear()
        self.data_input.setPlainText("{}")
        self.scan_summary.setText(self.summary_text())
        self.refresh_scan_table()
        self.result_view.clear()
        self.scan_button.setEnabled(True)
        if self.devtools_service is not None and hasattr(self.devtools_service, "clear_cloud_audit"):
            self.devtools_service.clear_cloud_audit()
        self.clear_cached_results()
        self.refresh_state()

    def start_static_scan(self) -> None:
        """提交静态扫描任务到独立 worker。"""
        output_dirs = [str(path) for path in self.current_output_dirs()]
        launched = 0
        self.pending_static_scans = 0
        if output_dirs:
            payload = self.cache_request_payload()
            payload.update(
                {
                    "output_dirs": output_dirs,
                    "force": False,
                }
            )
            self.static_task_id = self.ensure_runner().submit(
                "scan_static",
                payload,
            )
            launched += 1
        if self.devtools_service is not None and hasattr(self.devtools_service, "scan_cloud_static"):
            if not self.ensure_miniapp_connected():
                if launched == 0:
                    return
            else:
                self.devtools_service.scan_cloud_static(self.record)
                launched += 1
        if launched == 0:
            self.result_view.setPlainText("未找到可扫描的反编译输出目录，也没有可用的运行时静态扫描")
            return
        self.pending_static_scans = launched
        self.scan_button.setEnabled(False)
        self.result_view.setPlainText("正在执行静态扫描...")

    def export_report(self) -> None:
        """导出当前扫描结果和手动调用历史。"""
        path = Path(output_root_path()) / "cloud_audit_report.json"
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(self, "导出云审计报告", str(path), "JSON (*.json)")
        if not file_path:
            return
        self.export_button.setEnabled(False)
        payload = {
            "items": self.current_records(),
            "call_history": self.current_call_history(),
        }
        self.export_task_id = self.ensure_runner().submit("export_report", {"path": file_path, **payload})

    def on_scan_selection_changed(self) -> None:
        """把当前选中的扫描结果同步到手动调用页。"""
        items = self.scan_tree.selectedItems()
        if not items:
            self.selected_entry = None
            self.update_call_hints(None)
            return
        entry = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            self.selected_entry = None
            self.update_call_hints(None)
            return
        self.select_entry(entry)

    def select_entry(self, entry: dict) -> None:
        """保存当前选中项并填充手动调用表单。"""
        self.selected_entry = dict(entry)
        self.update_call_hints(self.selected_entry)
        self.fill_call_form(self.selected_entry)

    def update_call_hints(self, entry: dict | None) -> None:
        """刷新手动调用页上的选中项提示信息。"""
        if not entry:
            self.call_source_label.setText("-")
            self.call_type_label.setText("-")
            self.call_hint_label.setText("请选择一条可调用记录")
            self.call_button.setEnabled(False)
            return
        self.call_source_label.setText(str(entry.get("source_label") or "-"))
        self.call_type_label.setText(str(entry.get("type_label") or "-"))
        if str(entry.get("type") or "") != "function":
            self.call_hint_label.setText("当前选中项不是云函数，无法直接调用")
            self.call_button.setEnabled(False)
            return
        if str(entry.get("source") or "") == "dynamic":
            self.call_hint_label.setText("动态记录会带出真实参数")
        else:
            self.call_hint_label.setText("静态记录会使用默认模板")
        self.call_button.setEnabled(True)

    def fill_call_form_from_selected(self, *_args) -> None:
        """用当前选中的记录填充手动调用表单。"""
        if self.selected_entry is None:
            items = self.scan_tree.selectedItems()
            if items and isinstance(items[0].data(0, Qt.ItemDataRole.UserRole), dict):
                self.select_entry(items[0].data(0, Qt.ItemDataRole.UserRole))
            return
        self.fill_call_form(self.selected_entry)

    def fill_call_form(self, entry: dict | None) -> None:
        """把选中记录的云函数名和参数模板写入调用表单。"""
        if not entry:
            return
        name = str(entry.get("name") or "").strip()
        template = entry_template(entry)
        self.name_input.setText(name)
        self.data_input.setPlainText(format_json_text(template))

    def call_selected_function(self) -> None:
        """提交云函数调用命令到共享 DevTools 服务。"""
        name = self.name_input.text().strip()
        if not name:
            self.result_view.setPlainText("请输入云函数名")
            return
        try:
            data = json.loads(self.data_input.toPlainText().strip() or "{}")
        except json.JSONDecodeError:
            self.result_view.setPlainText("参数 JSON 格式错误")
            return
        if self.devtools_service is None or not hasattr(self.devtools_service, "call_cloud_function"):
            self.result_view.setPlainText("当前没有可用的 DevTools 服务")
            return
        if not self.ensure_miniapp_connected():
            return
        try:
            timeout_seconds = float(self.record.get("_cloud_call_timeout_seconds") or 0)
        except (TypeError, ValueError):
            timeout_seconds = 0.0
        if timeout_seconds <= 0:
            timeout_seconds = 5.0
        self.start_manual_call_timeout(name, data, timeout_seconds)
        self.result_view.setPlainText(f"正在调用 {name} ...")
        self.devtools_service.call_cloud_function(self.record, name, data)

    def ensure_miniapp_connected(self) -> bool:
        """需要运行时小程序的云函数操作执行前进行轻量检查。"""
        if not service_needs_miniapp_reconnect_hint(self.devtools_service, self.record):
            return True
        self.show_reconnect_hint()
        return False

    def show_reconnect_hint(self) -> None:
        """显示小程序未回连提示。"""
        show_miniapp_reconnect_hint(self)

    def on_tab_changed(self, index: int) -> None:
        """在扫描页和调用页之间切换时同步当前状态。"""
        if index == 1 and self.selected_entry is not None:
            self.fill_call_form(self.selected_entry)

    def update_record(self, record: dict) -> None:
        """用最新记录刷新页面，并按开关状态同步动态捕获。"""
        previous_cloud_enabled = self.cloud_enabled()
        previous_identity = self.record_identity(self.record)
        next_identity = self.record_identity(record)
        preserve_selection = bool(previous_identity and previous_identity == next_identity)
        preserved_selected_entry = dict(self.selected_entry) if preserve_selection and isinstance(self.selected_entry, dict) else None
        preserved_last_result_entry = dict(self.last_result_entry) if preserve_selection and isinstance(self.last_result_entry, dict) else None
        self.record = dict(record)
        if preserve_selection:
            self.selected_entry = preserved_selected_entry
            self.last_result_entry = preserved_last_result_entry
        else:
            self.stop_manual_call_timeout()
            self.selected_entry = None
            self.last_result_entry = None
            self.dynamic_entries = []
            self.static_entries = []
            self.runtime_static_entries = []
            self.cached_call_history = []
            self.pending_static_scans = 0
            self.update_call_hints(None)
            self.name_input.clear()
            self.data_input.setPlainText("{}")
            self.result_view.clear()
            self.scan_button.setEnabled(True)
        self.sync_service_snapshot()
        self.refresh_state()
        if not preserve_selection:
            QTimer.singleShot(0, self.load_cached_results)
        current_cloud_enabled = self.cloud_enabled()
        if current_cloud_enabled and not previous_cloud_enabled:
            QTimer.singleShot(0, self.start_dynamic_audit)
        elif not current_cloud_enabled and previous_cloud_enabled:
            self.stop_dynamic_audit()

    def record_identity(self, record: dict | None) -> tuple[str, str]:
        """生成用于判断详情页记录是否仍是同一卡片的稳定标识。"""
        if not isinstance(record, dict):
            return ("", "")
        return (str(record_owner_key(record)), str(record.get("_output_root") or ""))

    def current_record_id(self) -> int:
        """返回当前详情页对应的记录 ID。"""
        return int(self.record.get("id") or 0)

    def normalize_runtime_static_entry(self, item: dict) -> dict:
        """把运行时补充的静态结果转成可和文件扫描结果并列展示的结构。"""
        entry = normalize_static_entry(item)
        entry["source"] = "runtime_static"
        entry["source_label"] = "运行时静态"
        return entry

    def _complete_static_scan_step(self) -> None:
        """记录一个静态扫描子任务完成。"""
        if self.pending_static_scans > 0:
            self.pending_static_scans -= 1
        if self.pending_static_scans <= 0:
            self.pending_static_scans = 0
            self.scan_button.setEnabled(True)

    def start_manual_call_timeout(self, name: str, data: dict, timeout_seconds: float) -> None:
        """启动手动云函数调用的页面级超时兜底。"""
        self.pending_call_name = str(name or "")
        self.pending_call_data = dict(data or {})
        self.pending_call_timeout_seconds = float(timeout_seconds or 0.0)
        delay_ms = max(1, int(round(self.pending_call_timeout_seconds * 1000)))
        self.manual_call_timeout_timer.start(delay_ms)

    def clear_manual_call_timeout(self) -> None:
        """清理已完成的手动调用超时状态。"""
        self.manual_call_timeout_timer.stop()
        self.pending_call_name = ""
        self.pending_call_data = {}
        self.pending_call_timeout_seconds = 0.0

    def stop_manual_call_timeout(self) -> None:
        """停止超时计时器，不触发结果渲染。"""
        self.clear_manual_call_timeout()

    def handle_manual_call_timeout(self) -> None:
        """共享服务未回包时，把调用结果渲染为超时。"""
        name = self.pending_call_name.strip()
        if not name:
            return
        result = {
            "ok": False,
            "status": "timeout",
            "name": name,
            "data": dict(self.pending_call_data),
            "timeout_seconds": self.pending_call_timeout_seconds,
            "reason": f"调用超时({self.pending_call_timeout_seconds}s)",
        }
        self.last_result_entry = dict(result)
        self.result_view.setPlainText(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        self.clear_manual_call_timeout()
        self.refresh_state()

    def shutdown_worker(self) -> None:
        """关闭页面时停止本地 worker 和定时器。"""
        if self.worker_closed:
            return
        self.worker_closed = True
        self.stop_manual_call_timeout()
        self.event_timer.stop()
        if self.runner is not None:
            self.runner.shutdown()
            self.runner = None
