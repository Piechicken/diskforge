from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.filesystems import IsoImageFilesystem, create_iso_from_directory, replace_iso_file_safely
from diskforge.core.storage import DiskForgeError, sha256_file


def _source_iso(tmp_path: Path) -> tuple[Path, Path]:
    source_tree = tmp_path / "source"
    source_tree.mkdir()
    payload = source_tree / "payload.txt"
    payload.write_bytes(b"original")
    (source_tree / "untouched.txt").write_bytes(b"preserved")
    image = tmp_path / "source.iso"
    create_iso_from_directory(source_tree, image, volume_label="REPLACE")
    return image, payload


def test_safe_iso_replacement_writes_verified_new_image_without_changing_source(tmp_path: Path) -> None:
    source, original = _source_iso(tmp_path)
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"updated!")
    destination = tmp_path / "replaced.iso"
    source_before = sha256_file(source)
    replacement_before = sha256_file(replacement)

    result = replace_iso_file_safely(source, "/PAYLOAD.TXT", replacement, destination)

    assert result.source == source
    assert result.destination == destination
    assert result.iso_path == "/PAYLOAD.TXT;1"
    assert result.bytes_replaced == len(b"updated!")
    assert sha256_file(source) == source_before
    assert sha256_file(replacement) == replacement_before
    assert result.source_sha256 == source_before
    assert result.output_sha256 == sha256_file(destination)

    filesystem = IsoImageFilesystem(destination)
    try:
        output = filesystem.extract(["/PAYLOAD.TXT"], tmp_path / "extracted")
        assert output[0].read_bytes() == b"updated!"
        untouched = filesystem.extract(["/UNTOUCHED.TXT"], tmp_path / "untouched")
        assert untouched[0].read_bytes() == b"preserved"
    finally:
        filesystem.close()


def test_safe_iso_replacement_rejects_size_changes_and_cleans_partial_output(tmp_path: Path) -> None:
    source, _ = _source_iso(tmp_path)
    replacement = tmp_path / "wrong-size.txt"
    replacement.write_bytes(b"too long!")
    destination = tmp_path / "replaced.iso"

    with pytest.raises(DiskForgeError, match="exactly match"):
        replace_iso_file_safely(source, "/PAYLOAD.TXT", replacement, destination)

    assert not destination.exists()


def test_safe_iso_replacement_rejects_destination_equal_to_source_or_existing_output(tmp_path: Path) -> None:
    source, _ = _source_iso(tmp_path)
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"updated!")

    with pytest.raises(DiskForgeError, match="different"):
        replace_iso_file_safely(source, "/PAYLOAD.TXT", replacement, source)

    destination = tmp_path / "existing.iso"
    destination.write_bytes(b"not replaceable")
    with pytest.raises(FileExistsError):
        replace_iso_file_safely(source, "/PAYLOAD.TXT", replacement, destination)


def test_safe_iso_replacement_rejects_missing_or_directory_entry(tmp_path: Path) -> None:
    source, _ = _source_iso(tmp_path)
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"updated!")

    with pytest.raises(FileNotFoundError):
        replace_iso_file_safely(source, "/MISSING.TXT", replacement, tmp_path / "missing.iso")
    with pytest.raises(DiskForgeError, match="regular file"):
        replace_iso_file_safely(source, "/", replacement, tmp_path / "directory.iso")


def test_main_window_enables_safe_iso_replace_only_for_one_selected_file(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui.main_window import MainWindow

    source, _ = _source_iso(tmp_path)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window._open_path(source)

    assert not window.action_replace_iso.isEnabled()
    window.table.selectRow(0)
    window._update_action_state()
    assert window.action_replace_iso.isEnabled()
    window.close_image()
    assert not window.action_replace_iso.isEnabled()
