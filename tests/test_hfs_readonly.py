from __future__ import annotations

from pathlib import Path

from diskforge.core.formats import detect_filesystem
from diskforge.core.models import FileSystemType
from diskforge.core.readonly_fs import SleuthKitImageFilesystem


def test_detect_filesystem_recognizes_classic_hfs_and_hfs_plus_volume_headers() -> None:
    classic = bytearray(4096)
    classic[1024:1026] = b"BD"
    plus = bytearray(4096)
    plus[1024:1026] = b"H+"
    journaled_plus = bytearray(4096)
    journaled_plus[1024:1026] = b"HX"

    assert detect_filesystem(bytes(classic)) == FileSystemType.HFS
    assert detect_filesystem(bytes(plus)) == FileSystemType.HFS_PLUS
    assert detect_filesystem(bytes(journaled_plus)) == FileSystemType.HFS_PLUS


def test_sleuth_kit_readonly_adapter_uses_hfs_legacy_and_hfs_plus_types(tmp_path: Path) -> None:
    image = tmp_path / "hfs.img"
    image.write_bytes(b"\0" * 4096)

    classic = SleuthKitImageFilesystem(image, FileSystemType.HFS, fls_executable="fls", icat_executable="icat")
    plus = SleuthKitImageFilesystem(image, FileSystemType.HFS_PLUS, fls_executable="fls", icat_executable="icat")
    try:
        assert classic._base_args[:2] == ["-f", "hfsl"]
        assert plus._base_args[:2] == ["-f", "hfs"]
    finally:
        classic.close()
        plus.close()
