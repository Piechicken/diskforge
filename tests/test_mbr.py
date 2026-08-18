from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.mbr import backup_mbr, read_mbr, reset_mbr_to_neutral, restore_mbr
from diskforge.core.storage import DiskForgeError


def _mbr_image(path: Path) -> bytes:
    sector = bytearray(512)
    sector[:32] = b"bootstrap-code" * 2 + b"\0" * 4
    sector[446 + 4] = 0x0C
    sector[446 + 8:446 + 12] = (2048).to_bytes(4, "little")
    sector[446 + 12:446 + 16] = (4096).to_bytes(4, "little")
    sector[510:512] = b"\x55\xaa"
    path.write_bytes(sector + b"\0" * 1024)
    return bytes(sector)


def test_mbr_backup_reset_and_restore_preserve_partition_table(tmp_path: Path) -> None:
    image = tmp_path / "disk.img"
    original = _mbr_image(image)

    saved = backup_mbr(image)
    assert saved.backup.read_bytes() == original
    with pytest.raises(DiskForgeError, match="ERASE"):
        reset_mbr_to_neutral(image, "erase")

    reset_backup = reset_mbr_to_neutral(image, "ERASE")
    reset = read_mbr(image)
    assert reset[:446] == b"\0" * 446
    assert reset[446:] == original[446:]
    assert reset_backup.backup.read_bytes() == original

    pre_restore = restore_mbr(image, saved.backup, "ERASE")
    assert pre_restore.backup.read_bytes() == reset
    assert read_mbr(image) == original


def test_mbr_restore_rejects_invalid_backup(tmp_path: Path) -> None:
    image = tmp_path / "disk.img"
    _mbr_image(image)
    invalid = tmp_path / "bad.bak"
    invalid.write_bytes(b"\0" * 512)

    with pytest.raises(DiskForgeError, match="MBR backup"):
        restore_mbr(image, invalid, "ERASE")
