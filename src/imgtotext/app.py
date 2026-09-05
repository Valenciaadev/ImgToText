from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from imgtotext.ui import MainWindow, build_style_sheet


def apply_system_theme(app: QApplication) -> None:
    dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    app.setStyleSheet(build_style_sheet(dark))


def resource_path(relative_path: str) -> Path:
    packaged_root = getattr(sys, "_MEIPASS", None)
    root = Path(packaged_root) if packaged_root else Path(__file__).resolve().parents[2]
    return root / relative_path


def main() -> int:
    QCoreApplication.setOrganizationName("ImgToText")
    QCoreApplication.setApplicationName("ImgToText")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    icon_path = resource_path("assets/ImgToText.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    apply_system_theme(app)
    app.styleHints().colorSchemeChanged.connect(lambda _scheme: apply_system_theme(app))
    window = MainWindow()
    window.show()
    return app.exec()
