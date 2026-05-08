"""实现主窗口初始化、配置入口、详情页联动和关闭清理。"""
from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

from package.applet_logs import LogStore
from package.applet_detail import AppletDetailWindow
from package.applet_routes import RouteService
from package.applet_processing import AppletAutoProcessManager
from package.config.defaults import DEFAULT_APPLET_PACKAGES_PATH
from package.devtools import DevtoolsService
from package.monitor import MiniProgramMonitor
from package.storage.state_store import StateStore
from package.ui.config_dialog import ConfigDialog
from package.ui.crypto_dialog import CryptoDialog
from package.ui.main_window_controls import MainWindowControlsMixin
from package.ui.main_window_monitor import MainWindowMonitorMixin
from package.ui.paths import config_path, output_root_path as default_output_root_path
from package.ui.rules_dialog import RegexRulesDialog
from package.ui.widgets import ModuleButton


class MainWindow(MainWindowControlsMixin, MainWindowMonitorMixin, QMainWindow):
    def __init__(self) -> None:
        """初始化主窗口、事件队列和后台监控。"""
        super().__init__()
        self.ui_events: mp.Queue = mp.Queue()
        self.store = StateStore(config_path(), self.ui_events)
        self.module_buttons: dict[str, ModuleButton] = {}
        self.monitor: MiniProgramMonitor | None = None
        self.monitor_id = 0
        self.monitor_root_path: Path | None = None
        self.monitor_records: list[dict] = []
        self.current_page = 0
        self.detail_windows: dict[int, AppletDetailWindow] = {}
        self.log_store = LogStore()
        self.devtools_service = DevtoolsService(self)
        self.devtools_service.state_changed.connect(self.on_devtools_state_logged)
        self.devtools_service.route_state_changed.connect(self.on_route_state_logged)
        self.devtools_service.miniapp_jump_state_changed.connect(self.on_miniapp_jump_state_logged)
        self.devtools_service.debug_toggle_log_emitted.connect(self.on_debug_toggle_log_logged)
        self.devtools_service.cloud_state_changed.connect(self.on_cloud_state_logged)
        self.devtools_service.cloud_calls_changed.connect(self.on_cloud_calls_logged)
        self.devtools_service.cloud_call_completed.connect(self.on_cloud_call_completed_logged)
        self.devtools_service.cloud_static_scan_completed.connect(self.on_cloud_static_scan_completed_logged)
        self.devtools_service.cloud_static_scan_failed.connect(self.on_cloud_static_scan_failed_logged)
        self.route_service = RouteService(self.devtools_service, self)
        self.auto_processor = AppletAutoProcessManager(self)
        self.auto_processor.processing_updated.connect(self.on_auto_processing_updated)

        self.setWindowTitle("微信小程序自动化监控")
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)

        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        title_row = QHBoxLayout()
        title_row.setSpacing(16)
        title = QLabel("微信小程序自动化监控")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        self.github_hint = QLabel("e0e1-wx-gui:1.3 github: https://github.com/eeeeeeeeee-code/e0e1-wx")
        self.github_hint.setObjectName("HintText")
        self.github_hint.setToolTip(self.github_hint.text())
        self.github_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        github_font = self.github_hint.font()
        github_font.setPointSize(max(11, github_font.pointSize() - 1))
        self.github_hint.setFont(github_font)
        title_row.addWidget(self.github_hint)
        title_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.state_hint = QLabel()
        self.state_hint.setObjectName("HintText")
        title_row.addWidget(self.state_hint)
        root.addLayout(title_row)

        root.addWidget(self.build_control_panel())
        self.monitor_panel = self.build_monitor_panel()
        root.addWidget(self.monitor_panel, 1)

        self.refresh_module_buttons()
        self.refresh_monitor_cards()
        self.refresh_state_hint()
        self.start_monitor()

        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self.process_ui_events)
        self.event_timer.start(300)
    def output_root_path(self) -> Path:
        """返回小程序反编译输出根目录。"""
        return default_output_root_path()

    def open_regex_dialog(self) -> None:
        """打开正则规则配置窗口。"""
        dialog = RegexRulesDialog(self.store.snapshot()["rules"], self)
        dialog.rules_saved.connect(self.update_rules)
        dialog.exec()

    def update_rules(self, rules: list[dict]) -> None:
        """接收并保存正则规则列表。"""
        self.store.update_rules(rules)
        self.schedule_visible_auto_processing()
        self.refresh_open_detail_record()

    def current_config(self) -> dict:
        """返回当前配置快照。"""
        return dict(self.store.state.get("config", {}))

    def applet_packages_path(self) -> Path:
        """获取当前配置中的微信小程序 packages 路径。"""
        config = self.store.state.get("config", {})
        raw_path = str(config.get("applet_packages_path", DEFAULT_APPLET_PACKAGES_PATH)).strip()
        return Path(raw_path or DEFAULT_APPLET_PACKAGES_PATH).expanduser()

    def open_config_dialog(self) -> None:
        """打开 Config 配置窗口并在关闭后重启监控。"""
        dialog = ConfigDialog(self.store, self)
        dialog.exec()
        self.restart_monitor()
        self.refresh_open_detail_record()

    def open_crypto_dialog(self) -> None:
        """打开微信加密解密窗口。"""
        dialog = CryptoDialog(self)
        dialog.exec()

    def closeEvent(self, event) -> None:
        """窗口关闭时保存状态并停止后台任务。"""
        for window in list(self.detail_windows.values()):
            window.close()
        self.detail_windows.clear()
        self.route_service.shutdown()
        self.devtools_service.shutdown()
        self.store.save()
        self.auto_processor.shutdown()
        self.stop_monitor(wait=True)
        self.store.shutdown()
        super().closeEvent(event)
