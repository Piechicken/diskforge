from __future__ import annotations

from PySide6.QtWidgets import QApplication

from diskforge.gui.theme import apply_theme


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_theme_switches_between_light_and_dark_modes() -> None:
    app = _application()
    assert apply_theme(app, "light") == "light"
    assert "#F6F8FC" in app.styleSheet()
    assert apply_theme(app, "midnight") == "dark"
    assert "#111827" in app.styleSheet()
