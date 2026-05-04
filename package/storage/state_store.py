"""异步读写应用状态文件，并管理功能开关、配置和规则。"""

from __future__ import annotations

import asyncio
import copy
import json
import multiprocessing as mp
import queue
from pathlib import Path

from package.applet_logs import normalize_log_settings
from package.config.defaults import DEFAULT_STATE, normalize_cloud_call_timeout
from package.regex_rules import is_legacy_default_regex_rules


def merge_state(raw_state: dict) -> dict:
    """合并磁盘状态与默认状态，过滤掉无效配置。"""
    state = copy.deepcopy(DEFAULT_STATE)
    if not isinstance(raw_state, dict):
        return state

    toggles = raw_state.get("toggles")
    if isinstance(toggles, dict):
        for key in state["toggles"]:
            state["toggles"][key] = bool(toggles.get(key, state["toggles"][key]))

    config = raw_state.get("config")
    if isinstance(config, dict):
        applet_packages_path = config.get("applet_packages_path")
        if applet_packages_path is not None:
            state["config"]["applet_packages_path"] = str(applet_packages_path).strip()
        state["config"]["cloud_call_timeout_seconds"] = normalize_cloud_call_timeout(
            config.get("cloud_call_timeout_seconds", state["config"].get("cloud_call_timeout_seconds"))
        )

    rules = raw_state.get("rules")
    if isinstance(rules, list):
        valid_rules = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            name = str(rule.get("name", "")).strip()
            pattern = str(rule.get("pattern", "")).strip()
            if not name or not pattern:
                continue
            valid_rules.append(
                {
                    "name": name,
                    "pattern": pattern,
                    "enabled": bool(rule.get("enabled", True)),
                    "note": str(rule.get("note", "")).strip(),
                }
            )
        if valid_rules and not is_legacy_default_regex_rules(valid_rules):
            state["rules"] = valid_rules

    log_settings = raw_state.get("log_settings")
    if isinstance(log_settings, dict):
        records = log_settings.get("records")
        if isinstance(records, dict):
            valid_records = {}
            for key, settings in records.items():
                record_key = str(key or "").strip()
                if not record_key:
                    continue
                valid_records[record_key] = normalize_log_settings(settings)
            state["log_settings"]["records"] = valid_records

    return state


def load_from_disk(path: Path) -> dict:
    """在子进程中读取状态文件，失败时返回默认状态。"""
    if not path.exists():
        return copy.deepcopy(DEFAULT_STATE)
    try:
        with path.open("r", encoding="utf-8") as file:
            return merge_state(json.load(file))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULT_STATE)


def save_to_disk(path: Path, state: dict) -> None:
    """在子进程中保存状态文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


class AsyncStateWorker:
    """在独立进程中运行的 asyncio 状态读写 worker。"""

    def __init__(self, path: Path, event_queue: mp.Queue, command_queue: mp.Queue) -> None:
        """初始化状态 worker 的文件路径和进程队列。"""
        self.path = path
        self.event_queue = event_queue
        self.command_queue = command_queue
        self.running = True

    async def run(self) -> None:
        """运行状态加载和保存命令循环。"""
        try:
            state = load_from_disk(self.path)
            self.event_queue.put({"type": "state_loaded", "state": state})
            while self.running:
                await self.process_commands()
                await asyncio.sleep(0.05)
        except Exception as exc:
            self.event_queue.put({"type": "error", "message": f"配置进程异常：{exc}"})

    async def process_commands(self) -> None:
        """处理 UI 进程发送的状态保存命令。"""
        latest_state: dict | None = None
        while True:
            try:
                command = self.command_queue.get_nowait()
            except queue.Empty:
                break

            command_type = command.get("type")
            if command_type == "stop":
                self.running = False
                break
            if command_type == "save":
                latest_state = command.get("state")

        if latest_state is not None:
            save_to_disk(self.path, merge_state(latest_state))


def state_worker_main(path: str, event_queue: mp.Queue, command_queue: mp.Queue) -> None:
    """状态 worker 子进程入口。"""
    asyncio.run(AsyncStateWorker(Path(path), event_queue, command_queue).run())


class StateStore:
    """管理 UI 进程内状态快照，并把文件 IO 交给独立进程。"""

    def __init__(self, path: Path, event_queue: mp.Queue | None = None) -> None:
        """初始化状态仓库并启动状态 worker 进程。"""
        self.path = path
        self.event_queue = event_queue or mp.Queue()
        self.command_queue: mp.Queue = mp.Queue()
        self.state = copy.deepcopy(DEFAULT_STATE)
        self.process = mp.Process(
            target=state_worker_main,
            args=(str(self.path), self.event_queue, self.command_queue),
            daemon=True,
            name="state-async-worker",
        )
        self.process.start()

    def handle_event(self, event: dict) -> None:
        """接收状态 worker 发回的事件并更新本地快照。"""
        if event.get("type") == "state_loaded":
            self.state = merge_state(event.get("state", {}))

    def snapshot(self) -> dict:
        """返回 UI 进程内的状态快照。"""
        return copy.deepcopy(self.state)

    def save(self) -> None:
        """把当前状态快照提交给状态 worker 保存。"""
        self.command_queue.put({"type": "save", "state": self.snapshot()})

    def update_config(self, key: str, value) -> None:
        """更新单项配置并提交异步保存。"""
        self.state.setdefault("config", {})
        self.state["config"][key] = value
        self.save()

    def update_toggle(self, key: str, value: bool) -> None:
        """更新模块开关状态并提交异步保存。"""
        self.state.setdefault("toggles", {})
        self.state["toggles"][key] = bool(value)
        self.save()

    def update_rules(self, rules: list[dict]) -> None:
        """更新正则规则列表并提交异步保存。"""
        self.state["rules"] = copy.deepcopy(rules)
        self.save()

    def update_log_settings(self, record_key: str, settings: dict) -> None:
        """更新指定小程序卡片的日志设置并提交异步保存。"""
        key = str(record_key or "").strip()
        if not key:
            return
        self.state.setdefault("log_settings", {})
        self.state["log_settings"].setdefault("records", {})
        self.state["log_settings"]["records"][key] = normalize_log_settings(settings)
        self.save()

    def shutdown(self) -> None:
        """停止状态 worker 进程。"""
        if self.process.is_alive():
            self.command_queue.put({"type": "stop"})
            self.process.join(timeout=1.0)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1.0)
