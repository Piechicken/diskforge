from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from diskforge.core.browse_session import materialize_browsable_image
from diskforge.core.formats import create_legacy_zip_image, inspect_image
from diskforge.core.models import FileSystemType, ImageFormat
from diskforge.core.filesystems import create_fat_image
from diskforge.core.storage import DiskForgeError, sha256_file


def test_imz_and_wlz_zip_compatible_images_materialize_to_temporary_raw_fat(tmp_path: Path) -> None:
    raw = tmp_path / "legacy.img"
    create_fat_image(raw, 8 * 1024 * 1024, FileSystemType.FAT16, "LEGACY")
    before = sha256_file(raw)

    for image_format, suffix in ((ImageFormat.IMZ, ".imz"), (ImageFormat.WLZ, ".wlz")):
        container = tmp_path / f"legacy{suffix}"
        result = create_legacy_zip_image(raw, container, image_format)
        assert result.destination == container
        assert inspect_image(container).image_format == image_format
        session = materialize_browsable_image(container)
        try:
            assert session.temporary is True
            assert session.image != container
            assert inspect_image(session.image).filesystem == FileSystemType.FAT16
            assert sha256_file(session.image) == before
        finally:
            temporary = session.temporary_directory
            session.close()
        assert temporary is not None and not temporary.exists()
    assert sha256_file(raw) == before


def test_legacy_zip_image_rejects_unsafe_or_ambiguous_payloads(tmp_path: Path) -> None:
    ambiguous = tmp_path / "ambiguous.imz"
    with zipfile.ZipFile(ambiguous, "w") as archive:
        archive.writestr("first.img", b"one")
        archive.writestr("second.img", b"two")
    with pytest.raises(DiskForgeError, match="exactly one"):
        materialize_browsable_image(ambiguous)

    unsafe = tmp_path / "unsafe.wlz"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.img", b"payload")
    with pytest.raises(DiskForgeError, match="unsafe"):
        materialize_browsable_image(unsafe)


def test_legacy_zip_create_rejects_wrong_container_and_existing_destination(tmp_path: Path) -> None:
    raw = tmp_path / "raw.img"
    raw.write_bytes(b"raw")
    output = tmp_path / "legacy.imz"
    with pytest.raises(DiskForgeError, match="IMZ or WLZ"):
        create_legacy_zip_image(raw, output, ImageFormat.RAW)
    output.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        create_legacy_zip_image(raw, output, ImageFormat.IMZ)


def test_main_window_opens_zip_compatible_legacy_image_through_read_only_session(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui.main_window import MainWindow

    raw = tmp_path / "legacy.img"
    create_fat_image(raw, 8 * 1024 * 1024, FileSystemType.FAT16, "LEGACY")
    container = tmp_path / "legacy.imz"
    create_legacy_zip_image(raw, container, ImageFormat.IMZ)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window._open_path(container)
    assert window.current_browse_session is not None
    assert window.current_browse_session.temporary is True
    assert window.current_info is not None and window.current_info.image_format == ImageFormat.IMZ
    window.close_image()
