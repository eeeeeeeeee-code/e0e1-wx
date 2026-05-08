"""调度小程序卡片创建后的后台反编译、优化和正则扫描任务。"""

from __future__ import annotations

import copy
import hashlib
import json
import queue
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from package.cloud_audit.cache import cloud_audit_cache_path, delete_cloud_audit_entries
from package.decompiler import DecompileTaskRunner
from package.decompiler.auto_cache import delete_auto_process_entries
from package.decompiler.cache_keys import auto_process_cache_path, output_dirs_for_folders
from package.decompiler.core import normalize_new_folder_names, path_inside_root


AUTO_PROCESS_CACHE_DIR_NAME = ".e0e1_cache"
AUTO_PROCESS_CACHE_FILE_NAME = "applet_processing_state.json"
AUTO_PROCESS_EVENT_BATCH_LIMIT = 80


def record_new_folders(record: dict) -> list[str]:
    """从小程序记录中解析绑定的 new_folder 列表。"""
    raw_list = record.get("wxids_list")
    if isinstance(raw_list, list):
        return normalize_new_folder_names([str(item) for item in raw_list])
    display = str(record.get("wxids_display") or "").strip()
    if display:
        return normalize_new_folder_names([part.strip() for part in display.split(",")])
    return normalize_new_folder_names([str(record.get("wxid") or "")])


def enabled_rules(record: dict) -> list[dict]:
    """提取当前自动处理需要使用的启用正则规则。"""
    rules = record.get("_regex_rules")
    if not isinstance(rules, list):
        return []
    return [dict(rule) for rule in rules if isinstance(rule, dict) and bool(rule.get("enabled", True))]


def applet_cache_id(record: dict) -> str:
    """生成跨数据库记录稳定的小程序缓存标识。"""
    new_folders = record_new_folders(record)
    if new_folders:
        return "|".join(new_folders)
    return str(int(record.get("id") or 0))


def compact_match_summary(summary: dict) -> dict:
    """移除正则命中明细，避免 UI 线程复制大列表。"""
    if not isinstance(summary, dict):
        return {}
    compact = {key: value for key, value in summary.items() if key != "results"}
    results = summary.get("results")
    if isinstance(results, list):
        compact["match_count"] = int(summary.get("match_count") or len(results))
        compact["preview_results"] = [dict(item) for item in results[:20] if isinstance(item, dict)]
        compact["results_loaded"] = False
    elif isinstance(summary.get("preview_results"), list):
        compact["preview_results"] = [dict(item) for item in summary.get("preview_results", []) if isinstance(item, dict)]
        compact["results_loaded"] = bool(summary.get("results_loaded"))
    return compact


def compact_processing_state(state: dict) -> dict:
    """压缩自动处理状态，只保留界面状态与按需加载所需字段。"""
    if not isinstance(state, dict):
        return {}
    compact = {}
    for key, value in state.items():
        if key == "regex_result":
            compact[key] = compact_match_summary(value if isinstance(value, dict) else {})
        elif key == "matches" and isinstance(value, dict):
            section = dict(value)
            if isinstance(section.get("summary"), dict):
                section["summary"] = compact_match_summary(section["summary"])
            compact[key] = section
        else:
            compact[key] = value
    return compact


