"""Validated FAT layout import and reproducible image creation.

A layout is descriptive metadata for a new FAT superfloppy image.  It is never
used as an instruction to modify a physical device.  Import accepts only a
self-consistent FAT BPB and creation delegates to the native formatter.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import FileSystemType
from .storage import DiskForgeError


_SECTOR_SIZES = {512, 1024, 2048, 4096}
_CLUSTER_SECTORS = {1, 2, 4, 8, 16, 32, 64, 128}


@dataclass(frozen=True)
class FatImageLayout:
    """A complete, validated FAT superfloppy layout that can be recreated safely."""

    filesystem: FileSystemType
    size_bytes: int
    sector_size: int
    sectors_per_track: int
    heads: int
    fat_count: int
    media_type: int

    @classmethod
    def from_image(cls, path: Path | str) -> "FatImageLayout":
        """Import a reproducible layout from a raw FAT image's primary BPB."""
        image = Path(path)
        if not image.is_file():
            raise FileNotFoundError(image)
        return cls.from_boot_sector(image.read_bytes()[:4096], image.stat().st_size)

    @classmethod
    def from_boot_sector(cls, data: bytes, image_size: int, *, require_geometry: bool = True) -> "FatImageLayout":
        """Parse a FAT BPB from an image prefix with an explicit data-region size.

        Template-derived creation requires positive BIOS geometry.  Existing
        virtual disks may legitimately retain zero geometry metadata, so read-only
        validation of their data region can opt out without making the layout
        suitable for re-creation.
        """
        if len(data) < 512 or data[0] not in {0xEB, 0xE9}:
            raise DiskForgeError("The template does not contain a valid FAT boot sector.")
        sector_size = int.from_bytes(data[11:13], "little")
        if sector_size not in _SECTOR_SIZES or len(data) < sector_size:
            raise DiskForgeError("The template FAT sector size is not supported.")
        if data[sector_size - 2:sector_size] != b"\x55\xaa":
            raise DiskForgeError("The template does not contain a valid FAT boot sector signature.")
        sectors_per_cluster = data[13]
        reserved_sectors = int.from_bytes(data[14:16], "little")
        fat_count = data[16]
        root_entries = int.from_bytes(data[17:19], "little")
        total_sectors = int.from_bytes(data[19:21], "little") or int.from_bytes(data[32:36], "little")
        media_type = data[21]
        fat_sectors = int.from_bytes(data[22:24], "little") or int.from_bytes(data[36:40], "little")
        sectors_per_track = int.from_bytes(data[24:26], "little")
        heads = int.from_bytes(data[26:28], "little")
        size_bytes = total_sectors * sector_size

        if sectors_per_cluster not in _CLUSTER_SECTORS:
            raise DiskForgeError("The template FAT cluster size is not supported.")
        if reserved_sectors < 1 or fat_count not in {1, 2} or fat_sectors < 1:
            raise DiskForgeError("The template FAT allocation-table layout is not supported.")
        if require_geometry and (sectors_per_track < 1 or heads < 1):
            raise DiskForgeError("The template FAT BIOS geometry is incomplete.")
        if media_type != 0xF0 and not 0xF8 <= media_type <= 0xFF:
            raise DiskForgeError("The template FAT media descriptor is invalid.")
        if total_sectors < 1 or size_bytes != image_size:
            raise DiskForgeError("The template FAT size does not match its BPB.")
        root_directory_sectors = (root_entries * 32 + sector_size - 1) // sector_size
        data_sectors = total_sectors - (reserved_sectors + fat_count * fat_sectors + root_directory_sectors)
        clusters = data_sectors // sectors_per_cluster
        if clusters < 1:
            raise DiskForgeError("The template FAT data area is invalid.")
        filesystem = (
            FileSystemType.FAT12 if clusters < 4085 else
            FileSystemType.FAT16 if clusters < 65525 else
            FileSystemType.FAT32
        )
        return cls(filesystem, size_bytes, sector_size, sectors_per_track, heads, fat_count, media_type)

    def validate(self) -> None:
        """Reject parameters that cannot produce a portable, valid FAT image."""
        if self.filesystem not in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
            raise DiskForgeError("Only FAT12, FAT16 and FAT32 layouts can be created.")
        if self.sector_size not in _SECTOR_SIZES:
            raise DiskForgeError("FAT sector size must be a supported power of two from 512 to 4096 bytes.")
        if self.size_bytes < self.sector_size or self.size_bytes % self.sector_size:
            raise DiskForgeError("FAT layout size must be sector-aligned.")
        if self.fat_count not in {1, 2}:
            raise DiskForgeError("FAT layout must contain one or two allocation tables.")
        if not 1 <= self.sectors_per_track <= 0xFFFF or not 1 <= self.heads <= 0xFFFF:
            raise DiskForgeError("FAT layout BIOS geometry must contain positive 16-bit values.")
        if self.media_type != 0xF0 and not 0xF8 <= self.media_type <= 0xFF:
            raise DiskForgeError("FAT layout media descriptor is invalid.")

    def as_mapping(self) -> dict[str, int | str]:
        """Return a portable, JSON-ready description for GUI and CLI callers."""
        return {
            "filesystem": self.filesystem.value,
            "size_bytes": self.size_bytes,
            "sector_size": self.sector_size,
            "sectors_per_track": self.sectors_per_track,
            "heads": self.heads,
            "fat_count": self.fat_count,
            "media_type": self.media_type,
        }


def create_fat_image_from_layout(path: Path | str, layout: FatImageLayout, *, label: str = "DISKFORGE") -> Path:
    """Create a new FAT image from a validated template-derived layout."""
    layout.validate()
    from .filesystems import create_fat_image

    return create_fat_image(
        path,
        layout.size_bytes,
        layout.filesystem,
        label,
        media_type=layout.media_type,
        sectors_per_track=layout.sectors_per_track,
        heads=layout.heads,
        sector_size=layout.sector_size,
        fat_count=layout.fat_count,
    )
