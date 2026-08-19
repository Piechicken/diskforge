"""Optional acceptance tests for external, licensed filesystem fixture images.

Set ``DISKFORGE_REAL_FS_FIXTURES`` to a local directory containing the documented
fixtures.  Binary corpora deliberately remain outside the source repository and
ordinary CI jobs skip these checks when the optional samples or Sleuth Kit are
unavailable.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from diskforge.core.models import FileSystemType
from diskforge.core.readonly_fs import SleuthKitImageFilesystem


_FIXTURES = Path(os.environ.get("DISKFORGE_REAL_FS_FIXTURES", ""))
_HAS_TSK = bool(shutil.which("fls") and shutil.which("icat"))


def _fixture(name: str) -> Path:
    path = _FIXTURES / name
    if not _HAS_TSK or not _FIXTURES.is_dir() or not path.is_file():
        pytest.skip(f"optional real fixture is unavailable: {name}")
    return path


def test_real_ntfs_lastaccess_sample_lists_and_extracts(tmp_path: Path) -> None:
    """CC0 msuhanov/ntfs-samples `ntfs-lastaccess.raw`, NTFS partition at LBA 128."""
    filesystem = SleuthKitImageFilesystem(_fixture("ntfs-lastaccess.raw"), FileSystemType.NTFS, offset=128 * 512)
    try:
        assert any(entry.path == "/test" and entry.is_dir for entry in filesystem.list_entries("/"))
        outputs = filesystem.extract(["/test/1.txt"], tmp_path)
    finally:
        filesystem.close()
    assert len(outputs) == 1
    assert outputs[0].stat().st_size == 143


def test_real_ext4_sample_lists_and_extracts(tmp_path: Path) -> None:
    """MIT eribertomota/forensics-samples `fs.ext4`, EXT4 partition at LBA 2048."""
    filesystem = SleuthKitImageFilesystem(_fixture("fs.ext4"), FileSystemType.EXT, offset=2048 * 512)
    try:
        assert any(entry.path == "/audio1" and entry.is_dir for entry in filesystem.list_entries("/"))
        outputs = filesystem.extract(["/audio1/debian.mp3"], tmp_path)
    finally:
        filesystem.close()
    assert len(outputs) == 1
    assert outputs[0].stat().st_size == 69727


def test_real_hfs_plus_journal_sample_lists_and_extracts(tmp_path: Path) -> None:
    """Public Digital Corpora NPS `image.gen1.dmg`, HFS+ journal sample."""
    filesystem = SleuthKitImageFilesystem(_fixture("nps-hfsj-image.gen1.dmg"), FileSystemType.HFS_PLUS)
    try:
        assert any(entry.path == "/file1.txt" and not entry.is_dir for entry in filesystem.list_entries("/"))
        outputs = filesystem.extract(["/file1.txt"], tmp_path)
    finally:
        filesystem.close()
    assert len(outputs) == 1
    assert outputs[0].stat().st_size == 28
