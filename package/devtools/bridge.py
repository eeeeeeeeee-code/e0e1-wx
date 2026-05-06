"""Bridge abstractions used by the shared DevTools worker."""

from __future__ import annotations

import contextlib
import json
from typing import Callable, Protocol

from package.devtools.engine import DebugEngine, normalize_proxy_message


class EngineBridge(Protocol):
    """Protocol for the real or test bridge used by the worker."""

    async def start(
        self,
        session: dict,
        debug_port: int,
        cdp_port: int,
        status_callback: Callable[[dict], None],
    ) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def evaluate_js(self, expression: str, timeout: float = 5.0):
        ...

    async def send_cdp_command(self, method: str, params: dict | None = None, timeout: float = 5.0):
        ...

    def on_cdp_event(self, method: str, callback: Callable[[dict], None]) -> None:
        ...

    def off_cdp_event(self, method: str, callback: Callable[[dict], None]) -> None:
        ...


class WorkerLogger:
    """Minimal logger adapter for the background bridge."""

    def _emit(self, *messages) -> None:
        print(" ".join(str(message) for message in messages), flush=True)

    def info(self, *messages) -> None:
        self._emit(*messages)

    def error(self, *messages) -> None:
        self._emit(*messages)

    def warn(self, *messages) -> None:
        self._emit(*messages)

    def main_debug(self, *messages) -> None:
        return None

    def frida_debug(self, *messages) -> None:
        return None


def normalize_devtools_proxy_message(message: str) -> str:
    """Normalize pause-on-exception messages to the safe default."""
    return normalize_proxy_message(message)


class BridgeOptions:
    """Small option object for the embedded debug engine."""

    def __init__(self, cdp_port: int, debug_port: int) -> None:
        self.cdp_port = int(cdp_port)
        self.debug_port = int(debug_port)
        self.debug_main = False
        self.debug_frida = False
        self.scripts_dir = ""
        self.script_files: list[str] = []


class RealDebugEngineBridge:
    """Concrete bridge backed by the package-local debug engine."""

    def __init__(self) -> None:
        self.engine = None

    async def start(
        self,
        session: dict,
        debug_port: int,
        cdp_port: int,
        status_callback: Callable[[dict], None],
    ) -> None:
        del session
        options = BridgeOptions(cdp_port=cdp_port, debug_port=debug_port)
        engine = DebugEngine(options, WorkerLogger())
        engine.on_status_change(lambda state: status_callback(dict(state)))
        try:
            await engine.start()
        except Exception:
            with contextlib.suppress(Exception):
                await engine.stop()
            raise
        self.engine = engine
        status_callback(dict(engine.status))

    async def stop(self) -> None:
        engine = self.engine
        self.engine = None
        if engine is not None:
            await engine.stop()

    async def evaluate_js(self, expression: str, timeout: float = 5.0):
        if self.engine is None:
            raise RuntimeError("debug engine not started")
        return await self.engine.evaluate_js(expression, timeout=timeout)

    async def send_cdp_command(self, method: str, params: dict | None = None, timeout: float = 5.0):
        if self.engine is None:
            raise RuntimeError("debug engine not started")
        return await self.engine.send_cdp_command(method, params=params, timeout=timeout)

    def on_cdp_event(self, method: str, callback: Callable[[dict], None]) -> None:
        if self.engine is None:
            return
        self.engine.on_cdp_event(method, callback)

    def off_cdp_event(self, method: str, callback: Callable[[dict], None]) -> None:
        if self.engine is None:
            return
        self.engine.off_cdp_event(method, callback)
