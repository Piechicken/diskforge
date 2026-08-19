from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.legacy_floppy import (LEGACY_FLOPPY_PROFILES, LegacyFloppyGeometry,
                                          create_legacy_fat_floppy,
                                          create_legacy_fat_floppy_profile)
from diskforge.core.filesystems import FatImageFilesystem
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.models import FileSystemType, ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


@pytest.mark.parametrize("profile", LEGACY_FLOPPY_PROFILES, ids=lambda item: item.identifier)
def test_each_legacy_floppy_profile_creates_verified_ima(profile, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    created = create_legacy_fat_floppy_profile(tmp_path / profile.identifier, profile.identifier, label="LEGACY")

    assert created.suffix == ".ima"
    assert created.stat().st_size == profile.geometry.size_bytes
    info = inspect_image(created)
    assert info.image_format == ImageFormat.IMA
    assert info.filesystem == FileSystemType.FAT12
    with created.open("rb") as handle:
        boot = handle.read(64)
    assert int.from_bytes(boot[11:13], "little") == profile.geometry.sector_size
    assert int.from_bytes(boot[24:26], "little") == profile.geometry.sectors_per_track
    assert int.from_bytes(boot[26:28], "little") == profile.geometry.heads


def test_legacy_floppy_can_explicitly_use_img_suffix(tmp_path: Path) -> None:
    created = create_legacy_fat_floppy_profile(
        tmp_path / "disk.ima", "pc525_dsdd_360", image_format=ImageFormat.IMG, label="LEGACY",
    )

    assert created == tmp_path / "disk.img"
    assert inspect_image(created).image_format == ImageFormat.IMG


def test_ima_uses_the_full_fat_edit_extract_verify_and_convert_workflow(tmp_path: Path) -> None:
    image = create_legacy_fat_floppy_profile(tmp_path / "legacy", "pc525_dsdd_360")
    source = tmp_path / "note.txt"
    source.write_text("legacy IMA edit", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        inserted = filesystem.inject([source])
        assert inserted == ["/note.txt"]
        renamed = filesystem.rename("/note.txt", "renamed.txt")
        filesystem.set_attributes(renamed, read_only=True, hidden=True)
    finally:
        filesystem.close()

    reopened = FatImageFilesystem(image, read_only=True)
    try:
        entries = reopened.list_entries("/")
        assert [(entry.name, entry.attributes) for entry in entries] == [("renamed.txt", "RH")]
        extracted = reopened.extract(["/renamed.txt"], tmp_path / "out")
    finally:
        reopened.close()
    assert extracted[0].read_text(encoding="utf-8") == "legacy IMA edit"
    assert len(sha256_file(image)) == 64

    img_copy = tmp_path / "converted.img"
    ima_copy = tmp_path / "roundtrip.ima"
    assert convert_image(image, img_copy, ImageFormat.IMG).image_format == ImageFormat.IMG
    assert convert_image(img_copy, ima_copy, ImageFormat.IMA).image_format == ImageFormat.IMA
    assert sha256_file(image) == sha256_file(img_copy) == sha256_file(ima_copy)


def test_custom_legacy_geometry_is_explicit_and_verified(tmp_path: Path) -> None:
    geometry = LegacyFloppyGeometry(40, 1, 9)
    created = create_legacy_fat_floppy(tmp_path / "custom", geometry, image_format=ImageFormat.IMA, label="CUSTOM")

    assert created.stat().st_size == 184_320
    assert inspect_image(created).filesystem == FileSystemType.FAT12


@pytest.mark.parametrize("geometry, message", [
    (LegacyFloppyGeometry(40, 1, 9, 256), "512, 1024"),
    (LegacyFloppyGeometry(0, 1, 9), "cylinders"),
    (LegacyFloppyGeometry(40, 0, 9), "heads"),
])
def test_legacy_floppy_rejects_unsupported_or_invalid_geometry(tmp_path: Path, geometry: LegacyFloppyGeometry, message: str) -> None:
    with pytest.raises(DiskForgeError, match=message):
        create_legacy_fat_floppy(tmp_path / "invalid", geometry)
