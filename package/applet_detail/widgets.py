"""Applet detail window and tab container widgets."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from package.applet_detail.constants import DETAIL_TABS
from package.applet_detail.pages import DetailContentFactory, clean_text, status_text
from package.ui.record_text import mini_program_display_name


class AppletDetailPage(QWidget):
    """Detail page that hosts the tab strip and tab content widgets."""

    back_requested = Signal()

    def __init__(
        self,
        record: dict,
        parent: QWidget | None = None,
        back_button_text: str = "返回",
        devtools_service=None,
        route_service=None,
        on_log_settings_changed=None,
        log_store=None,
        on_global_search_state_changed=None,
    ) -> None:
        """初始化详情页容器并保存各功能服务和日志设置回调。"""
        super().__init__(parent)
        self.record = dict(record)
        self.devtools_service = devtools_service
        self.route_service = route_service
        self.on_log_settings_changed = on_log_settings_changed
        self.log_store = log_store
        self.on_global_search_state_changed = on_global_search_state_changed
        self.tab_hosts: dict[int, QWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.back_button = QPushButton(back_button_text)
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        title_box.addWidget(self.title_label)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("MutedLabel")
        title_box.addWidget(self.meta_label)
        header.addLayout(title_box, 1)
        header.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.render_tab)
        root.addWidget(self.tabs, 1)

        self.build_tabs()
        self.refresh_header()
        initial_index = self.initial_tab_index()
        self.tabs.setCurrentIndex(initial_index)
        self.render_tab(initial_index)

    def build_tabs(self) -> None:
        """Create the tab strip and empty tab hosts."""
        self.tabs.blockSignals(True)
        self.tabs.clear()
        self.tab_hosts.clear()
        for index, (_tab_key, title) in enumerate(DETAIL_TABS):
            host = QWidget()
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self.tab_hosts[index] = host
            self.tabs.addTab(host, title)
        self.tabs.blockSignals(False)

    def update_record(self, record: dict) -> None:
        """Refresh the page against the latest monitor record."""
        was_decompile_enabled = bool(self.record.get("_decompile_enabled"))
        self.record = dict(record)
        self.refresh_header()
        if bool(self.record.get("_decompile_enabled")) and not was_decompile_enabled:
            target_index = self.tab_index("decompile_folder")
            if target_index >= 0 and self.tabs.currentIndex() != target_index:
                self.tabs.setCurrentIndex(target_index)
                return
        self.render_tab(self.tabs.currentIndex())

    def refresh_header(self) -> None:
        """Refresh title and metadata labels."""
        title = mini_program_display_name(self.record)
        wxid = clean_text(self.record.get("wxids_display") or self.record.get("wxid"))
        self.title_label.setText(title)
        self.meta_label.setText(f"wxid: {wxid}    状态: {status_text(self.record)}")

    def render_tab(self, index: int) -> None:
        """Render the current tab on demand."""
        if index < 0 or index >= len(DETAIL_TABS):
            return
        host = self.tab_hosts.get(index)
        if host is None:
            return
        layout = host.layout()
        if layout is None:
            return
        tab_key = DETAIL_TABS[index][0]
        if layout.count() == 1:
            existing_widget = layout.itemAt(0).widget()
            if existing_widget is not None and hasattr(existing_widget, "update_record"):
                existing_widget.update_record(self.record)
                return
        self.clear_layout(layout)
        layout.addWidget(
            DetailContentFactory.create_page(
                tab_key,
                self.record,
                self.devtools_service,
                self.route_service,
                self.on_log_settings_changed,
                self.log_store,
                self.on_global_search_state_changed,
            )
        )

    def initial_tab_index(self) -> int:
        """Choose the initial tab from the record state."""
        if bool(self.record.get("_decompile_enabled")):
            decompile_index = self.tab_index("decompile_folder")
            if decompile_index >= 0:
                return decompile_index
        return 0

    def tab_index(self, tab_key: str) -> int:
        """Find the tab index by key."""
        for index, (current_key, _title) in enumerate(DETAIL_TABS):
            if current_key == tab_key:
                return index
        return -1

    def clear_layout(self, layout) -> None:
        """Delete the current tab widget if present."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if hasattr(widget, "shutdown_worker"):
                    widget.shutdown_worker()
                widget.deleteLater()

    def shutdown(self) -> None:
        """Shut down any tab-local background work when the window closes."""
        for host in self.tab_hosts.values():
            layout = host.layout()
            if layout is None:
                continue
            for index in range(layout.count()):
                widget = layout.itemAt(index).widget()
                if widget is not None and hasattr(widget, "shutdown_worker"):
                    widget.shutdown_worker()


class AppletDetailWindow(QMainWindow):
    """Standalone applet detail window."""

    closed = Signal(int)

    def __init__(
        self,
        record: dict,
        parent: QWidget | None = None,
        devtools_service=None,
        route_service=None,
        on_log_settings_changed=None,
        log_store=None,
        on_global_search_state_changed=None,
    ) -> None:
        """初始化独立详情窗口并把日志设置回调传给页面容器。"""
        super().__init__(parent)
        self.record_key = int(record.get("id") or 0)
        self.setWindowTitle(self.window_title(record))
        self.resize(980, 680)
        self.setMinimumSize(860, 560)
        self.page = AppletDetailPage(
            record,
            self,
            back_button_text="关闭",
            devtools_service=devtools_service,
            route_service=route_service,
            on_log_settings_changed=on_log_settings_changed,
            log_store=log_store,
            on_global_search_state_changed=on_global_search_state_changed,
        )
        self.page.back_requested.connect(self.close)
        self.setCentralWidget(self.page)

    def update_record(self, record: dict) -> None:
        """Refresh the window against the latest record."""
        self.record_key = int(record.get("id") or 0)
        self.setWindowTitle(self.window_title(record))
        self.page.update_record(record)

    def window_title(self, record: dict) -> str:
        """Build the window title from the record name."""
        title = mini_program_display_name(record)
        return f"{title} - 小程序详情"

    def closeEvent(self, event) -> None:
        """Notify the main window to drop the detail-window reference."""
        self.page.shutdown()
        self.closed.emit(self.record_key)
        super().closeEvent(event)
