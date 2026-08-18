"""Media-layout helpers that never write to physical devices automatically.

The module covers portable image-file layouts only.  It intentionally avoids
controller-specific floppy formatting and proprietary boot code.
"""
from __future__ import annotations

import os
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

from .filesystems import create_fat_image
from .formats import inspect_image
from .models import FileSystemType, OperationKind, Progress, ProgressCallback, SECTOR_SIZE
from .storage import CancellationToken, DiskForgeError


DMF_TRACKS = 80
DMF_HEADS = 2
DMF_SECTORS_PER_TRACK = 21
DMF_SIZE_BYTES = DMF_TRACKS * DMF_HEADS * DMF_SECTORS_PER_TRACK * SECTOR_SIZE


@dataclass(frozen=True)
class MediaLayout:
    name: str
    size_bytes: int
    bytes_per_sector: int
    sectors_per_track: int
    heads: int
    tracks: int
    filesystem: FileSystemType


DMF_LAYOUT = MediaLayout(
    name="DMF 1.68 MB",
    size_bytes=DMF_SIZE_BYTES,
    bytes_per_sector=SECTOR_SIZE,
    sectors_per_track=DMF_SECTORS_PER_TRACK,
    heads=DMF_HEADS,
    tracks=DMF_TRACKS,
    filesystem=FileSystemType.FAT12,
)


@dataclass(frozen=True)
class MbrWrappedImage:
    path: Path
    source: Path
    partition_start_lba: int
    partition_sectors: int
    partition_type: int


@dataclass(frozen=True)
class TrimResult:
    source: Path
    destination: Path
    original_size: int
    trimmed_size: int

    @property
    def bytes_removed(self) -> int:
        return self.original_size - self.trimmed_size


def create_dmf_image(path: Path | str, label: str = "DISKFORGE") -> Path:
    """Create an image with documented 80×2×21×512 FAT12 geometry.

    This produces a portable *image-file* layout.  Physical media formatting is
    intentionally outside this function because modern platforms generally lack
    an addressable floppy controller.
    """
    return create_fat_image(
        path,
        DMF_LAYOUT.size_bytes,
        DMF_LAYOUT.filesystem,
        label,
        media_type=0xF0,
        sectors_per_track=DMF_LAYOUT.sectors_per_track,
        heads=DMF_LAYOUT.heads,
    )


def detect_dmf_layout(path: Path | str) -> MediaLayout | None:
    """Return the DMF layout only when both size and BPB geometry agree."""
    target = Path(path)
    if not target.is_file() or target.stat().st_size != DMF_LAYOUT.size_bytes:
        return None
    with target.open("rb") as handle:
        sector = handle.read(SECTOR_SIZE)
    if len(sector) != SECTOR_SIZE:
        return None
    sector_size = int.from_bytes(sector[11:13], "little")
    sectors_per_track = int.from_bytes(sector[24:26], "little")
    heads = int.from_bytes(sector[26:28], "little")
    filesystem = inspect_image(target).filesystem
    if (sector_size, sectors_per_track, heads, filesystem) == (
        DMF_LAYOUT.bytes_per_sector,
        DMF_LAYOUT.sectors_per_track,
        DMF_LAYOUT.heads,
        DMF_LAYOUT.filesystem,
    ):
        return DMF_LAYOUT
    return None


def _fat_partition_type(filesystem: FileSystemType) -> int:
    if filesystem == FileSystemType.FAT12:
        return 0x01
    if filesystem == FileSystemType.FAT16:
        return 0x06
    if filesystem == FileSystemType.FAT32:
        return 0x0C
    raise DiskForgeError("Only FAT images can be wrapped in a single-partition MBR image.")


