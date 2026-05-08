"""实现小程序详情页日志查看与筛选页面。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

from package.applet_logs import (
    LOG_LEVELS,
    LOG_SOURCE_DEFS,
    LogStore,
    filter_log_entries,
    format_log_entry,
    log_record_key,
    normalize_log_settings,
)


class LogsPage(QWidget):
    """小程序详情页中的日志筛选和展示页面。"""

    def __init__(
        self,
        record: dict,
        parent: QWidget | None = None,
        log_store: LogStore | None = None,
        on_settings_changed: Callable[[dict], None] | None = None,
    ) -> None:
        """初始化日志页控件、设置和内存日志来源。"""
        super().__init__(parent)
        self.record = dict(record)
        self.record_key = str(self.record.get("_log_record_key") or log_record_key(self.record))
        self.log_store = log_store or LogStore()
        self.on_settings_changed = on_settings_changed
        self.settings = normalize_log_settings(self.record.get("_log_settings"))
        self.source_buttons: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        source_label = QLabel("功能日志")
        source_label.setObjectName("MutedLabel")
        source_row.addWidget(source_label)

        for source_key, source_title in LOG_SOURCE_DEFS:
            button = QPushButton(source_title)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("variant", "ghost")
            button.setProperty("size", "sm")
            button.setProperty("logSourceButton", "true")
            button.toggled.connect(self.handle_settings_changed)
            source_row.addWidget(button)
            self.source_buttons[source_key] = button

        source_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        root.addLayout(source_row)

        level_row = QHBoxLayout()
        level_row.setSpacing(8)
        level_label = QLabel("日志级别")
        level_label.setObjectName("MutedLabel")
        level_row.addWidget(level_label)
        self.level_combo = QComboBox()
        self.level_combo.addItems(list(LOG_LEVELS))
        self.level_combo.currentTextChanged.connect(self.handle_settings_changed)
        level_row.addWidget(self.level_combo)
        level_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        root.addLayout(level_row)

        self.log_editor = QPlainTextEdit()
        self.log_editor.setObjectName("CodePreview")
        self.log_editor.setReadOnly(True)
        self.log_editor.setPlaceholderText("当前没有符合筛选条件的日志")
        root.addWidget(self.log_editor, 1)

        self.apply_settings_to_controls()
        self.refresh_logs()

    def current_settings(self) -> dict:
        """从当前控件状态生成可保存的日志设置。"""
        enabled_sources = [key for key, _label in LOG_SOURCE_DEFS if self.source_buttons[key].isChecked()]
        return normalize_log_settings({"enabled_sources": enabled_sources, "level": self.level_combo.currentText()})

    def apply_settings_to_controls(self) -> None:
        """把记录中的日志设置应用到按钮和级别选择器。"""
        normalized = normalize_log_settings(self.settings)
        enabled_sources = set(normalized["enabled_sources"])
        for source_key, button in self.source_buttons.items():
            button.blockSignals(True)
            button.setChecked(source_key in enabled_sources)
            button.blockSignals(False)
        self.level_combo.blockSignals(True)
        self.level_combo.setCurrentText(normalized["level"])
        self.level_combo.blockSignals(False)
        self.settings = normalized

    def handle_settings_changed(self, *_args) -> None:
        """处理按钮或级别变化，并把设置交给外层异步保存。"""
        self.settings = self.current_settings()
        if self.on_settings_changed is not None:
            self.on_settings_changed(dict(self.settings))
        self.refresh_logs()

    def update_record(self, record: dict) -> None:
        """详情页记录刷新时同步当前小程序和保存过的日志设置。"""
        self.record = dict(record)
        self.record_key = str(self.record.get("_log_record_key") or log_record_key(self.record))
        self.settings = normalize_log_settings(self.record.get("_log_settings"))
        self.apply_settings_to_controls()
        self.refresh_logs()

    def refresh_logs(self) -> None:
        """按当前筛选条件刷新只读日志文本。"""
        entries = self.log_store.entries(self.record_key)
        filtered = filter_log_entries(entries, self.settings, record_key=self.record_key)
        self.log_editor.setPlainText("\n".join(format_log_entry(entry) for entry in filtered))
