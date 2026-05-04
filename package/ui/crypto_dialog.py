"""提供微信加解密和密钥派生任务的交互弹窗。"""

from __future__ import annotations

import queue

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from package.crypto import CryptoTaskRunner
from package.ui.constants import UI_EVENT_BATCH_LIMIT


class CryptoDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化微信加密解密窗口和独立后台任务进程。"""
        super().__init__(parent)
        self.setWindowTitle("微信加密解密")
        self.setModal(True)
        self.runner = CryptoTaskRunner()
        self.active_task_id: int | None = None
        self.active_operation = ""
        self.worker_closed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("微信加密解密")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_aes_tab(), "AES-CBC")
        self.tabs.addTab(self.build_key_tab(), "PBKDF2 密钥")
        root.addWidget(self.tabs, 1)

        status_row = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("MutedLabel")
        status_row.addWidget(self.status_label, 1)
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_current_task)
        status_row.addWidget(self.cancel_button)
        root.addLayout(status_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self.process_crypto_events)
        self.event_timer.start(100)

        self.setMinimumSize(760, 620)

    def build_aes_tab(self) -> QWidget:
        """构建 AES-CBC 加密解密页。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        key_label = QLabel("SessionKey(Base64)")
        self.aes_key_input = QLineEdit()
        self.aes_key_input.setPlaceholderText("请输入 SessionKey，Base64 格式")
        form.addWidget(key_label, 0, 0)
        form.addWidget(self.aes_key_input, 0, 1)

        iv_label = QLabel("IV(Base64)")
        self.aes_iv_input = QLineEdit()
        self.aes_iv_input.setPlaceholderText("16 字节 IV 的 Base64")
        form.addWidget(iv_label, 1, 0)
        form.addWidget(self.aes_iv_input, 1, 1)
        layout.addLayout(form)

        input_label = QLabel("输入内容")
        layout.addWidget(input_label)
        self.aes_input_text = QPlainTextEdit()
        self.aes_input_text.setObjectName("CodePreview")
        self.aes_input_text.setMinimumHeight(130)
        self.aes_input_text.setPlaceholderText("加密时输入明文，解密时输入 Base64 密文")
        layout.addWidget(self.aes_input_text, 1)

        action_row = QHBoxLayout()
        self.encrypt_button = QPushButton("加密")
        self.encrypt_button.setObjectName("PrimaryButton")
        self.encrypt_button.clicked.connect(lambda: self.submit_aes_task("encrypt"))
        action_row.addWidget(self.encrypt_button)

        self.decrypt_button = QPushButton("解密")
        self.decrypt_button.clicked.connect(lambda: self.submit_aes_task("decrypt"))
        action_row.addWidget(self.decrypt_button)

        self.clear_aes_button = QPushButton("清空")
        self.clear_aes_button.clicked.connect(self.clear_aes)
        action_row.addWidget(self.clear_aes_button)
        action_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addLayout(action_row)

        output_label = QLabel("输出内容")
        layout.addWidget(output_label)
        self.aes_output_text = QPlainTextEdit()
        self.aes_output_text.setObjectName("CodePreview")
        self.aes_output_text.setReadOnly(True)
        self.aes_output_text.setMinimumHeight(130)
        layout.addWidget(self.aes_output_text, 1)
        return widget

    def build_key_tab(self) -> QWidget:
        """构建 PBKDF2 密钥派生页。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        wxid_label = QLabel("wxid")
        self.wxid_input = QLineEdit()
        self.wxid_input.setPlaceholderText("用于 PBKDF2 的 wxid")
        form.addWidget(wxid_label, 0, 0)
        form.addWidget(self.wxid_input, 0, 1)

        salt_label = QLabel("salt")
        self.salt_input = QLineEdit()
        self.salt_input.setPlaceholderText("用于 PBKDF2 的 salt")
        form.addWidget(salt_label, 1, 0)
        form.addWidget(self.salt_input, 1, 1)

        iv_label = QLabel("校验 IV(原文)")
        self.derive_iv_input = QLineEdit()
        self.derive_iv_input.setPlaceholderText("可选，16 字节原文 IV")
        form.addWidget(iv_label, 2, 0)
        form.addWidget(self.derive_iv_input, 2, 1)
        layout.addLayout(form)

        action_row = QHBoxLayout()
        self.derive_button = QPushButton("生成 AES Key")
        self.derive_button.setObjectName("PrimaryButton")
        self.derive_button.clicked.connect(self.submit_key_derivation)
        action_row.addWidget(self.derive_button)

        self.clear_key_button = QPushButton("清空")
        self.clear_key_button.clicked.connect(self.clear_key_inputs)
        action_row.addWidget(self.clear_key_button)
        action_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addLayout(action_row)

        output_label = QLabel("派生结果")
        layout.addWidget(output_label)
        self.derive_output_text = QPlainTextEdit()
        self.derive_output_text.setObjectName("CodePreview")
        self.derive_output_text.setReadOnly(True)
        self.derive_output_text.setMinimumHeight(210)
        layout.addWidget(self.derive_output_text, 1)
        return widget

    def submit_aes_task(self, operation: str) -> None:
        """校验 AES 表单并把加密或解密任务提交给后台进程。"""
        if self.active_task_id is not None:
            return
        key_b64 = self.aes_key_input.text().strip()
        iv_b64 = self.aes_iv_input.text().strip()
        data = self.aes_input_text.toPlainText()
        if not key_b64:
            QMessageBox.warning(self, "缺少密钥", "请先输入 SessionKey(Base64)。")
            return
        if not iv_b64:
            QMessageBox.warning(self, "缺少 IV", "请先输入 IV(Base64)。")
            return
        if not data.strip():
            QMessageBox.warning(self, "缺少输入", "请先输入需要处理的内容。")
            return

        self.active_operation = operation
        self.active_task_id = self.runner.submit(
            operation,
            {
                "key_b64": key_b64,
                "iv_b64": iv_b64,
                "data": data,
            },
        )
        self.set_busy(True)
        self.set_status(f"{self.operation_name(operation)}处理中")

    def submit_key_derivation(self) -> None:
        """校验 PBKDF2 表单并把密钥派生任务提交给后台进程。"""
        if self.active_task_id is not None:
            return
        wxid = self.wxid_input.text().strip()
        salt = self.salt_input.text().strip()
        iv = self.derive_iv_input.text()
        if not wxid:
            QMessageBox.warning(self, "缺少 wxid", "请先输入 wxid。")
            return
        if not salt:
            QMessageBox.warning(self, "缺少 salt", "请先输入 salt。")
            return

        self.active_operation = "derive_key"
        self.active_task_id = self.runner.submit(
            "derive_key",
            {
                "wxid": wxid,
                "salt": salt,
                "iv": iv,
            },
        )
        self.set_busy(True)
        self.set_status("密钥派生处理中")

    def cancel_current_task(self) -> None:
        """请求取消当前正在执行的加解密任务。"""
        if self.active_task_id is None:
            return
        self.runner.cancel(self.active_task_id)
        self.set_status("正在取消任务")

    def process_crypto_events(self) -> None:
        """从加解密进程队列中消费事件并更新窗口状态。"""
        for _index in range(UI_EVENT_BATCH_LIMIT):
            try:
                event = self.runner.get_event_nowait()
            except queue.Empty:
                break

            task_id = event.get("task_id")
            if task_id is not None and self.active_task_id is not None and task_id != self.active_task_id:
                continue

            event_type = event.get("type")
            operation = str(event.get("operation") or self.active_operation)
            if event_type == "crypto_started":
                self.set_status(f"{self.operation_name(operation)}处理中")
            elif event_type == "crypto_result":
                self.handle_crypto_result(operation, event.get("result", {}))
                self.finish_task(f"{self.operation_name(operation)}完成")
            elif event_type == "crypto_error":
                QMessageBox.warning(self, "加解密失败", str(event.get("message", "未知错误")))
                self.finish_task("任务失败")
            elif event_type == "crypto_cancelled":
                self.finish_task("任务已取消")

    def handle_crypto_result(self, operation: str, result: dict) -> None:
        """把后台任务结果写入对应输出框。"""
        if operation == "derive_key":
            key_b64 = str(result.get("key_b64", ""))
            key_hex = str(result.get("key_hex", ""))
            self.derive_output_text.setPlainText(f"Base64:\n{key_b64}\n\nHex:\n{key_hex}")
            if key_b64:
                self.aes_key_input.setText(key_b64)
            return
        self.aes_output_text.setPlainText(str(result.get("text", "")))

    def finish_task(self, message: str) -> None:
        """结束当前任务并恢复可点击控件状态。"""
        self.active_task_id = None
        self.active_operation = ""
        self.set_busy(False)
        self.set_status(message)

    def set_busy(self, busy: bool) -> None:
        """根据任务运行状态启用或禁用操作控件。"""
        self.encrypt_button.setEnabled(not busy)
        self.decrypt_button.setEnabled(not busy)
        self.derive_button.setEnabled(not busy)
        self.clear_aes_button.setEnabled(not busy)
        self.clear_key_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def set_status(self, message: str) -> None:
        """刷新底部状态提示文本。"""
        self.status_label.setText(message)

    def operation_name(self, operation: str) -> str:
        """返回任务类型对应的中文名称。"""
        names = {
            "encrypt": "AES 加密",
            "decrypt": "AES 解密",
            "derive_key": "密钥派生",
        }
        return names.get(operation, "加解密任务")

    def clear_aes(self) -> None:
        """清空 AES-CBC 页的输入和输出。"""
        self.aes_key_input.clear()
        self.aes_iv_input.clear()
        self.aes_input_text.clear()
        self.aes_output_text.clear()

    def clear_key_inputs(self) -> None:
        """清空 PBKDF2 密钥派生页的输入和输出。"""
        self.wxid_input.clear()
        self.salt_input.clear()
        self.derive_iv_input.clear()
        self.derive_output_text.clear()

    def shutdown_worker(self) -> None:
        """关闭窗口时停止加解密后台进程。"""
        if self.worker_closed:
            return
        self.worker_closed = True
        self.event_timer.stop()
        if self.active_task_id is not None:
            self.runner.cancel(self.active_task_id)
        self.runner.shutdown(wait=False)

    def reject(self) -> None:
        """关闭对话框并释放后台进程。"""
        self.shutdown_worker()
        super().reject()

    def closeEvent(self, event) -> None:
        """处理窗口关闭事件并释放后台进程。"""
        self.shutdown_worker()
        super().closeEvent(event)
