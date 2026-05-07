"""Package-local devtools runtime engine."""

from __future__ import annotations

import asyncio
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from package.devtools.protocol_codec import wrap_debug_message_data, unwrap_debug_message_data
from package.devtools.protocol_userscript import (
    build_cdp_add_script_command,
    build_cdp_enable_page_command,
    build_injection_wrapper,
)
from package.devtools.third_party import wmpf_debug_pb2 as proto


class DebugMessageBus:
    """Bridge messages between the miniapp debug server and DevTools proxy."""

    def __init__(self) -> None:
        self._cdp_callbacks = []
        self._proxy_callbacks = []

    def on_cdp_message(self, callback) -> None:
        self._cdp_callbacks.append(callback)

    def on_proxy_message(self, callback) -> None:
        self._proxy_callbacks.append(callback)

    def emit_cdp_message(self, message: str) -> None:
        for callback in self._cdp_callbacks:
            callback(message)

    def emit_proxy_message(self, message: str) -> None:
        for callback in self._proxy_callbacks:
            callback(message)


def buffer_to_hex_string(data: bytes) -> str:
    return data.hex()


def workspace_root() -> Path:
    """Return the project root containing package/ and tools/."""
    return Path(__file__).resolve().parents[2]


def tools_root() -> Path:
    """Return the runtime tools directory containing hook/config assets."""
    return workspace_root() / "tools"


def normalize_proxy_message(message: str) -> str:
    """Force pause-on-exception requests into the safe default used by the UI."""
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return message
    if not isinstance(payload, dict):
        return message
    if str(payload.get("method") or "") != "Debugger.setPauseOnExceptions":
        return message
    normalized = dict(payload)
    normalized["params"] = {"state": "none"}
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _build_protobuf_cdp_message(cdp_json: str, seq: int) -> bytes:
    """Wrap a CDP JSON command into protobuf binary for the miniapp runtime."""
    raw_payload = {
        "jscontext_id": "",
        "op_id": round(100 * random.random()),
        "payload": cdp_json,
    }
    wrapped = wrap_debug_message_data(raw_payload, "chromeDevtools", 0)
    out_msg = proto.WARemoteDebug_DebugMessage()
    out_msg.seq = seq
    out_msg.category = "chromeDevtools"
    out_msg.data = wrapped["buffer"]
    out_msg.compressAlgo = 0
    out_msg.originalSize = wrapped["originalSize"]
    return out_msg.SerializeToString()


