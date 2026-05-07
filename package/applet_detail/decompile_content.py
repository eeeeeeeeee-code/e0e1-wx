"""处理反编译输出文件的文本、图片预览和匹配跳转定位。"""

from __future__ import annotations

from package.applet_detail.decompile_support import *


class DecompileContentMixin:
    def build_inline_find_bar(self) -> QWidget:
        """构建当前文件内联查找条。"""
        bar = LogicalVisibilityWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel("查找")
        layout.addWidget(label)

        self.inline_find_input = QLineEdit()
        self.inline_find_input.setPlaceholderText("在当前文件中搜索")
        self.inline_find_input.returnPressed.connect(self.find_next_in_current_file)
        self.inline_find_input.textChanged.connect(self.on_inline_find_text_changed)
        layout.addWidget(self.inline_find_input, 1)

        self.inline_find_status_label = QLabel("")
        self.inline_find_status_label.setObjectName("MutedLabel")
        layout.addWidget(self.inline_find_status_label)

        self.inline_find_next_button = QToolButton()
        self.inline_find_next_button.setText("下一个")
        self.inline_find_next_button.clicked.connect(self.find_next_in_current_file)
        layout.addWidget(self.inline_find_next_button)

        self.inline_find_close_button = QToolButton()
        self.inline_find_close_button.setText("关闭")
        self.inline_find_close_button.clicked.connect(self.toggle_inline_find_bar)
        layout.addWidget(self.inline_find_close_button)

        bar.hide()
        return bar

    def install_inline_find_shortcut(self) -> None:
        """为代码预览区安装 Ctrl+F 快捷键。"""
        self.inline_find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.inline_find_shortcut.activated.connect(self.toggle_inline_find_bar)

    def toggle_inline_find_bar(self) -> None:
        """显示或关闭当前文件内联查找条。"""
        visible = bool(self.inline_find_bar.isVisible())
        self.inline_find_bar.setVisible(not visible)
        if not visible:
            self.inline_find_input.setText(self.content_editor.textCursor().selectedText())
            self.inline_find_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.inline_find_input.selectAll()
        else:
            self.content_editor.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def on_inline_find_text_changed(self) -> None:
        """查找关键字变化时刷新提示。"""
        if not self.inline_find_input.text():
            self.inline_find_status_label.setText("")

    def clear_current_preview_highlight(self) -> None:
        """Clear the explicit preview highlight for the active match."""
        self.current_preview_match_selection = None
        self.content_editor.setExtraSelections([])

    def apply_current_preview_highlight(self, cursor: QTextCursor) -> None:
        """Apply a strong explicit highlight for the active preview match."""
        self.current_preview_match_selection = build_preview_match_selection(cursor)
        self.content_editor.setExtraSelections([self.current_preview_match_selection])

    def find_next_in_current_file(self) -> None:
        """在当前代码预览中查找下一条命中。"""
        query = self.inline_find_input.text()
        if not query:
            self.inline_find_status_label.setText("请输入关键字")
            return

        cursor = self.content_editor.textCursor()
        found = self.content_editor.document().find(query, cursor)
        if found.isNull():
            restart = QTextCursor(self.content_editor.document())
            restart.movePosition(QTextCursor.MoveOperation.Start)
            found = self.content_editor.document().find(query, restart)
        if found.isNull():
            self.inline_find_status_label.setText("未找到")
            return

        self.show_jump_cursor(found)
        self.content_editor.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.inline_find_status_label.setText("")

    def load_file_content(self, path: Path) -> None:
        """根据文件类型选择图片、代码或普通文本预览。"""
        if is_image_file(path):
            self.load_image_content(path)
            return
        if self.read_task_id is not None:
            self.cancel_task(self.read_task_id)
        if self.image_task_id is not None:
            self.cancel_task(self.image_task_id)
            self.image_task_id = None
        self.prepare_text_content(path)
        self.status_label.setText(f"正在读取：{path.name}")
        self.cancel_button.setEnabled(True)
        self.ensure_runner()
        assert self.content_loader is not None
        jump = dict(self.pending_jump) if isinstance(self.pending_jump, dict) else None
        self.read_task_id = self.content_loader.load(path, jump)

    def prepare_text_content(self, path: Path) -> None:
        """初始化文本或代码预览区域。"""
        self.stop_image_movie()
        self.preview_stack.setCurrentWidget(self.content_editor)
        self.content_editor.clear()
        self.clear_current_preview_highlight()
        self.content_line_base = 1
        self.move_content_to_top()
        language = language_for_path(path)
        self.content_title.setText("代码内容" if language else "文件内容")
        self.set_code_highlighter(language)

    def load_image_content(self, path: Path) -> None:
        """异步读取图片字节并准备图片预览区域。"""
        if self.read_task_id is not None:
            self.cancel_task(self.read_task_id)
            self.read_task_id = None
        if self.image_task_id is not None:
            self.cancel_task(self.image_task_id)
            self.image_task_id = None
        self.set_code_highlighter("")
        self.content_editor.clear()
        self.clear_current_preview_highlight()
        self.stop_image_movie()
        self.content_title.setText("图片预览")
        self.preview_stack.setCurrentWidget(self.image_scroll)
        self.image_label.clear()
        self.status_label.setText(f"正在读取图片：{path.name}")
        self.cancel_button.setEnabled(True)
        self.ensure_runner()
        assert self.image_loader is not None
        self.image_task_id = self.image_loader.load(path)

    def show_image_content(self, path: Path, data: bytes) -> None:
        """用后台返回的图片字节刷新 UI 预览。"""
        self.stop_image_movie()
        if path.suffix.lower() == ".gif":
            self.image_data = QByteArray(data)
            self.image_buffer = QBuffer(self.image_data, self)
            self.image_buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            movie = QMovie(self.image_buffer, QByteArray(b"gif"), self)
            if movie.isValid():
                self.image_movie = movie
                self.image_label.setMovie(movie)
                movie.start()
                self.image_label.adjustSize()
                self.image_scroll.verticalScrollBar().setValue(self.image_scroll.verticalScrollBar().minimum())
                self.image_scroll.horizontalScrollBar().setValue(self.image_scroll.horizontalScrollBar().minimum())
                self.status_label.setText(f"图片已加载：{path.name}")
                self.update_cancel_button()
                return
            self.image_buffer.close()
            self.image_buffer.deleteLater()
            self.image_buffer = None
            self.image_data = None

        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if pixmap.isNull():
            self.status_label.setText(f"图片加载失败：{path.name}")
            self.update_cancel_button()
            return
        self.image_label.setPixmap(pixmap)
        self.image_label.resize(pixmap.size())
        self.image_scroll.verticalScrollBar().setValue(self.image_scroll.verticalScrollBar().minimum())
        self.image_scroll.horizontalScrollBar().setValue(self.image_scroll.horizontalScrollBar().minimum())
        self.status_label.setText(f"图片已加载：{path.name}")
        self.update_cancel_button()

    def set_code_highlighter(self, language: str) -> None:
        """为当前编辑器设置或移除语法高亮。"""
        if self.highlighter is not None:
            self.highlighter.setDocument(None)
            self.highlighter = None
        if language:
            self.highlighter = CodeSyntaxHighlighter(self.content_editor.document(), language)

    def stop_image_movie(self) -> None:
        """停止当前 GIF 动画，避免切换文件后继续播放。"""
        if self.image_movie is not None:
            self.image_movie.stop()
            self.image_movie = None
        if self.image_buffer is not None:
            self.image_buffer.close()
            self.image_buffer.deleteLater()
            self.image_buffer = None
        self.image_data = None
    def append_content(self, text: str) -> None:
        """把分块文本追加到右侧内容区域。"""
        if not text:
            return
        cursor = QTextCursor(self.content_editor.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)

    def move_content_to_top(self) -> None:
        """把文件预览光标和视图移动到第一行。"""
        cursor = QTextCursor(self.content_editor.document())
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.content_editor.setTextCursor(cursor)
        self.content_editor.ensureCursorVisible()
        self.reset_content_scroll()
        QTimer.singleShot(0, self.reset_content_scroll)

    def reset_content_scroll(self) -> None:
        """强制把文本预览滚动条复位到左上角。"""
        self.content_editor.verticalScrollBar().setValue(self.content_editor.verticalScrollBar().minimum())
        self.content_editor.horizontalScrollBar().setValue(self.content_editor.horizontalScrollBar().minimum())

    def apply_pending_jump(self, loaded_path: str) -> bool:
        """在文件读取完成后跳转并选中匹配内容。"""
        if not self.pending_jump:
            return False
        target_path = str(self.pending_jump.get("file_path") or "")
        if not self.same_file_path(loaded_path, target_path):
            return False

        line_number = max(1, int(self.pending_jump.get("line_number") or 1))
        match_start = max(0, int(self.pending_jump.get("match_start") or 0))
        match_end = max(match_start, int(self.pending_jump.get("match_end") or match_start))
        match_text = str(self.pending_jump.get("match_text") or "")
        block_index = line_number - max(1, int(self.content_line_base or 1))
        block = self.content_editor.document().findBlockByNumber(block_index)
        cursor = self.cursor_for_match_block(block, match_start, match_end, match_text)

        if cursor.isNull() and match_text:
            cursor = self.cursor_for_match_text(match_text)
            if not cursor.isNull():
                line_number = int(self.content_line_base or 1) + cursor.blockNumber()

        if cursor.isNull():
            self.pending_jump = None
            self.status_label.setText(f"未能定位到第 {line_number} 行，可能文件内容已变化")
            return False
        self.show_jump_cursor(cursor)
        self.content_title.setText(f"代码内容 - 第 {line_number} 行")
        self.pending_jump = None
        return True

    def same_file_path(self, left_path: str, right_path: str) -> bool:
        """宽松比较两个文件路径，避免路径格式差异导致跳转被跳过。"""
        if not left_path or not right_path:
            return False
        left = str(Path(left_path).expanduser().resolve(strict=False)).replace("\\", "/").lower()
        right = str(Path(right_path).expanduser().resolve(strict=False)).replace("\\", "/").lower()
        return left == right

    def cursor_for_match_block(self, block, match_start: int, match_end: int, match_text: str) -> QTextCursor:
        """在目标行内创建尽可能精确的匹配光标。"""
        cursor = QTextCursor()
        if not block.isValid():
            return cursor

        line_text = block.text()
        safe_start = min(max(0, match_start), len(line_text))
        safe_end = min(max(safe_start, match_end), len(line_text))
        if safe_end > safe_start:
            cursor = QTextCursor(block)
            cursor.setPosition(block.position() + safe_start)
            cursor.setPosition(block.position() + safe_end, QTextCursor.MoveMode.KeepAnchor)
            return cursor

        search_text = match_text[:-3] if match_text.endswith("...") else match_text
        if search_text:
            if line_text[match_start : match_start + len(search_text)] == search_text:
                start = match_start
            else:
                start = line_text.find(search_text, max(0, match_start - 20))
                if start < 0:
                    start = line_text.find(search_text)
            if start >= 0:
                end = min(len(line_text), start + max(1, len(search_text)))
                cursor = QTextCursor(block)
                cursor.setPosition(block.position() + start)
                cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
                return cursor

        return QTextCursor()

    def cursor_for_match_text(self, match_text: str) -> QTextCursor:
        """在当前预览内容中按匹配文本兜底查找光标。"""
        search_text = match_text[:-3] if match_text.endswith("...") else match_text
        if not search_text:
            return QTextCursor()
        return self.content_editor.document().find(search_text)

    def show_jump_cursor(self, cursor: QTextCursor) -> None:
        """显示并居中当前跳转光标。"""
        self.content_editor.setTextCursor(cursor)
        self.apply_current_preview_highlight(cursor)
        self.content_editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.content_editor.ensureCursorVisible()
        self.content_editor.centerCursor()
        QTimer.singleShot(0, self.content_editor.centerCursor)
