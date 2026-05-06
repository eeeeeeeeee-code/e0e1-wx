"""Build detail-page tab content widgets from a monitor record."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from package.applet_detail.cloud_page import CloudFunctionsPage
from package.applet_detail.debug_page import DebugTogglePage
from package.applet_detail.decompile_page import DecompileFolderPage
from package.applet_detail.devtools_page import DevtoolsCdpPage
from package.applet_detail.logs_page import LogsPage
from package.applet_routes.page import RoutePage


def clean_text(value, fallback: str = "-") -> str:
    """Normalize record values for readable UI output."""
    text = str(value or "").strip()
    return text if text else fallback


def status_text(record: dict) -> str:
    """Return the display status for a monitor record."""
    return "存活" if record.get("status") == 1 else "已关闭"


def timestamp_text(value) -> str:
    """Render a unix timestamp as a local datetime string."""
    try:
        timestamp = float(value or 0.0)
    except (TypeError, ValueError):
        timestamp = 0.0
    if timestamp <= 0:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))


class DetailContentFactory:
    """Create content widgets for each detail-page tab."""

    @staticmethod
    def create_page(
        tab_key: str,
        record: dict,
        devtools_service=None,
        route_service=None,
        on_log_settings_changed=None,
        log_store=None,
        on_global_search_state_changed=None,
    ) -> QWidget:
        """根据 Tab 标识创建对应的详情页内容控件。"""
        if tab_key == "devtools_cdp":
            return DetailContentFactory.create_devtools_cdp_page(record, devtools_service)
        if tab_key == "routes":
            return DetailContentFactory.create_routes_page(record, route_service)
        if tab_key == "decompile_folder":
            return DetailContentFactory.create_decompile_folder_page(record, on_global_search_state_changed)
        if tab_key == "cloud_functions":
            return DetailContentFactory.create_cloud_functions_page(record, devtools_service)
        if tab_key == "debug_toggle":
            return DetailContentFactory.create_debug_toggle_page(record, devtools_service)
        if tab_key == "logs":
            return DetailContentFactory.create_logs_page(
                record,
                on_log_settings_changed=on_log_settings_changed,
                log_store=log_store,
            )
        return DetailContentFactory.create_empty_page("未知模块", "暂无数据")

    @staticmethod
    def create_devtools_cdp_page(record: dict, devtools_service=None) -> QWidget:
        """Create the devtools CDP tab page."""
        return DevtoolsCdpPage(record, devtools_service)

    @staticmethod
    def create_routes_page(record: dict, route_service=None) -> QWidget:
        """Create the routes tab page."""
        return RoutePage(record, route_service)

    @staticmethod
    def create_decompile_folder_page(record: dict, on_global_search_state_changed=None) -> QWidget:
        """Create the decompile folder tab page."""
        return DecompileFolderPage(record, on_global_search_state_changed=on_global_search_state_changed)

    @staticmethod
    def create_cloud_functions_page(record: dict, devtools_service=None) -> QWidget:
        """Create the cloud-functions tab page."""
        return CloudFunctionsPage(record, devtools_service)

    @staticmethod
    def create_debug_toggle_page(record: dict, devtools_service=None) -> QWidget:
        """创建调试开关详情页。"""
        return DebugTogglePage(record, devtools_service)

    @staticmethod
    def create_logs_page(record: dict, on_log_settings_changed=None, log_store=None) -> QWidget:
        """创建日志筛选与展示页面。"""
        return LogsPage(record, log_store=log_store, on_settings_changed=on_log_settings_changed)

    @staticmethod
    def create_module_page(title: str, rows: list[tuple[str, str]], empty_text: str) -> QWidget:
        """Create a generic simple module page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        if rows:
            layout.addWidget(DetailContentFactory.create_info_grid(rows))
        layout.addWidget(DetailContentFactory.create_readonly_text(title, empty_text), 1)
        return widget

    @staticmethod
    def create_empty_page(title: str, text: str) -> QWidget:
        """Create an empty fallback page."""
        return DetailContentFactory.create_module_page(title, [], text)

    @staticmethod
    def create_info_grid(rows: list[tuple[str, str]]) -> QFrame:
        """Create a two-column key/value grid."""
        frame = QFrame()
        frame.setObjectName("DetailInfo")
        grid = QGridLayout(frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        for row, (name, value) in enumerate(rows):
            name_label = QLabel(name)
            name_label.setObjectName("MutedLabel")
            value_label = QLabel(clean_text(value))
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value_label.setWordWrap(True)
            grid.addWidget(name_label, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)
        return frame

    @staticmethod
    def create_readonly_text(title: str, text: str) -> QWidget:
        """Create a titled read-only text block."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        editor = QPlainTextEdit()
        editor.setObjectName("CodePreview")
        editor.setReadOnly(True)
        editor.setPlainText(text)
        editor.setMinimumHeight(160)
        layout.addWidget(editor, 1)
        return widget
