"""Mini program route JS injection and action helpers."""

from __future__ import annotations

import json
from pathlib import Path

_NAV_JS = Path(__file__).with_name("nav_inject.js").read_text(encoding="utf-8")


class MiniProgramRouteNavigator:
    """Encapsulate route-script injection, route reads, and route actions."""

    def __init__(self, bridge) -> None:
        self.bridge = bridge
        self._injected = False

    async def ensure_injected(self, force: bool = False) -> None:
        if force or not self._injected:
            await self.bridge.evaluate_js(_NAV_JS, timeout=10.0)
            self._injected = True

    async def fetch_routes(self) -> dict:
        await self.ensure_injected()
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
        await self.ensure_injected()
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
