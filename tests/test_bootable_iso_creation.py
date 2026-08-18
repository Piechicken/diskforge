from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.eltorito import inspect_eltorito
from diskforge.core.filesystems import create_iso_from_directory
from diskforge.core.storage import DiskForgeError


def test_create_bootable_iso_with_external_boot_image(tmp_path: Path) -> None:
    source = tmp_path / "payload"
    source.mkdir()
    (source / "README.TXT").write_text("DiskForge bootable ISO", encoding="utf-8")
    boot = tmp_path / "boot.img"
    boot_bytes = b"\xEB\x3C\x90" + b"DiskForge boot test" + b"\x00" * (2048 - 22)
    boot.write_bytes(boot_bytes)
    output = create_iso_from_directory(source, tmp_path / "bootable.iso", boot_image=boot, boot_media="noemul")
    catalog = inspect_eltorito(output)
    assert output.is_file()
    assert len(catalog.images) == 1
    assert catalog.images[0].bootable
    assert catalog.images[0].byte_count >= len(boot_bytes)
    assert boot.read_bytes() == boot_bytes


def test_bootable_iso_rejects_unknown_media_mode(tmp_path: Path) -> None:
    source = tmp_path / "payload"
    source.mkdir()
    with pytest.raises(DiskForgeError, match="boot media"):
        create_iso_from_directory(source, tmp_path / "invalid.iso", boot_media="invalid")
