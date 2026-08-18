from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from diskforge.gui.main_window import MainWindow


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_directory_view_mode_switches_and_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _application()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow()
    try:
        assert window.view_stack.count() == 2
        window.set_view_mode("icons")
        assert window.view_stack.currentWidget() is window.icon_view
        assert window.action_view_icons.isChecked()
        assert window.settings.value("directory_view") == "icons"
        window.set_view_mode("details")
        assert window.view_stack.currentWidget() is window.table
        assert window.action_view_details.isChecked()
    finally:
        window.close()
