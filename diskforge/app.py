"""Application entry point for the DiskForge desktop GUI."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from diskforge.gui.i18n import install_language_manager
from diskforge.gui.main_window import MainWindow
from diskforge.gui.settings import create_settings


STYLE = """
QMainWindow { background: #F7F8FA; }
QToolBar { background: #FFFFFF; border-bottom: 1px solid #E4E7EC; spacing: 6px; padding: 5px; }
QToolButton { border-radius: 6px; padding: 6px 9px; }
QToolButton:hover { background: #EEF4FF; }
QMenuBar { background: #FFFFFF; border-bottom: 1px solid #E4E7EC; }
QTreeWidget, QTableWidget, QTextBrowser, QPlainTextEdit { background: #FFFFFF; border: 1px solid #D0D5DD; border-radius: 7px; }
QHeaderView::section { background: #F9FAFB; border: none; border-bottom: 1px solid #EAECF0; padding: 7px; font-weight: 600; color: #344054; }
QPushButton { background: #FFFFFF; border: 1px solid #D0D5DD; border-radius: 6px; padding: 6px 10px; }
QPushButton:hover { background: #F9FAFB; }
QPushButton:disabled { color: #98A2B3; background: #F2F4F7; }
QProgressBar { border: 1px solid #D0D5DD; border-radius: 5px; text-align: center; background: #FFFFFF; }
QProgressBar::chunk { background: #2E90FA; border-radius: 4px; }
QStatusBar { background: #FFFFFF; border-top: 1px solid #E4E7EC; }
"""


def _resource_path(relative: str) -> Path:
    """Resolve bundled resources in source and frozen application layouts."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / relative


def _is_offscreen_platform() -> bool:
    return QApplication.platformName() == "offscreen"


def _qt_message_handler(message_type: QtMsgType, context, message: str) -> None:  # type: ignore[no-untyped-def]
    """Keep an expected offscreen-plugin notice out of strict test/package logs."""
    if (message == "This plugin does not support propagateSizeHints()"
            and _is_offscreen_platform()):
        return
    category = context.category or "Qt"
    print(f"{category}: {message}", file=sys.stderr)


def _exception_hook(exc_type, exc_value, exc_traceback) -> None:  # type: ignore[no-untyped-def]
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(text, file=sys.stderr)
    QMessageBox.critical(None, "DiskForge unexpected error", f"An unexpected error occurred:\n\n{exc_value}\n\nDetails were written to stderr.")


def main() -> int:
    QCoreApplication.setOrganizationName("DiskForge")
    QCoreApplication.setApplicationName("DiskForge")
    app = QApplication(sys.argv)
    qInstallMessageHandler(_qt_message_handler)
    app.setWindowIcon(QIcon(str(_resource_path("assets/icons/diskforge-icon.png"))))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    settings = create_settings(sys.argv[1:])
    install_language_manager(app, settings)
    sys.excepthook = _exception_hook
    window = MainWindow(settings=settings)
    window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
