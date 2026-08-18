from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.formats import create_fixed_vhd
from diskforge.core.models import FileSystemType
from diskforge.gui.main_window import MainWindow


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_browses_fixed_vhd_through_temporary_session(tmp_path: Path) -> None:
    _application()
    raw = create_fat_image(tmp_path / "source.img", 32 * 1024 * 1024, FileSystemType.FAT16, "VHD")
    host_file = tmp_path / "inside.txt"
    host_file.write_text("vhd browse", encoding="utf-8")
    filesystem = FatImageFilesystem(raw)
    try:
        filesystem.inject([host_file])
    finally:
        filesystem.close()
    vhd = tmp_path / "source.vhd"
    create_fixed_vhd(raw, vhd)
    window = MainWindow()
    window._open_path(vhd)
    assert window.current_fs is not None
    assert window.current_browse_session is not None
    temporary = window.current_browse_session.temporary_directory
    assert any(entry.name == "inside.txt" for entry in window.current_entries)
    window.close_image()
    assert temporary is not None and not temporary.exists()
