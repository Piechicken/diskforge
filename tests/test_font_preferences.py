from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from diskforge.gui.main_window import MainWindow


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_applies_persisted_interface_font_size(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = _application()
    original = app.font()
    settings = QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)
    settings.setValue("interface_font_family", original.family())
    settings.setValue("interface_font_size", 15)
    window = MainWindow(settings=settings)
    assert app.font().pointSize() == 15
    window.close()
