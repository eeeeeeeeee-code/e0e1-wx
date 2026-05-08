"""实现主界面模块按钮、状态点和小程序卡片控件。"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QFrame, QMenu, QMessageBox, QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout, QHBoxLayout, QWidget

from package.ui.constants import CARD_HEIGHT
from package.ui.record_text import mini_program_display_name


class ModuleButton(QPushButton):
    def __init__(self, title: str, action_only: bool = False, parent: QWidget | None = None) -> None:
        """初始化模块按钮，并区分状态按钮和动作按钮。"""
        super().__init__(parent)
        self.title = title
        self.action_only = action_only
        self.setCheckable(not action_only)
        self.setProperty("moduleButton", True)
        self.setProperty("actionButton", "true" if action_only else "false")
        self.setProperty("variant", "secondary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(38)
        self.setMaximumHeight(42)
        if not action_only:
            self.toggled.connect(self.refresh_text)
        self.refresh_text(False)

    def refresh_text(self, checked: bool) -> None:
        """根据按钮状态刷新显示文本。"""
        if self.action_only:
            self.setText(self.title)
            return
        state_text = "开启" if checked else "关闭"
        self.setText(f"{self.title} · {state_text}")


class StatusDot(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化状态圆点控件。"""
        super().__init__(parent)
        self.setObjectName("StatusDot")
        self.setFixedSize(12, 12)
        self.setProperty("active", "false")

    def set_active(self, active: bool) -> None:
        """根据存活状态切换低饱和状态点颜色。"""
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class MiniProgramCard(QFrame):
    delete_requested = Signal(int)
    rebind_requested = Signal(int)
    detail_requested = Signal(dict)

    def __init__(self, record: dict, parent: QWidget | None = None) -> None:
        """根据数据库记录创建小程序卡片。"""
        super().__init__(parent)
        self.record = record
        self.setObjectName("Card")
        self.setProperty("active", "true" if record.get("status") == 1 else "false")
        self.setFixedHeight(CARD_HEIGHT)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)

        self.dot = StatusDot()
        self.dot.set_active(record.get("status") == 1)
        header.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignTop)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        display_name = mini_program_display_name(record)
        self.name_full_text = display_name
        self.name_label = QLabel()
        self.name_label.setObjectName("CardTitle")
        self.name_label.setMinimumWidth(0)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.name_label.setToolTip(self.name_full_text)
        title_box.addWidget(self.name_label)

        wxid_text = str(record.get("wxids_display") or record.get("wxid") or "-")
        self.wxid_full_text = f"wxid: {wxid_text}"
        self.wxid_label = QLabel()
        self.wxid_label.setObjectName("MutedLabel")
        self.wxid_label.setMinimumWidth(0)
        self.wxid_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.wxid_label.setWordWrap(False)
        self.wxid_label.setToolTip(self.wxid_full_text)
        title_box.addWidget(self.wxid_label)

        header.addLayout(title_box, 1)
        root.addLayout(header)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.status_label = QLabel()
        self.status_label.setObjectName("StatusBadge")
        footer.addWidget(self.status_label)

        footer.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.time_label = QLabel()
        self.time_label.setObjectName("MutedLabel")
        footer.addWidget(self.time_label)

        root.addLayout(footer)
        self.refresh_state()

    def resizeEvent(self, event) -> None:
        """卡片宽度变化时重新计算 wxid 省略显示。"""
        super().resizeEvent(event)
        self.refresh_wxid_text()

    def mousePressEvent(self, event) -> None:
        """左键点击卡片时请求打开小程序详情页。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.detail_requested.emit(dict(self.record))
        super().mousePressEvent(event)

    def set_equal_width(self, width: int) -> None:
        """按网格计算结果强制设置卡片宽度。"""
        self.setFixedWidth(max(1, width))
        self.refresh_wxid_text()

    def refresh_state(self) -> None:
        """刷新卡片状态、徽标颜色和最近出现时间。"""
        active = self.record.get("status") == 1
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.dot.set_active(active)
        self.status_label.setText("存活" if active else "已关闭")
        self.status_label.setProperty("status", "success" if active else "neutral")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        timestamp = float(self.record.get("last_seen") or self.record.get("start_time") or 0.0)
        time_text = time.strftime("%H:%M:%S", time.localtime(timestamp)) if timestamp else "-"
        self.time_label.setText(f"时间: {time_text}")
        self.refresh_wxid_text()

    def refresh_wxid_text(self) -> None:
        """按当前宽度把过长 wxid 文本显示为省略号。"""
        name_width = max(40, self.name_label.width())
        name_metrics = QFontMetrics(self.name_label.font())
        self.name_label.setText(name_metrics.elidedText(self.name_full_text, Qt.TextElideMode.ElideRight, name_width))
        available_width = max(40, self.wxid_label.width())
        metrics = QFontMetrics(self.wxid_label.font())
        self.wxid_label.setText(metrics.elidedText(self.wxid_full_text, Qt.TextElideMode.ElideRight, available_width))

    def open_context_menu(self, position) -> None:
        """打开卡片右键菜单并发送操作信号。"""
        record_id = int(self.record.get("id") or 0)
        if record_id <= 0:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("删除记录")
        # hide_action = menu.addAction("隐藏卡片")
        rebind_action = menu.addAction("重新绑定 wxid")
        selected_action = menu.exec(self.mapToGlobal(position))
        if selected_action == delete_action:
            self.delete_requested.emit(record_id)
        elif selected_action == rebind_action:
            self.rebind_requested.emit(record_id)