class AppletAutoProcessManager(QObject):
    """负责卡片级自动反编译、优化和正则扫描任务的轻量调度。"""

    processing_updated = Signal(int, dict)

    def __init__(self, parent: QObject | None = None) -> None:
        """初始化后台任务 runner、去重表和事件轮询定时器。"""
        super().__init__(parent)
        self.runner = DecompileTaskRunner()
        self.active_tasks: dict[int, int] = {}
        self.task_records: dict[int, int] = {}
        self.task_signatures: dict[int, str] = {}
        self.record_signatures: dict[int, str] = {}
        self.snapshots: dict[int, dict] = {}
        self.pending_delete_cleanups: dict[int, dict] = {}
        self.closed = False

        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self.process_events)
        self.event_timer.start(100)

    def cache_path(self, output_root: Path) -> Path:
        """返回自动处理流水线共享缓存文件路径。"""
        return output_root / AUTO_PROCESS_CACHE_DIR_NAME / AUTO_PROCESS_CACHE_FILE_NAME

    def should_auto_process(self, record: dict) -> bool:
        """判断当前记录是否需要在卡片创建时自动处理。"""
        return int(record.get("id") or 0) > 0 and bool(record.get("_decompile_enabled")) and bool(record_new_folders(record))

    def request_signature(self, record: dict) -> str:
        """生成轻量请求签名，避免每次刷新卡片都重复提交任务。"""
        rules = [
            {
                "name": str(rule.get("name") or ""),
                "pattern": str(rule.get("pattern") or ""),
                "enabled": bool(rule.get("enabled", True)),
            }
            for rule in enabled_rules(record)
        ]
        payload = {
            "id": int(record.get("id") or 0),
            "applet_cache_id": applet_cache_id(record),
            "new_folders": record_new_folders(record),
            "packages_root": str(record.get("_packages_root") or ""),
            "output_root": str(record.get("_output_root") or "output"),
            "optimize_code": bool(record.get("_optimize_code_enabled")),
            "rules": rules,
        }
        raw_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

    def build_payload(self, record: dict) -> dict:
        """把详情记录转换为 worker 可执行的自动处理 payload。"""
        output_root = Path(str(record.get("_output_root") or "output")).expanduser()
        return {
            "applet_id": applet_cache_id(record),
            "packages_root": str(record.get("_packages_root") or ""),
            "output_root": str(output_root),
            "cache_path": str(self.cache_path(output_root)),
            "new_folders": record_new_folders(record),
            "optimize_enabled": bool(record.get("_optimize_code_enabled")),
            "rules": enabled_rules(record),
        }

    def ensure_record(self, record: dict) -> None:
        """在卡片生成时确保对应小程序已有后台自动处理任务或缓存。"""
        record_id = int(record.get("id") or 0)
        if record_id <= 0:
            return
        if not self.should_auto_process(record):
            self.cancel_record(record_id)
            return

        signature = self.request_signature(record)
        active_task_id = self.active_tasks.get(record_id)
        if active_task_id is not None and self.task_signatures.get(active_task_id) == signature:
            return

        snapshot = self.snapshots.get(record_id, {})
        if self.record_signatures.get(record_id) == signature and snapshot.get("status") in {"done", "running", "skipped"}:
            return

        if active_task_id is not None:
            self.runner.cancel(active_task_id)
            self.active_tasks.pop(record_id, None)
            self.task_records.pop(active_task_id, None)
            self.task_signatures.pop(active_task_id, None)

        payload = self.build_payload(record)
        task_id = self.runner.submit("auto_process", payload)
        output_root = Path(str(payload.get("output_root") or "output")).expanduser()
        self.active_tasks[record_id] = task_id
        self.task_records[task_id] = record_id
        self.task_signatures[task_id] = signature
        self.record_signatures[record_id] = signature
        self.snapshots[record_id] = {
            "applet_id": str(payload.get("applet_id") or ""),
            "cache_path": str(payload.get("cache_path") or ""),
            "output_dirs": [str(path) for path in output_dirs_for_folders(output_root, record_new_folders(record))],
            "status": "running",
            "stage": "queued",
            "message": "后台自动处理已排队",
            "_request_signature": signature,
        }
        self.processing_updated.emit(record_id, copy.deepcopy(compact_processing_state(self.snapshots[record_id])))

    def cancel_record(self, record_id: int) -> None:
        """取消指定小程序仍在运行的自动处理任务。"""
        task_id = self.active_tasks.get(record_id)
        if task_id is None:
            return
        self.runner.cancel(task_id)
        self.snapshots[record_id] = {"status": "cancelling", "message": "自动处理取消中"}
        self.processing_updated.emit(record_id, copy.deepcopy(compact_processing_state(self.snapshots[record_id])))

    def delete_record(self, record: dict) -> None:
        """Cancel active auto-processing and clean output/cache after the task settles."""
        record_id = int(record.get("id") or 0)
        if record_id <= 0:
            return
        cleanup = self.build_delete_cleanup(record)
        task_id = self.active_tasks.get(record_id)
        if task_id is None:
            self.cleanup_deleted_record(record_id, cleanup)
            return
        self.pending_delete_cleanups[record_id] = cleanup
        self.runner.cancel(task_id)

    def build_delete_cleanup(self, record: dict) -> dict:
        """Build cleanup context for a deleted record."""
        output_root = Path(str(record.get("_output_root") or "output")).expanduser()
        new_folders = record_new_folders(record)
        raw_keys = [applet_cache_id(record), str(record.get("wxid") or "").strip(), str(int(record.get("id") or 0))]
        raw_keys.extend(new_folders)
        cache_keys: list[str] = []
        seen: set[str] = set()
        for key in raw_keys:
            text = str(key or "").strip()
            if text and text not in seen:
                seen.add(text)
                cache_keys.append(text)
        return {
            "output_root": output_root,
            "output_dirs": output_dirs_for_folders(output_root, new_folders),
            "cache_keys": cache_keys,
        }

    def cleanup_deleted_record(self, record_id: int, cleanup: dict | None = None) -> None:
        """Delete on-disk artifacts for a removed record and clear in-memory state."""
        cleanup = cleanup or self.pending_delete_cleanups.pop(record_id, None)
        if cleanup is None:
            cleanup = {"output_root": Path("output"), "output_dirs": [], "cache_keys": []}
        output_root = Path(cleanup.get("output_root") or "output").expanduser()
        output_dirs = cleanup.get("output_dirs") if isinstance(cleanup.get("output_dirs"), list) else []
        cache_keys = cleanup.get("cache_keys") if isinstance(cleanup.get("cache_keys"), list) else []
        self.cleanup_output_dirs(output_root, output_dirs)
        delete_auto_process_entries(auto_process_cache_path(output_root), cache_keys)
        delete_cloud_audit_entries(cloud_audit_cache_path(output_root), cache_keys)
        self.pending_delete_cleanups.pop(record_id, None)
        self.snapshots.pop(record_id, None)
        self.record_signatures.pop(record_id, None)
        task_id = self.active_tasks.pop(record_id, None)
        if task_id is not None:
            self.task_records.pop(task_id, None)
            self.task_signatures.pop(task_id, None)

    def cleanup_output_dirs(self, output_root: Path, output_dirs: list[Path]) -> None:
        """Delete output directories for a deleted record and prune empty parents."""
        root = Path(output_root).expanduser()
        for output_dir in output_dirs:
            folder = Path(output_dir).expanduser()
            try:
                if folder == root or not path_inside_root(root, folder) or not folder.is_dir():
                    continue
                shutil.rmtree(folder)
                parent = folder.parent
                while parent != root and path_inside_root(root, parent):
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
            except OSError:
                continue

    def snapshot(self, record_id: int) -> dict:
        """返回指定小程序的最新自动处理状态快照。"""
        return copy.deepcopy(compact_processing_state(self.snapshots.get(int(record_id or 0), {})))

    def process_events(self) -> None:
        """从后台 worker 队列非阻塞消费自动处理事件。"""
        for _index in range(AUTO_PROCESS_EVENT_BATCH_LIMIT):
            try:
                event = self.runner.get_event_nowait()
            except queue.Empty:
                break
            self.handle_event(event)

    def handle_event(self, event: dict) -> None:
        """按事件类型更新本地状态并通知主窗口刷新展示。"""
        task_id = int(event.get("task_id") or 0)
        record_id = self.task_records.get(task_id)
        if record_id is None:
            applet_id = str(event.get("applet_id") or "").strip()
            record_id = int(applet_id) if applet_id.isdigit() else 0
        if record_id <= 0:
            return

        event_type = str(event.get("type") or "")
        if record_id in self.pending_delete_cleanups and event_type in {"auto_process_started", "auto_process_stage"}:
            return
        if event_type == "auto_process_started":
            self.update_running_snapshot(record_id, task_id, "started", str(event.get("message") or "自动处理已启动"))
            return
        if event_type == "auto_process_stage":
            entry = event.get("entry") if isinstance(event.get("entry"), dict) else None
            self.update_running_snapshot(record_id, task_id, str(event.get("stage") or ""), str(event.get("message") or ""), entry)
            return
        if event_type == "auto_process_result":
            self.finish_record(record_id, task_id, event.get("entry") if isinstance(event.get("entry"), dict) else {})
            return
        if event_type == "auto_process_error":
            self.fail_record(record_id, task_id, str(event.get("message") or "自动处理失败"))
            return
        if event_type == "auto_process_cancelled":
            self.fail_record(record_id, task_id, "自动处理已取消", status="cancelled")

    def update_running_snapshot(
        self,
        record_id: int,
        task_id: int,
        stage: str,
        message: str,
        entry: dict | None = None,
    ) -> None:
        """保存运行中状态并通知界面刷新。"""
        signature = self.task_signatures.get(task_id, self.record_signatures.get(record_id, ""))
        snapshot = compact_processing_state(entry) if isinstance(entry, dict) else copy.deepcopy(self.snapshots.get(record_id, {}))
        snapshot.update(
            {
                "status": "running",
                "stage": stage,
                "message": message or snapshot.get("message") or "后台自动处理中",
                "_request_signature": signature,
            }
        )
        self.snapshots[record_id] = snapshot
        self.processing_updated.emit(record_id, copy.deepcopy(compact_processing_state(snapshot)))

    def finish_record(self, record_id: int, task_id: int, entry: dict) -> None:
        """保存完成状态并清理任务映射。"""
        if record_id in self.pending_delete_cleanups:
            self.cleanup_deleted_record(record_id)
            return
        signature = self.task_signatures.get(task_id, self.record_signatures.get(record_id, ""))
        snapshot = compact_processing_state(entry)
        snapshot.setdefault("status", "done")
        snapshot.setdefault("message", "自动处理完成")
        snapshot["_request_signature"] = signature
        self.snapshots[record_id] = snapshot
        self.active_tasks.pop(record_id, None)
        self.task_records.pop(task_id, None)
        self.task_signatures.pop(task_id, None)
        self.processing_updated.emit(record_id, copy.deepcopy(compact_processing_state(snapshot)))

    def fail_record(self, record_id: int, task_id: int, message: str, status: str = "error") -> None:
        if record_id in self.pending_delete_cleanups:
            self.cleanup_deleted_record(record_id)
            return
        """保存失败或取消状态，避免单任务异常影响主程序。"""
        signature = self.task_signatures.get(task_id, self.record_signatures.get(record_id, ""))
        snapshot = {
            "status": status,
            "message": message,
            "_request_signature": signature,
        }
        self.snapshots[record_id] = snapshot
        self.active_tasks.pop(record_id, None)
        self.task_records.pop(task_id, None)
        self.task_signatures.pop(task_id, None)
        self.processing_updated.emit(record_id, copy.deepcopy(compact_processing_state(snapshot)))

    def shutdown(self) -> None:
        """停止自动处理调度器和后台 worker 进程。"""
        if self.closed:
            return
        self.closed = True
        self.event_timer.stop()
        for task_id in list(self.active_tasks.values()):
            self.runner.cancel(task_id)
        self.active_tasks.clear()
        self.task_records.clear()
        self.task_signatures.clear()
        self.pending_delete_cleanups.clear()
        self.runner.shutdown(wait=False)
