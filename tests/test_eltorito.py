from __future__ import annotations

from pathlib import Path

import pytest
import pycdlib

from diskforge.core.eltorito import export_boot_image, inspect_eltorito
from diskforge.core.storage import DiskForgeError


def _bootable_iso(path: Path, payload: bytes) -> Path:
    boot = path.with_suffix(".boot")
    boot.write_bytes(payload)
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3)
    try:
        iso.add_file(str(boot), iso_path="/BOOT.IMG;1")
        iso.add_eltorito("/BOOT.IMG;1", boot_load_size=len(payload) // 512, media_name="noemul")
        iso.write(str(path))
    finally:
        iso.close()
    return path


def test_inspect_and_export_eltorito_boot_image(tmp_path: Path) -> None:
    payload = (b"BOOT" * 128)  # exactly 512 bytes
    iso = _bootable_iso(tmp_path / "bootable.iso", payload)
    catalog = inspect_eltorito(iso)
    assert len(catalog.images) == 1
    image = catalog.images[0]
    assert image.bootable
    assert image.sector_count_512 == 1
    exported = export_boot_image(iso, tmp_path / "boot.img")
    assert exported.read_bytes() == payload


def test_eltorito_rejects_non_bootable_iso(tmp_path: Path) -> None:
    plain = tmp_path / "plain.iso"
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3)
    try:
        iso.write(str(plain))
    finally:
        iso.close()
    with pytest.raises(DiskForgeError, match="El Torito"):
        inspect_eltorito(plain)
