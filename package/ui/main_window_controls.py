"""构建主窗口功能按钮区并处理模块开关状态。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

from package.config.defaults import ACTION_MODULE_KEYS, CONTROL_DEFS
from package.ui.constants import CARD_COLUMN_SPACING
from package.ui.widgets import ModuleButton


class MainWindowControlsMixin:
    def build_control_panel(self) -> QFrame:
        """构建顶部功能按钮区域。"""
        frame = QFrame()
        frame.setObjectName("Toolbar")
        layout = QGridLayout(frame)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        state = self.store.snapshot()

        for column, (key, title) in enumerate(CONTROL_DEFS):
            action_only = key in ACTION_MODULE_KEYS
            button = ModuleButton(title, action_only=action_only)
            if not action_only:
                button.setChecked(bool(state["toggles"].get(key, False)))
            button.clicked.connect(lambda checked, module_key=key: self.on_module_clicked(module_key, checked))
            layout.addWidget(button, 0, column)
            self.module_buttons[key] = button

        return frame

    def build_monitor_panel(self) -> QFrame:
        """构建小程序监控卡片与分页区域。"""
        frame = QFrame()
        frame.setObjectName("Surface")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("小程序监控区域")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self.monitor_status_label = QLabel()
        self.monitor_status_label.setObjectName("MutedLabel")
        header.addWidget(self.monitor_status_label)
        layout.addLayout(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.card_container = QWidget()
        self.card_container.setStyleSheet("background-color: transparent;")
        self.cards_layout = QGridLayout(self.card_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setHorizontalSpacing(CARD_COLUMN_SPACING)
        self.cards_layout.setVerticalSpacing(12)
        self.scroll_area.setWidget(self.card_container)
        layout.addWidget(self.scroll_area, 1)

        pagination = QHBoxLayout()
        pagination.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.prev_page_button = QPushButton("上一页")
        self.prev_page_button.clicked.connect(self.previous_page)
        pagination.addWidget(self.prev_page_button)
        self.page_label = QLabel()
        self.page_label.setObjectName("MutedLabel")
        pagination.addWidget(self.page_label)
        self.next_page_button = QPushButton("下一页")
        self.next_page_button.clicked.connect(self.next_page)
        pagination.addWidget(self.next_page_button)
        layout.addLayout(pagination)

        return frame

    def on_module_clicked(self, key: str, checked: bool) -> None:
        """处理顶部模块按钮点击事件。"""
        if key in ACTION_MODULE_KEYS:
            if key == "config":
                self.open_config_dialog()
            elif key == "regex":
                self.open_regex_dialog()
            elif key == "crypto":
                self.open_crypto_dialog()
            self.refresh_module_buttons()
            self.refresh_state_hint()
            return

        self.store.update_toggle(key, checked)
        self.refresh_module_buttons()
        self.refresh_state_hint()
        if key in {"decompile", "optimize_code"}:
            self.schedule_visible_auto_processing()
        if key in {"decompile", "optimize_code", "cloud"}:
            self.refresh_open_detail_record()

    def refresh_module_buttons(self) -> None:
        """根据状态快照刷新顶部按钮显示。"""
        state = self.store.snapshot()
        for key, button in self.module_buttons.items():
            button.blockSignals(True)
            if key not in ACTION_MODULE_KEYS:
                button.setChecked(bool(state["toggles"].get(key, False)))
            button.refresh_text(button.isChecked())
            button.blockSignals(False)

    def refresh_state_hint(self) -> None:
        """刷新窗口右上角状态统计。"""
        state = self.store.snapshot()
        toggle_keys = [key for key, _ in CONTROL_DEFS if key not in ACTION_MODULE_KEYS]
        active_count = sum(1 for key in toggle_keys if state["toggles"].get(key, False))
        program_count = len(self.monitor_records)
        open_count = sum(1 for record in self.monitor_records if record.get("status") == 1)
        self.state_hint.setText(f"模块启动：{active_count} / {len(toggle_keys)}    小程序存活：{open_count} / {program_count}")
