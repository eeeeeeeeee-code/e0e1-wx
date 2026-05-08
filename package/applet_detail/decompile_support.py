"""提供反编译详情页共享常量、语法高亮、工具函数和异步加载器。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import queue
import re
import time
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QMovie, QPixmap, QShortcut, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from package.decompiler import DecompileTaskRunner
from package.decompiler.core import normalize_new_folder_names, output_folder_display_name, safe_output_folder_name


PATH_ROLE = Qt.ItemDataRole.UserRole
IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1
LOADED_ROLE = Qt.ItemDataRole.UserRole + 2
MATCH_ROOT_ROLE = Qt.ItemDataRole.UserRole + 3
MATCH_RESULT_ROLE = Qt.ItemDataRole.UserRole + 4
CACHE_DIR_NAME = ".e0e1_cache"
CACHE_FILE_NAME = "decompile_page_state.json"
CACHE_VERSION = 1
CACHE_SECTION_LIMIT = 80
MATCH_RENDER_BATCH_SIZE = 120
WORKER_EVENT_BATCH_LIMIT = 80
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    ".json": "json",
    ".jsonc": "json",
    ".wxml": "html",
    ".wxss": "css",
    ".xml": "xml",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".md": "markdown",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".rs": "rust",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".dart": "dart",
    ".lua": "lua",
    ".sql": "sql",
    ".vue": "html",
    ".svelte": "html",
}

MATCH_CELL_FOREGROUND = "#7C2D12"
MATCH_CELL_BACKGROUND = "#FDE68A"
PREVIEW_HIGHLIGHT_FOREGROUND = "#111827"
PREVIEW_HIGHLIGHT_BACKGROUND = "#FBBF24"


KEYWORDS_BY_LANGUAGE = {
    "python": {
        "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif", "else",
        "except", "False", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "None",
        "nonlocal", "not", "or", "pass", "raise", "return", "True", "try", "while", "with", "yield",
    },
    "javascript": {
        "async", "await", "break", "case", "catch", "class", "const", "continue", "debugger", "default",
        "delete", "do", "else", "export", "extends", "false", "finally", "for", "from", "function", "if",
        "import", "in", "instanceof", "let", "new", "null", "return", "static", "super", "switch", "this",
        "throw", "true", "try", "typeof", "undefined", "var", "void", "while", "with", "yield",
    },
    "typescript": {
        "abstract", "any", "as", "async", "await", "boolean", "break", "case", "catch", "class", "const",
        "continue", "declare", "default", "do", "else", "enum", "export", "extends", "false", "finally",
        "for", "from", "function", "if", "implements", "import", "in", "interface", "let", "module",
        "namespace", "new", "null", "number", "private", "protected", "public", "readonly", "return",
        "static", "string", "super", "switch", "this", "throw", "true", "try", "type", "undefined", "var",
        "void", "while",
    },
    "go": {
        "break", "case", "chan", "const", "continue", "default", "defer", "else", "fallthrough", "for",
        "func", "go", "goto", "if", "import", "interface", "map", "package", "range", "return", "select",
        "struct", "switch", "type", "var",
    },
    "java": {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const",
        "continue", "default", "do", "double", "else", "enum", "extends", "final", "finally", "float",
        "for", "if", "implements", "import", "instanceof", "int", "interface", "long", "new", "package",
        "private", "protected", "public", "return", "short", "static", "strictfp", "super", "switch",
        "synchronized", "this", "throw", "throws", "transient", "try", "void", "volatile", "while",
    },
    "css": {
        "align-items", "background", "border", "color", "display", "flex", "font-size", "grid", "height",
        "justify-content", "margin", "padding", "position", "width",
    },
    "c": {"auto", "break", "case", "char", "const", "continue", "default", "do", "double", "else", "enum", "extern", "float", "for", "goto", "if", "int", "long", "register", "return", "short", "signed", "sizeof", "static", "struct", "switch", "typedef", "union", "unsigned", "void", "volatile", "while"},
    "cpp": {"alignas", "alignof", "auto", "bool", "break", "case", "catch", "class", "const", "constexpr", "continue", "default", "delete", "do", "else", "enum", "explicit", "export", "extern", "false", "for", "friend", "if", "inline", "namespace", "new", "noexcept", "nullptr", "operator", "private", "protected", "public", "return", "static", "struct", "switch", "template", "this", "throw", "true", "try", "typedef", "typename", "using", "virtual", "void", "while"},
}


def record_new_folders(record: dict) -> list[str]:
    """从小程序记录中解析绑定的 new_folder 列表。"""
    raw_list = record.get("wxids_list")
    if isinstance(raw_list, list):
        return normalize_new_folder_names([str(item) for item in raw_list])
    display = str(record.get("wxids_display") or "").strip()
    if display:
        return normalize_new_folder_names([part.strip() for part in display.split(",")])
    return normalize_new_folder_names([str(record.get("wxid") or "")])


def is_image_file(path: Path) -> bool:
    """根据文件后缀判断是否走图片预览。"""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def language_for_path(path: Path) -> str:
    """根据文件后缀识别代码语言。"""
    return LANGUAGE_BY_EXTENSION.get(path.suffix.lower(), "")


def make_text_format(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    """创建语法高亮文本格式。"""
    text_format = QTextCharFormat()
    text_format.setForeground(QColor(color))
    if bold:
        text_format.setFontWeight(QFont.Weight.Bold)
    if italic:
        text_format.setFontItalic(True)
    return text_format


def emphasize_match_tree_cell(item: QTreeWidgetItem, column: int) -> None:
    """Apply a stronger visual style to the match-content column."""
    font = item.font(column)
    font.setBold(True)
    item.setFont(column, font)
    item.setForeground(column, QBrush(QColor(MATCH_CELL_FOREGROUND)))
    item.setBackground(column, QBrush(QColor(MATCH_CELL_BACKGROUND)))


def build_preview_match_selection(cursor: QTextCursor) -> QTextEdit.ExtraSelection:
    """Build a strong explicit highlight selection for the active preview match."""
    selection = QTextEdit.ExtraSelection()
    selection.cursor = QTextCursor(cursor)
    selection.format.setBackground(QColor(PREVIEW_HIGHLIGHT_BACKGROUND))
    selection.format.setForeground(QColor(PREVIEW_HIGHLIGHT_FOREGROUND))
    selection.format.setFontWeight(QFont.Weight.Bold)
    return selection


class CodeSyntaxHighlighter(QSyntaxHighlighter):
    """轻量级代码高亮器，按语言后缀生成常用规则。"""

    def __init__(self, document, language: str) -> None:
        super().__init__(document)
        self.language = language
        self.keyword_format = make_text_format("#3F6F9F", bold=True)
        self.string_format = make_text_format("#2F7D57")
        self.comment_format = make_text_format("#6F7B88", italic=True)
        self.number_format = make_text_format("#A66A1F")
        self.tag_format = make_text_format("#735C9E", bold=True)
        self.attr_format = make_text_format("#8A6A2F")
        self.key_format = make_text_format("#3A6996")
        self.rules = self.build_rules(language)

    def build_rules(self, language: str) -> list[tuple[re.Pattern, QTextCharFormat]]:
        """生成当前语言的单行高亮规则。"""
        rules: list[tuple[re.Pattern, QTextCharFormat]] = [
            (re.compile(r"\b\d+(?:\.\d+)?\b"), self.number_format),
            (re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`'), self.string_format),
        ]
        keywords = KEYWORDS_BY_LANGUAGE.get(language, set())
        if not keywords and language in {"json", "yaml", "toml", "ini", "markdown"}:
            keywords = {"true", "false", "null", "yes", "no", "on", "off"}
        if keywords:
            pattern = r"\b(" + "|".join(sorted(re.escape(keyword) for keyword in keywords)) + r")\b"
            rules.append((re.compile(pattern), self.keyword_format))
        if language == "json":
            rules.append((re.compile(r'"(?:\\.|[^"\\])*"(?=\s*:)'), self.key_format))
        if language in {"html", "xml"}:
            rules.extend(
                [
                    (re.compile(r"</?[\w:-]+"), self.tag_format),
                    (re.compile(r"\b[\w:-]+(?=\s*=)"), self.attr_format),
                    (re.compile(r"<!--.*?-->"), self.comment_format),
                ]
            )
        if language in {"python", "shell", "powershell", "ruby"}:
            rules.append((re.compile(r"#.*$"), self.comment_format))
        elif language == "batch":
            rules.append((re.compile(r"\bREM\b.*$", re.IGNORECASE), self.comment_format))
        else:
            rules.extend(
                [
                    (re.compile(r"//.*$"), self.comment_format),
                    (re.compile(r"/\*.*?\*/"), self.comment_format),
                ]
            )
        return rules

    def highlightBlock(self, text: str) -> None:
        """对当前代码块应用规则。"""
        for pattern, text_format in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)


class LogicalVisibilityWidget(QWidget):
    """在未显示父窗口的测试环境下，保留组件的逻辑显隐状态。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._requested_visible = True

    def setVisible(self, visible: bool) -> None:
        self._requested_visible = bool(visible)
        super().setVisible(visible)

    def isVisible(self) -> bool:
        return self._requested_visible