def wrap_fat_image_in_mbr(source: Path | str, destination: Path | str, *, bootable: bool = False,
                          overwrite: bool = False,
                          progress: ProgressCallback | None = None,
                          token: CancellationToken | None = None) -> MbrWrappedImage:
    """Create a neutral MBR image containing one FAT partition.

    The partition starts at LBA 1 and has the exact byte content of the source
    superfloppy image.  The bootstrap region intentionally contains zero bytes;
    no third-party boot program is copied or implied.
    """
    source_path, destination_path = Path(source), Path(destination)
    info = inspect_image(source_path)
    if info.filesystem not in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        raise DiskForgeError("The source must be a recognized FAT superfloppy image.")
    size = source_path.stat().st_size
    if size <= 0 or size % SECTOR_SIZE:
        raise DiskForgeError("FAT image size must be a non-zero multiple of 512 bytes.")
    sectors = size // SECTOR_SIZE
    if sectors > 0xFFFFFFFF:
        raise DiskForgeError("FAT image is too large for this MBR partition wrapper.")
    if destination_path.exists() and not overwrite:
        raise FileExistsError(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    mbr = bytearray(SECTOR_SIZE)
    entry = memoryview(mbr)[446:462]
    entry[0] = 0x80 if bootable else 0x00
    entry[1:4] = b"\x00\x02\x00"  # conventional CHS start for LBA 1
    entry[4] = _fat_partition_type(info.filesystem)
    entry[5:8] = b"\xfe\xff\xff"  # LBA addressing; CHS intentionally saturated
    struct.pack_into("<II", entry, 8, 1, sectors)
    mbr[510:512] = b"\x55\xaa"
    block_size = 1024 * 1024
    copied = 0
    try:
        with source_path.open("rb") as reader, destination_path.open("wb") as writer:
            writer.write(mbr)
            while True:
                if token:
                    token.raise_if_cancelled()
                chunk = reader.read(block_size)
                if not chunk:
                    break
                writer.write(chunk)
                copied += len(chunk)
                if progress:
                    progress(Progress(OperationKind.CREATE, copied, size, "Writing FAT partition into MBR image"))
            writer.flush()
            os.fsync(writer.fileno())
    except Exception:
        destination_path.unlink(missing_ok=True)
        raise
    return MbrWrappedImage(destination_path, source_path, 1, sectors, _fat_partition_type(info.filesystem))


def trim_zero_tail(source: Path | str, destination: Path | str, *, minimum_size: int = SECTOR_SIZE,
                   overwrite: bool = False,
                   progress: ProgressCallback | None = None,
                   token: CancellationToken | None = None) -> TrimResult:
    """Copy an image to a new file after removing only full trailing zero sectors.

    The caller must choose this raw/block-level operation explicitly.  It does
    not infer filesystem free space or shrink partition metadata, and it rejects
    a minimum size that is not sector aligned.
    """
    source_path, destination_path = Path(source), Path(destination)
    source_size = source_path.stat().st_size
    if minimum_size < 0 or minimum_size % SECTOR_SIZE:
        raise DiskForgeError("Minimum trim size must be a non-negative multiple of 512 bytes.")
    if source_size % SECTOR_SIZE:
        raise DiskForgeError("Only sector-aligned images can be trimmed safely.")
    if destination_path.exists() and not overwrite:
        raise FileExistsError(destination_path)
    block_size = 1024 * 1024
    retained = source_size
    with source_path.open("rb") as reader:
        cursor = source_size
        while cursor > minimum_size:
            if token:
                token.raise_if_cancelled()
            amount = min(block_size, cursor - minimum_size)
            cursor -= amount
            reader.seek(cursor)
            block = reader.read(amount)
            nonzero = block.rstrip(b"\x00")
            if nonzero:
                retained = cursor + len(nonzero)
                retained = max(minimum_size, ((retained + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE)
                break
        else:
            retained = minimum_size
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source_path.open("rb") as reader, destination_path.open("wb") as writer:
            copied = 0
            while copied < retained:
                if token:
                    token.raise_if_cancelled()
                chunk = reader.read(min(block_size, retained - copied))
                if not chunk:
                    raise DiskForgeError("Source image ended while trimming.")
                writer.write(chunk)
                copied += len(chunk)
                if progress:
                    progress(Progress(OperationKind.RESIZE, copied, retained, "Copying retained image sectors"))
            writer.flush()
            os.fsync(writer.fileno())
    except Exception:
        destination_path.unlink(missing_ok=True)
        raise
    return TrimResult(source_path, destination_path, source_size, retained)
