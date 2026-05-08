"""负责反编译输出文件树加载、展开、选择和文件定位。"""

from __future__ import annotations

from package.applet_detail.decompile_support import *


class DecompileTreeMixin:
    def load_tree_item(self, item: QTreeWidgetItem) -> None:
        """提交指定树节点的子目录加载任务。"""
        if bool(item.data(0, LOADED_ROLE)):
            return
        if any(existing_item is item for existing_item in self.tree_tasks.values()):
            return
        path = Path(str(item.data(0, PATH_ROLE) or ""))
        self.ensure_runner()
        assert self.tree_loader is not None
        task_id = self.tree_loader.load(path)
        self.tree_tasks[task_id] = item

    def on_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        """展开目录节点时触发懒加载。"""
        if bool(item.data(0, IS_DIR_ROLE)):
            self.load_tree_item(item)

    def on_tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """点击文件节点时异步加载文件内容。"""
        if bool(item.data(0, MATCH_ROOT_ROLE)):
            self.show_match_results_panel()
            return
        if item.data(0, PATH_ROLE) == "__global_search__":
            self.show_global_search_panel()
            return
        if bool(item.data(0, IS_DIR_ROLE)):
            return
        path = Path(str(item.data(0, PATH_ROLE) or ""))
        self.load_file_content(path)

    def on_match_result_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """点击匹配结果时打开对应文件并定位到命中位置。"""
        result = item.data(0, MATCH_RESULT_ROLE)
        if not isinstance(result, dict):
            return
        self.pending_jump = dict(result)
        file_path = Path(str(result.get("file_path") or ""))
        self.reveal_file_in_tree(file_path)
        self.load_file_content(file_path)

    def normalized_tree_path(self, path: Path | str) -> str:
        """生成不访问磁盘的规范化路径文本，用于文件树节点比较。"""
        raw_path = os.path.expanduser(str(path or ""))
        normalized = os.path.abspath(os.path.normpath(raw_path))
        return os.path.normcase(normalized).replace("\\", "/").rstrip("/")

    def reveal_file_in_tree(self, file_path: Path) -> None:
        """在左侧文件树中定位并选中匹配结果对应文件。"""
        target_path = self.normalized_tree_path(file_path)
        if not target_path:
            return
        root_item = self.tree_root_for_path(target_path)
        if root_item is None:
            self.pending_tree_reveal_path = ""
            return
        self.pending_tree_reveal_path = target_path
        self.continue_tree_reveal(root_item)

    def tree_root_for_path(self, target_path: str) -> QTreeWidgetItem | None:
        """根据目标文件路径找到所属的输出目录根节点。"""
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item is None or bool(item.data(0, MATCH_ROOT_ROLE)):
                continue
            root_path = self.normalized_tree_path(str(item.data(0, PATH_ROLE) or ""))
            if target_path == root_path or target_path.startswith(root_path + "/"):
                return item
        return None

    def continue_tree_reveal(self, item: QTreeWidgetItem) -> None:
        """沿已加载节点继续定位目标文件，必要时触发后台加载。"""
        target_path = self.pending_tree_reveal_path
        if not target_path:
            return
        item_path = self.normalized_tree_path(str(item.data(0, PATH_ROLE) or ""))
        if not item_path or not (target_path == item_path or target_path.startswith(item_path + "/")):
            return
        if target_path == item_path or not bool(item.data(0, IS_DIR_ROLE)):
            self.select_tree_item(item)
            self.pending_tree_reveal_path = ""
            return

        self.tree.expandItem(item)
        if not bool(item.data(0, LOADED_ROLE)):
            self.load_tree_item(item)
            return

        child = self.child_for_reveal_path(item, target_path)
        if child is None:
            return
        self.continue_tree_reveal(child)

    def child_for_reveal_path(self, parent: QTreeWidgetItem, target_path: str) -> QTreeWidgetItem | None:
        """在父节点已加载子节点中查找目标路径所在的下一层节点。"""
        for index in range(parent.childCount()):
            child = parent.child(index)
            child_path = self.normalized_tree_path(str(child.data(0, PATH_ROLE) or ""))
            if not child_path:
                continue
            if target_path == child_path or target_path.startswith(child_path + "/"):
                return child
        return None

    def select_tree_item(self, item: QTreeWidgetItem) -> None:
        """选中并滚动到左侧文件树中的指定文件节点。"""
        self.tree.setCurrentItem(item)
        item.setSelected(True)
        self.tree.scrollToItem(item)
