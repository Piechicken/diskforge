from __future__ import annotations

import binascii
import struct
import uuid
from pathlib import Path

import pytest

from diskforge.core.partitions import inspect_gpt, parse_gpt
from diskforge.core.storage import DiskForgeError


def _header(*, current_lba: int, backup_lba: int, entry_lba: int, entries: bytes,
            disk_guid: uuid.UUID) -> bytes:
    header = bytearray(512)
    header[0:8] = b"EFI PART"
    struct.pack_into("<I", header, 8, 0x00010000)
    struct.pack_into("<I", header, 12, 92)
    struct.pack_into("<Q", header, 24, current_lba)
    struct.pack_into("<Q", header, 32, backup_lba)
    struct.pack_into("<Q", header, 40, 34)
    struct.pack_into("<Q", header, 48, 66)
    header[56:72] = disk_guid.bytes_le
    struct.pack_into("<Q", header, 72, entry_lba)
    struct.pack_into("<I", header, 80, 4)
    struct.pack_into("<I", header, 84, 128)
    struct.pack_into("<I", header, 88, binascii.crc32(entries) & 0xFFFFFFFF)
    struct.pack_into("<I", header, 16, binascii.crc32(header[:92]) & 0xFFFFFFFF)
    return bytes(header)


def _gpt_image(path: Path) -> None:
    data = bytearray(100 * 512)
    entries = bytearray(4 * 128)
    entries[0:16] = uuid.UUID("c12a7328-f81f-11d2-ba4b-00a0c93ec93b").bytes_le
    entries[16:32] = uuid.uuid4().bytes_le
    struct.pack_into("<QQ", entries, 32, 40, 50)
    entries[56:56 + len("DATA".encode("utf-16-le"))] = "DATA".encode("utf-16-le")
    disk_guid = uuid.uuid4()
    data[1 * 512:2 * 512] = _header(current_lba=1, backup_lba=99, entry_lba=2, entries=bytes(entries), disk_guid=disk_guid)
    data[2 * 512:3 * 512] = entries
    data[98 * 512:99 * 512] = entries
    data[99 * 512:100 * 512] = _header(current_lba=99, backup_lba=1, entry_lba=98, entries=bytes(entries), disk_guid=disk_guid)
    path.write_bytes(data)


def test_inspect_gpt_validates_primary_backup_and_entries(tmp_path: Path) -> None:
    image = tmp_path / "valid-gpt.img"
    _gpt_image(image)

    inspection = inspect_gpt(image)

    assert inspection is not None
    assert inspection.backup_header_valid is True
    assert inspection.warnings == ()
    assert len(inspection.partitions) == 1
    assert inspection.partitions[0].name == "DATA"
    assert parse_gpt(image)[0].start_lba == 40


def test_parse_gpt_rejects_invalid_primary_crc(tmp_path: Path) -> None:
    image = tmp_path / "bad-gpt.img"
    _gpt_image(image)
    data = bytearray(image.read_bytes())
    data[1 * 512 + 24] ^= 0x01
    image.write_bytes(data)

    with pytest.raises(DiskForgeError, match="CRC32"):
        parse_gpt(image)
