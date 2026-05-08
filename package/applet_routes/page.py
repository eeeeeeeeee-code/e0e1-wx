"""Mini program route detail tab."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from package.applet_detail.reconnect_hint import show_miniapp_reconnect_hint


class RoutePage(QWidget):
    """Render route state, route list, and route actions for one card."""

    COMPACT_FONT_SIZE = 12
    COMPACT_BUTTON_MIN_HEIGHT = 28
    COMPACT_BUTTON_MAX_HEIGHT = 30
    TRAVERSE_HIGHLIGHT_COLOR = QColor("#F7D9A6")
    TRAVERSE_HIGHLIGHT_TEXT_COLOR = QColor("#7A4300")
    RECONNECT_FAILURE_MARKERS = ("等待小程序回连", "小程序未回连", "No miniapp client connected", "miniapp disconnected")

    STATUS_TEXT = {
        "stopped": "未启动",
        "starting": "正在接管",
        "refreshing": "正在刷新",
        "executing": "正在执行",
        "traversing": "正在遍历",
        "ready": "已就绪",
        "failed": "执行失败",
    }

    ACTION_TEXT = {
        "navigate_to": "打开新页面",
        "redirect_to": "替换当前页",
        "relaunch": "重启到页面",
        "navigate_back": "返回上一页",
    }

    def __init__(self, record: dict, route_service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.record = dict(record)
        self.route_service = route_service
        self._state = {}
        self._info_titles: list[QLabel] = []
        self._last_reconnect_failure_signature: tuple[str, str] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        info_frame = QFrame()
        info_frame.setObjectName("StatusStrip")
        info_grid = QGridLayout(info_frame)
        info_grid.setContentsMargins(10, 8, 10, 8)
        info_grid.setHorizontalSpacing(10)
        info_grid.setVerticalSpacing(2)
        self.status_value = self._add_row(info_grid, 0, "状态")
        self.current_route_value = self._add_row(info_grid, 1, "当前路由")
        self.message_value = self._add_row(info_grid, 2, "最近消息")
        self.error_value = self._add_row(info_grid, 3, "错误")
        root.addWidget(info_frame)

        self.button_scroll_area = QScrollArea()
        self.button_scroll_area.setWidgetResizable(False)
        self.button_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.button_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.button_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.button_scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        button_row_widget = QWidget()
        self.button_row_layout = QHBoxLayout(button_row_widget)
        self.button_row_layout.setContentsMargins(0, 0, 0, 0)
        self.button_row_layout.setSpacing(6)
        self.start_button = QPushButton("启动并接管路由")
        self.refresh_button = QPushButton("刷新路由")
        self.traverse_button = QPushButton("遍历全部路由")
        self.traverse_from_button = QPushButton("从指定路由开始遍历")
        self.guard_button = QPushButton("防跳转：已关闭")
        self.guard_button.setCheckable(True)
        self.back_button = QPushButton("返回上一页")
        self.navigate_to_button = QPushButton("打开新页面")
        self.redirect_to_button = QPushButton("替换当前页")
        self.relaunch_button = QPushButton("重启到页面")

        buttons = [
            self.start_button,
            self.refresh_button,
            self.traverse_button,
            self.traverse_from_button,
            self.guard_button,
            self.back_button,
            self.navigate_to_button,
            self.redirect_to_button,
            self.relaunch_button,
        ]
        for button in buttons:
            self._configure_compact_button(button)
            self.button_row_layout.addWidget(button)
        button_row_widget.adjustSize()
        self.button_scroll_area.setWidget(button_row_widget)
        self.button_scroll_area.setFixedHeight(self.COMPACT_BUTTON_MAX_HEIGHT + 16)
        root.addWidget(self.button_scroll_area)

        routes_tree_frame = QFrame()
        routes_tree_frame.setObjectName("RoutesTreeFrame")
        routes_tree_layout = QVBoxLayout(routes_tree_frame)
        routes_tree_layout.setContentsMargins(1, 1, 1, 1)
        routes_tree_layout.setSpacing(0)

        self.routes_tree = QTreeWidget()
        self.routes_tree.setObjectName("RoutesTree")
        self.routes_tree.setColumnCount(3)
        self.routes_tree.setHeaderLabels(["路由", "来源", "类型"])
        self.routes_tree.setRootIsDecorated(False)
        self.routes_tree.setAlternatingRowColors(False)
        self.routes_tree.header().setSectionResizeMode(QHeaderView.Fixed)
        routes_tree_layout.addWidget(self.routes_tree)
        root.addWidget(routes_tree_frame, 1)

        self.start_button.clicked.connect(self.start_route)
        self.refresh_button.clicked.connect(self.refresh_routes)
        self.traverse_button.clicked.connect(self.traverse_routes)
        self.traverse_from_button.clicked.connect(self.traverse_from_selected_route)
        self.guard_button.clicked.connect(self.toggle_guard)
        self.back_button.clicked.connect(self.navigate_back)
        self.navigate_to_button.clicked.connect(lambda: self.execute_action("navigate_to"))
        self.redirect_to_button.clicked.connect(lambda: self.execute_action("redirect_to"))
        self.relaunch_button.clicked.connect(lambda: self.execute_action("relaunch"))
        self.routes_tree.itemSelectionChanged.connect(self.refresh_actions)

        if self.route_service is not None and hasattr(self.route_service, "state_changed"):
            self.route_service.state_changed.connect(self.handle_state_changed)
        self.refresh_state()

    def _add_row(self, grid: QGridLayout, row: int, name: str) -> QLabel:
        title = QLabel(name)
        title.setObjectName("MutedLabel")
        self._configure_compact_label(title)
        self._info_titles.append(title)
        value = QLabel("-")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value.setWordWrap(True)
        self._configure_compact_label(value)
        grid.addWidget(title, row, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        return value

    def _configure_compact_button(self, button: QPushButton) -> None:
        """配置路由页功能按钮尺寸，视觉样式交给全局 QSS。"""
        font = QFont(button.font())
        font.setPointSize(self.COMPACT_FONT_SIZE)
        button.setFont(font)
        button.setMinimumHeight(self.COMPACT_BUTTON_MIN_HEIGHT)
        button.setMaximumHeight(self.COMPACT_BUTTON_MAX_HEIGHT)
        button.setMinimumWidth(max(button.sizeHint().width() + 4, 72))
        button.setProperty("routeCompactButton", "true")

    def _configure_compact_label(self, label: QLabel) -> None:
        font = QFont(label.font())
        font.setPointSize(self.COMPACT_FONT_SIZE)
        label.setFont(font)

    @staticmethod
    def compute_tree_column_widths(total_width: int) -> tuple[int, int, int]:
        total = max(int(total_width or 0), 3)
        route_width = total // 2
        remaining = total - route_width
        source_width = remaining // 2
        type_width = remaining - source_width
        return route_width, source_width, type_width

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.sync_tree_columns()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.sync_tree_columns()

    def sync_tree_columns(self) -> None:
        width = self.routes_tree.viewport().width() or self.routes_tree.width() or 0
        route_width, source_width, type_width = self.compute_tree_column_widths(width)
        self.routes_tree.setColumnWidth(0, route_width)
        self.routes_tree.setColumnWidth(1, source_width)
        self.routes_tree.setColumnWidth(2, type_width)

    def update_record(self, record: dict) -> None:
        self.record = dict(record)
        self.refresh_state()

    def handle_state_changed(self, record_id: int, _state: dict) -> None:
        if int(record_id or 0) != int(self.record.get("id") or 0):
            return
        self.refresh_state()
        self.maybe_show_reconnect_failure_hint(_state)

    def refresh_state(self) -> None:
        self._state = self.route_service.state_for_record(self.record) if self.route_service is not None else {}
        state = self._state
        status = str(state.get("status") or "")
        current_route = str(state.get("current_route") or "")
        traversing_route = self.traversing_route_text(state)
        self.status_value.setText(self.status_text(status))
        self.current_route_value.setText(traversing_route or current_route or "-")
        self.message_value.setText(self.message_text(state))
        self.error_value.setText(str(state.get("error") or "-"))

        pages = state.get("pages") if isinstance(state.get("pages"), list) else []
        self.sync_route_tree(pages, current_route, traversing_route)

        self.sync_tree_columns()
        self.sync_guard_button(state)
        self.refresh_actions()

    def sync_route_tree(self, pages: list[dict], current_route: str, traversing_route: str = "") -> None:
        """同步路由树，并在遍历状态下高亮当前遍历项。"""
        selected_route = self.selected_route()
        if self._route_tree_matches_pages(pages):
            self.apply_traverse_highlight(traversing_route)
            if not selected_route and current_route:
                self._select_route(current_route)
            return

        vertical_scrollbar = self.routes_tree.verticalScrollBar()
        horizontal_scrollbar = self.routes_tree.horizontalScrollBar()
        previous_vertical = vertical_scrollbar.value()
        previous_horizontal = horizontal_scrollbar.value()
        selection_route = selected_route or current_route

        with QSignalBlocker(self.routes_tree):
            self.routes_tree.clear()
            for page in pages:
                source = str(page.get("source") or "main")
                item = QTreeWidgetItem(
                    [
                        str(page.get("route") or ""),
                        "主包" if source == "main" else "分包",
                        "标签页" if page.get("is_tabbar") else "普通页",
                    ]
                )
                if source != "main":
                    item.setToolTip(1, source)
                self.routes_tree.addTopLevelItem(item)

        if selection_route and not self._select_route(selection_route):
            self._select_route(current_route)
        self.apply_traverse_highlight(traversing_route)

        vertical_scrollbar.setValue(min(previous_vertical, vertical_scrollbar.maximum()))
        horizontal_scrollbar.setValue(min(previous_horizontal, horizontal_scrollbar.maximum()))

    def _route_tree_matches_pages(self, pages: list[dict]) -> bool:
        if self.routes_tree.topLevelItemCount() != len(pages):
            return False
        for index, page in enumerate(pages):
            item = self.routes_tree.topLevelItem(index)
            source = str(page.get("source") or "main")
            source_text = "主包" if source == "main" else "分包"
            type_text = "标签页" if page.get("is_tabbar") else "普通页"
            if item is None:
                return False
            if item.text(0) != str(page.get("route") or ""):
                return False
            if item.text(1) != source_text:
                return False
            if item.text(2) != type_text:
                return False
        return True

    def _select_route(self, route: str) -> bool:
        target_route = str(route or "").strip()
        if not target_route:
            return False
        for index in range(self.routes_tree.topLevelItemCount()):
            item = self.routes_tree.topLevelItem(index)
            if item is not None and item.text(0).strip() == target_route:
                self.routes_tree.setCurrentItem(item)
                return True
        return False

    def apply_traverse_highlight(self, route: str) -> None:
        """把正在遍历的路由项颜色加深，其他项恢复默认背景。"""
        target_route = str(route or "").strip().lstrip("/")
        highlight = QBrush(self.TRAVERSE_HIGHLIGHT_COLOR)
        highlight_text = QBrush(self.TRAVERSE_HIGHLIGHT_TEXT_COLOR)
        clear = QBrush()
        for index in range(self.routes_tree.topLevelItemCount()):
            item = self.routes_tree.topLevelItem(index)
            if item is None:
                continue
            is_target = bool(target_route) and item.text(0).strip().lstrip("/") == target_route
            brush = highlight if is_target else clear
            text_brush = highlight_text if is_target else clear
            for column in range(self.routes_tree.columnCount()):
                item.setBackground(column, brush)
                item.setForeground(column, text_brush)

    def refresh_actions(self) -> None:
        state = self._state if isinstance(self._state, dict) else {}
        attached = bool(state.get("attached"))
        status = str(state.get("status") or "")
        busy = status in {"starting", "refreshing", "executing"}
        traversing = status == "traversing"
        selected_route = self.selected_route()
        has_pages = bool(state.get("pages"))
        enabled = self.route_service is not None
        interruptible = traversing and attached

        self.start_button.setEnabled(enabled and (interruptible or not busy))
        self.refresh_button.setEnabled(enabled and (interruptible or not busy))
        self.traverse_button.setEnabled(enabled and attached and has_pages and not busy and not traversing)
        self.traverse_from_button.setEnabled(
            enabled and attached and has_pages and bool(selected_route) and not busy and not traversing
        )
        self.guard_button.setEnabled(enabled and attached and (interruptible or not busy))
        self.back_button.setEnabled(enabled and attached and (interruptible or not busy))

        action_enabled = enabled and attached and bool(selected_route) and (interruptible or not busy)
        self.navigate_to_button.setEnabled(action_enabled)
        self.redirect_to_button.setEnabled(action_enabled)
        self.relaunch_button.setEnabled(action_enabled)

    def sync_guard_button(self, state: dict) -> None:
        enabled = bool(state.get("guard_enabled"))
        self.guard_button.blockSignals(True)
        self.guard_button.setChecked(enabled)
        self.guard_button.setText("防跳转：已开启" if enabled else "防跳转：已关闭")
        self.guard_button.blockSignals(False)

    def status_text(self, status: str) -> str:
        return self.STATUS_TEXT.get(status, status or "-")

    def guard_text(self, state: dict) -> str:
        if not bool(state.get("guard_enabled")):
            return "已关闭"
        blocked_count = int(state.get("blocked_redirects_count") or 0)
        if blocked_count > 0:
            return f"已开启（已拦截 {blocked_count} 次）"
        return "已开启"

    def message_text(self, state: dict) -> str:
        message = str(state.get("message") or "")
        last_action = str(state.get("last_action") or "")
        if message:
            return message
        if last_action:
            return f"{self.ACTION_TEXT.get(last_action, last_action)}已完成"
        return "-"

    def traversing_route_text(self, state: dict) -> str:
        """仅在遍历状态下返回当前正在尝试访问的目标路由。"""
        if str(state.get("status") or "") != "traversing":
            return ""
        return str(state.get("traversing_route") or "").strip()

    def selected_route(self) -> str:
        item = self.routes_tree.currentItem()
        if item is None:
            return ""
        return item.text(0).strip()

    def start_route(self) -> None:
        if not self.ensure_miniapp_connected():
            return
        if self.route_service is not None:
            self.route_service.start_route(self.record)

    def refresh_routes(self) -> None:
        if not self.ensure_miniapp_connected():
            return
        if self.route_service is not None:
            self.route_service.refresh_routes(self.record)

    def traverse_routes(self) -> None:
        if not self.ensure_miniapp_connected():
            return
        if self.route_service is not None:
            self.route_service.traverse_routes(self.record)

    def traverse_from_selected_route(self) -> None:
        """从路由树当前选中项开始遍历全部后续路由。"""
        if not self.ensure_miniapp_connected():
            return
        route = self.selected_route()
        if not route or self.route_service is None:
            return
        self.route_service.traverse_routes(self.record, start_route=route)

    def toggle_guard(self, enabled: bool) -> None:
        if not self.ensure_miniapp_connected():
            self.sync_guard_button(self._state if isinstance(self._state, dict) else {})
            return
        if self.route_service is not None:
            self.route_service.toggle_guard(self.record, bool(enabled))

    def navigate_back(self) -> None:
        if not self.ensure_miniapp_connected():
            return
        if self.route_service is not None:
            self.route_service.navigate_back(self.record, delta=1)

    def execute_action(self, action: str) -> None:
        if not self.ensure_miniapp_connected():
            return
        route = self.selected_route()
        if not route or self.route_service is None:
            return
        self.route_service.execute_action(self.record, action, route)

    def ensure_miniapp_connected(self) -> bool:
        """需要小程序已回连的操作执行前进行轻量检查。"""
        if self.route_service is None or not hasattr(self.route_service, "miniapp_connected_for_record"):
            return True
        if self.route_service.miniapp_connected_for_record(self.record):
            return True
        self.show_reconnect_hint()
        return False

    def maybe_show_reconnect_failure_hint(self, state: dict) -> None:
        """启动或执行路由异步失败且原因是未回连时，只提示一次重启小程序。"""
        if not self.is_reconnect_failure_state(state):
            self._last_reconnect_failure_signature = None
            return
        signature = (str(state.get("message") or ""), str(state.get("error") or ""))
        if signature == self._last_reconnect_failure_signature:
            return
        self._last_reconnect_failure_signature = signature
        self.show_reconnect_hint()

    @classmethod
    def is_reconnect_failure_state(cls, state: dict) -> bool:
        """判断路由失败状态是否由小程序未回连导致。"""
        if not isinstance(state, dict) or str(state.get("status") or "") != "failed":
            return False
        combined = f"{state.get('message') or ''}\n{state.get('error') or ''}"
        return any(marker in combined for marker in cls.RECONNECT_FAILURE_MARKERS)

    def show_reconnect_hint(self) -> None:
        """显示小程序未回连提示。"""
        show_miniapp_reconnect_hint(self)

    def shutdown_worker(self) -> None:
        if self.route_service is not None:
            self.route_service.cancel_record(self.record)
