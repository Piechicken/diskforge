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


def test_safe_legacy_raw_alias_zip_materializes_and_reidentifies(tmp_path: Path) -> None:
    image = tmp_path / "payload.img"
    create_fat_image(image, 360 * 1024, FileSystemType.FAT12, "ZIPVFD")
    archive = tmp_path / "payload.zip"
    _write_zip(archive, "payload.vfd", image.read_bytes())

    session = materialize_browsable_image(archive)
    try:
        info = inspect_image(session.image)
        assert info.image_format == ImageFormat.RAW
        assert info.filesystem == FileSystemType.FAT12
        assert "Conventional legacy raw-sector image shape recognized" in info.notes
    finally:
        session.close()


def test_explicit_multi_image_zip_selection_is_read_only_across_entrypoints(tmp_path: Path, capsys, qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.api import DiskForgeClient
    from diskforge.cli import main
    from diskforge.core.formats import list_zip_image_payloads
    from diskforge.gui.main_window import MainWindow

    first = tmp_path / "first.img"
    second = tmp_path / "second.img"
    create_fat_image(first, 360 * 1024, FileSystemType.FAT12, "FIRST")
    create_fat_image(second, 720 * 1024, FileSystemType.FAT12, "SECOND")
    first_note = tmp_path / "first.txt"
    second_note = tmp_path / "second.txt"
    first_note.write_text("first payload", encoding="utf-8")
    second_note.write_text("second payload", encoding="utf-8")
    from diskforge.core.filesystems import FatImageFilesystem
    for image, note in ((first, first_note), (second, second_note)):
        filesystem = FatImageFilesystem(image)
        try:
            filesystem.inject([note])
        finally:
            filesystem.close()
    archive = tmp_path / "collection.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as container:
        container.write(first, "first.img")
        container.write(second, "second.vfd")
    source_hash = sha256_file(archive)

    assert list_zip_image_payloads(archive) == ("first.img", "second.vfd")
    with pytest.raises(DiskForgeError, match="exactly one"):
        materialize_browsable_image(archive)
    with pytest.raises(DiskForgeError, match="not present"):
        materialize_browsable_image(archive, zip_payload="missing.img")

    session = materialize_browsable_image(archive, zip_payload="second.vfd")
    try:
        assert session.image.suffix == ".vfd"
        assert inspect_image(session.image).image_format == ImageFormat.RAW
        assert inspect_image(session.image).filesystem == FileSystemType.FAT12
    finally:
        session.close()

    client = DiskForgeClient()
    assert client.list_zip_image_payloads(archive) == ("first.img", "second.vfd")
    with client.filesystem(archive, zip_payload="second.vfd") as filesystem:
        assert [entry.name for entry in filesystem.list_entries("/")] == ["second.txt"]

    assert main(["--json", "zip-info", str(archive)]) == 0
    report = __import__("json").loads(capsys.readouterr().out)
    assert report["payloads"] == ["first.img", "second.vfd"]
    assert main(["--json", "list", str(archive), "--zip-payload", "first.img"]) == 0
    listing = __import__("json").loads(capsys.readouterr().out)
    assert [entry["name"] for entry in listing] == ["first.txt"]

    settings = QSettings(str(tmp_path / "multi-zip.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window._open_path(archive, zip_payload="second.vfd")
    assert window.current_zip_payload == "second.vfd"
    assert window.current_browse_session is not None
    assert [entry.name for entry in window.current_entries] == ["second.txt"]
    assert window.action_inject.isEnabled() is False
    window.close_image()
    assert sha256_file(archive) == source_hash
