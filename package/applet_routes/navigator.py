"""Mini program route JS injection and action helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

_NAV_JS_PATH = Path(__file__).with_name("nav_inject.js")
_NAV_JS_CACHE: str | None = None


def read_nav_js() -> str:
    """在线程中读取路由注入脚本，避免模块导入时阻塞主线程。"""
    return _NAV_JS_PATH.read_text(encoding="utf-8")


async def load_nav_js() -> str:
    """异步懒加载路由注入脚本，复用进程内缓存。"""
    global _NAV_JS_CACHE
    if _NAV_JS_CACHE is None:
        _NAV_JS_CACHE = await asyncio.to_thread(read_nav_js)
    return _NAV_JS_CACHE


class MiniProgramRouteNavigator:
    """Encapsulate route-script injection, route reads, and route actions."""

    def __init__(self, bridge) -> None:
        self.bridge = bridge
        self._injected = False

    async def ensure_injected(self, force: bool = False) -> None:
        """确保路由辅助脚本已经注入到小程序运行环境。"""
        if force or not self._injected:
            await self.bridge.evaluate_js(await load_nav_js(), timeout=10.0)
            self._injected = True

    async def fetch_routes(self) -> dict:
        """读取路由配置和当前路由，页面切换后强制重新确认注入。"""
        await self.ensure_injected(force=True)
        result = await self.bridge.evaluate_js("window.__routeNavigator.fetchConfigJson()", timeout=5.0)
        payload = self._load_json_response(result)
        return {
            "pages": [self._normalize_page(page) for page in payload.get("pages", [])],
            "tabbar_pages": [str(item) for item in payload.get("tabBarPages", [])],
            "current_route": str(payload.get("currentRoute") or ""),
            "guard_enabled": bool(payload.get("guardEnabled")),
            "blocked_redirects_count": int(payload.get("blockedRedirectsCount") or 0),
        }

    async def navigate_to(self, route: str) -> dict:
        return await self._run_action("navigateToJson", route=route)

    async def switch_tab(self, route: str) -> dict:
        return await self._run_action("switchTabJson", route=route)

    async def redirect_to(self, route: str) -> dict:
        return await self._run_action("redirectToJson", route=route)

    async def relaunch(self, route: str) -> dict:
        return await self._run_action("reLaunchJson", route=route)

    async def navigate_back(self, delta: int = 1) -> dict:
        return await self._run_action("navigateBackJson", delta=int(delta or 1))

    async def enable_redirect_guard(self) -> dict:
        return await self._run_action("enableRedirectGuardJson")

    async def disable_redirect_guard(self) -> dict:
        return await self._run_action("disableRedirectGuardJson")

    async def visit_route(self, route: str, *, is_tabbar: bool = False) -> dict:
        if is_tabbar:
            return await self.switch_tab(route)
        return await self.relaunch(route)

    async def _run_action(self, method_name: str, *, route: str = "", delta: int = 1) -> dict:
        """执行路由动作，每次动作前重新注入以适配页面上下文切换。"""
        await self.ensure_injected(force=True)
        expression = (
            f"window.__routeNavigator.{method_name}("
            f"{json.dumps(str(route or '').lstrip('/'))}, {int(delta or 1)})"
        )
        result = await self.bridge.send_cdp_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=5.0,
        )
        return self._load_json_response(result)

    @staticmethod
    def _normalize_page(page: dict) -> dict:
        return {
            "route": str(page.get("route") or ""),
            "source": str(page.get("source") or "main"),
            "is_tabbar": bool(page.get("isTabBar")),
        }

    def _load_json_response(self, result: dict) -> dict:
        value = self._extract_value(result)
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        return json.loads(value)

    @staticmethod
    def _extract_value(result: dict):
        if not isinstance(result, dict):
            return None
        return result.get("result", {}).get("result", {}).get("value")
