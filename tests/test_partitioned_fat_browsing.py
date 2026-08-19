from __future__ import annotations

import binascii
import struct
import uuid
from pathlib import Path

import pytest

from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.partitions import fat_partition_offset, select_partition
from diskforge.core.storage import DiskForgeError


def _gpt_header(*, current_lba: int, backup_lba: int, entry_lba: int, entries: bytes,
                disk_guid: uuid.UUID, first_usable: int, last_usable: int) -> bytes:
    header = bytearray(512)
    header[0:8] = b"EFI PART"
    struct.pack_into("<I", header, 8, 0x00010000)
    struct.pack_into("<I", header, 12, 92)
    struct.pack_into("<Q", header, 24, current_lba)
    struct.pack_into("<Q", header, 32, backup_lba)
    struct.pack_into("<Q", header, 40, first_usable)
    struct.pack_into("<Q", header, 48, last_usable)
    header[56:72] = disk_guid.bytes_le
    struct.pack_into("<Q", header, 72, entry_lba)
    struct.pack_into("<I", header, 80, 4)
    struct.pack_into("<I", header, 84, 128)
    struct.pack_into("<I", header, 88, binascii.crc32(entries) & 0xFFFFFFFF)
    struct.pack_into("<I", header, 16, binascii.crc32(header[:92]) & 0xFFFFFFFF)
    return bytes(header)


def _gpt_fat_image(path: Path, tmp_path: Path) -> int:
    fat = tmp_path / "partition.fat"
    create_fat_image(fat, 8 * 1024 * 1024, FileSystemType.FAT16, "GPTFAT")
    start_lba = 40
    sectors = fat.stat().st_size // 512
    total_lbas = start_lba + sectors + 40
    backup_lba = total_lbas - 1
    entries = bytearray(4 * 128)
    entries[0:16] = uuid.UUID("ebd0a0a2-b9e5-4433-87c0-68b6b72699c7").bytes_le
    entries[16:32] = uuid.uuid4().bytes_le
    struct.pack_into("<QQ", entries, 32, start_lba, start_lba + sectors - 1)
    entries[56:56 + len("FAT DATA".encode("utf-16-le"))] = "FAT DATA".encode("utf-16-le")
    disk_guid = uuid.uuid4()
    data = bytearray(total_lbas * 512)
    data[1 * 512:2 * 512] = _gpt_header(
        current_lba=1, backup_lba=backup_lba, entry_lba=2, entries=bytes(entries), disk_guid=disk_guid,
        first_usable=34, last_usable=backup_lba - 33,
    )
    data[2 * 512:3 * 512] = entries
    backup_entries_lba = backup_lba - 1
    data[backup_entries_lba * 512:(backup_entries_lba + 1) * 512] = entries
    data[backup_lba * 512:(backup_lba + 1) * 512] = _gpt_header(
        current_lba=backup_lba, backup_lba=1, entry_lba=backup_entries_lba, entries=bytes(entries), disk_guid=disk_guid,
        first_usable=34, last_usable=backup_lba - 33,
    )
    data[start_lba * 512:(start_lba + sectors) * 512] = fat.read_bytes()
    path.write_bytes(data)
    return start_lba * 512


def test_explicit_gpt_fat_partition_selection_can_browse_and_edit(tmp_path: Path) -> None:
    image = tmp_path / "gpt-fat.img"
    expected_offset = _gpt_fat_image(image, tmp_path)
    source = tmp_path / "payload.txt"
    source.write_text("partitioned payload", encoding="utf-8")

    assert select_partition(image, 1).offset == expected_offset
    assert fat_partition_offset(image, partition_index=1) == expected_offset
    filesystem = FatImageFilesystem(image, partition_index=1)
    try:
        filesystem.inject([source])
        assert [entry.name for entry in filesystem.list_entries("/")] == ["payload.txt"]
    finally:
        filesystem.close()

    reopened = FatImageFilesystem(image, partition_index=1, read_only=True)
    try:
        extracted = reopened.extract(["/payload.txt"], tmp_path / "extracted")
        assert extracted[0].read_text(encoding="utf-8") == "partitioned payload"
    finally:
        reopened.close()


def test_partition_selection_rejects_unknown_index_and_non_fat_partition(tmp_path: Path) -> None:
    image = tmp_path / "gpt-fat.img"
    _gpt_fat_image(image, tmp_path)

    with pytest.raises(DiskForgeError, match="does not exist"):
        select_partition(image, 2)
    with pytest.raises(DiskForgeError, match="does not exist"):
        FatImageFilesystem(image, partition_index=2)
