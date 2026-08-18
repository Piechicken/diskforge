"""Read-only El Torito boot catalog inspection and boot image export."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import OperationKind, Progress, ProgressCallback
from .storage import CancellationToken, DiskForgeError


ISO_BLOCK_SIZE = 2048


@dataclass(frozen=True)
class ElToritoBootImage:
    index: int
    bootable: bool
    media_type: int
    load_segment: int
    system_type: int
    sector_count_512: int
    lba: int

    @property
    def byte_count(self) -> int:
        return self.sector_count_512 * 512


@dataclass(frozen=True)
class ElToritoCatalog:
    iso_path: Path
    catalog_lba: int
    images: tuple[ElToritoBootImage, ...]


def _read_block(handle, lba: int) -> bytes:
    handle.seek(lba * ISO_BLOCK_SIZE)
    data = handle.read(ISO_BLOCK_SIZE)
    if len(data) != ISO_BLOCK_SIZE:
        raise DiskForgeError("ISO image ends before the requested El Torito structure.")
    return data


def _boot_catalog_lba(path: Path) -> int:
    with path.open("rb") as handle:
        # Descriptors start at LBA 16.  A boot record may appear before the PVD.
        for lba in range(16, 256):
            descriptor = _read_block(handle, lba)
            if descriptor[1:6] != b"CD001" or descriptor[6] != 1:
                raise DiskForgeError("Image does not contain a valid ISO9660 descriptor sequence.")
            if descriptor[0] == 0 and descriptor[7:39].upper().startswith(b"EL TORITO SPECIFICATION"):
                return int.from_bytes(descriptor[71:75], "little")
            if descriptor[0] == 255:
                break
    raise DiskForgeError("ISO image does not contain an El Torito boot record.")


def _catalog_entries(data: bytes) -> tuple[ElToritoBootImage, ...]:
    if data[0] not in {0x01, 0x00} or data[30:32] != b"\x55\xaa":
        raise DiskForgeError("El Torito boot catalog validation entry is invalid.")
    entries: list[ElToritoBootImage] = []
    platform = data[1] if data[0] == 0x01 else 0
    index = 0
    position = 32
    while position + 32 <= len(data):
        entry = data[position:position + 32]
        indicator = entry[0]
        if indicator in {0x90, 0x91}:  # section header, with or without final flag
            platform = entry[1]
            position += 32
            continue
        if indicator in {0x88, 0x00}:
            sectors = int.from_bytes(entry[6:8], "little")
            lba = int.from_bytes(entry[8:12], "little")
            # Zero padding marks the remainder of this catalog sector.
            if lba == 0 and sectors == 0 and entry[1:] == b"\x00" * 31:
                break
            entries.append(ElToritoBootImage(
                index=index,
                bootable=indicator == 0x88,
                media_type=entry[1],
                load_segment=int.from_bytes(entry[2:4], "little"),
                system_type=entry[4],
                sector_count_512=sectors,
                lba=lba,
            ))
            index += 1
        position += 32
    if not entries:
        raise DiskForgeError("El Torito boot catalog does not contain a boot image entry.")
    return tuple(entries)


def inspect_eltorito(path: Path | str) -> ElToritoCatalog:
    """Inspect a valid ISO9660 El Torito boot catalog without altering the image."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    catalog_lba = _boot_catalog_lba(source)
    with source.open("rb") as handle:
        entries = _catalog_entries(_read_block(handle, catalog_lba))
    return ElToritoCatalog(source, catalog_lba, entries)


def export_boot_image(path: Path | str, destination: Path | str, *, index: int = 0,
                      overwrite: bool = False, progress: ProgressCallback | None = None,
                      token: CancellationToken | None = None) -> Path:
    """Export one catalog-referenced boot image using its declared load size."""
    catalog = inspect_eltorito(path)
    if index < 0 or index >= len(catalog.images):
        raise DiskForgeError("El Torito boot image index is outside the catalog range.")
    image = catalog.images[index]
    if image.byte_count <= 0:
        raise DiskForgeError("El Torito boot image declares zero load sectors.")
    target = Path(destination)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    source_size = catalog.iso_path.stat().st_size
    start = image.lba * ISO_BLOCK_SIZE
    if start + image.byte_count > source_size:
        raise DiskForgeError("El Torito boot image extends beyond the ISO image.")
    target.parent.mkdir(parents=True, exist_ok=True)
    copied = 0
    block_size = 1024 * 1024
    try:
        with catalog.iso_path.open("rb") as reader, target.open("wb") as writer:
            reader.seek(start)
            while copied < image.byte_count:
                if token:
                    token.raise_if_cancelled()
                chunk = reader.read(min(block_size, image.byte_count - copied))
                if not chunk:
                    raise DiskForgeError("ISO image ended while exporting the boot image.")
                writer.write(chunk)
                copied += len(chunk)
                if progress:
                    progress(Progress(OperationKind.EXTRACT, copied, image.byte_count, "Exporting El Torito boot image"))
            writer.flush()
            os.fsync(writer.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target
