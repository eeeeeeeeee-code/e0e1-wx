"""维护反编译详情页全局搜索状态的默认值与归一化逻辑。"""

from __future__ import annotations


def default_global_search_state() -> dict:
    """返回全局搜索状态的默认结构。"""
    return {
        "query": "",
        "regex_enabled": False,
        "results": [],
        "selected_result": {},
        "status_message": "",
        "last_output_dirs_signature": [],
    }


def normalize_global_search_state(state) -> dict:
    """把任意输入归一化为可持久化的全局搜索状态。"""
    payload = state if isinstance(state, dict) else {}
    normalized = default_global_search_state()
    normalized["query"] = str(payload.get("query") or "").strip()
    normalized["regex_enabled"] = bool(payload.get("regex_enabled"))
    normalized["results"] = [dict(item) for item in payload.get("results", []) if isinstance(item, dict)]
    selected_result = payload.get("selected_result")
    normalized["selected_result"] = dict(selected_result) if isinstance(selected_result, dict) else {}
    normalized["status_message"] = str(payload.get("status_message") or "").strip()
    signature = payload.get("last_output_dirs_signature")
    if isinstance(signature, list):
        normalized["last_output_dirs_signature"] = [str(item or "").strip() for item in signature if str(item or "").strip()]
    return normalized
