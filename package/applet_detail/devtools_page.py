"""Devtools CDP detail page backed by the global devtools service."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class DevtoolsCdpPage(QWidget):
    """Render devtools session state and control buttons for a detail record."""

    def __init__(self, record: dict, devtools_service=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record = dict(record)
        self.devtools_service = devtools_service

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.start_button = QPushButton("开启当前小程序调试")
        self.start_button.setProperty("variant", "primary")
        self.start_button.setProperty("size", "sm")
        self.start_button.clicked.connect(self.start_debug)
        action_row.addWidget(self.start_button)

        self.stop_button = QPushButton("手动停止调试")
        self.stop_button.setProperty("variant", "danger")
        self.stop_button.setProperty("size", "sm")
        self.stop_button.clicked.connect(self.stop_debug)
        action_row.addWidget(self.stop_button)

        self.copy_button = QPushButton("复制链接")
        self.copy_button.setProperty("variant", "ghost")
        self.copy_button.setProperty("size", "sm")
        self.copy_button.clicked.connect(self.copy_link)
        action_row.addWidget(self.copy_button)
        action_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        root.addLayout(action_row)

        info_frame = QFrame()
        info_frame.setObjectName("StatusStrip")
        info_grid = QGridLayout(info_frame)
        info_grid.setContentsMargins(12, 10, 12, 10)
        info_grid.setHorizontalSpacing(16)
        info_grid.setVerticalSpacing(8)

        self.status_value = self.add_row(info_grid, 0, "会话状态")
        self.owner_value = self.add_row(info_grid, 1, "当前归属")
        self.port_value = self.add_row(info_grid, 2, "CDP 端口")
        self.link_value = self.add_row(info_grid, 3, "调试链接", selectable=True)
        root.addWidget(info_frame)

        connection_frame = QFrame()
        connection_frame.setObjectName("InsetPanel")
        connection_grid = QGridLayout(connection_frame)
        connection_grid.setContentsMargins(12, 12, 12, 12)
        connection_grid.setHorizontalSpacing(16)
        connection_grid.setVerticalSpacing(8)
        self.frida_value = self.add_row(connection_grid, 0, "Frida")
        self.miniapp_value = self.add_row(connection_grid, 1, "小程序")
        self.devtools_value = self.add_row(connection_grid, 2, "DevTools")
        root.addWidget(connection_frame)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("HintText")
        root.addWidget(self.message_label)

        root.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        if self.devtools_service is not None and hasattr(self.devtools_service, "state_changed"):
            self.devtools_service.state_changed.connect(self.handle_service_state_changed)
        self.refresh_state()

    def add_row(self, grid: QGridLayout, row: int, name: str, selectable: bool = False) -> QLabel:
        """Add one label/value row to the page info grid."""
        name_label = QLabel(name)
        name_label.setObjectName("MutedLabel")
        value_label = QLabel("-")
        value_label.setWordWrap(True)
        if selectable:
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(name_label, row, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)
        return value_label

    def update_record(self, record: dict) -> None:
        """Refresh the page against a new monitor record snapshot."""
        self.record = dict(record)
        self.refresh_state()

    def handle_service_state_changed(self, _state: dict) -> None:
        """Refresh the page when the global devtools state changes."""
        self.refresh_state()

    def current_state(self) -> dict:
        """Return the devtools state decorated for this record."""
        if self.devtools_service is not None and hasattr(self.devtools_service, "state_for_record"):
            return self.devtools_service.state_for_record(self.record)
        state = self.record.get("_devtools_state")
        return dict(state) if isinstance(state, dict) else {}

    def start_debug(self) -> None:
        """Route the start or switch request to the global service."""
        if self.devtools_service is not None and hasattr(self.devtools_service, "start_debug"):
            self.devtools_service.start_debug(self.record)

    def stop_debug(self) -> None:
        """Route the stop request to the global service."""
        if self.devtools_service is not None and hasattr(self.devtools_service, "stop_debug"):
            self.devtools_service.stop_debug()

    def copy_link(self) -> None:
        """Copy the current devtools URL to the clipboard."""
        link = self.link_value.text().strip()
        if link and link != "-":
            QApplication.clipboard().setText(link)

    def refresh_state(self) -> None:
        """Render the latest global devtools state for the current record."""
        state = self.current_state()
        status = str(state.get("status") or "stopped")
        current_record = bool(state.get("current_record"))
        worker_alive = bool(state.get("worker_alive"))
        link = str(state.get("link") or "")
        owner_name = str(state.get("display_name") or "").strip() or "-"
        if state.get("owner_key") and not current_record:
            owner_name = f"{owner_name}（其他卡片）"
        if not state.get("owner_key"):
            owner_name = "-"

        self.status_value.setText(self.status_text(status, current_record))
        self.owner_value.setText(owner_name)
        self.port_value.setText(str(int(state.get("cdp_port") or 0)) if int(state.get("cdp_port") or 0) > 0 else "-")
        self.link_value.setText(link or "-")
        self.frida_value.setText("已连接" if state.get("frida") else "未连接")
        self.miniapp_value.setText("已回连" if state.get("miniapp") else "未回连")
        self.devtools_value.setText("已连接" if state.get("devtools") else "未连接")
        self.message_label.setText(str(state.get("message") or state.get("error") or ""))

        start_text, start_enabled = self.start_button_state(status, current_record)
        self.start_button.setText(start_text)
        self.start_button.setEnabled(start_enabled and self.devtools_service is not None)

        stop_enabled = worker_alive and status in {"starting", "running", "stopping"}
        self.stop_button.setEnabled(stop_enabled and self.devtools_service is not None)
        self.copy_button.setEnabled(bool(link))

    def start_button_state(self, status: str, current_record: bool) -> tuple[str, bool]:
        """Return the current start-button label and enabled state."""
        if status == "running" and current_record:
            return "当前小程序调试中", False
        if status == "starting" and current_record:
            return "正在开启当前小程序调试", False
        if status in {"starting", "running", "stopping"} and not current_record:
            return "切换到当前小程序调试", True
        if status == "failed" and current_record:
            return "重新开启当前小程序调试", True
        return "开启当前小程序调试", True

    def status_text(self, status: str, current_record: bool) -> str:
        """Translate the global worker state into page-facing copy."""
        mapping = {
            "starting": "当前会话启动中" if current_record else "其他会话启动中",
            "running": "当前会话运行中" if current_record else "其他会话运行中",
            "stopping": "调试停止中",
            "failed": "当前会话失败" if current_record else "其他会话失败",
            "stopped": "未启动调试",
        }
        return mapping.get(status, status or "未启动调试")
