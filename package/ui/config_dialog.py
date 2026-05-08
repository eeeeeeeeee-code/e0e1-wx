"""提供小程序 packages 路径等应用配置编辑弹窗。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from package.config.defaults import (
    DEFAULT_APPLET_PACKAGES_PATH,
    DEFAULT_DEVTOOLS_CDP_PORT,
    DEFAULT_MINIAPP_DEBUG_PORT,
    MAX_DEVTOOLS_PORT,
    MAX_ROUTE_TRAVERSE_INTERVAL_SECONDS,
    MAX_CLOUD_CALL_TIMEOUT_SECONDS,
    MIN_DEVTOOLS_PORT,
    MIN_ROUTE_TRAVERSE_INTERVAL_SECONDS,
    MIN_CLOUD_CALL_TIMEOUT_SECONDS,
    normalize_cloud_call_timeout,
    normalize_devtools_port,
    normalize_route_traverse_interval,
)
from package.storage.state_store import StateStore


class ConfigDialog(QDialog):
    def __init__(self, store: StateStore, parent: QWidget | None = None) -> None:
        """初始化 Config 配置窗口。"""
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Config 配置")
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Config 配置")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        path_label = QLabel("微信小程序文件位置")
        root.addWidget(path_label)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        config = self.store.snapshot().get("config", {})
        current_path = str(config.get("applet_packages_path", DEFAULT_APPLET_PACKAGES_PATH))
        self.applet_path_input = QLineEdit()
        self.applet_path_input.setPlaceholderText(DEFAULT_APPLET_PACKAGES_PATH)
        self.applet_path_input.setText(current_path)
        path_row.addWidget(self.applet_path_input, 1)

        browse_button = QPushButton("选择")
        browse_button.setProperty("variant", "ghost")
        browse_button.clicked.connect(self.select_applet_path)
        path_row.addWidget(browse_button)
        root.addLayout(path_row)

        timeout_label = QLabel("云函数调用超时时间")
        root.addWidget(timeout_label)

        timeout_row = QHBoxLayout()
        timeout_row.setSpacing(8)
        self.cloud_timeout_input = QSpinBox()
        self.cloud_timeout_input.setRange(MIN_CLOUD_CALL_TIMEOUT_SECONDS, MAX_CLOUD_CALL_TIMEOUT_SECONDS)
        self.cloud_timeout_input.setSuffix(" 秒")
        self.cloud_timeout_input.setValue(normalize_cloud_call_timeout(config.get("cloud_call_timeout_seconds")))
        timeout_row.addWidget(self.cloud_timeout_input)
        timeout_hint = QLabel("默认 5 秒；超时后会把结果显示为调用超时")
        timeout_hint.setObjectName("MutedLabel")
        timeout_row.addWidget(timeout_hint, 1)
        root.addLayout(timeout_row)

        route_interval_label = QLabel("遍历全部路由跳转间隔")
        root.addWidget(route_interval_label)

        route_interval_row = QHBoxLayout()
        route_interval_row.setSpacing(8)
        self.route_interval_input = QDoubleSpinBox()
        self.route_interval_input.setRange(
            MIN_ROUTE_TRAVERSE_INTERVAL_SECONDS,
            MAX_ROUTE_TRAVERSE_INTERVAL_SECONDS,
        )
        self.route_interval_input.setDecimals(1)
        self.route_interval_input.setSingleStep(0.5)
        self.route_interval_input.setSuffix(" 秒")
        self.route_interval_input.setValue(
            float(normalize_route_traverse_interval(config.get("route_traverse_interval_seconds")))
        )
        route_interval_row.addWidget(self.route_interval_input)
        route_interval_hint = QLabel("默认 2 秒；断连或单页失败时继续遍历后续路由")
        route_interval_hint.setObjectName("MutedLabel")
        route_interval_row.addWidget(route_interval_hint, 1)
        root.addLayout(route_interval_row)

        miniapp_port_label = QLabel("小程序回连端口")
        root.addWidget(miniapp_port_label)

        miniapp_port_row = QHBoxLayout()
        miniapp_port_row.setSpacing(8)
        self.miniapp_debug_port_input = QSpinBox()
        self.miniapp_debug_port_input.setRange(MIN_DEVTOOLS_PORT, MAX_DEVTOOLS_PORT)
        self.miniapp_debug_port_input.setValue(
            normalize_devtools_port(config.get("miniapp_debug_port"), DEFAULT_MINIAPP_DEBUG_PORT)
        )
        miniapp_port_row.addWidget(self.miniapp_debug_port_input)
        miniapp_port_hint = QLabel("默认 9421；小程序端需要连接到这个端口")
        miniapp_port_hint.setObjectName("MutedLabel")
        miniapp_port_row.addWidget(miniapp_port_hint, 1)
        root.addLayout(miniapp_port_row)

        devtools_port_label = QLabel("小程序 DevTools 端口")
        root.addWidget(devtools_port_label)

        devtools_port_row = QHBoxLayout()
        devtools_port_row.setSpacing(8)
        self.devtools_cdp_port_input = QSpinBox()
        self.devtools_cdp_port_input.setRange(MIN_DEVTOOLS_PORT, MAX_DEVTOOLS_PORT)
        self.devtools_cdp_port_input.setValue(
            normalize_devtools_port(config.get("devtools_cdp_port"), DEFAULT_DEVTOOLS_CDP_PORT)
        )
        devtools_port_row.addWidget(self.devtools_cdp_port_input)
        devtools_port_hint = QLabel("默认 62000；被占用时从该端口向后查找可用端口")
        devtools_port_hint.setObjectName("MutedLabel")
        devtools_port_row.addWidget(devtools_port_hint, 1)
        root.addLayout(devtools_port_row)

        self.status_label = QLabel("已自动保存")
        self.status_label.setObjectName("HintText")
        root.addWidget(self.status_label)

        root.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.applet_path_input.textChanged.connect(self.save_applet_path)
        self.cloud_timeout_input.valueChanged.connect(self.save_cloud_timeout)
        self.route_interval_input.valueChanged.connect(self.save_route_traverse_interval)
        self.miniapp_debug_port_input.valueChanged.connect(self.save_miniapp_debug_port)
        self.devtools_cdp_port_input.valueChanged.connect(self.save_devtools_cdp_port)
        self.setMinimumSize(720, 430)

    def save_applet_path(self, path: str) -> None:
        """自动保存微信小程序文件位置配置。"""
        self.store.update_config("applet_packages_path", path.strip())
        self.status_label.setText("已自动保存")

    def save_cloud_timeout(self, value: int) -> None:
        """自动保存云函数调用超时时间配置。"""
        self.store.update_config("cloud_call_timeout_seconds", normalize_cloud_call_timeout(value))
        self.status_label.setText("已自动保存")

    def save_route_traverse_interval(self, value: float) -> None:
        """自动保存遍历全部路由跳转间隔配置。"""
        self.store.update_config("route_traverse_interval_seconds", normalize_route_traverse_interval(value))
        self.status_label.setText("已自动保存")

    def save_miniapp_debug_port(self, value: int) -> None:
        """自动保存小程序回连端口配置。"""
        self.store.update_config("miniapp_debug_port", normalize_devtools_port(value, DEFAULT_MINIAPP_DEBUG_PORT))
        self.status_label.setText("已自动保存")

    def save_devtools_cdp_port(self, value: int) -> None:
        """自动保存小程序 DevTools 代理端口配置。"""
        self.store.update_config("devtools_cdp_port", normalize_devtools_port(value, DEFAULT_DEVTOOLS_CDP_PORT))
        self.status_label.setText("已自动保存")

    def select_applet_path(self) -> None:
        """打开目录选择器并更新小程序文件位置。"""
        current_path = self.applet_path_input.text().strip() or DEFAULT_APPLET_PACKAGES_PATH
        selected_path = QFileDialog.getExistingDirectory(self, "选择微信小程序文件位置", current_path)
        if selected_path:
            self.applet_path_input.setText(selected_path)
