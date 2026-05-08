"""Helpers for mini program route state snapshots."""

from __future__ import annotations

import copy


def default_route_state(
    *,
    record_id: int = 0,
    owner_key: str = "",
    display_name: str = "",
    worker_alive: bool = False,
    message: str = "未启动路由",
) -> dict:
    """Create a fresh route-state snapshot."""
    return {
        "record_id": int(record_id or 0),
        "owner_key": str(owner_key or ""),
        "display_name": str(display_name or ""),
        "status": "stopped",
        "worker_alive": bool(worker_alive),
        "attached": False,
        "current_route": "",
        "traversing_route": "",
        "pages": [],
        "tabbar_pages": [],
        "last_action": "",
        "guard_enabled": False,
        "blocked_redirects_count": 0,
        "message": str(message or ""),
        "error": "",
    }


def copy_route_state(state: dict) -> dict:
    """Return a deep copy so UI code never shares mutable route state."""
    return copy.deepcopy(state if isinstance(state, dict) else default_route_state())
