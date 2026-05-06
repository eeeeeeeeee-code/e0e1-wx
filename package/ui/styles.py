"""定义 Qt 应用全局样式表和现代安全分析工具视觉规范。"""


APP_STYLESHEET = """
QWidget {
    background-color: #F7F9FB;
    color: #4A5568;
    font-family: "Microsoft YaHei", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #F7F9FB;
}

QLabel {
    background-color: transparent;
}

QLabel#TitleLabel {
    font-size: 20px;
    font-weight: 600;
    color: #1F2A37;
}

QLabel#SectionTitle {
    font-size: 15px;
    font-weight: 600;
    color: #1F2A37;
}

QLabel#MutedLabel {
    color: #7A8696;
}

QLabel#StatusBadge {
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#StatusBadge[status="info"] {
    background-color: #EAF2FA;
    color: #3F6F9F;
}

QLabel#StatusBadge[status="success"] {
    background-color: #EAF6EF;
    color: #2F7D57;
}

QLabel#StatusBadge[status="warning"] {
    background-color: #FFF3E3;
    color: #A66A1F;
}

QLabel#StatusBadge[status="danger"] {
    background-color: #FCEDEA;
    color: #B4534B;
}

QLabel#StatusBadge[status="neutral"] {
    background-color: #EEF3F7;
    color: #607587;
}

QLabel[status="ok"] {
    background-color: #EAF6EF;
    color: #2F7D57;
    padding: 2px 8px;
    border-radius: 10px;
}

QLabel[status="warn"] {
    background-color: #FFF3E3;
    color: #A66A1F;
    padding: 2px 8px;
    border-radius: 10px;
}

QLabel[status="error"] {
    background-color: #FCEDEA;
    color: #B4534B;
    padding: 2px 8px;
    border-radius: 10px;
}

QFrame#Surface, QFrame#Toolbar, QFrame#Card, QFrame#DetailInfo {
    background-color: #FFFFFF;
    border: 1px solid #DDE5EE;
    border-radius: 8px;
}

QFrame#Toolbar {
    background-color: #FFFFFF;
}

QFrame#Card {
    border-color: #DDE5EE;
}

QFrame#Card:hover {
    background-color: #F8FAFC;
    border-color: #D8E1EA;
}

QFrame#Card[active="true"] {
    background-color: #FFFFFF;
    border-color: #B8CFE7;
}

QFrame#DetailInfo {
    background-color: #FFFFFF;
    padding: 10px;
}

QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #DDE5EE;
    border-radius: 8px;
    margin-top: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #374151;
    font-weight: 600;
}

QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #D5DDE6;
    border-radius: 6px;
    color: #374151;
    padding: 5px 12px;
    min-height: 24px;
}

QPushButton:hover {
    background-color: #F4F7FA;
    border-color: #CCD6E0;
}

QPushButton:pressed {
    background-color: #E9EEF4;
    border-color: #C6D0DB;
}

QPushButton:disabled {
    color: #A1AAB5;
    background-color: #F3F4F6;
    border-color: #DDE5EE;
}

QPushButton[moduleButton="true"] {
    background-color: #FFFFFF;
    border: 1px solid #D5DDE6;
    border-radius: 6px;
    color: #374151;
    font-size: 13px;
    font-weight: 600;
    padding: 6px 12px;
    min-height: 32px;
}

QPushButton[moduleButton="true"]:hover {
    background-color: #F4F7FA;
    border-color: #CCD6E0;
}

QPushButton[moduleButton="true"]:checked {
    background-color: #EAF2FA;
    border-color: #8DB3D8;
    color: #3F6F9F;
}

QPushButton[moduleButton="true"][actionButton="true"] {
    background-color: #FFFFFF;
    border-color: #D5DDE6;
    color: #374151;
}

QPushButton[routeCompactButton="true"] {
    background-color: #FFFFFF;
    border: 1px solid #D5DDE6;
    color: #374151;
    padding: 5px 12px;
    min-height: 28px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton[routeCompactButton="true"]:hover {
    background-color: #F4F7FA;
    border-color: #CCD6E0;
    color: #1F2A37;
}

QPushButton[routeCompactButton="true"]:pressed {
    background-color: #E9EEF4;
    border-color: #C6D0DB;
    color: #1F2A37;
}

QPushButton[routeCompactButton="true"]:checked {
    background-color: #EAF2FA;
    border-color: #8DB3D8;
    color: #3F6F9F;
}

QPushButton[routeCompactButton="true"]:disabled {
    background-color: #F3F4F6;
    border-color: #DDE5EE;
    color: #A1AAB5;
}

QPushButton[logSourceButton="true"]:checked {
    background-color: #EAF2FA;
    border-color: #8DB3D8;
    color: #3F6F9F;
    font-weight: 600;
}

QPushButton#PrimaryButton, QPushButton#primaryBtn {
    background-color: #3F6F9F;
    border-color: #3F6F9F;
    color: #FFFFFF;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover, QPushButton#primaryBtn:hover {
    background-color: #365F89;
    border-color: #365F89;
}

QPushButton#PrimaryButton:pressed, QPushButton#primaryBtn:pressed {
    background-color: #2E5276;
    border-color: #2E5276;
}

QPushButton#DangerButton {
    background-color: #FFFFFF;
    border-color: #EAB7B0;
    color: #B4534B;
}

QPushButton#DangerButton:hover {
    background-color: #FCEDEA;
    border-color: #DDA19C;
}

QLineEdit, QSpinBox, QPlainTextEdit, QTextEdit, QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #D5DDE6;
    border-radius: 6px;
    color: #1F2A37;
    padding: 6px;
    selection-background-color: #EAF2FA;
    selection-color: #1F2A37;
}

QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    border-color: #8DB3D8;
}

QPlainTextEdit, QTextEdit, QPlainTextEdit#CodePreview {
    background-color: #FFFFFF;
    border: 1px solid #D5DDE6;
    border-radius: 6px;
    color: #1F2A37;
    font-family: "JetBrains Mono", "Cascadia Mono", "Consolas", monospace;
    padding: 8px;
}

QCheckBox {
    background-color: transparent;
    color: #4A5568;
    spacing: 8px;
}

QTabWidget::pane {
    border: none;
    background-color: transparent;
}

QTabBar::tab {
    background-color: #EEF3F7;
    border: 1px solid #E3E9F0;
    border-radius: 6px;
    color: #4A5568;
    font-weight: 600;
    padding: 6px 14px;
    margin-right: 6px;
}

QTabBar::tab:hover {
    background-color: #F5F8FB;
    color: #374151;
}

QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #3F6F9F;
    border-color: #B8CFE7;
}

QTableWidget, QTreeWidget, QListWidget {
    background-color: #FFFFFF;
    alternate-background-color: #FAFBFC;
    border: 1px solid #DDE5EE;
    border-radius: 8px;
    color: #1F2A37;
    gridline-color: #EEF2F6;
    selection-background-color: #EAF2FA;
    selection-color: #1F2A37;
}

QTableWidget::item, QTreeWidget::item, QListWidget::item {
    padding: 6px;
    border: none;
}

QTableWidget::item:hover, QTreeWidget::item:hover, QListWidget::item:hover {
    background-color: #F7F9FB;
}

QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #EAF2FA;
    color: #1F2A37;
}

QHeaderView::section {
    background-color: #F3F6FA;
    color: #374151;
    border: none;
    border-bottom: 1px solid #DDE5EE;
    padding: 6px;
    font-weight: 600;
}

QScrollArea {
    border: 0;
    background-color: #F7F9FB;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #D6DEE7;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #97A5B5;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #D6DEE7;
    border-radius: 4px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #97A5B5;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background-color: transparent;
}
"""
