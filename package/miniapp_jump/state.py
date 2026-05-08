"""跨小程序跳转任务的状态快照工具。"""

from __future__ import annotations

from typing import TypedDict


VALID_MINIAPP_JUMP_STATUS = {
    "stopped",
    "executing",
    "success",
    "failed",
    "cancelled",
}
TRUE_BOOL_TEXT = {"1", "true", "yes", "on"}
FALSE_BOOL_TEXT = {"0", "false", "no", "off", ""}


class MiniappJumpState(TypedDict):
    """定义跨小程序跳转状态的标准字段结构。"""

    record_id: int
    owner_key: str
    display_name: str
    worker_alive: bool
    status: str
    target_appid: str
    target_path: str
    last_action: str
    message: str
    error: str


def _safe_int(value, default: int = 0) -> int:
    """把输入安全转换为整数，失败时回退到默认值。"""
    try:
        if value is None:
            return int(default or 0)
        return int(value)
    except (TypeError, ValueError):
        return int(default or 0)


def _normalize_bool(value) -> bool:
    """把常见布尔输入统一归一化为真假值。"""
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


def _coerce_text(value, *, strip: bool = False) -> str:
    """把任意值安全转换为字符串。"""
    text = "" if value is None else str(value)
    return text.strip() if strip else text


def _build_miniapp_jump_state(
    *,
    record_id: int,
    owner_key: str,
    display_name: str,
    worker_alive: bool,
    status: str,
    target_appid: str,
    target_path: str,
    last_action: str,
    message: str,
    error: str,
) -> MiniappJumpState:
    """按统一字段顺序组装一份跳转状态快照。"""
    return {
        "record_id": record_id,
        "owner_key": owner_key,
        "display_name": display_name,
        "worker_alive": worker_alive,
        "status": status,
        "target_appid": target_appid,
        "target_path": target_path,
        "last_action": last_action,
        "message": message,
        "error": error,
    }


def default_miniapp_jump_state(
    *,
    record_id: int = 0,
    owner_key: str = "",
    display_name: str = "",
    worker_alive: bool = False,
    status: str = "stopped",
    target_appid: str = "",
    target_path: str = "",
    last_action: str = "",
    message: str = "未执行",
    error: str = "",
) -> MiniappJumpState:
    """创建一份新的跨小程序跳转状态默认快照。"""
    message_value = "未执行" if message is None else _coerce_text(message)
    return _build_miniapp_jump_state(
        record_id=_safe_int(record_id),
        owner_key=_coerce_text(owner_key),
        display_name=_coerce_text(display_name),
        worker_alive=_normalize_bool(worker_alive),
        status=status if status in VALID_MINIAPP_JUMP_STATUS else "stopped",
        target_appid=_coerce_text(target_appid),
        target_path=_coerce_text(target_path),
        last_action=_coerce_text(last_action, strip=True),
        message=message_value,
        error=_coerce_text(error),
    )


def normalize_miniapp_jump_state(state: dict | None) -> MiniappJumpState:
    """把任意输入整理成字段完整且类型安全的跳转状态。"""
    payload = state if isinstance(state, dict) else {}
    status = _coerce_text(payload.get("status"), strip=True)
    last_action = payload.get("last_action")
    message_value = payload.get("message") if "message" in payload else None
    message = "未执行" if message_value is None else _coerce_text(message_value)
    return _build_miniapp_jump_state(
        record_id=_safe_int(payload.get("record_id")),
        owner_key=_coerce_text(payload.get("owner_key")),
        display_name=_coerce_text(payload.get("display_name")),
        worker_alive=_normalize_bool(payload.get("worker_alive")),
        status=status if status in VALID_MINIAPP_JUMP_STATUS else "stopped",
        target_appid=_coerce_text(payload.get("target_appid")),
        target_path=_coerce_text(payload.get("target_path")),
        last_action=_coerce_text(last_action, strip=True),
        message=message,
        error=_coerce_text(payload.get("error")),
    )


def copy_miniapp_jump_state(state: dict | None) -> MiniappJumpState:
    """深拷贝跳转状态；输入无效时返回默认状态快照。"""
    if isinstance(state, dict):
        return normalize_miniapp_jump_state(state)
    return default_miniapp_jump_state()
