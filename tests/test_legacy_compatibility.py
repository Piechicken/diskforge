from __future__ import annotations

import zipfile
from pathlib import Path

from diskforge.core.filesystems import FatImageFilesystem
from diskforge.core.formats import inspect_image
from diskforge.core.models import FileSystemType, ImageFormat
from diskforge.core.preview import inspect_file_preview


def _legacy_360k_fat12(path: Path) -> None:
    """Build a valid 360 KB FAT12 superfloppy without a FAT display label."""
    image = bytearray(720 * 512)
    image[0:3] = b"\xeb\x2c\x90"
    image[3:11] = b"IBM  2.0"
    image[11:13] = (512).to_bytes(2, "little")
    image[13] = 2
    image[14:16] = (1).to_bytes(2, "little")
    image[16] = 2
    image[17:19] = (112).to_bytes(2, "little")
    image[19:21] = (720).to_bytes(2, "little")
    image[21] = 0xFD
    image[22:24] = (2).to_bytes(2, "little")
    image[24:26] = (9).to_bytes(2, "little")
    image[26:28] = (2).to_bytes(2, "little")
    image[510:512] = b"\x55\xaa"
    image[512:515] = b"\xfd\xff\xff"
    image[3 * 512:3 * 512 + 3] = b"\xfd\xff\xff"
    path.write_bytes(image)


def test_unlabelled_legacy_fat12_superfloppy_is_browsable(tmp_path: Path) -> None:
    image = tmp_path / "windows-setup-disk.img"
    _legacy_360k_fat12(image)

    assert inspect_image(image).filesystem == FileSystemType.FAT12
    filesystem = FatImageFilesystem(image, read_only=True)
    try:
        assert filesystem.list_entries("/") == []
    finally:
        filesystem.close()


def test_ima_extension_is_a_raw_image_alias() -> None:
    assert ImageFormat.from_path("mouse-driver.IMA") == ImageFormat.IMG


def test_safe_preview_handles_text_zip_and_dos_executable(tmp_path: Path) -> None:
    text = tmp_path / "README.TXT"
    text.write_bytes("Legacy driver notes\r\n".encode("cp437"))
    text_preview = inspect_file_preview(text)
    assert text_preview.kind == "text"
    assert "Legacy driver notes" in text_preview.text

    archive = tmp_path / "DRIVER.ZIP"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("README.TXT", "driver notes")
    archive_preview = inspect_file_preview(archive)
    assert archive_preview.kind == "archive"
    assert "README.TXT" in archive_preview.text

    executable = tmp_path / "SETUP.EXE"
    executable.write_bytes(b"MZ" + b"\0" * 126)
    executable_preview = inspect_file_preview(executable)
    assert executable_preview.kind == "executable"
    assert any("Execution is disabled" in detail for detail in executable_preview.details)
