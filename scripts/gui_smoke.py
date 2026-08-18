"""Offscreen smoke test used by local validation and CI."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from diskforge.gui.main_window import MainWindow


def main() -> int:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    application.processEvents()
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    if not window.grab().save(str(output / "main-window.png")):
        raise RuntimeError("Unable to save main window screenshot")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
