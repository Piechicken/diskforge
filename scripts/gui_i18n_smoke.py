"""Offscreen runtime-localization verification for DiskForge."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from diskforge.gui.i18n import LANGUAGES, install_language_manager
from diskforge.gui.main_window import MainWindow


def main() -> int:
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(Path("artifacts") / "i18n-smoke.ini"), QSettings.Format.IniFormat)
    manager = install_language_manager(app, settings)
    window = MainWindow()
    window.show()
    app.processEvents()

    for language in LANGUAGES:
        manager.set_language(language.code)
        app.processEvents()
        if manager.language.code != language.code:
            raise RuntimeError(f"Language selection failed for {language.code}")
        expected = Qt.LayoutDirection.RightToLeft if language.code == "ar" else Qt.LayoutDirection.LeftToRight
        if app.layoutDirection() != expected:
            raise RuntimeError(f"Layout direction mismatch for {language.code}")

    manager.set_language("ar")
    app.processEvents()
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    if not window.grab().save(str(output / "main-window-ar.png")):
        raise RuntimeError("Unable to save Arabic GUI screenshot")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
