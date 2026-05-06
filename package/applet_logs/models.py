"""定义小程序卡片日志来源、级别、设置和内存缓冲。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


LOG_SOURCE_DEFS = [
    ("devtools_cdp", "devtools-cdp"),
    ("routes", "小程序路由"),
    ("decompile_folder", "反编译文件夹"),
    ("cloud_functions", "云函数"),
    ("debug_toggle", "调试开关"),
]
LOG_SOURCE_KEYS = tuple(key for key, _label in LOG_SOURCE_DEFS)
LOG_SOURCE_LABELS = dict(LOG_SOURCE_DEFS)
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
LOG_LEVEL_WEIGHTS = {level: index for index, level in enumerate(LOG_LEVELS)}


@dataclass(frozen=True)
class LogEntry:
    """表示一条属于指定小程序和功能点的日志。"""

    record_key: str
    source: str
    level: str
    message: str
    created_at: float = field(default_factory=time.time)


def default_log_settings() -> dict:
    """返回日志页的安全默认设置。"""
    return {"enabled_sources": [], "level": "INFO"}


def normalize_log_level(value) -> str:
    """把任意输入归一化为合法日志级别。"""
    level = str(value or "").strip().upper()
    return level if level in LOG_LEVEL_WEIGHTS else "INFO"


def normalize_log_settings(settings) -> dict:
    """过滤日志设置中的未知功能点和非法级别。"""
    if not isinstance(settings, dict):
        return default_log_settings()
    raw_sources = settings.get("enabled_sources")
    enabled_raw = raw_sources if isinstance(raw_sources, list) else []
    enabled_set = {str(item).strip() for item in enabled_raw}
    enabled_sources = [key for key in LOG_SOURCE_KEYS if key in enabled_set]
    return {
        "enabled_sources": enabled_sources,
        "level": normalize_log_level(settings.get("level")),
    }


def log_record_key(record: dict) -> str:
    """生成日志设置和日志缓冲使用的小程序记录键。"""
    record_id = str(record.get("id") or "").strip()
    if record_id and record_id != "0":
        return record_id
    wxid = str(record.get("wxids_display") or record.get("wxid") or "").strip()
    return wxid or "unknown"


def log_level_weight(level) -> int:
    """返回日志级别权重，非法级别按 INFO 处理。"""
    return LOG_LEVEL_WEIGHTS[normalize_log_level(level)]


def filter_log_entries(entries, settings: dict, record_key: str | None = None) -> list[LogEntry]:
    """按小程序记录、功能点和最低级别过滤日志。"""
    normalized = normalize_log_settings(settings)
    enabled_sources = set(normalized["enabled_sources"])
    if not enabled_sources:
        return []
    minimum_weight = log_level_weight(normalized["level"])
    filtered: list[LogEntry] = []
    for entry in entries:
        if not isinstance(entry, LogEntry):
            continue
        if record_key is not None and entry.record_key != str(record_key):
            continue
        if entry.source not in enabled_sources:
            continue
        if log_level_weight(entry.level) < minimum_weight:
            continue
        filtered.append(entry)
    return filtered


def format_log_entry(entry: LogEntry) -> str:
    """把日志条目格式化为日志页展示文本。"""
    timestamp = time.strftime("%H:%M:%S", time.localtime(float(entry.created_at or 0.0)))
    source_label = LOG_SOURCE_LABELS.get(entry.source, entry.source)
    return f"[{timestamp}] [{normalize_log_level(entry.level)}] [{source_label}] {entry.message}"


def log_entry_from_state(source: str, state: dict, fallback_message: str = "", record_key: str | None = None) -> LogEntry | None:
    """把功能状态快照转换为对应小程序的日志条目。"""
    if source not in LOG_SOURCE_KEYS or not isinstance(state, dict):
        return None
    key = str(record_key or state.get("record_id") or "").strip()
    if not key or key == "0":
        return None
    error_text = str(state.get("error") or "").strip()
    message = error_text or str(state.get("message") or fallback_message or "").strip()
    if not message:
        return None
    status = str(state.get("status") or "").strip().lower()
    if error_text or status in {"failed", "error"}:
        level = "ERROR"
    elif status in {"cancelled", "cancelling", "stopping"}:
        level = "WARNING"
    else:
        level = "INFO"
    return LogEntry(record_key=key, source=source, level=level, message=message)


class LogStore:
    """保存每个小程序最近日志的进程内缓冲。"""

    def __init__(self, max_entries: int = 500) -> None:
        """初始化日志缓冲容量。"""
        self.max_entries = max(1, int(max_entries or 500))
        self._entries: dict[str, list[LogEntry]] = {}

    def append(self, entry: LogEntry) -> None:
        """追加一条日志并裁剪到最大容量。"""
        entries = self._entries.setdefault(str(entry.record_key), [])
        entries.append(entry)
        if len(entries) > self.max_entries:
            del entries[: len(entries) - self.max_entries]

    def entries(self, record_key: str) -> list[LogEntry]:
        """返回指定小程序的日志副本。"""
        return list(self._entries.get(str(record_key), []))

    def clear(self, record_key: str) -> None:
        """清空指定小程序的日志。"""
        self._entries.pop(str(record_key), None)
