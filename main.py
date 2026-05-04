
from __future__ import annotations

import multiprocessing as mp
import sys

from PySide6.QtWidgets import QApplication

from package.ui.main_window import MainWindow
from package.ui.styles import APP_STYLESHEET


def main() -> int:
    mp.freeze_support()
    app = QApplication(sys.argv)
    app.setApplicationName("e0e1-wx-gui")
    app.setOrganizationName("e0e1")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
