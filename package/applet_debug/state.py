"""调试开关状态快照工具。"""

from __future__ import annotations

import copy


VALID_DEBUG_TOGGLE_STATUS = {
    "idle",
    "enabling",
    "disabling",
    "failed",
}
TRUE_BOOL_TEXT = {"1", "true", "yes", "on"}
FALSE_BOOL_TEXT = {"0", "false", "no", "off", ""}


def _safe_int(value, default: int = 0) -> int:
    """把任意值安全转换为整数，失败时回退到默认值。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return int(default or 0)


def _normalize_bool(value) -> bool:
    """把常见布尔输入安全归一化，避免字符串假值被误判成真。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in TRUE_BOOL_TEXT:
            return True
        if text in FALSE_BOOL_TEXT:
            return False
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def default_debug_toggle_state(
    *,
    record_id: int = 0,
    owner_key: str = "",
    display_name: str = "",
    worker_alive: bool = False,
    status: str = "idle",
    debug_enabled: bool = False,
    vconsole_visible: bool = False,
    message: str = "",
    error: str = "",
    last_action: str = "",
) -> dict:
    """创建一份新的调试开关状态默认快照。"""
    return normalize_debug_toggle_state(
        {
            "record_id": record_id,
            "owner_key": owner_key,
            "display_name": display_name,
            "worker_alive": worker_alive,
            "status": status,
            "debug_enabled": debug_enabled,
            "vconsole_visible": vconsole_visible,
            "message": message,
            "error": error,
            "last_action": last_action,
        }
    )


def normalize_debug_toggle_state(state: dict | None) -> dict:
    """把任意输入整理成合法且字段完整的调试开关状态。"""
    payload = state if isinstance(state, dict) else {}
    status = str(payload.get("status") or "").strip()
    last_action = payload.get("last_action")
    return {
        "record_id": _safe_int(payload.get("record_id")),
        "owner_key": str(payload.get("owner_key") or ""),
        "display_name": str(payload.get("display_name") or ""),
        "worker_alive": _normalize_bool(payload.get("worker_alive")),
        "status": status if status in VALID_DEBUG_TOGGLE_STATUS else "idle",
        "debug_enabled": _normalize_bool(payload.get("debug_enabled")),
        "vconsole_visible": _normalize_bool(payload.get("vconsole_visible")),
        "message": str(payload.get("message") or ""),
        "error": str(payload.get("error") or ""),
        "last_action": str(last_action).strip() if isinstance(last_action, str) else "",
    }


def copy_debug_toggle_state(state: dict | None) -> dict:
    """复制已有状态快照；仅负责深拷贝，不负责重新规范化传入内容。"""
    if isinstance(state, dict):
        return copy.deepcopy(state)
    return copy.deepcopy(default_debug_toggle_state())
