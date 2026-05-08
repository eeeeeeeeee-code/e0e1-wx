"""小程序跳转注入与执行封装。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

_JUMP_JS_PATH = Path(__file__).with_name("jump_inject.js")
_JUMP_JS_CACHE: str | None = None


def read_jump_js() -> str:
    """用 UTF-8 读取跳转注入脚本。"""
    return _JUMP_JS_PATH.read_text(encoding="utf-8")


async def load_jump_js() -> str:
    """异步懒加载跳转脚本，并复用进程内缓存。"""
    global _JUMP_JS_CACHE
    if _JUMP_JS_CACHE is None:
        _JUMP_JS_CACHE = await asyncio.to_thread(read_jump_js)
    return _JUMP_JS_CACHE


class MiniAppJumpNavigator:
    """管理跳转脚本注入、等待用户点击和结果轮询。"""

    @staticmethod
    def normalize_path(path: str) -> str:
        """归一化跨小程序跳转路径，统一去掉首尾空白和前导斜杠。"""
        return str(path or "").strip().lstrip("/")

    def __init__(
        self,
        bridge,
        *,
        poll_interval: float = 0.25,
        tap_timeout: float = 90.0,
        sleep_func=None,
    ) -> None:
        """保存 bridge 引用，并初始化注入状态与轮询参数。"""
        self.bridge = bridge
        self._injected = False
        self.poll_interval = max(0.0, float(poll_interval))
        self.tap_timeout = max(0.5, float(tap_timeout))
        self.sleep_func = sleep_func or asyncio.sleep

    async def ensure_injected(self, force: bool = False) -> None:
        """确保跳转脚本已注入到当前页面上下文。"""
        if force or not self._injected:
            await self.bridge.evaluate_js(await load_jump_js(), timeout=10.0)
            self._injected = True

    async def navigate_to_mini_program(self, appid: str, path: str = "") -> dict:
        """执行完整跳转流程，必要时等待用户在小程序内点击。"""
        appid_text = str(appid or "")
        path_text = self.normalize_path(path)
        prepared = await self.prepare_navigate_to_mini_program(appid_text, path_text)
        if str(prepared.get("status") or "") != "waiting_tap":
            return prepared
        return await self.wait_for_navigation_result(appid_text, path_text)

    async def prepare_navigate_to_mini_program(self, appid: str, path: str = "") -> dict:
        """准备悬浮跳转按钮，并返回当前等待状态。"""
        appid_text = str(appid or "")
        path_text = self.normalize_path(path)
        await self.ensure_injected()
        return await self._evaluate_json(
            "window.__miniappJumpNavigator.prepareNavigateToMiniProgramJson("
            f"{json.dumps(appid_text)}, {json.dumps(path_text)})",
            appid=appid_text,
            path=path_text,
        )

    async def poll_navigation_result(self, appid: str, path: str = "") -> dict:
        """读取当前跳转状态，供后台轮询等待最终结果。"""
        appid_text = str(appid or "")
        path_text = self.normalize_path(path)
        await self.ensure_injected()
        return await self._evaluate_json(
            "window.__miniappJumpNavigator.pollNavigationResultJson()",
            appid=appid_text,
            path=path_text,
        )

    async def wait_for_navigation_result(self, appid: str, path: str = "") -> dict:
        """等待用户点击悬浮按钮后的最终跳转结果。"""
        appid_text = str(appid or "")
        path_text = self.normalize_path(path)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.tap_timeout
        while True:
            result = await self.poll_navigation_result(appid_text, path_text)
            if str(result.get("status") or "") != "waiting_tap":
                return result
            if loop.time() >= deadline:
                try:
                    await self.cancel_pending_navigation(appid_text, path_text)
                except Exception:
                    pass
                return self._timeout_result(appid_text, path_text)
            await self.sleep_func(self.poll_interval)

    async def cancel_pending_navigation(self, appid: str = "", path: str = "") -> dict:
        """取消当前待点击的跳转悬浮层，并返回取消结果。"""
        appid_text = str(appid or "")
        path_text = self.normalize_path(path)
        await self.ensure_injected()
        return await self._evaluate_json(
            "window.__miniappJumpNavigator.cancelPendingNavigationJson()",
            appid=appid_text,
            path=path_text,
        )

    async def _evaluate_json(self, expression: str, *, appid: str = "", path: str = "") -> dict:
        """执行返回 JSON 字符串的表达式，并解析为字典。"""
        result = await self.bridge.send_cdp_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=5.0,
        )
        return self._load_json_response(result, appid=appid, path=path)

    def _load_json_response(self, result: dict, *, appid: str = "", path: str = "") -> dict:
        """将 CDP 返回值安全解析为 Python 字典。"""
        value = self._extract_value(result)
        if isinstance(value, dict):
            return value
        if not value:
            return self._failure_result(appid, path, "invalid cdp result")
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._failure_result(appid, path, "invalid json result")
        if isinstance(parsed, dict):
            parsed.setdefault("path", self.normalize_path(path))
            return parsed
        return self._failure_result(appid, path, "invalid json result")

    @staticmethod
    def _extract_value(result: dict):
        """从 Runtime.evaluate 结果中提取 value 字段。"""
        if not isinstance(result, dict):
            return None
        outer = result.get("result")
        if not isinstance(outer, dict):
            return None
        inner = outer.get("result")
        if not isinstance(inner, dict):
            return None
        return inner.get("value")

    @staticmethod
    def _failure_result(appid: str, path: str, error: str) -> dict:
        """构造统一的失败结果，避免把错误静默压成空字典。"""
        return {
            "ok": False,
            "action": "navigate_to_mini_program",
            "appId": str(appid or ""),
            "path": MiniAppJumpNavigator.normalize_path(path),
            "error": str(error or "unknown error"),
        }

    @staticmethod
    def _timeout_result(appid: str, path: str) -> dict:
        """构造等待用户点击超时后的统一返回结果。"""
        return {
            "ok": False,
            "status": "waiting_tap_timeout",
            "action": "navigate_to_mini_program",
            "appId": str(appid or ""),
            "path": MiniAppJumpNavigator.normalize_path(path),
            "message": "等待在小程序内点击跳转按钮超时",
            "error": "wait for tap timeout",
        }
