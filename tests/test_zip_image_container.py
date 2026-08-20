from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from diskforge.core.browse_session import materialize_browsable_image
from diskforge.core.filesystems import create_fat_image
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.models import FileSystemType, ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _write_zip(path: Path, name: str, payload: bytes, *, compression: int = zipfile.ZIP_DEFLATED) -> None:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        archive.writestr(name, payload)


def test_safe_single_fat_image_zip_materializes_read_only_and_cleans_up(tmp_path: Path) -> None:
    image = tmp_path / "payload.img"
    create_fat_image(image, 8 * 1024 * 1024, FileSystemType.FAT16, "ZIPTEST")
    archive = tmp_path / "payload.zip"
    _write_zip(archive, image.name, image.read_bytes())
    before = sha256_file(archive)

    assert inspect_image(archive).image_format == ImageFormat.ZIP
    assert inspect_image(archive).writable is False
    session = materialize_browsable_image(archive)
    try:
        assert session.temporary is True
        assert session.source == archive
        assert session.source_info.image_format == ImageFormat.ZIP
        assert session.image != archive
        assert inspect_image(session.image).filesystem == FileSystemType.FAT16
        assert sha256_file(session.image) == sha256_file(image)
        temporary = session.temporary_directory
    finally:
        session.close()
    assert temporary is not None and not temporary.exists()
    assert sha256_file(archive) == before


@pytest.mark.parametrize(
    ("archive_name", "writer", "message"),
    [
        ("ambiguous.zip", lambda path: _write_ambiguous(path), "exactly one"),
        ("directory.zip", lambda path: _write_directory(path), "exactly one"),
        ("unsafe.zip", lambda path: _write_zip(path, "folder/payload.img", b"payload"), "unsafe"),
        ("unsupported.zip", lambda path: _write_zip(path, "payload.txt", b"payload"), "extension"),
        ("bzip2.zip", lambda path: _write_zip(path, "payload.img", b"payload", compression=zipfile.ZIP_BZIP2), "compression method"),
    ],
)
def test_zip_image_container_rejects_unsafe_or_ambiguous_entries(
    tmp_path: Path, archive_name: str, writer, message: str,
) -> None:  # type: ignore[no-untyped-def]
    archive = tmp_path / archive_name
    writer(archive)
    with pytest.raises(DiskForgeError, match=message):
        materialize_browsable_image(archive)


def _write_ambiguous(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("first.img", b"one")
        archive.writestr("second.img", b"two")


def _write_directory(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("folder/", b"")


def test_zip_image_container_rejects_size_limit_and_unrecognised_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import diskforge.core.formats as formats

    oversized = tmp_path / "oversized.zip"
    _write_zip(oversized, "payload.img", b"0123456789")
    monkeypatch.setattr(formats, "ZIP_IMAGE_MAX_BYTES", 8)
    with pytest.raises(DiskForgeError, match="safety limit"):
        materialize_browsable_image(oversized)

    monkeypatch.setattr(formats, "ZIP_IMAGE_MAX_BYTES", 2 * 1024 * 1024 * 1024)
    unknown = tmp_path / "unknown.zip"
    _write_zip(unknown, "payload.img", b"not a disk image")
    with pytest.raises(DiskForgeError, match="not a supported browsable"):
        materialize_browsable_image(unknown)



def test_zip_image_container_cannot_be_converted_as_raw_image(tmp_path: Path) -> None:
    image = tmp_path / "inside.img"
    create_fat_image(image, 8 * 1024 * 1024, FileSystemType.FAT16, "ZIPCONVERT")
    archive = tmp_path / "inside.zip"
    _write_zip(archive, image.name, image.read_bytes())

    with pytest.raises(DiskForgeError, match="read-only"):
        convert_image(archive, tmp_path / "invalid-output.img", ImageFormat.IMG)


def test_main_window_opens_zip_image_as_read_only_temporary_session(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui.main_window import MainWindow

    image = tmp_path / "inside.img"
    create_fat_image(image, 8 * 1024 * 1024, FileSystemType.FAT16, "ZIPGUI")
    payload = tmp_path / "payload.txt"
    payload.write_text("zip GUI payload", encoding="utf-8")
    from diskforge.core.filesystems import FatImageFilesystem
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([payload])
    finally:
        filesystem.close()
    archive = tmp_path / "inside.zip"
    _write_zip(archive, image.name, image.read_bytes())

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window._open_path(archive)

    assert window.current_info is not None and window.current_info.image_format == ImageFormat.ZIP
    assert window.current_browse_session is not None and window.current_browse_session.temporary
    assert window.current_fs is not None and getattr(window.current_fs, "read_only", False)
    assert window.action_inject.isEnabled() is False
    assert window.action_delete.isEnabled() is False
    assert window.action_move.isEnabled() is False
    assert window.action_boot.isEnabled() is False
    assert window.action_convert.isEnabled() is False
    assert window.action_resize.isEnabled() is False
    assert window.action_trim_zero_tail.isEnabled() is False
    assert window.action_wrap_mbr.isEnabled() is False
    assert window.action_prepare_deployment.isEnabled() is False
    assert [entry.name for entry in window.current_entries] == ["payload.txt"]
    temporary = window.current_browse_session.temporary_directory
    window.close_image()
    assert temporary is not None and not temporary.exists()



def test_zip_image_payload_rejects_encrypted_entry_marker() -> None:
    import diskforge.core.formats as formats

    entry = zipfile.ZipInfo("payload.img")
    entry.file_size = 1
    entry.flag_bits = 0x1

    class _Archive:
        def infolist(self):  # type: ignore[no-untyped-def]
            return [entry]

    with pytest.raises(DiskForgeError, match="Encrypted"):
        formats._zip_image_payload(_Archive())


def test_zip_image_materialization_cancellation_cleans_private_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import diskforge.core.browse_session as browse_session

    from diskforge.core.storage import CancellationToken, OperationCancelled

    image = tmp_path / "inside.img"
    create_fat_image(image, 8 * 1024 * 1024, FileSystemType.FAT16, "ZIPCANCEL")
    archive = tmp_path / "inside.zip"
    _write_zip(archive, image.name, image.read_bytes())
    temporary = tmp_path / "private-browse"

    def _mkdtemp(*, prefix: str) -> str:
        temporary.mkdir()
        return str(temporary)

    monkeypatch.setattr(browse_session.tempfile, "mkdtemp", _mkdtemp)
    token = CancellationToken()
    token.cancel()
    with pytest.raises(OperationCancelled):
        materialize_browsable_image(archive, token=token)
    assert not temporary.exists()
