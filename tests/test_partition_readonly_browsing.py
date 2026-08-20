from __future__ import annotations

import struct
from pathlib import Path

import pytest

from diskforge.core.models import FileSystemType
from diskforge.core import partition_filesystems
from diskforge.core.partition_filesystems import open_partition_filesystem
from diskforge.core.storage import DiskForgeError


class _RecordedFilesystem:
    def __init__(self, image: Path, filesystem: FileSystemType, *, offset: int = 0,
                 fls_executable: str | None = None, icat_executable: str | None = None) -> None:
        self.image = image
        self.filesystem = filesystem
        self.offset = offset
        self.fls_executable = fls_executable
        self.icat_executable = icat_executable

    def close(self) -> None:
        pass


def _mbr_image(path: Path, *, type_id: int, start_lba: int = 64, sectors: int = 32) -> int:
    data = bytearray((start_lba + sectors + 1) * 512)
    entry = 446
    data[entry + 4] = type_id
    struct.pack_into("<II", data, entry + 8, start_lba, sectors)
    data[510:512] = b"\x55\xaa"
    path.write_bytes(data)
    return start_lba * 512


def test_explicit_ext_partition_uses_validated_offset_and_stays_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = tmp_path / "partitioned-ext.img"
    expected_offset = _mbr_image(image, type_id=0x83)
    monkeypatch.setattr(partition_filesystems, "SleuthKitImageFilesystem", _RecordedFilesystem)

    filesystem = open_partition_filesystem(image, 1)

    assert isinstance(filesystem, _RecordedFilesystem)
    assert filesystem.filesystem == FileSystemType.EXT
    assert filesystem.offset == expected_offset


def test_explicit_non_fat_partition_rejects_write_before_backend_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = tmp_path / "partitioned-ext.img"
    _mbr_image(image, type_id=0x83)
    called = False

    def unexpected_backend(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        raise AssertionError("read-only backend must not start for a write request")

    monkeypatch.setattr(partition_filesystems, "SleuthKitImageFilesystem", unexpected_backend)

    with pytest.raises(DiskForgeError, match="read-only browsing only"):
        open_partition_filesystem(image, 1, writable=True)
    assert not called


def test_explicit_unknown_partition_is_rejected(tmp_path: Path) -> None:
    image = tmp_path / "partitioned-swap.img"
    _mbr_image(image, type_id=0x82)

    with pytest.raises(DiskForgeError, match="not a supported FAT"):
        open_partition_filesystem(image, 1)
