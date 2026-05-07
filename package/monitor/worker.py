"""Async worker that coordinates applet monitoring, storage, and commands."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import sqlite3
from pathlib import Path

from package.monitor.constants import MONITOR_INTERVAL_SECONDS
from package.monitor.worker_commands import MonitorCommandMixin
from package.monitor.worker_database import MonitorDatabaseMixin
from package.monitor.worker_files import MonitorFileMixin
from package.monitor.worker_identity import MonitorIdentityMixin
from package.monitor.worker_scan import MonitorScanMixin


class AsyncMiniProgramMonitorWorker(
    MonitorIdentityMixin,
    MonitorFileMixin,
    MonitorDatabaseMixin,
    MonitorScanMixin,
    MonitorCommandMixin,
):
    """Async worker process for applet monitoring."""

    def __init__(self, root_path: Path, db_path: Path, event_queue: mp.Queue, command_queue: mp.Queue, monitor_id: int) -> None:
        """Initialize worker state and IPC handles."""
        self.root_path = root_path
        self.db_path = db_path
        self.event_queue = event_queue
        self.command_queue = command_queue
        self.monitor_id = monitor_id
        self.running = True
        self.previous_dirs: dict[str, dict[str, float]] = {}
        self.last_titles: dict[int, str] = {}
        self.last_records_signature: tuple | None = None
        self.conn: sqlite3.Connection | None = None

    async def run(self) -> None:
        """Run the monitor loop inside the child process."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self.ensure_schema()
            await asyncio.to_thread(self.prepare_root_path)
            self.previous_dirs = await asyncio.to_thread(self.snapshot_dirs)
            self.publish_records(force=True)

            while self.running:
                await self.process_commands()
                await self.scan_once()
                await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
        except Exception as exc:
            self.emit({"type": "error", "message": f"小程序监控异常：{exc}"})
        finally:
            if self.conn is not None:
                self.conn.close()

    def emit(self, event: dict) -> None:
        """Send a monitor event back to the UI process."""
        event.setdefault("monitor_id", self.monitor_id)
        self.event_queue.put(event)
