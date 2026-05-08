"""实现小程序详情页中的调试开关页面。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from package.applet_debug import default_debug_toggle_state


class DebugTogglePage(QWidget):
    """展示调试状态，并把调试开关命令转发给共享服务。"""

    STATUS_TEXT = {
        "idle": "未检测",
        "enabling": "正在开启调试",
        "disabling": "正在关闭调试",
        "failed": "执行失败",
        "ready": "已完成",
    }

    def __init__(self, record: dict, devtools_service=None, parent: QWidget | None = None) -> None:
        """初始化调试开关页面，并在安全前提下决定是否自动检测。"""
        super().__init__(parent)
        self.record = dict(record)
        self.devtools_service = devtools_service

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.detect_button = QPushButton("检测状态")
        self.detect_button.setProperty("variant", "ghost")
        self.detect_button.setProperty("size", "sm")
        self.detect_button.clicked.connect(self.detect_debug)
        action_row.addWidget(self.detect_button)
        self.enable_button = QPushButton("开启调试")
        self.enable_button.setProperty("variant", "primary")
        self.enable_button.setProperty("size", "sm")
        self.enable_button.clicked.connect(self.enable_debug)
        action_row.addWidget(self.enable_button)
        self.disable_button = QPushButton("关闭调试")
        self.disable_button.setProperty("variant", "danger")
        self.disable_button.setProperty("size", "sm")
        self.disable_button.clicked.connect(self.disable_debug)
        action_row.addWidget(self.disable_button)
        action_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        root.addLayout(action_row)

        info_frame = QFrame()
        info_frame.setObjectName("StatusStrip")
        info_grid = QGridLayout(info_frame)
        info_grid.setContentsMargins(12, 10, 12, 10)
        info_grid.setHorizontalSpacing(16)
        info_grid.setVerticalSpacing(8)
        self.status_value = self.add_row(info_grid, 0, "当前状态")
        self.debug_value = self.add_row(info_grid, 1, "调试开关")
        self.vconsole_value = self.add_row(info_grid, 2, "vConsole")
        self.owner_value = self.add_row(info_grid, 3, "当前归属")
        self.action_value = self.add_row(info_grid, 4, "最近操作")
        self.error_value = self.add_row(info_grid, 5, "错误信息")
        root.addWidget(info_frame)

        self.message_label = QLabel(
            "通过官方接口 wx.setEnableDebug 控制小程序内置调试能力。\n"
            "开启或关闭后通常需要重启小程序才能完全确认最终效果。"
        )
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("HintText")
        root.addWidget(self.message_label)

        if self.devtools_service is not None and hasattr(self.devtools_service, "debug_toggle_state_changed"):
            self.devtools_service.debug_toggle_state_changed.connect(self.handle_debug_state_changed)

        self.refresh_state()
        self.auto_detect_if_safe()

    def add_row(self, grid: QGridLayout, row: int, name: str) -> QLabel:
        """向状态信息区添加标题和值标签。"""
        title = QLabel(name)
        title.setObjectName("MutedLabel")
        value = QLabel("-")
        value.setWordWrap(True)
        grid.addWidget(title, row, 0)
        grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        return value

    def current_state(self) -> dict:
        """返回当前卡片对应的调试开关状态快照。"""
        if self.devtools_service is not None and hasattr(self.devtools_service, "debug_toggle_state_for_record"):
            return self.devtools_service.debug_toggle_state_for_record(self.record)
        return default_debug_toggle_state(
            record_id=int(self.record.get("id") or 0),
            owner_key=str(self.record.get("wxid") or ""),
            display_name=str(self.record.get("name") or ""),
        )

    def refresh_state(self) -> None:
        """把当前状态快照渲染到页面控件。"""
        state = self.current_state()
        status = str(state.get("status") or "idle")
        busy = status in {"enabling", "disabling"}
        self.status_value.setText(self.STATUS_TEXT.get(status, status))
        self.debug_value.setText("已开启" if state.get("debug_enabled") else "未开启")
        self.vconsole_value.setText("已检测到" if state.get("vconsole_visible") else "未检测到")
        self.owner_value.setText(str(state.get("display_name") or "-"))
        self.action_value.setText(str(state.get("last_action") or "-"))
        self.error_value.setText(str(state.get("error") or "-"))
        enabled = self.devtools_service is not None
        self.detect_button.setEnabled(enabled and not busy)
        self.enable_button.setEnabled(enabled and not busy)
        self.disable_button.setEnabled(enabled and not busy)
        if self.should_show_reconnect_hint():
            self.message_label.setText(
                "当前调试会话已存在，但小程序还未回连。\n"
                "可直接点击按钮继续操作，后台会保持等待小程序回连。"
            )
            return
        if self.should_auto_detect_current_record():
            self.message_label.setText(
                "通过官方接口 wx.setEnableDebug 控制小程序内置调试能力。\n"
                "开启或关闭后通常需要重启小程序才能完全确认最终效果。"
            )
            return
        self.message_label.setText(
            "通过官方接口 wx.setEnableDebug 控制小程序内置调试能力。\n"
            "可直接点击按钮开启调试，后台会自动拉起 DevTools 并等待小程序回连。"
        )

    def current_devtools_state(self) -> dict:
        """返回当前卡片对应的共享调试会话状态。"""
        if self.devtools_service is not None and hasattr(self.devtools_service, "state_for_record"):
            state = self.devtools_service.state_for_record(self.record)
            if isinstance(state, dict):
                return dict(state)
        return {}

    def should_auto_detect_current_record(self) -> bool:
        """仅当当前卡片已经持有活动会话且小程序已回连时才自动检测。"""
        state = self.current_devtools_state()
        if not isinstance(state, dict):
            return False
        if not bool(state.get("worker_alive")):
            return False
        if not bool(state.get("current_record")):
            return False
        if str(state.get("status") or "") != "running":
            return False
        return bool(state.get("miniapp"))

    def should_show_reconnect_hint(self) -> bool:
        """判断当前是否应提示用户先重启小程序再继续。"""
        state = self.current_devtools_state()
        if not isinstance(state, dict):
            return False
        if not bool(state.get("worker_alive")):
            return False
        if not bool(state.get("current_record")):
            return False
        if str(state.get("status") or "") not in {"starting", "running"}:
            return False
        return not bool(state.get("miniapp"))

    def auto_detect_if_safe(self) -> None:
        """只在不会触发隐式会话切换时自动发起检测。"""
        if not self.should_auto_detect_current_record():
            return
        self.detect_debug()

    def detect_debug(self) -> None:
        """请求后台检测当前小程序的调试状态。"""
        if self.devtools_service is not None and hasattr(self.devtools_service, "detect_debug_toggle"):
            self.devtools_service.detect_debug_toggle(self.record)

    def enable_debug(self) -> None:
        """在用户确认风险后请求后台开启调试。"""
        reply = QMessageBox.question(
            self,
            "风险确认",
            "非正规开启小程序调试有封号风险。\n测试需谨慎！\n\n确定要开启吗？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return
        if self.devtools_service is not None and hasattr(self.devtools_service, "set_debug_toggle"):
            self.devtools_service.set_debug_toggle(self.record, True)

    def disable_debug(self) -> None:
        """请求后台关闭当前小程序调试。"""
        if self.devtools_service is not None and hasattr(self.devtools_service, "set_debug_toggle"):
            self.devtools_service.set_debug_toggle(self.record, False)

    def handle_debug_state_changed(self, record_id: int, _state: dict) -> None:
        """仅在事件属于当前记录时刷新页面。"""
        if int(record_id or 0) != int(self.record.get("id") or 0):
            return
        self.refresh_state()

    def update_record(self, record: dict) -> None:
        """切换记录时取消旧任务，并仅在安全前提下对新记录重新检测。"""
        previous_record = dict(self.record)
        self.record = dict(record)
        previous_record_id = int(previous_record.get("id") or 0)
        current_record_id = int(self.record.get("id") or 0)
        if (
            self.devtools_service is not None
            and hasattr(self.devtools_service, "cancel_debug_toggle")
            and previous_record_id != current_record_id
        ):
            self.devtools_service.cancel_debug_toggle(previous_record)
        self.refresh_state()
        if previous_record_id != current_record_id:
            self.auto_detect_if_safe()

    def shutdown_worker(self) -> None:
        """详情页关闭时取消当前记录尚未完成的调试任务。"""
        if self.devtools_service is not None and hasattr(self.devtools_service, "cancel_debug_toggle"):
            self.devtools_service.cancel_debug_toggle(self.record)
