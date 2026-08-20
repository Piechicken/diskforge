from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from diskforge.core.formats import inspect_image
from diskforge.core.hfs_create import HfsImageCreator, MIN_CLASSIC_HFS_BYTES
from diskforge.core.models import FileSystemType
from diskforge.core.storage import DiskForgeError, sha256_file


def test_hfs_creator_reports_missing_optional_backend_and_refuses_use(tmp_path: Path) -> None:
    creator = HfsImageCreator("missing-hformat")
    report = creator.capability_report()

    assert report.available is False
    assert report.adapter == "hfsutils"
    with pytest.raises(DiskForgeError, match="requires an explicitly configured"):
        creator.create(tmp_path / "output.hfs", MIN_CLASSIC_HFS_BYTES)


@pytest.mark.parametrize("label", ["", "colon:name", ".hidden", "unicode-文件", "x" * 28])
def test_hfs_creator_rejects_unsafe_volume_labels(label: str) -> None:
    with pytest.raises(DiskForgeError):
        HfsImageCreator._validate_label(label)


@pytest.mark.parametrize("label", ["DISKFORGE", "Test Disk", "A-1_.2", "x" * 27])
def test_hfs_creator_accepts_safe_volume_labels(label: str) -> None:
    assert HfsImageCreator._validate_label(label) == label


@pytest.mark.parametrize("size", [MIN_CLASSIC_HFS_BYTES - 512, MIN_CLASSIC_HFS_BYTES + 1])
def test_hfs_creator_rejects_invalid_sizes(size: int) -> None:
    with pytest.raises(DiskForgeError):
        HfsImageCreator._validate_size(size)


@pytest.mark.skipif(not shutil.which("hformat"), reason="optional hfsutils hformat unavailable")
def test_hfs_creator_makes_verified_classic_hfs_image(tmp_path: Path) -> None:
    destination = tmp_path / "created.hfs"
    creator = HfsImageCreator()

    result = creator.create(destination, MIN_CLASSIC_HFS_BYTES, "DISKFORGE")

    assert result.destination == destination
    assert result.label == "DISKFORGE"
    assert result.bytes_created == MIN_CLASSIC_HFS_BYTES
    assert result.sha256 == sha256_file(destination)
    assert destination.stat().st_size == MIN_CLASSIC_HFS_BYTES
    assert inspect_image(destination).filesystem == FileSystemType.HFS

    with pytest.raises(FileExistsError):
        creator.create(destination, MIN_CLASSIC_HFS_BYTES, "SECOND")


def test_hfs_creator_rejects_device_output_before_backend_execution() -> None:
    creator = HfsImageCreator(sys.executable)

    with pytest.raises(DiskForgeError, match="file outputs only"):
        creator.create("/dev/fd0", MIN_CLASSIC_HFS_BYTES)
