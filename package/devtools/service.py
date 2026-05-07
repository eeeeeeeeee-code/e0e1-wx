"""UI-side service for the shared DevTools worker process."""

from __future__ import annotations

import multiprocessing as mp
import queue

from PySide6.QtCore import QObject, QTimer, Signal

from package.applet_debug import copy_debug_toggle_state, default_debug_toggle_state
from package.applet_routes.state import copy_route_state, default_route_state
from package.config.defaults import (
    DEFAULT_DEVTOOLS_CDP_PORT,
    DEFAULT_MINIAPP_DEBUG_PORT,
    normalize_cloud_call_timeout,
    normalize_devtools_port,
    normalize_route_traverse_interval,
)
from package.cloud_audit import copy_cloud_state, default_cloud_state
from package.devtools.constants import SERVICE_EVENT_BATCH_LIMIT
from package.devtools.identity import record_display_name, record_owner_key
from package.devtools.state import copy_state, default_state
from package.devtools.worker import devtools_worker_main


class DevtoolsService(QObject):
    """Expose one global DevTools worker to all detail pages."""

    state_changed = Signal(dict)
    route_state_changed = Signal(int, dict)
    debug_toggle_state_changed = Signal(int, dict)
    debug_toggle_log_emitted = Signal(dict)
    cloud_state_changed = Signal(dict)
    cloud_calls_changed = Signal(list)
    cloud_call_completed = Signal(dict)
    cloud_static_scan_completed = Signal(int, list)
    cloud_static_scan_failed = Signal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.event_queue: mp.Queue | None = None
        self.command_queue: mp.Queue | None = None
        self.process: mp.Process | None = None
        self.state = default_state()
        self.route_states: dict[int, dict] = {}
        # 缓存各记录的调试开关状态，避免 UI 卡片在无事件时丢失上下文。
        self.debug_toggle_states: dict[int, dict] = {}
        self.cloud_state = default_cloud_state()
        self.cloud_calls: list[dict] = []
        self.cloud_call_history: list[dict] = []
        self.last_cloud_call_result: dict = {}

        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self.process_events)
        self.event_timer.start(80)

    def snapshot(self) -> dict:
        return copy_state(self.state)

    def state_for_record(self, record: dict) -> dict:
        state = self.snapshot()
        owner_key = record_owner_key(record)
        state["record_owner_key"] = owner_key
        state["record_display_name"] = record_display_name(record)
        state["current_record"] = bool(owner_key) and owner_key == state.get("owner_key")
        return state

    def route_state_for_record(self, record: dict) -> dict:
        record_id = int(record.get("id") or 0)
        state = self.route_states.get(record_id)
        if state is not None:
            return copy_route_state(state)
        return default_route_state(
            record_id=record_id,
            owner_key=record_owner_key(record),
            display_name=record_display_name(record),
        )

    def debug_toggle_state_for_record(self, record: dict) -> dict:
        """返回附带当前卡片信息的调试开关状态快照。"""
        record_id = int(record.get("id") or 0)
        state = self.debug_toggle_states.get(record_id)
        if state is not None:
            return copy_debug_toggle_state(state)
        return default_debug_toggle_state(
            record_id=record_id,
            owner_key=record_owner_key(record),
            display_name=record_display_name(record),
        )

    def cloud_state_for_record(self, record: dict) -> dict:
        """返回附带当前卡片归属信息的云审计状态快照。"""
        state = copy_cloud_state(self.cloud_state)
        owner_key = record_owner_key(record)
        state["record_owner_key"] = owner_key
        state["record_display_name"] = record_display_name(record)
        state["current_record"] = bool(owner_key) and owner_key == state.get("owner_key")
        return state

    def cloud_calls_for_record(self, record: dict) -> list[dict]:
        """返回当前卡片可见的动态云审计记录列表。"""
        state = self.cloud_state_for_record(record)
        if state.get("owner_key") and not state.get("current_record"):
            return []
        return [dict(item) for item in self.cloud_calls if isinstance(item, dict)]

    def cloud_call_history_for_record(self, record: dict) -> list[dict]:
        """返回当前卡片可见的云函数手动调用历史。"""
        state = self.cloud_state_for_record(record)
        if state.get("owner_key") and not state.get("current_record"):
            return []
        return [dict(item) for item in self.cloud_call_history if isinstance(item, dict)]

    def ensure_worker_started(self) -> None:
        if self.process is not None and self.process.is_alive():
            return
        self.event_queue = mp.Queue()
        self.command_queue = mp.Queue()
        self.process = mp.Process(
            target=devtools_worker_main,
            args=(self.event_queue, self.command_queue),
            daemon=True,
            name="devtools-async-worker",
        )
        self.process.start()

    def start_debug(self, record: dict) -> None:
        self.ensure_worker_started()
        self._send_record_command(record, "start_session")

    def stop_debug(self) -> None:
        if self.command_queue is not None:
            self.command_queue.put({"type": "stop_session"})

    def detect_debug_toggle(self, record: dict) -> None:
        """向共享 worker 请求探测当前记录的调试开关状态。"""
        self.ensure_worker_started()
        self._send_record_command(record, "detect_debug_toggle")

    def set_debug_toggle(self, record: dict, enabled: bool) -> None:
        """向共享 worker 转发调试开关设置命令。"""
        self.ensure_worker_started()
        self._send_record_command(record, "set_debug_toggle", {"enabled": bool(enabled)})

    def start_cloud_audit(self, record: dict) -> None:
        """启动当前卡片对应的小程序动态云函数捕获。"""
        self.ensure_worker_started()
        self._send_record_command(record, "start_cloud_audit")

    def stop_cloud_audit(self) -> None:
        """停止当前共享会话上的动态云函数捕获。"""
        if self.command_queue is not None:
            self.command_queue.put({"type": "stop_cloud_audit"})

    def clear_cloud_audit(self) -> None:
        """清空当前共享会话中的动态捕获记录。"""
        self.cloud_calls.clear()
        self.cloud_call_history.clear()
        self.last_cloud_call_result = {}
        self.cloud_state["captured_count"] = 0
        self.cloud_state_changed.emit(copy_cloud_state(self.cloud_state))
        self.cloud_calls_changed.emit([])
        if self.command_queue is not None:
            self.command_queue.put({"type": "clear_cloud_audit"})

    def call_cloud_function(self, record: dict, name: str, data: dict | None = None) -> None:
        """在当前卡片对应的小程序上下文中手动调用云函数。"""
        self.ensure_worker_started()
        self._send_record_command(
            record,
            "call_cloud_function",
            {
                "name": str(name or ""),
                "data": dict(data or {}),
                "timeout_seconds": normalize_cloud_call_timeout(
                    record.get("_cloud_call_timeout_seconds")
                    if isinstance(record, dict)
                    else None
                ),
            },
        )

    def scan_cloud_static(self, record: dict) -> None:
        """为当前卡片触发一次运行时静态扫描。"""
        self.ensure_worker_started()
        self._send_record_command(record, "scan_cloud_static")

    def start_route(self, record: dict) -> None:
        self.ensure_worker_started()
        self._send_record_command(record, "attach_route")

    def refresh_routes(self, record: dict) -> None:
        self.ensure_worker_started()
        self._send_record_command(record, "refresh_routes")

    def execute_route_action(self, record: dict, action: str, route: str) -> None:
        self.ensure_worker_started()
        self._send_record_command(record, "execute_route_action", {"action": action, "route": route})

    def navigate_back_route(self, record: dict, delta: int = 1) -> None:
        self.ensure_worker_started()
        self._send_record_command(record, "navigate_back_route", {"delta": int(delta or 1)})

    def traverse_routes(self, record: dict, start_route: str = "") -> None:
        """向 worker 请求遍历路由，并下发配置的跳转间隔。"""
        self.ensure_worker_started()
        self._send_record_command(
            record,
            "traverse_routes",
            {
                "start_route": str(start_route or "").strip(),
                "traverse_interval_seconds": normalize_route_traverse_interval(
                    record.get("_route_traverse_interval_seconds") if isinstance(record, dict) else None
                ),
            },
        )

    def toggle_route_guard(self, record: dict, enabled: bool) -> None:
        self.ensure_worker_started()
        self._send_record_command(record, "toggle_route_guard", {"enabled": bool(enabled)})

    def cancel_route(self, record: dict | int) -> None:
        if self.command_queue is None:
            return
        record_id = int(record if isinstance(record, int) else record.get("id") or 0)
        self.command_queue.put({"type": "cancel_route_tasks", "record_id": record_id})

    def cancel_debug_toggle(self, record: dict | int) -> None:
        """取消指定记录仍在执行中的调试开关任务。"""
        if self.command_queue is None:
            return
        record_id = int(record if isinstance(record, int) else record.get("id") or 0)
        self.command_queue.put({"type": "cancel_debug_toggle", "record_id": record_id})

    def process_events(self) -> None:
        """轮询 worker 事件，并在 worker 退出时清理本地缓存状态。"""
        if self.process is not None and not self.process.is_alive():
            self.process = None
            self.event_queue = None
            self.command_queue = None
            if self.state.get("worker_alive"):
                self.state = default_state(message="调试 worker 已退出")
                self.state_changed.emit(self.snapshot())
            if self.cloud_state.get("worker_alive"):
                self.cloud_state = default_cloud_state(message="云审计 worker 已退出")
                self.cloud_state_changed.emit(copy_cloud_state(self.cloud_state))
            if self.cloud_calls or self.cloud_call_history:
                self.cloud_calls.clear()
                self.cloud_call_history.clear()
                self.cloud_calls_changed.emit([])
            for record_id, state in list(self.route_states.items()):
                state.update({"worker_alive": False, "status": "failed", "message": "调试 worker 已退出"})
                self.route_state_changed.emit(record_id, copy_route_state(state))
            for record_id, state in list(self.debug_toggle_states.items()):
                state.update({"worker_alive": False, "status": "failed", "message": "调试 worker 已退出"})
                self.debug_toggle_state_changed.emit(record_id, copy_debug_toggle_state(state))
            self.debug_toggle_states.clear()
            return

        if self.event_queue is None:
            return

        for _index in range(SERVICE_EVENT_BATCH_LIMIT):
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            self.handle_event(event)

    def handle_event(self, event: dict) -> None:
        """按事件类型同步服务缓存，并向 UI 分发对应信号。"""
        event_type = str(event.get("type") or "")
        if event_type == "devtools_state":
            next_state = event.get("state") if isinstance(event.get("state"), dict) else default_state()
            if next_state == self.state:
                return
            self.state = copy_state(next_state)
            self.state_changed.emit(self.snapshot())
            return
        if event_type == "route_state":
            record_id = int(event.get("record_id") or 0)
            state = copy_route_state(event.get("state") if isinstance(event.get("state"), dict) else {})
            self.route_states[record_id] = state
            self.route_state_changed.emit(record_id, copy_route_state(state))
            return
        if event_type == "debug_toggle_state":
            record_id = int(event.get("record_id") or 0)
            state = copy_debug_toggle_state(
                event.get("state") if isinstance(event.get("state"), dict) else default_debug_toggle_state()
            )
            self.debug_toggle_states[record_id] = state
            self.debug_toggle_state_changed.emit(record_id, copy_debug_toggle_state(state))
            return
        if event_type == "debug_toggle_log":
            payload = {
                "record_id": int(event.get("record_id") or 0),
                "owner_key": str(event.get("owner_key") or ""),
                "display_name": str(event.get("display_name") or ""),
                "level": str(event.get("level") or "INFO"),
                "stage": str(event.get("stage") or ""),
                "action": str(event.get("action") or ""),
                "message": str(event.get("message") or ""),
            }
            self.debug_toggle_log_emitted.emit(payload)
            return
        if event_type == "cloud_audit_state":
            next_state = copy_cloud_state(event.get("state") if isinstance(event.get("state"), dict) else {})
            previous_owner_key = str(self.cloud_state.get("owner_key") or "")
            next_owner_key = str(next_state.get("owner_key") or "")
            if previous_owner_key and previous_owner_key != next_owner_key:
                self.cloud_calls = []
                self.cloud_call_history = []
                self.cloud_calls_changed.emit([])
            self.cloud_state = next_state
            self.cloud_state_changed.emit(copy_cloud_state(next_state))
            return
        if event_type == "cloud_audit_calls":
            calls = event.get("calls") if isinstance(event.get("calls"), list) else []
            if calls:
                self.cloud_calls.extend(dict(item) for item in calls if isinstance(item, dict))
                self.cloud_state["captured_count"] = len(self.cloud_calls)
                self.cloud_state_changed.emit(copy_cloud_state(self.cloud_state))
                self.cloud_calls_changed.emit([dict(item) for item in self.cloud_calls if isinstance(item, dict)])
            return
        if event_type == "cloud_audit_call_result":
            result = event.get("result") if isinstance(event.get("result"), dict) else {}
            self.last_cloud_call_result = dict(result)
            self.cloud_call_history.append(dict(result))
            self.cloud_call_history = self.cloud_call_history[-200:]
            self.cloud_call_completed.emit(dict(result))
            return
        if event_type == "cloud_audit_static_scan_result":
            record_id = int(event.get("record_id") or 0)
            results = event.get("results") if isinstance(event.get("results"), list) else []
            self.cloud_static_scan_completed.emit(record_id, [dict(item) for item in results if isinstance(item, dict)])
            return
        if event_type == "scan_cloud_static_error":
            record_id = int(event.get("record_id") or 0)
            self.cloud_static_scan_failed.emit(record_id, str(event.get("message") or "任务失败"))

    def shutdown(self) -> None:
        """停止共享 worker，并重置所有本地缓存快照。"""
        self.event_timer.stop()
        if self.command_queue is not None:
            self.command_queue.put({"type": "shutdown"})
        if self.process is not None and self.process.is_alive():
            self.process.join(timeout=1.0)
        if self.process is not None and self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1.0)
        self.process = None
        self.event_queue = None
        self.command_queue = None
        self.state = default_state()
        self.cloud_state = default_cloud_state()
        self.cloud_calls.clear()
        self.cloud_call_history = []
        self.last_cloud_call_result = {}
        self.route_states.clear()
        self.debug_toggle_states.clear()

    def _send_record_command(self, record: dict, command_type: str, payload: dict | None = None) -> None:
        if self.command_queue is None:
            return
        command = {
            "type": command_type,
            "record_id": int(record.get("id") or 0),
            "owner_key": record_owner_key(record),
            "display_name": record_display_name(record),
            "debug_port": normalize_devtools_port(
                record.get("_miniapp_debug_port") if isinstance(record, dict) else None,
                DEFAULT_MINIAPP_DEBUG_PORT,
            ),
            "cdp_port_start": normalize_devtools_port(
                record.get("_devtools_cdp_port") if isinstance(record, dict) else None,
                DEFAULT_DEVTOOLS_CDP_PORT,
            ),
        }
        if payload:
            command.update(payload)
        self.command_queue.put(command)
