"""保存应用默认路径、功能开关和主界面模块定义。"""

import math
from pathlib import Path

from package.regex_rules.presets import copy_default_regex_rules


CONTROL_DEFS = [
    ("decompile", "反编译源代码"),
    ("optimize_code", "是否优化代码"),
    ("config", "Config 配置"),
    ("regex", "正则规则"),
    ("crypto", "加密解密"),
]

ACTION_MODULE_KEYS = {"config", "regex", "crypto"}

DEFAULT_APPLET_PACKAGES_PATH = str(
    Path.home() / "AppData" / "Roaming" / "Tencent" / "xwechat" / "radium" / "Applet" / "packages"
)
DEFAULT_CLOUD_CALL_TIMEOUT_SECONDS = 5
MIN_CLOUD_CALL_TIMEOUT_SECONDS = 1
MAX_CLOUD_CALL_TIMEOUT_SECONDS = 120


def normalize_cloud_call_timeout(
    value,
    *,
    minimum: float = MIN_CLOUD_CALL_TIMEOUT_SECONDS,
    maximum: float = MAX_CLOUD_CALL_TIMEOUT_SECONDS,
):
    """把云函数调用超时时间归一到安全范围。"""
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = float(DEFAULT_CLOUD_CALL_TIMEOUT_SECONDS)
    if not math.isfinite(timeout):
        timeout = float(DEFAULT_CLOUD_CALL_TIMEOUT_SECONDS)
    bounded = min(max(timeout, float(minimum)), float(maximum))
    if bounded.is_integer():
        return int(bounded)
    return round(bounded, 3)

DEFAULT_STATE = {
    "toggles": {
        "decompile": False,
        "optimize_code": False,
        "cloud": False,
        "hook": False,
    },
    "config": {
        "applet_packages_path": DEFAULT_APPLET_PACKAGES_PATH,
        "cloud_call_timeout_seconds": DEFAULT_CLOUD_CALL_TIMEOUT_SECONDS,
    },
    "rules": copy_default_regex_rules(),
    "log_settings": {
        "records": {},
    },
    "global_search": {
        "records": {},
    },
}
