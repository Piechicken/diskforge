from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.bootsector import edit_fat_boot_properties, inspect_boot_sector
from diskforge.core.filesystems import create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.storage import DiskForgeError


def test_edit_fat_boot_properties_creates_backup_and_updates_bpb(tmp_path: Path) -> None:
    image = tmp_path / "fat16.img"
    create_fat_image(image, 8 * 1024 * 1024, FileSystemType.FAT16, "BEFORE")
    original = image.read_bytes()

    info, backup = edit_fat_boot_properties(
        image, oem_name="DFORGE", volume_label="AFTER", serial_number=0x1234ABCD
    )

    assert backup.read_bytes() == original
    assert info.oem_name == "DFORGE"
    assert info.volume_label == "AFTER"
    sector = image.read_bytes()[:512]
    assert int.from_bytes(sector[39:43], "little") == 0x1234ABCD
    assert inspect_boot_sector(sector).signature_valid is True


def test_edit_fat_boot_properties_rejects_non_fat_sector(tmp_path: Path) -> None:
    image = tmp_path / "raw.img"
    image.write_bytes(b"\0" * 1024)

    with pytest.raises(DiskForgeError, match="FAT"):
        edit_fat_boot_properties(image, oem_name="DFORGE")
