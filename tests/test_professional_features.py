from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.core.batch import BatchRunner
from diskforge.core.bootsector import backup_and_write_boot_sector, inspect_boot_sector, parse_hexdump, sector_hexdump
from diskforge.core.filesystems import FatImageFilesystem, create_fat_image, defragment_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.storage import SafetyError, validate_device_write


def test_physical_write_requires_exact_phrase_and_safe_target() -> None:
    with pytest.raises(SafetyError, match="ERASE"):
        validate_device_write("/dev/sdz", 1024, 2048, "no")
    with pytest.raises(SafetyError, match="operating-system"):
        validate_device_write("/dev/sdz", 1024, 2048, "ERASE", is_system_disk=True)
    with pytest.raises(SafetyError, match="mounted"):
        validate_device_write("/dev/sdz", 1024, 2048, "ERASE", mounted=True)
    with pytest.raises(SafetyError, match="larger"):
        validate_device_write("/dev/sdz", 4096, 2048, "ERASE")
    validate_device_write("/dev/sdz", 1024, 2048, "ERASE")


def test_batch_rejects_unattended_raw_device_write(tmp_path: Path) -> None:
    recipe = tmp_path / "unsafe.json"
    recipe.write_text(json.dumps({"schema": "diskforge.batch/v1", "operations": [{"kind": "write_device", "source": "image.img", "destination": "/dev/sdz"}]}), encoding="utf-8")
    result = BatchRunner().run(recipe)
    assert result.failed == 1
    assert "not permitted" in result.items[0].message


def test_boot_sector_edit_creates_full_backup(tmp_path: Path) -> None:
    image = tmp_path / "boot.img"
    data = bytearray(1024)
    data[0:3] = b"\xeb\x3c\x90"
    data[3:11] = b"MSDOS5.0"
    data[11:13] = (512).to_bytes(2, "little")
    data[13] = 1
    data[54:62] = b"FAT16   "
    data[510:512] = b"\x55\xaa"
    image.write_bytes(data)
    edited = bytearray(data[:512])
    edited[3:11] = b"DISKFRGE"
    backup = backup_and_write_boot_sector(image, bytes(edited))
    assert backup.read_bytes() == bytes(data)
    assert inspect_boot_sector(image.read_bytes()[:512]).oem_name == "DISKFRGE"
    assert parse_hexdump(sector_hexdump(bytes(edited))) == bytes(edited)


def test_defragment_fat_image_rebuilds_into_a_new_image(tmp_path: Path) -> None:
    source_image = tmp_path / "source.img"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    create_fat_image(source_image, 4 * 1024 * 1024, FileSystemType.FAT12)
    fs = FatImageFilesystem(source_image)
    try:
        fs.inject([first, second])
        fs.delete(["/first.txt"])
        fs.inject([first])
    finally:
        fs.close()
    rebuilt = tmp_path / "rebuilt.img"
    defragment_fat_image(source_image, rebuilt)
    rebuilt_fs = FatImageFilesystem(rebuilt, read_only=True)
    try:
        output = rebuilt_fs.extract(["/first.txt", "/second.txt"], tmp_path / "extract")
        assert {item.name for item in output} == {"first.txt", "second.txt"}
    finally:
        rebuilt_fs.close()


def test_fat_export_supports_html_and_timestamp_edit(tmp_path: Path) -> None:
    image = tmp_path / "listing.img"
    source = tmp_path / "record.txt"
    source.write_text("record", encoding="utf-8")
    create_fat_image(image, 4 * 1024 * 1024, FileSystemType.FAT12)
    fs = FatImageFilesystem(image)
    try:
        fs.inject([source])
        result = fs.export_listing(tmp_path / "listing.html", html=True)
        assert "record.txt" in result.read_text(encoding="utf-8")
    finally:
        fs.close()
