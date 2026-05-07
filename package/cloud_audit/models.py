"""定义云审计模块共享的数据模型、状态快照和模板辅助函数。"""

from __future__ import annotations

import copy
import json


SOURCE_LABELS = {
    "dynamic": "动态",
    "static": "静态",
}

TYPE_LABELS = {
    "function": "云函数",
    "storage": "云存储",
    "container": "云托管",
    "database": "云数据库",
}


def default_cloud_state(*, worker_alive: bool = False, message: str = "未启动云函数审计") -> dict:
    """创建新的云审计状态快照。"""
    return {
        "status": "stopped",
        "worker_alive": bool(worker_alive),
        "owner_key": "",
        "display_name": "",
        "record_id": 0,
        "enabled": False,
        "captured_count": 0,
        "message": message,
        "error": "",
    }


def copy_cloud_state(state: dict) -> dict:
    """返回云审计状态快照的深拷贝。"""
    return copy.deepcopy(state if isinstance(state, dict) else default_cloud_state())


def source_label(source: str) -> str:
    """把来源标识转换成界面展示文案。"""
    return SOURCE_LABELS.get(str(source or ""), str(source or "") or "-")


def type_label(entry_type: str) -> str:
    """把记录类型转换成界面展示文案。"""
    text = str(entry_type or "").strip()
    if not text:
        return "-"
    if text.startswith("db"):
        return TYPE_LABELS["database"]
    return TYPE_LABELS.get(text, text)


def build_static_template(params: list[str] | tuple[str, ...] | None) -> dict:
    """根据静态扫描出的参数名生成默认调用模板。"""
    template: dict[str, str] = {}
    for name in params or []:
        field_name = str(name or "").strip()
        if field_name and field_name not in template:
            template[field_name] = ""
    return template


def format_json_text(payload) -> str:
    """把任意 JSON 兼容对象格式化为可编辑文本。"""
    if payload in (None, ""):
        return "{}"
    if isinstance(payload, str):
        text = payload.strip()
        return text or "{}"
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def entry_template(entry: dict) -> dict:
    """根据扫描记录生成手动调用页面使用的参数模板。"""
    if not isinstance(entry, dict):
        return {}
    if str(entry.get("source") or "") == "dynamic":
        data = entry.get("data")
        if isinstance(data, dict):
            return copy.deepcopy(data)
    return build_static_template(entry.get("params") if isinstance(entry.get("params"), list) else [])


def normalize_dynamic_call(call: dict) -> dict:
    """把动态 Hook 原始记录转换为统一的云审计行结构。"""
    data = call.get("data") if isinstance(call.get("data"), dict) else {}
    params = [str(key) for key in data.keys()]
    return {
        "source": "dynamic",
        "source_label": source_label("dynamic"),
        "type": str(call.get("type") or "function"),
        "type_label": type_label(str(call.get("type") or "function")),
        "name": str(call.get("name") or ""),
        "app_id": str(call.get("appId") or ""),
        "params": params,
        "data": copy.deepcopy(data),
        "status": str(call.get("status") or ""),
        "timestamp": str(call.get("timestamp") or ""),
        "count": 1,
        "callable": str(call.get("type") or "function") == "function",
        "result": copy.deepcopy(call.get("result")),
        "error": copy.deepcopy(call.get("error")),
        "raw": copy.deepcopy(call),
    }


def normalize_static_entry(entry: dict) -> dict:
    """把静态扫描结果转换为统一的云审计行结构。"""
    params = [str(name) for name in entry.get("params", []) if str(name or "").strip()]
    return {
        "source": "static",
        "source_label": source_label("static"),
        "type": str(entry.get("type") or "function"),
        "type_label": type_label(str(entry.get("type") or "function")),
        "name": str(entry.get("name") or ""),
        "app_id": str(entry.get("appId") or ""),
        "params": params,
        "data": build_static_template(params),
        "status": f"x{int(entry.get('count') or 1)}",
        "timestamp": "",
        "count": int(entry.get("count") or 1),
        "callable": str(entry.get("type") or "function") == "function",
        "files": [str(path) for path in entry.get("files", []) if str(path or "").strip()],
        "raw": copy.deepcopy(entry),
    }


def build_report_payload(items: list[dict], call_history: list[dict] | None = None) -> dict:
    """把当前云审计界面数据整理成可导出的报告结构。"""
    return {
        "items": copy.deepcopy(items),
        "call_history": copy.deepcopy(call_history or []),
    }
