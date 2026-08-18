from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.resize import boot_sector_size, resize_image
from diskforge.core.storage import DiskForgeError


def test_resize_raw_only_shrinks_zero_tail_and_extends(tmp_path: Path) -> None:
    source = tmp_path / "raw.img"
    source.write_bytes(b"payload" + b"\0" * (4096 - 7))

    shrunk = tmp_path / "shrunk.img"
    result = resize_image(source, shrunk, 512)
    assert result.new_size == 512
    assert shrunk.stat().st_size == 512
    assert shrunk.read_bytes().startswith(b"payload")

    extended = tmp_path / "extended.img"
    resize_image(shrunk, extended, 2048)
    assert extended.stat().st_size == 2048
    assert extended.read_bytes()[512:] == b"\0" * 1536


def test_resize_raw_refuses_non_zero_truncation(tmp_path: Path) -> None:
    source = tmp_path / "raw.img"
    source.write_bytes(b"\0" * 512 + b"not zero")

    with pytest.raises(DiskForgeError, match="non-zero"):
        resize_image(source, tmp_path / "smaller.img", 512)


def test_resize_fat_rebuilds_content_and_preserves_label(tmp_path: Path) -> None:
    source = tmp_path / "source.img"
    host_file = tmp_path / "record.txt"
    host_file.write_text("diskforge data", encoding="utf-8")
    create_fat_image(source, 8 * 1024 * 1024, FileSystemType.FAT16, "SOURCE")
    fs = FatImageFilesystem(source)
    try:
        fs.inject([host_file])
        fs.set_attributes("/record.txt", hidden=True)
    finally:
        fs.close()

    resized = tmp_path / "resized.img"
    resize_image(source, resized, 12 * 1024 * 1024)
    assert boot_sector_size(resized) == resized.stat().st_size
    reopened = FatImageFilesystem(resized, read_only=True)
    try:
        assert reopened.volume_label() == "SOURCE"
        assert reopened.list_entries("/")[0].attributes == "H"
        output = reopened.extract(["/record.txt"], tmp_path / "output")
        assert output[0].read_text(encoding="utf-8") == "diskforge data"
    finally:
        reopened.close()
