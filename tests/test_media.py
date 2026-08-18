from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.media import (
    DMF_LAYOUT,
    create_dmf_image,
    detect_dmf_layout,
    trim_zero_tail,
    wrap_fat_image_in_mbr,
)
from diskforge.core.models import FileSystemType
from diskforge.core.partitions import parse_mbr
from diskforge.core.storage import DiskForgeError


def test_create_and_detect_dmf_fat12_layout(tmp_path: Path) -> None:
    image = create_dmf_image(tmp_path / "media.dmf", "DMFTEST")
    assert image.stat().st_size == DMF_LAYOUT.size_bytes
    assert detect_dmf_layout(image) == DMF_LAYOUT
    with image.open("rb") as handle:
        boot = handle.read(512)
    assert int.from_bytes(boot[11:13], "little") == 512
    assert int.from_bytes(boot[24:26], "little") == 21
    assert int.from_bytes(boot[26:28], "little") == 2
    fs = FatImageFilesystem(image, read_only=True)
    try:
        assert fs.volume_label() == "DMFTEST"
    finally:
        fs.close()


def test_wrap_fat_image_in_neutral_mbr_preserves_payload(tmp_path: Path) -> None:
    source = create_fat_image(tmp_path / "source.img", 2 * 1024 * 1024, FileSystemType.FAT12, "WRAPPED")
    destination = tmp_path / "wrapped.img"
    result = wrap_fat_image_in_mbr(source, destination)
    assert result.partition_start_lba == 1
    assert destination.stat().st_size == source.stat().st_size + 512
    partitions = parse_mbr(destination)
    assert len(partitions) == 1
    assert partitions[0].start_lba == 1
    assert partitions[0].sectors == source.stat().st_size // 512
    with source.open("rb") as original, destination.open("rb") as wrapped:
        wrapped.seek(512)
        assert wrapped.read() == original.read()


def test_trim_zero_tail_copies_only_zero_tail_and_rejects_partial_sector(tmp_path: Path) -> None:
    source = tmp_path / "source.img"
    source.write_bytes(b"A" * 512 + b"\x00" * 1024)
    result = trim_zero_tail(source, tmp_path / "trimmed.img")
    assert result.original_size == 1536
    assert result.trimmed_size == 512
    assert result.destination.read_bytes() == b"A" * 512
    partial = tmp_path / "partial.img"
    partial.write_bytes(b"X" * 513)
    with pytest.raises(DiskForgeError, match="sector-aligned"):
        trim_zero_tail(partial, tmp_path / "not-created.img")
