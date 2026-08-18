"""Render a populated FAT-image workspace in an offscreen Qt session."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.gui.main_window import MainWindow


def main() -> int:
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    image = output / "demo.img"
    source = output / "README.TXT"
    source.write_text("DiskForge GUI demo image\n", encoding="utf-8")
    create_fat_image(image, 4 * 1024 * 1024, FileSystemType.FAT12, "DEMO")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([source])
    finally:
        filesystem.close()
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._open_path(image)
    window.show()
    application.processEvents()
    if not window.grab().save(str(output / "open-image-window.png")):
        raise RuntimeError("Unable to save populated main window screenshot")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
