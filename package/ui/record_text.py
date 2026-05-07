"""Helpers for rendering mini program monitor records."""

from __future__ import annotations


def mini_program_display_name(record: dict, fallback: str = "-") -> str:
    """Return the best available label without inventing an unknown app name."""
    for key in ("name", "window_title", "wxids_display", "wxid"):
        text = str(record.get(key) or "").strip()
        if text:
            return text
    return fallback
