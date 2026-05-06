"""Route-page service proxy backed by the shared DevTools service."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from package.applet_detail.reconnect_hint import needs_miniapp_reconnect_hint


class RouteService(QObject):
    """Forward route-page commands to the shared DevTools service."""

    state_changed = Signal(int, dict)

    def __init__(self, devtools_service, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.devtools_service = devtools_service
        if self.devtools_service is not None and hasattr(self.devtools_service, "route_state_changed"):
            self.devtools_service.route_state_changed.connect(self.state_changed.emit)

    def state_for_record(self, record: dict) -> dict:
        """返回指定小程序卡片的路由状态。"""
        if self.devtools_service is None:
            return {}
        return self.devtools_service.route_state_for_record(record)

    def miniapp_connected_for_record(self, record: dict) -> bool:
        """判断当前卡片对应的小程序是否已经回连。"""
        if self.devtools_service is None or not hasattr(self.devtools_service, "state_for_record"):
            return True
        state = self.devtools_service.state_for_record(record)
        if not isinstance(state, dict):
            return True
        return not needs_miniapp_reconnect_hint(state)

    def start_route(self, record: dict) -> None:
        """请求共享 DevTools 服务启动并接管路由。"""
        if self.devtools_service is not None:
            self.devtools_service.start_route(record)

    def refresh_routes(self, record: dict) -> None:
        """请求刷新当前小程序路由列表。"""
        if self.devtools_service is not None:
            self.devtools_service.refresh_routes(record)

    def execute_action(self, record: dict, action: str, route: str) -> None:
        """请求执行指定路由跳转动作。"""
        if self.devtools_service is not None:
            self.devtools_service.execute_route_action(record, action, route)

    def navigate_back(self, record: dict, delta: int = 1) -> None:
        """请求当前小程序返回上一页。"""
        if self.devtools_service is not None:
            self.devtools_service.navigate_back_route(record, delta=delta)

    def traverse_routes(self, record: dict) -> None:
        """请求遍历当前小程序全部路由。"""
        if self.devtools_service is not None:
            self.devtools_service.traverse_routes(record)

    def toggle_guard(self, record: dict, enabled: bool) -> None:
        """请求开启或关闭当前小程序防跳转。"""
        if self.devtools_service is not None:
            self.devtools_service.toggle_route_guard(record, enabled)

    def cancel_record(self, record: dict | int) -> None:
        if self.devtools_service is not None:
            self.devtools_service.cancel_route(record)

    def shutdown(self) -> None:
        return None
