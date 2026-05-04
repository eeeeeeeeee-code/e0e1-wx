"""渲染、过滤和导出正则匹配结果列表。"""

from __future__ import annotations

from package.applet_detail.decompile_support import *


class DecompileMatchMixin:
    def load_auto_match_results(self) -> None:
        """按需从后台缓存加载完整正则匹配明细。"""
        if self.auto_matches_task_id is not None:
            return
        if self.match_results:
            return
        applet_id = self.processing_applet_id()
        if not applet_id:
            self.status_label.setText("缺少小程序缓存 ID，无法加载匹配结果")
            return
        self.status_label.setText("正在后台加载匹配结果...")
        self.cancel_button.setEnabled(True)
        self.auto_matches_task_id = self.ensure_runner().submit(
            "load_auto_matches",
            {
                "cache_path": str(self.processing_cache_path()),
                "applet_id": applet_id,
                "legacy_applet_id": str(int(self.record.get("id") or 0)),
                "new_folders": record_new_folders(self.record),
                "output_dirs": self.current_output_dir_payload(),
            },
        )

    def filtered_match_results(self) -> list[dict]:
        """按搜索框内容过滤匹配结果。"""
        keyword = self.match_filter_input.text().strip().lower() if hasattr(self, "match_filter_input") else ""
        if not keyword:
            return list(self.match_results)
        results = []
        for result in self.match_results:
            haystack = " ".join(
                [
                    str(result.get("rule_name") or ""),
                    str(result.get("file_path") or ""),
                    str(result.get("match_text") or ""),
                ]
            ).lower()
            if keyword in haystack:
                results.append(result)
        return results

    def refresh_match_results_view(self) -> None:
        """分批刷新右侧匹配结果树，避免大量结果一次性阻塞 UI。"""
        if not hasattr(self, "match_results_tree"):
            return
        if self.match_render_timer is not None:
            self.match_render_timer.stop()
        self.match_results_tree.clear()
        if not self.match_results:
            if self.auto_matches_task_id is not None:
                self.match_results_tree.addTopLevelItem(QTreeWidgetItem(["正在后台加载匹配结果...", "", "", ""]))
            elif self.match_result_count > 0:
                self.match_results_tree.addTopLevelItem(QTreeWidgetItem([f"已命中 {self.match_result_count} 条，点击左侧匹配结果节点加载明细", "", "", ""]))
            return

        self.match_render_index = 0
        self.match_render_keyword = self.match_filter_input.text().strip().lower() if hasattr(self, "match_filter_input") else ""
        self.match_render_groups = {}
        self.match_render_counts = {}
        if self.match_render_timer is None:
            self.match_render_timer = QTimer(self)
            self.match_render_timer.timeout.connect(self.render_match_results_batch)
        self.match_render_timer.start(0)

    def render_match_results_batch(self) -> None:
        """按固定批量把匹配结果追加到树控件。"""
        rendered_count = 0
        while self.match_render_index < len(self.match_results) and rendered_count < MATCH_RENDER_BATCH_SIZE:
            result = self.match_results[self.match_render_index]
            self.match_render_index += 1
            if not self.match_result_matches_keyword(result, self.match_render_keyword):
                continue
            self.append_match_result_item(result)
            rendered_count += 1

        if self.match_render_index >= len(self.match_results):
            if self.match_render_timer is not None:
                self.match_render_timer.stop()
            self.match_results_tree.resizeColumnToContents(0)
            self.match_results_tree.resizeColumnToContents(1)

    def match_result_matches_keyword(self, result: dict, keyword: str) -> bool:
        """判断单条匹配结果是否满足当前搜索关键字。"""
        if not keyword:
            return True
        haystack = " ".join(
            [
                str(result.get("rule_name") or ""),
                str(result.get("file_path") or ""),
                str(result.get("match_text") or ""),
            ]
        ).lower()
        return keyword in haystack

    def append_match_result_item(self, result: dict) -> None:
        """向匹配结果树追加一条结果并维护规则分组。"""
        rule_name = str(result.get("rule_name") or "未命名规则")
        group_item = self.match_render_groups.get(rule_name)
        if group_item is None:
            group_item = QTreeWidgetItem([f"{rule_name} (0)", "", "", ""])
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            group_item.setExpanded(True)
            self.match_render_groups[rule_name] = group_item
            self.match_render_counts[rule_name] = 0
            self.match_results_tree.addTopLevelItem(group_item)
        self.match_render_counts[rule_name] += 1
        group_item.setText(0, f"{rule_name} ({self.match_render_counts[rule_name]})")
        file_path = str(result.get("file_path") or "")
        line_number = int(result.get("line_number") or 0)
        child = QTreeWidgetItem(
            [
                rule_name,
                str(line_number),
                file_path,
                str(result.get("match_text") or ""),
            ]
        )
        child.setToolTip(2, file_path)
        child.setData(0, MATCH_RESULT_ROLE, result)
        group_item.addChild(child)