class DebugEngine:
    """Run the websocket servers and Frida injection required for devtools."""

    def __init__(self, options, logger, userscripts=None):
        self.options = options
        self.logger = logger
        self.bus = DebugMessageBus()
        self.userscripts = userscripts or []
        self.debug_srv = None
        self.proxy_srv = None
        self.frida_session = None
        self.frida_script = None
        self.miniapp_clients = set()
        self.devtools_clients = set()
        self.message_counter = 0
        self._pending_responses = {}
        self._cmd_counter = 80000
        self._status_callbacks = []
        self._event_listeners = {}
        self.status = {"frida": False, "miniapp": False, "devtools": False}

    def on_status_change(self, callback) -> None:
        self._status_callbacks.append(callback)

    def _notify_status(self, key, value) -> None:
        self.status[key] = value
        for callback in self._status_callbacks:
            try:
                callback(dict(self.status))
            except Exception:
                pass

    def _next_cmd_id(self) -> int:
        self._cmd_counter += 1
        return self._cmd_counter

    async def start(self) -> None:
        """Start the debug server, proxy server, and Frida hook."""
        self.debug_srv = await self._start_debug_server()
        self.proxy_srv = await self._start_proxy_server()
        try:
            self.frida_session, self.frida_script = await self._start_frida()
            self._notify_status("frida", True)
        except Exception as exc:
            self.logger.error(str(exc))
            raise

    async def stop(self) -> None:
        """Gracefully stop all runtime components and clear connection state."""
        if self.debug_srv:
            self.debug_srv.close()
            await self.debug_srv.wait_closed()
            self.debug_srv = None
        if self.proxy_srv:
            self.proxy_srv.close()
            await self.proxy_srv.wait_closed()
            self.proxy_srv = None
        if self.frida_script:
            try:
                self.frida_script.unload()
            except Exception:
                pass
            self.frida_script = None
        if self.frida_session:
            try:
                self.frida_session.detach()
            except Exception:
                pass
            self.frida_session = None
        self._notify_status("frida", False)
        self._notify_status("miniapp", False)
        self._notify_status("devtools", False)
        self.miniapp_clients.clear()
        self.devtools_clients.clear()
        self.message_counter = 0
        self._pending_responses.clear()
        self.logger.info("[server] engine stopped")

    async def evaluate_js(self, expression, timeout=5.0):
        """Send Runtime.evaluate via CDP and return the response dict."""
        if not self.miniapp_clients:
            raise RuntimeError("No miniapp client connected")
        cmd_id = self._next_cmd_id()
        cdp_cmd = json.dumps(
            {
                "id": cmd_id,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True},
            }
        )
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[cmd_id] = future
        self.bus.emit_proxy_message(cdp_cmd)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_responses.pop(cmd_id, None)
            raise

    async def send_cdp_command(self, method, params=None, timeout=5.0):
        """Send an arbitrary CDP command and return the response."""
        if not self.miniapp_clients:
            raise RuntimeError("No miniapp client connected")
        cmd_id = self._next_cmd_id()
        cdp_cmd = json.dumps({"id": cmd_id, "method": method, "params": params or {}})
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[cmd_id] = future
        self.bus.emit_proxy_message(cdp_cmd)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_responses.pop(cmd_id, None)
            raise

    async def set_extra_headers(self, headers: dict) -> None:
        """Enable the Network domain and attach extra request headers."""
        await self.send_cdp_command("Network.enable")
        await self.send_cdp_command("Network.setExtraHTTPHeaders", {"headers": headers})

    def on_cdp_event(self, method, callback) -> None:
        """Subscribe to a CDP event by method name."""
        self._event_listeners.setdefault(method, []).append(callback)

    def off_cdp_event(self, method, callback) -> None:
        """Unsubscribe from a CDP event."""
        callbacks = self._event_listeners.get(method, [])
        if callback in callbacks:
            callbacks.remove(callback)

    def _handle_cdp_response(self, message_str) -> None:
        """Dispatch CDP responses to pending callers or event listeners."""
        try:
            data = json.loads(message_str)
        except (json.JSONDecodeError, TypeError):
            return
        msg_id = data.get("id")
        if msg_id is not None and msg_id in self._pending_responses:
            future = self._pending_responses.pop(msg_id)
            if not future.done():
                future.set_result(data)
        method = data.get("method")
        if method and method in self._event_listeners:
            for callback in self._event_listeners[method]:
                try:
                    callback(data)
                except Exception:
                    pass

    async def _start_debug_server(self):
        import websockets.exceptions
        import websockets.server

        engine = self
        logger = self.logger
        bus = self.bus
        userscripts = self.userscripts
        scripts_injected = False

        def on_proxy_message(message: str) -> None:
            engine.message_counter += 1
            raw_payload = {
                "jscontext_id": "",
                "op_id": round(100 * random.random()),
                "payload": str(message),
            }
            logger.main_debug(raw_payload)
            wrapped = wrap_debug_message_data(raw_payload, "chromeDevtools", 0)
            out_msg = proto.WARemoteDebug_DebugMessage()
            out_msg.seq = engine.message_counter
            out_msg.category = "chromeDevtools"
            out_msg.data = wrapped["buffer"]
            out_msg.compressAlgo = 0
            out_msg.originalSize = wrapped["originalSize"]
            encoded = out_msg.SerializeToString()
            for websocket in list(engine.miniapp_clients):
                try:
                    task = asyncio.ensure_future(websocket.send(encoded))
                    task.add_done_callback(
                        lambda current_task: current_task.exception()
                        if current_task.done() and not current_task.cancelled() and current_task.exception()
                        else None
                    )
                except Exception:
                    pass

        bus.on_proxy_message(on_proxy_message)

        async def handler(websocket):
            nonlocal scripts_injected
            engine.miniapp_clients.add(websocket)
            engine._notify_status("miniapp", True)
            logger.info("[miniapp] miniapp client connected")

            if userscripts and not scripts_injected:
                scripts_injected = True
                logger.info("[userscript] registering scripts immediately on connection...")
                try:
                    seq = engine.message_counter
                    cmd_id = 90000
                    seq += 1
                    await websocket.send(_build_protobuf_cdp_message(build_cdp_enable_page_command(cmd_id), seq))
                    cmd_id += 1
                    seq += 1
                    await websocket.send(
                        _build_protobuf_cdp_message(
                            json.dumps({"id": cmd_id, "method": "Debugger.enable", "params": {}}),
                            seq,
                        )
                    )
                    cmd_id += 1
                    logger.info("[anti-debug] Debugger.enable sent")
                    seq += 1
                    await websocket.send(
                        _build_protobuf_cdp_message(
                            json.dumps({"id": cmd_id, "method": "Debugger.setSkipAllPauses", "params": {"skip": True}}),
                            seq,
                        )
                    )
                    cmd_id += 1
                    logger.info("[anti-debug] Debugger.setSkipAllPauses(true) sent")
                    for script in userscripts:
                        seq += 1
                        await websocket.send(_build_protobuf_cdp_message(build_cdp_add_script_command(script, cmd_id), seq))
                        cmd_id += 1
                        logger.info(f"[userscript] registered (persistent): {script.name}")
                    engine.message_counter = seq
                    logger.info("[userscript] registration done, scripts will run on page load")
                except Exception as exc:
                    logger.error(f"[userscript] registration error: {exc}")

            immediate_done = False
            try:
                async for message in websocket:
                    if isinstance(message, str):
                        message = message.encode("utf-8")
                    msg_category = ""
                    try:
                        decoded_msg = proto.WARemoteDebug_DebugMessage()
                        decoded_msg.ParseFromString(message)
                        msg_category = decoded_msg.category
                    except Exception:
                        pass
                    self._process_miniapp_message(message)
                    if msg_category == "setupContext" and userscripts and not immediate_done:
                        immediate_done = True
                        await asyncio.sleep(0.5)
                        try:
                            seq = engine.message_counter
                            cmd_id = 91000
                            seq += 1
                            await websocket.send(
                                _build_protobuf_cdp_message(
                                    json.dumps({"id": cmd_id, "method": "Debugger.enable", "params": {}}),
                                    seq,
                                )
                            )
                            cmd_id += 1
                            seq += 1
                            await websocket.send(
                                _build_protobuf_cdp_message(
                                    json.dumps({"id": cmd_id, "method": "Debugger.setSkipAllPauses", "params": {"skip": True}}),
                                    seq,
                                )
                            )
                            cmd_id += 1
                            logger.info("[anti-debug] Debugger.setSkipAllPauses re-sent after setupContext")
                            for script in userscripts:
                                wrapped = build_injection_wrapper(script)
                                seq += 1
                                cdp_cmd = json.dumps(
                                    {
                                        "id": cmd_id,
                                        "method": "Runtime.evaluate",
                                        "params": {
                                            "expression": wrapped,
                                            "includeCommandLineAPI": True,
                                            "silent": False,
                                        },
                                    }
                                )
                                await websocket.send(_build_protobuf_cdp_message(cdp_cmd, seq))
                                cmd_id += 1
                                logger.info(f"[userscript] immediate inject (Runtime.evaluate): {script.name}")
                            engine.message_counter = seq
                        except Exception as exc:
                            logger.error(f"[userscript] immediate inject warning: {exc}")
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as exc:
                logger.error(f"[miniapp] miniapp client err: {exc}")
            finally:
                engine.miniapp_clients.discard(websocket)
                if not engine.miniapp_clients:
                    engine._notify_status("miniapp", False)
                    for future in list(engine._pending_responses.values()):
                        if not future.done():
                            future.set_exception(RuntimeError("miniapp disconnected"))
                    engine._pending_responses.clear()
                logger.info("[miniapp] miniapp client disconnected")

        server = await websockets.server.serve(handler, "0.0.0.0", self.options.debug_port, max_size=None)
        logger.info(f"[server] debug server running on ws://localhost:{self.options.debug_port}")
        logger.info("[server] debug server waiting for miniapp to connect...")
        return server

    def _process_miniapp_message(self, message: bytes) -> None:
        self.logger.main_debug(f"[miniapp] client received raw message (hex): {buffer_to_hex_string(message)}")
        unwrapped_data = None
        try:
            decoded = proto.WARemoteDebug_DebugMessage()
            decoded.ParseFromString(message)
            unwrapped_data = unwrap_debug_message_data(decoded)
            self.logger.main_debug("[miniapp] [DEBUG] decoded data:")
            self.logger.main_debug(unwrapped_data)
        except Exception as exc:
            self.logger.error(f"[miniapp] miniapp client err: {exc}")

        if unwrapped_data is None:
            return

        if unwrapped_data.get("category") == "chromeDevtoolsResult":
            payload = unwrapped_data["data"].get("payload", "")
            self.bus.emit_cdp_message(payload)
            self._handle_cdp_response(payload)

    async def _start_proxy_server(self):
        import websockets.exceptions
        import websockets.server

        engine = self
        logger = self.logger
        bus = self.bus

        def on_cdp_message(message: str) -> None:
            for websocket in list(engine.devtools_clients):
                try:
                    task = asyncio.ensure_future(websocket.send(message))
                    task.add_done_callback(
                        lambda current_task: current_task.exception()
                        if current_task.done() and not current_task.cancelled() and current_task.exception()
                        else None
                    )
                except Exception:
                    pass

        bus.on_cdp_message(on_cdp_message)

        async def handler(websocket):
            engine.devtools_clients.add(websocket)
            engine._notify_status("devtools", True)
            logger.info("[cdp] CDP client connected")
            try:
                async for message in websocket:
                    if isinstance(message, bytes):
                        message = message.decode("utf-8")
                    bus.emit_proxy_message(normalize_proxy_message(message))
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as exc:
                logger.error(f"[cdp] CDP client err: {exc}")
            finally:
                engine.devtools_clients.discard(websocket)
                if not engine.devtools_clients:
                    engine._notify_status("devtools", False)
                logger.info("[cdp] CDP client disconnected")

        server = await websockets.server.serve(handler, "0.0.0.0", self.options.cdp_port, max_size=None)
        logger.info(f"[server] proxy server running on ws://localhost:{self.options.cdp_port}")
        logger.info(f"[server] link: devtools://devtools/bundled/inspector.html?ws=127.0.0.1:{self.options.cdp_port}")
        return server

    def _load_frida(self):
        import frida

        return frida

    def _find_wmpf_pids_win(self):
        """Windows: find the main WeChatAppEx.exe PID via PPID frequency."""
        frida = self._load_frida()
        device = frida.get_local_device()
        processes = device.enumerate_processes(scope="metadata")
        wmpf_procs = [process for process in processes if process.name == "WeChatAppEx.exe"]
        if not wmpf_procs:
            raise RuntimeError("[frida] WeChatAppEx.exe process not found")

        ppids = [process.parameters.get("ppid", 0) or 0 for process in wmpf_procs]
        main_pid = Counter(ppids).most_common(1)[0][0]
        if main_pid == 0:
            raise RuntimeError("[frida] WeChatAppEx.exe main process not found")

        main_proc = next((process for process in processes if process.pid == main_pid), None)
        if main_proc is None:
            raise RuntimeError("[frida] could not locate main WMPF process")

        proc_path = main_proc.parameters.get("path", "")
        numbers = re.findall(r"\d+", proc_path)
        if not numbers:
            raise RuntimeError("[frida] cannot detect WMPF version from path")
        version = int(numbers[-1])
        if version == 0:
            raise RuntimeError("[frida] invalid WMPF version")

        return [main_pid], version

    def _find_wmpf_pids_darwin(self):
        """macOS: find WeChatAppEx PIDs and the bundled version number."""
        try:
            output = subprocess.check_output(
                ["pgrep", "-f", "/MacOS/WeChatAppEx.app/Contents/MacOS/WeChatAppEx"],
                text=True,
            ).strip()
            pids = [int(pid) for pid in output.splitlines() if pid.strip()]
        except (subprocess.CalledProcessError, ValueError):
            pids = []
        if not pids:
            raise RuntimeError("[frida] WeChatAppEx process not found on macOS")

        try:
            version_output = subprocess.check_output(
                [
                    "defaults",
                    "read",
                    "/Applications/WeChat.app/Contents/MacOS/WeChatAppEx.app/Contents/Info.plist",
                    "CFBundleVersion",
                ],
                text=True,
            ).strip()
            version = int(version_output.split(".")[1])
        except Exception:
            raise RuntimeError("[frida] cannot detect WeChatAppEx version from Info.plist")

        return pids, version

    async def _start_frida(self):
        logger = self.logger
        frida = self._load_frida()
        is_mac = sys.platform == "darwin"
        platform_dir = "mac" if is_mac else "win"

        if is_mac:
            pids, wmpf_version = self._find_wmpf_pids_darwin()
        else:
            pids, wmpf_version = self._find_wmpf_pids_win()

        hook_path = tools_root() / "hook.js"
        if not hook_path.exists():
            raise RuntimeError("[frida] hook script not found")

        config_path = tools_root() / "config" / platform_dir / f"addresses.{wmpf_version}.json"
        if not config_path.exists():
            raise RuntimeError(f"[frida] version config not found: {platform_dir}/{wmpf_version}")

        script_content = hook_path.read_text(encoding="utf-8")
        config_content = json.dumps(json.loads(config_path.read_text(encoding="utf-8")))
        final_script = script_content.replace("@@CONFIG@@", config_content)

        device = frida.get_local_device()
        session = None
        script = None

        def on_message(message, data) -> None:
            if message.get("type") == "error":
                logger.error("[frida client]", message)
                return
            logger.frida_debug("[frida client]", message.get("payload", ""))

        for pid in pids:
            try:
                current_session = device.attach(pid)
                current_script = current_session.create_script(final_script)
                current_script.on("message", on_message)
                current_script.load()
                logger.info(f"[frida] injected pid={pid}, version={wmpf_version}")
                if session is None:
                    session, script = current_session, current_script
            except Exception as exc:
                logger.error(f"[frida] failed to inject pid={pid}: {exc}")

        if session is None:
            raise RuntimeError("[frida] failed to inject any WeChatAppEx process")

        logger.info(f"[frida] ready ({platform_dir}), version={wmpf_version}, {len(pids)} process(es)")
        logger.info("[frida] you can now open any miniapps")
        return session, script
