"""提供小程序未回连时的轻量 UI 提示工具。"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


MINIAPP_RECONNECT_MESSAGE = "当前小程序未回连，请重启小程序后再试。"


def devtools_session_started(state: dict) -> bool:
    """判断 DevTools 调试会话是否已经真正开启。"""
    if not isinstance(state, dict):
        return False
    if str(state.get("status") or "") == "running":
        return True
    try:
        if int(state.get("cdp_port") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    return bool(state.get("link"))


def needs_miniapp_reconnect_hint(state: dict) -> bool:
    """判断当前状态是否需要提示用户重启小程序。"""
    if not isinstance(state, dict):
        return False
    if not bool(state.get("worker_alive")):
        return False
    if state.get("owner_key") and not bool(state.get("current_record")):
        return False
    if not devtools_session_started(state):
        return False
    return not bool(state.get("miniapp"))


def service_needs_miniapp_reconnect_hint(service, record: dict) -> bool:
    """从共享调试服务读取当前卡片状态并判断是否未回连。"""
    if service is None or not hasattr(service, "state_for_record"):
        return False
    state = service.state_for_record(record)
    return needs_miniapp_reconnect_hint(state if isinstance(state, dict) else {})


def show_miniapp_reconnect_hint(parent: QWidget | None = None) -> None:
    """弹出小程序未回连提示。"""
    QMessageBox.information(parent, "小程序未回连", MINIAPP_RECONNECT_MESSAGE)
