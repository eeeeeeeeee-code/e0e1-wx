"""Route worker 与调试引擎之间的桥接层。"""

from __future__ import annotations

import contextlib

from package.devtools.bridge import BridgeOptions, WorkerLogger
from package.devtools.constants import DEBUG_PORT
from package.devtools.engine import DebugEngine
from package.devtools.worker import find_available_cdp_port


class RealRouteEngineBridge:
    """封装 Route worker 对底层 DebugEngine 的启动与调用。"""

    def __init__(self) -> None:
        """初始化 bridge，并延迟创建调试引擎。"""
        self.engine = None

    async def start(self) -> None:
        """启动底层调试引擎，供路由任务执行 JS 注入与跳转。"""
        options = BridgeOptions(cdp_port=find_available_cdp_port(), debug_port=DEBUG_PORT)
        engine = DebugEngine(options, WorkerLogger())
        try:
            await engine.start()
        except Exception:
            with contextlib.suppress(Exception):
                await engine.stop()
            raise
        self.engine = engine

    async def stop(self) -> None:
        """停止当前调试引擎并释放端口资源。"""
        engine = self.engine
        self.engine = None
        if engine is not None:
            await engine.stop()

    async def evaluate_js(self, expression: str, timeout: float = 5.0):
        """执行普通的 Runtime.evaluate 表达式。"""
        if self.engine is None:
            raise RuntimeError("route bridge not started")
        return await self.engine.evaluate_js(expression, timeout=timeout)

    async def send_cdp_command(self, method: str, params: dict | None = None, timeout: float = 5.0):
        """发送任意 CDP 命令到当前小程序上下文。"""
        if self.engine is None:
            raise RuntimeError("route bridge not started")
        return await self.engine.send_cdp_command(method, params=params, timeout=timeout)
