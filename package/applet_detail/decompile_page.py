"""组合详情页反编译文件夹页面及其布局和任务入口。"""

from __future__ import annotations

from package.applet_detail.decompile_cache import DecompileCacheMixin
from package.applet_detail.decompile_content import DecompileContentMixin
from package.applet_detail.decompile_events import DecompileEventMixin
from package.applet_detail.decompile_matches import DecompileMatchMixin
from package.applet_detail.decompile_processing import DecompileProcessingMixin
from package.applet_detail.decompile_search import DecompileSearchMixin
from package.applet_detail.decompile_search_events import DecompileSearchEventMixin
from package.applet_detail.decompile_support import *
from package.applet_detail.decompile_task_state import DecompileTaskStateMixin
from package.applet_detail.decompile_tree import DecompileTreeMixin


class DecompileFolderPage(
    DecompileCacheMixin,
    DecompileProcessingMixin,
    DecompileMatchMixin,
    DecompileSearchMixin,
    DecompileTreeMixin,
    DecompileContentMixin,
    DecompileEventMixin,
    DecompileSearchEventMixin,
    DecompileTaskStateMixin,
    QWidget,
):
    """?????????????????????"""

    def __init__(
        self,
        record: dict,
        parent: QWidget | None = None,
        on_global_search_state_changed=None,
    ) -> None:
        """初始化反编译文件夹页面并在开关开启时自动启动任务。"""
        super().__init__(parent)
        self.record = dict(record)
        self.on_global_search_state_changed = on_global_search_state_changed
        self.runner: DecompileTaskRunner | None = None
        self.tree_loader: FileTreeLoader | None = None
        self.content_loader: FileContentLoader | None = None
        self.image_loader: ImageContentLoader | None = None
        self.match_loader: MatchScanLoader | None = None
        self.search_loader: SearchTextLoader | None = None
        self.tree_tasks: dict[int, QTreeWidgetItem] = {}
        self.decompile_task_id: int | None = None
        self.optimize_task_id: int | None = None
        self.match_scan_task_id: int | None = None
        self.search_task_id: int | None = None
        self.auto_matches_task_id: int | None = None
        self.export_task_id: int | None = None
        self.read_task_id: int | None = None
        self.image_task_id: int | None = None
        self.started_decompile = False
        self.pending_optimize_after_decompile = False
        self.worker_closed = False
        self.highlighter: CodeSyntaxHighlighter | None = None
        self.image_movie: QMovie | None = None
        self.image_data: QByteArray | None = None
        self.image_buffer: QBuffer | None = None
        self.match_root_item: QTreeWidgetItem | None = None
        self.match_results: list[dict] = []
        self.match_result_count = 0
        self.full_match_results_key: tuple | None = None
        self.global_search_results: list[dict] = []
        self.global_search_result_count = 0
        self.global_search_selected_result: dict = {}
        self.pending_jump: dict | None = None
        self.current_preview_match_selection: QTextEdit.ExtraSelection | None = None
        self.last_match_signature: tuple | None = None
        self.match_render_timer: QTimer | None = None
        self.match_render_index = 0
        self.match_render_keyword = ""
        self.match_render_groups: dict[str, QTreeWidgetItem] = {}
        self.match_render_counts: dict[str, int] = {}
        self.content_line_base = 1
        self.pending_tree_reveal_path = ""
        self.pending_tree_expand_paths: set[str] = set()
        self.saved_matches_load_attempted = False

        self.output_root = self.current_output_root()
        self.app_output_dir = self.output_root

        self.build_ui()
        self.reset_tree_root()
        self.start_initial_processing()

        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self.process_worker_events)
        self.event_timer.start(100)
        self.destroyed.connect(lambda _obj=None: self.shutdown_worker())

    def build_ui(self) -> None:
        """构建反编译页面的文件树和内容预览区域。"""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        status_frame = QFrame()
        status_frame.setObjectName("StatusStrip")
        status_bar = QHBoxLayout(status_frame)
        status_bar.setContentsMargins(12, 8, 12, 8)
        status_bar.setSpacing(8)
        self.status_label = QLabel()
        self.status_label.setObjectName("HintText")
        status_bar.addWidget(self.status_label, 1)
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setProperty("variant", "ghost")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_active_tasks)
        status_bar.addWidget(self.cancel_button)
        root.addWidget(status_frame)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        tree_title = QLabel("文件目录")
        tree_title.setObjectName("SectionTitle")
        left_layout.addWidget(tree_title)
        self.tree = QTreeWidget()
        self.tree.setObjectName("FileBrowserTree")
        self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self.on_tree_item_expanded)
        self.tree.itemClicked.connect(self.on_tree_item_clicked)
        left_layout.addWidget(self.tree, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        self.content_title = QLabel("文件内容")
        self.content_title.setObjectName("SectionTitle")
        right_layout.addWidget(self.content_title)
        self.inline_find_bar = self.build_inline_find_bar()
        right_layout.addWidget(self.inline_find_bar)
        self.preview_stack = QStackedWidget()
        self.content_editor = QPlainTextEdit()
        self.content_editor.setObjectName("CodePreview")
        self.content_editor.setReadOnly(True)
        self.content_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.content_editor.setFont(QFont("Cascadia Mono", 10))
        self.preview_stack.addWidget(self.content_editor)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(False)
        self.image_scroll.setWidget(self.image_label)
        self.preview_stack.addWidget(self.image_scroll)
        self.match_panel = self.build_match_panel()
        self.preview_stack.addWidget(self.match_panel)
        self.global_search_panel = self.build_global_search_panel()
        self.preview_stack.addWidget(self.global_search_panel)
        right_layout.addWidget(self.preview_stack, 1)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self.install_inline_find_shortcut()
        self.restore_global_search_state()

    def resizeEvent(self, event) -> None:
        """窗口尺寸变化时同步全局搜索列表列宽。"""
        super().resizeEvent(event)
        self.update_global_search_column_widths()

    def build_match_panel(self) -> QWidget:
        """构建匹配结果列表、过滤和导出区域。"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.match_filter_input = QLineEdit()
        self.match_filter_input.setPlaceholderText("搜索匹配文本、文件路径或规则")
        self.match_filter_input.textChanged.connect(self.refresh_match_results_view)
        toolbar.addWidget(self.match_filter_input, 1)
        self.export_json_button = QPushButton("导出 JSON")
        self.export_json_button.setProperty("variant", "ghost")
        self.export_json_button.setProperty("size", "sm")
        self.export_json_button.clicked.connect(lambda: self.export_match_results("json"))
        toolbar.addWidget(self.export_json_button)
        self.export_txt_button = QPushButton("导出 TXT")
        self.export_txt_button.setProperty("variant", "ghost")
        self.export_txt_button.setProperty("size", "sm")
        self.export_txt_button.clicked.connect(lambda: self.export_match_results("txt"))
        toolbar.addWidget(self.export_txt_button)
        layout.addLayout(toolbar)

        self.match_results_tree = QTreeWidget()
        self.match_results_tree.setColumnCount(4)
        self.match_results_tree.setHeaderLabels(["规则", "行号", "文件", "匹配内容"])
        self.match_results_tree.itemClicked.connect(self.on_match_result_clicked)
        layout.addWidget(self.match_results_tree, 1)
        return panel

    def ensure_runner(self) -> DecompileTaskRunner:
        """按需启动详情页后台 worker，避免打开卡片时阻塞 UI。"""
        if self.runner is None:
            self.runner = DecompileTaskRunner()
            self.tree_loader = FileTreeLoader(self.runner)
            self.content_loader = FileContentLoader(self.runner)
            self.image_loader = ImageContentLoader(self.runner)
            self.match_loader = MatchScanLoader(self.runner)
            self.search_loader = SearchTextLoader(self.runner)
        return self.runner

    def cancel_task(self, task_id: int | None) -> None:
        """安全取消详情页后台任务。"""
        if task_id is not None and self.runner is not None:
            self.runner.cancel(task_id)
