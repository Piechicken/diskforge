"""Explicit, FAT-compatible legacy floppy geometries for flat IMG/IMA images.

A flat image has no trustworthy physical-media identity beyond its bytes.  These
profiles therefore describe only layouts that the native FAT formatter can
create and re-open.  Non-FAT, GCR, variable-sector, hard-sectored, and flux
formats must remain raw data workflows rather than be mislabeled as editable.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .filesystems import create_fat_image
from .formats import inspect_image
from .models import FileSystemType, ImageFormat
from .storage import DiskForgeError


@dataclass(frozen=True)
class LegacyFloppyGeometry:
    """A reproducible CHS geometry for a flat, sector-addressable FAT image."""

    cylinders: int
    heads: int
    sectors_per_track: int
    sector_size: int = 512

    @property
    def size_bytes(self) -> int:
        return self.cylinders * self.heads * self.sectors_per_track * self.sector_size

    @property
    def size_kib(self) -> int:
        return self.size_bytes // 1024

    def validate(self) -> None:
        if not 1 <= self.cylinders <= 0xFFFF:
            raise DiskForgeError("Legacy floppy cylinders must fit in an unsigned 16-bit field.")
        if not 1 <= self.heads <= 0xFFFF:
            raise DiskForgeError("Legacy floppy heads must fit in an unsigned 16-bit field.")
        if not 1 <= self.sectors_per_track <= 0xFFFF:
            raise DiskForgeError("Legacy floppy sectors per track must fit in an unsigned 16-bit field.")
        if self.sector_size not in {512, 1024, 2048, 4096}:
            raise DiskForgeError(
                "Native legacy FAT creation supports 512, 1024, 2048, or 4096 byte sectors; "
                "128/256-byte and track-encoded formats must remain raw image workflows."
            )
        if self.size_bytes < self.sector_size or self.size_bytes % self.sector_size:
            raise DiskForgeError("Legacy floppy geometry does not produce a sector-aligned image size.")


@dataclass(frozen=True)
class LegacyFloppyProfile:
    """A named, transparent legacy floppy layout visible in GUI, CLI and recipes."""

    identifier: str
    name: str
    form_factor: str
    density: str
    geometry: LegacyFloppyGeometry

    @property
    def description(self) -> str:
        geometry = self.geometry
        # The chooser itself stays language-neutral: no locale is inferred from
        # a raw image, while capacity, form factor, density and CHS remain fully
        # visible and unambiguous in every translated user interface.
        form_factor = self.form_factor.replace("-inch", "″")
        return (
            f"{geometry.size_kib:,} KiB · {form_factor} · {self.density} · "
            f"{geometry.cylinders}×{geometry.heads}×{geometry.sectors_per_track}×{geometry.sector_size}"
        )


# The table covers the conventional DOS/Windows PC-compatible 5.25-inch and
# 3.5-inch FAT layouts with 512-byte sectors.  Duplicate byte geometries are
# intentionally retained when they represent historically distinct media.
LEGACY_FLOPPY_PROFILES: tuple[LegacyFloppyProfile, ...] = (
    LegacyFloppyProfile("pc525_ssdd_160", "PC 5.25-inch 160 KB", "5.25-inch", "SS/DD", LegacyFloppyGeometry(40, 1, 8)),
    LegacyFloppyProfile("pc525_ssdd_180", "PC 5.25-inch 180 KB", "5.25-inch", "SS/DD", LegacyFloppyGeometry(40, 1, 9)),
    LegacyFloppyProfile("pc525_dsdd_320", "PC 5.25-inch 320 KB", "5.25-inch", "DS/DD", LegacyFloppyGeometry(40, 2, 8)),
    LegacyFloppyProfile("pc525_dsdd_360", "PC 5.25-inch 360 KB", "5.25-inch", "DS/DD", LegacyFloppyGeometry(40, 2, 9)),
    LegacyFloppyProfile("pc525_qd_640", "PC 5.25-inch 640 KB", "5.25-inch", "DS/QD", LegacyFloppyGeometry(80, 2, 8)),
    LegacyFloppyProfile("pc525_qd_720", "PC 5.25-inch 720 KB", "5.25-inch", "DS/QD", LegacyFloppyGeometry(80, 2, 9)),
    LegacyFloppyProfile("pc525_dshd_1200", "PC 5.25-inch 1.2 MB", "5.25-inch", "DS/HD", LegacyFloppyGeometry(80, 2, 15)),
    LegacyFloppyProfile("pc35_ssdd_320", "PC 3.5-inch 320 KB", "3.5-inch", "SS/DD", LegacyFloppyGeometry(80, 1, 8)),
    LegacyFloppyProfile("pc35_ssdd_360", "PC 3.5-inch 360 KB", "3.5-inch", "SS/DD", LegacyFloppyGeometry(80, 1, 9)),
    LegacyFloppyProfile("pc35_dsdd_640", "PC 3.5-inch 640 KB", "3.5-inch", "DS/DD", LegacyFloppyGeometry(80, 2, 8)),
    LegacyFloppyProfile("pc35_dsdd_720", "PC 3.5-inch 720 KB", "3.5-inch", "DS/DD", LegacyFloppyGeometry(80, 2, 9)),
    LegacyFloppyProfile("pc35_dshd_1440", "PC 3.5-inch 1.44 MB", "3.5-inch", "DS/HD", LegacyFloppyGeometry(80, 2, 18)),
    LegacyFloppyProfile("pc35_dshd_dmf_1680", "PC 3.5-inch DMF 1.68 MB", "3.5-inch", "DS/HD", LegacyFloppyGeometry(80, 2, 21)),
    LegacyFloppyProfile("pc35_dshd_82track_1722", "PC 3.5-inch 82-track 1,722 KiB", "3.5-inch", "DS/HD", LegacyFloppyGeometry(82, 2, 21)),
    LegacyFloppyProfile("pc35_dsed_2880", "PC 3.5-inch 2.88 MB", "3.5-inch", "DS/ED", LegacyFloppyGeometry(80, 2, 36)),
)


def legacy_floppy_profile(identifier: str) -> LegacyFloppyProfile:
    """Return one built-in profile or raise a clear validation error."""
    for profile in LEGACY_FLOPPY_PROFILES:
        if profile.identifier == identifier:
            return profile
    raise DiskForgeError(f"Unknown legacy floppy profile: {identifier}.")


def legacy_floppy_destination(path: Path | str, image_format: ImageFormat) -> Path:
    """Apply the explicit raw-image extension selected by the caller."""
    if image_format not in {ImageFormat.IMG, ImageFormat.IMA}:
        raise DiskForgeError("Legacy floppy images must use IMG or IMA output format.")
    target = Path(path)
    return target.with_suffix(f".{image_format.value}")


def create_legacy_fat_floppy(path: Path | str, geometry: LegacyFloppyGeometry, *,
                              image_format: ImageFormat = ImageFormat.IMA,
                              label: str = "DISKFORGE", profile: str | None = None) -> Path:
    """Create and verify a FAT12 legacy floppy image with explicit geometry.

    `profile` is audit metadata for the caller; the exact geometry always remains
    authoritative.  A new independently writable image is produced and reopened
    before the path is returned.
    """
    geometry.validate()
    target = legacy_floppy_destination(path, image_format)
    created = create_fat_image(
        target, geometry.size_bytes, FileSystemType.FAT12, label, media_type=0xF0,
        sectors_per_track=geometry.sectors_per_track, heads=geometry.heads,
        sector_size=geometry.sector_size,
    )
    info = inspect_image(created)
    if info.image_format != image_format or info.filesystem != FileSystemType.FAT12:
        created.unlink(missing_ok=True)
        raise DiskForgeError("Created legacy floppy did not reopen as the requested FAT12 IMG/IMA image.")
    with created.open("rb") as handle:
        boot = handle.read(64)
    actual = (
        int.from_bytes(boot[11:13], "little"), int.from_bytes(boot[24:26], "little"),
        int.from_bytes(boot[26:28], "little"),
    )
    expected = (geometry.sector_size, geometry.sectors_per_track, geometry.heads)
    if actual != expected:
        created.unlink(missing_ok=True)
        raise DiskForgeError("Created legacy floppy BPB geometry did not match the requested layout.")
    return created


def create_legacy_fat_floppy_profile(path: Path | str, identifier: str, *,
                                      image_format: ImageFormat = ImageFormat.IMA,
                                      label: str = "DISKFORGE") -> Path:
    """Create one built-in legacy FAT profile with an explicit IMG or IMA suffix."""
    profile = legacy_floppy_profile(identifier)
    return create_legacy_fat_floppy(path, profile.geometry, image_format=image_format, label=label, profile=profile.identifier)