def create_loading_item() -> QTreeWidgetItem:
    """创建不可点击的文件树加载占位节点。"""
    item = QTreeWidgetItem(["加载中..."])
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
    return item


class FileTreeLoader:
    """文件树目录懒加载任务封装。"""

    def __init__(self, runner: DecompileTaskRunner) -> None:
        """保存反编译任务调度器引用。"""
        self.runner = runner

    def load(self, path: Path) -> int:
        """提交单层目录加载任务并返回任务编号。"""
        return self.runner.submit("list_dir", {"path": str(path)})


class FileContentLoader:
    """文件内容分块读取任务封装。"""

    def __init__(self, runner: DecompileTaskRunner) -> None:
        """保存反编译任务调度器引用。"""
        self.runner = runner

    def load(self, path: Path, jump: dict | None = None) -> int:
        """提交文件分块读取任务并返回任务编号。"""
        payload = {"path": str(path)}
        if isinstance(jump, dict):
            payload["target_line"] = int(jump.get("line_number") or 0)
        return self.runner.submit("read_file", payload)


class ImageContentLoader:
    """图片内容异步读取任务封装。"""

    def __init__(self, runner: DecompileTaskRunner) -> None:
        """保存反编译任务调度器引用。"""
        self.runner = runner

    def load(self, path: Path) -> int:
        """提交图片字节读取任务并返回任务编号。"""
        return self.runner.submit("read_binary", {"path": str(path)})


class MatchScanLoader:
    """正则匹配扫描任务封装。"""

    def __init__(self, runner: DecompileTaskRunner) -> None:
        """保存反编译任务调度器引用。"""
        self.runner = runner

    def scan(self, output_dirs: list[str], rules: list[dict]) -> int:
        """提交正则匹配扫描任务并返回任务编号。"""
        return self.runner.submit("scan_matches", {"output_dirs": output_dirs, "rules": rules})


class SearchTextLoader:
    """全局文本搜索任务封装。"""

    def __init__(self, runner: DecompileTaskRunner) -> None:
        """保存反编译任务调度器引用。"""
        self.runner = runner

    def search(self, output_dirs: list[str], query: str, regex_enabled: bool) -> int:
        """提交全局搜索任务并返回任务编号。"""
        return self.runner.submit(
            "search_text",
            {
                "output_dirs": output_dirs,
                "query": str(query or ""),
                "regex_enabled": bool(regex_enabled),
            },
        )
