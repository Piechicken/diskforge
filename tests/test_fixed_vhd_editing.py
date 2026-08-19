from __future__ import annotations

from pathlib import Path

from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.formats import create_editable_fixed_vhd_copy, create_fixed_vhd, validate_fixed_vhd_fat
from diskforge.core.models import FileSystemType


def test_fixed_vhd_fat_can_be_edited_only_through_an_independent_validated_copy(tmp_path: Path) -> None:
    raw = create_fat_image(tmp_path / "source.img", 2 * 1024 * 1024, FileSystemType.FAT12, "SOURCE")
    source_vhd = tmp_path / "source.vhd"
    create_fixed_vhd(raw, source_vhd)

    destination_vhd = tmp_path / "editable-copy.vhd"
    copy = create_editable_fixed_vhd_copy(source_vhd, destination_vhd)
    layout = validate_fixed_vhd_fat(destination_vhd)
    assert copy.destination == destination_vhd
    assert copy.virtual_size == raw.stat().st_size
    assert layout.size_bytes == copy.virtual_size

    payload = tmp_path / "note.txt"
    payload.write_text("fixed VHD edit", encoding="utf-8")
    filesystem = FatImageFilesystem(destination_vhd, read_only=False)
    try:
        filesystem.inject([payload])
    finally:
        filesystem.close()

    validate_fixed_vhd_fat(destination_vhd)
    edited = FatImageFilesystem(destination_vhd, read_only=True)
    original = FatImageFilesystem(source_vhd, read_only=True)
    try:
        assert "/note.txt" in {entry.path.lower() for entry in edited.list_entries("/")}
        assert "/note.txt" not in {entry.path.lower() for entry in original.list_entries("/")}
    finally:
        edited.close()
        original.close()


def test_cli_creates_validated_editable_fixed_vhd_copy(tmp_path: Path, capsys) -> None:
    import json

    from diskforge.cli import main

    raw = create_fat_image(tmp_path / "source.img", 2 * 1024 * 1024, FileSystemType.FAT12)
    source_vhd = tmp_path / "source.vhd"
    create_fixed_vhd(raw, source_vhd)
    destination_vhd = tmp_path / "editable-copy.vhd"

    assert main(["--json", "create-editable-vhd-copy", str(source_vhd), str(destination_vhd)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"source": str(source_vhd), "destination": str(destination_vhd), "virtual_bytes": raw.stat().st_size}
    validate_fixed_vhd_fat(destination_vhd)


def test_main_window_opens_validated_fixed_vhd_copy_as_writable_fat_session(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui.main_window import MainWindow

    raw = create_fat_image(tmp_path / "source.img", 2 * 1024 * 1024, FileSystemType.FAT12)
    source_vhd = tmp_path / "source.vhd"
    create_fixed_vhd(raw, source_vhd)
    editable_vhd = tmp_path / "editable.vhd"
    create_editable_fixed_vhd_copy(source_vhd, editable_vhd)

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window._open_path(editable_vhd, editable_fixed_vhd=True)

    assert window.current_browse_session is None
    assert isinstance(window.current_fs, FatImageFilesystem)
    assert not window.current_fs.read_only
    assert window.action_editable_vhd.isEnabled()
