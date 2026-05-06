"""Stable record identity helpers for global devtools sessions."""

from __future__ import annotations

from package.decompiler.core import normalize_new_folder_names


def record_new_folders(record: dict) -> list[str]:
    """Extract stable folder names from a monitor record."""
    raw_list = record.get("wxids_list")
    if isinstance(raw_list, list):
        return normalize_new_folder_names([str(item) for item in raw_list])
    display = str(record.get("wxids_display") or "").strip()
    if display:
        return normalize_new_folder_names([part.strip() for part in display.split(",")])
    return normalize_new_folder_names([str(record.get("wxid") or "")])


def record_owner_key(record: dict) -> str:
    """Return a stable ownership key for a monitor record."""
    folders = record_new_folders(record)
    if folders:
        return "|".join(folders)
    wxid = str(record.get("wxid") or "").strip()
    if wxid:
        return wxid
    record_id = int(record.get("id") or 0)
    return str(record_id) if record_id > 0 else ""


def record_display_name(record: dict) -> str:
    """Return the UI display name for a monitor record."""
    text = str(record.get("name") or record.get("window_title") or "").strip()
    if text:
        return text
    owner = record_owner_key(record)
    return owner or "当前小程序"
