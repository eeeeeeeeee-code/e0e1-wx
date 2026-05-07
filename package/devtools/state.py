"""Helpers for devtools session state snapshots."""

from __future__ import annotations

import copy

from package.devtools.constants import DEBUG_PORT


def build_devtools_link(port: int) -> str:
    """Return the devtools inspector URL for the given websocket port."""
    if int(port or 0) <= 0:
        return ""
    return f"devtools://devtools/bundled/inspector.html?ws=127.0.0.1:{int(port)}"


def default_state(*, worker_alive: bool = False, message: str = "未启动调试") -> dict:
    """Create a fresh devtools session snapshot."""
    return {
        "status": "stopped",
        "worker_alive": bool(worker_alive),
        "owner_key": "",
        "display_name": "",
        "record_id": 0,
        "debug_port": DEBUG_PORT,
        "cdp_port": 0,
        "link": "",
        "frida": False,
        "miniapp": False,
        "devtools": False,
        "message": message,
        "error": "",
    }


def copy_state(state: dict) -> dict:
    """Return a deep copy of a devtools state snapshot."""
    return copy.deepcopy(state if isinstance(state, dict) else default_state())
