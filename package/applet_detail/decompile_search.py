"""Build and manage the global-search panel inside the decompile detail page."""

from __future__ import annotations

from package.applet_detail.decompile_search_state import normalize_global_search_state
from package.applet_detail.decompile_support import *


class DecompileSearchMixin:
    GLOBAL_SEARCH_FILE_COLUMN_WIDTH = 240
    GLOBAL_SEARCH_LINE_COLUMN_WIDTH = 96
    GLOBAL_SEARCH_MATCH_PREVIEW_LIMIT = 160

    def build_global_search_panel(self) -> QWidget:
        """Build the global-search subpage."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.global_search_input = QLineEdit()
        self.global_search_input.setPlaceholderText("搜索当前小程序反编译输出")
        self.global_search_input.returnPressed.connect(self.start_global_search)
        self.global_search_input.textChanged.connect(self.on_global_search_input_changed)
        toolbar.addWidget(self.global_search_input, 1)

        self.global_search_regex_checkbox = QCheckBox("正则")
        self.global_search_regex_checkbox.toggled.connect(self.on_global_search_input_changed)
        toolbar.addWidget(self.global_search_regex_checkbox)

        self.global_search_run_button = QPushButton("搜索")
        self.global_search_run_button.clicked.connect(self.start_global_search)
        toolbar.addWidget(self.global_search_run_button)

        self.global_search_cancel_button = QPushButton("取消")
        self.global_search_cancel_button.clicked.connect(self.cancel_global_search)
        toolbar.addWidget(self.global_search_cancel_button)
        layout.addLayout(toolbar)

        self.global_search_status_label = QLabel("等待搜索")
        self.global_search_status_label.setObjectName("MutedLabel")
        layout.addWidget(self.global_search_status_label)

        self.global_search_results_tree = QTreeWidget()
        self.global_search_results_tree.setColumnCount(3)
        self.global_search_results_tree.setHeaderLabels(["文件", "行号", "命中内容"])
        self.global_search_results_tree.setHorizontalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        self.global_search_results_tree.setUniformRowHeights(True)
        self.global_search_results_tree.header().setStretchLastSection(False)
        self.global_search_results_tree.itemDoubleClicked.connect(self.on_global_search_result_clicked)
        layout.addWidget(self.global_search_results_tree, 1)
        self.update_global_search_column_widths()
        return panel

    def restore_global_search_state(self) -> None:
        """Restore the saved global-search state for the current record."""
        state = normalize_global_search_state(self.record.get("_global_search_state"))
        self.global_search_results = [dict(item) for item in state.get("results", []) if isinstance(item, dict)]
        self.global_search_result_count = len(self.global_search_results)
        self.global_search_selected_result = dict(state.get("selected_result") or {})
        self.global_search_input.setText(str(state.get("query") or ""))
        self.global_search_regex_checkbox.setChecked(bool(state.get("regex_enabled")))
        self.global_search_status_label.setText(str(state.get("status_message") or "等待搜索"))
        self.refresh_global_search_results_view()
        self.refresh_global_search_controls()

    def refresh_global_search_controls(self) -> None:
        """Refresh global-search control enabled states and fallback status text."""
        ready = self.global_search_ready()
        searching = self.search_task_id is not None
        query = self.global_search_input.text().strip()
        self.global_search_run_button.setEnabled(ready and not searching and bool(query))
        self.global_search_cancel_button.setEnabled(searching)
        self.global_search_input.setEnabled(not searching)
        self.global_search_regex_checkbox.setEnabled(not searching)
        if searching:
            return
        if ready:
            if not self.global_search_results and not self.global_search_status_label.text().strip():
                self.global_search_status_label.setText("等待搜索")
            return
        self.global_search_status_label.setText(self.global_search_unavailable_message())

    def global_search_unavailable_message(self) -> str:
        """Return the reason global search cannot currently run."""
        state = self.processing_state()
        if not self.current_output_dir_payload():
            return "当前无可搜索的反编译输出目录"
        if not bool(state.get("decompile_processed")):
            return "请等待反编译完成后再搜索"
        if self.optimize_code_enabled() and not self.processing_summary(state, "optimize_result", "optimize"):
            return "请等待代码优化完成后再搜索"
        return "等待搜索"

    def start_global_search(self) -> None:
        """Submit a background global-search task."""
        if not self.global_search_ready():
            self.refresh_global_search_controls()
            return
        query = self.global_search_input.text().strip()
        if not query:
            self.global_search_status_label.setText("请输入搜索内容")
            self.refresh_global_search_controls()
            return
        if self.search_task_id is not None:
            self.cancel_task(self.search_task_id)
            self.search_task_id = None
        self.global_search_results = []
        self.global_search_result_count = 0
        self.global_search_selected_result = {}
        self.refresh_global_search_results_view()
        self.global_search_status_label.setText("正在搜索...")
        self.cancel_button.setEnabled(True)
        self.ensure_runner()
        assert self.search_loader is not None
        self.search_task_id = self.search_loader.search(
            self.global_search_output_dirs(),
            query,
            self.global_search_regex_checkbox.isChecked(),
        )
        self.persist_global_search_state()
        self.refresh_global_search_controls()

    def cancel_global_search(self) -> None:
        """Cancel the running global-search task, if any."""
        if self.search_task_id is None:
            return
        self.cancel_task(self.search_task_id)

    def global_search_output_dirs(self) -> list[str]:
        """Return the output directories global search should scan."""
        state = self.processing_state()
        optimize_summary = self.processing_summary(state, "optimize_result", "optimize")
        optimize_dirs = optimize_summary.get("directories") if isinstance(optimize_summary.get("directories"), list) else []
        if self.optimize_code_enabled() and optimize_dirs:
            return [str(path or "").strip() for path in optimize_dirs if str(path or "").strip()]
        return self.current_output_dir_payload()

    def refresh_global_search_results_view(self) -> None:
        """Refresh the global-search result tree."""
        self.global_search_results_tree.clear()
        if not self.global_search_results:
            if self.search_task_id is not None:
                self.global_search_results_tree.addTopLevelItem(QTreeWidgetItem(["正在搜索...", "", ""]))
            elif self.global_search_result_count > 0:
                self.global_search_results_tree.addTopLevelItem(
                    QTreeWidgetItem([f"共有 {self.global_search_result_count} 条结果", "", ""])
                )
            return

        for result in self.global_search_results:
            match_text = str(result.get("match_text") or "")
            line_text = str(result.get("line_text") or match_text)
            preview_text = self.elide_global_search_match_text(match_text)
            item = QTreeWidgetItem(
                [
                    str(result.get("relative_path") or result.get("file_path") or ""),
                    str(int(result.get("line_number") or 0)),
                    preview_text,
                ]
            )
            item.setToolTip(0, str(result.get("file_path") or ""))
            item.setToolTip(2, line_text)
            item.setData(0, MATCH_RESULT_ROLE, dict(result))
            emphasize_match_tree_cell(item, 2)
            self.global_search_results_tree.addTopLevelItem(item)
        self.update_global_search_column_widths()

    def elide_global_search_match_text(self, text: str) -> str:
        """Show a one-line preview for long global-search matches."""
        normalized = str(text or "").replace("\r", " ").replace("\n", " ")
        if len(normalized) <= self.GLOBAL_SEARCH_MATCH_PREVIEW_LIMIT:
            return normalized
        return normalized[: self.GLOBAL_SEARCH_MATCH_PREVIEW_LIMIT - 3].rstrip() + "..."

    def update_global_search_column_widths(self) -> None:
        """Keep the global-search columns within the available width."""
        if not hasattr(self, "global_search_results_tree"):
            return
        tree = self.global_search_results_tree
        viewport_width = max(0, tree.viewport().width())
        if viewport_width <= 0:
            tree.setColumnWidth(0, self.GLOBAL_SEARCH_FILE_COLUMN_WIDTH)
            tree.setColumnWidth(1, self.GLOBAL_SEARCH_LINE_COLUMN_WIDTH)
            return
        file_width = min(self.GLOBAL_SEARCH_FILE_COLUMN_WIDTH, max(120, viewport_width // 4))
        line_width = min(self.GLOBAL_SEARCH_LINE_COLUMN_WIDTH, max(72, viewport_width // 10))
        match_width = max(160, viewport_width - file_width - line_width - 8)
        tree.setColumnWidth(0, file_width)
        tree.setColumnWidth(1, line_width)
        tree.setColumnWidth(2, match_width)

    def on_global_search_result_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Reuse the file-tree and preview jump flow for a global-search result."""
        result = item.data(0, MATCH_RESULT_ROLE)
        if not isinstance(result, dict):
            return
        self.global_search_selected_result = dict(result)
        self.pending_jump = dict(result)
        file_path = Path(str(result.get("file_path") or ""))
        self.reveal_file_in_tree(file_path)
        self.load_file_content(file_path)
        self.persist_global_search_state()

    def persist_global_search_state(self) -> None:
        """Persist the current global-search state through the parent callback."""
        callback = getattr(self, "on_global_search_state_changed", None)
        if callback is None:
            return
        callback(
            {
                "query": self.global_search_input.text().strip(),
                "regex_enabled": self.global_search_regex_checkbox.isChecked(),
                "results": [dict(item) for item in self.global_search_results],
                "selected_result": dict(self.global_search_selected_result),
                "status_message": self.global_search_status_label.text().strip(),
                "last_output_dirs_signature": list(self.global_search_output_dirs()),
            }
        )

    def on_global_search_input_changed(self) -> None:
        """Refresh controls and persist search state when input changes."""
        self.refresh_global_search_controls()
        self.persist_global_search_state()
