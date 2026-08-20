"""Conservative read-only recovery of simple deleted FAT root-directory files.

This module deliberately offers a narrow forensic convenience, not generic file
recovery. It never writes the source volume; it only copies a strictly checked
single-cluster candidate to a new local output path.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .storage import CancellationToken, DiskForgeError


_MAX_BPB_SECTOR_SIZE = 4096


@dataclass(frozen=True)
class DeletedFatFileCandidate:
    """A deleted 8.3 root-directory file slot and its conservative recovery state."""

    slot_index: int
    display_name: str
    bytes: int
    first_cluster: int
    cluster_bytes: int
    recoverable: bool
    reason: str


@dataclass(frozen=True)
class _FatLayout:
    kind: str
    volume_offset: int
    volume_bytes: int
    bytes_per_sector: int
    sectors_per_cluster: int
    cluster_bytes: int
    root_directory_offset: int
    root_directory_entries: int
    first_data_sector: int
    cluster_count: int
    first_fat_offset: int
    fat_bytes: int


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _read_exact(handle: BinaryIO, size: int, message: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise DiskForgeError(message)
    return data


def _layout(image: Path, offset: int) -> _FatLayout:
    """Read and validate only the BPB fields necessary for this bounded service."""
    if offset < 0:
        raise DiskForgeError("FAT recovery requires a non-negative volume offset.")
    image_bytes = image.stat().st_size
    if offset + 64 > image_bytes:
        raise DiskForgeError("The selected FAT volume is too small to contain a valid BPB.")
    with image.open("rb") as handle:
        handle.seek(offset)
        bpb = _read_exact(handle, 64, "The selected FAT volume has a truncated BPB.")
    bytes_per_sector = _u16(bpb, 11)
    sectors_per_cluster = bpb[13]
    reserved_sectors = _u16(bpb, 14)
    fat_count = bpb[16]
    root_entries = _u16(bpb, 17)
    total_sectors = _u16(bpb, 19) or _u32(bpb, 32)
    sectors_per_fat = _u16(bpb, 22)
    if bytes_per_sector not in {512, 1024, 2048, _MAX_BPB_SECTOR_SIZE}:
        raise DiskForgeError("FAT recovery requires a supported 512–4096-byte BPB sector size.")
    if not sectors_per_cluster or sectors_per_cluster & (sectors_per_cluster - 1):
        raise DiskForgeError("FAT recovery requires a power-of-two sectors-per-cluster value.")
    if not reserved_sectors or not fat_count or not root_entries or not total_sectors or not sectors_per_fat:
        raise DiskForgeError("FAT recovery requires a FAT12/FAT16 BPB with a fixed root directory.")
    root_directory_sectors = (root_entries * 32 + bytes_per_sector - 1) // bytes_per_sector
    first_data_sector = reserved_sectors + fat_count * sectors_per_fat + root_directory_sectors
    if first_data_sector >= total_sectors:
        raise DiskForgeError("The FAT BPB does not leave a valid data area.")
    data_sectors = total_sectors - first_data_sector
    cluster_count = data_sectors // sectors_per_cluster
    kind = "fat12" if cluster_count < 4085 else "fat16" if cluster_count < 65525 else "fat32"
    if kind == "fat32":
        raise DiskForgeError("Deleted-file recovery currently supports FAT12 and FAT16 fixed root directories only.")
    volume_bytes = total_sectors * bytes_per_sector
    if offset + volume_bytes > image_bytes:
        raise DiskForgeError("The FAT BPB declares bytes beyond the selected source image.")
    return _FatLayout(
        kind=kind,
        volume_offset=offset,
        volume_bytes=volume_bytes,
        bytes_per_sector=bytes_per_sector,
        sectors_per_cluster=sectors_per_cluster,
        cluster_bytes=bytes_per_sector * sectors_per_cluster,
        root_directory_offset=offset + (reserved_sectors + fat_count * sectors_per_fat) * bytes_per_sector,
        root_directory_entries=root_entries,
        first_data_sector=first_data_sector,
        cluster_count=cluster_count,
        first_fat_offset=offset + reserved_sectors * bytes_per_sector,
        fat_bytes=sectors_per_fat * bytes_per_sector,
    )


def _display_name(entry: bytes) -> str:
    """Render a stable name while admitting that the first deleted character is lost."""
    base = "?" + entry[1:8].decode("cp437", errors="replace").rstrip(" ")
    extension = entry[8:11].decode("cp437", errors="replace").rstrip(" ")
    return f"{base}.{extension}" if extension else base


def _fat_value(handle: BinaryIO, layout: _FatLayout, cluster: int) -> int:
    if layout.kind == "fat12":
        entry_offset = cluster + cluster // 2
        if entry_offset + 2 > layout.fat_bytes:
            raise DiskForgeError("The deleted-file cluster is outside the FAT12 allocation table.")
        handle.seek(layout.first_fat_offset + entry_offset)
        packed = int.from_bytes(_read_exact(handle, 2, "The FAT12 allocation table is truncated."), "little")
        return packed >> 4 if cluster & 1 else packed & 0x0FFF
    entry_offset = cluster * 2
    if entry_offset + 2 > layout.fat_bytes:
        raise DiskForgeError("The deleted-file cluster is outside the FAT16 allocation table.")
    handle.seek(layout.first_fat_offset + entry_offset)
    return int.from_bytes(_read_exact(handle, 2, "The FAT16 allocation table is truncated."), "little")


def _candidate_from_slot(handle: BinaryIO, layout: _FatLayout, slot_index: int, entry: bytes) -> DeletedFatFileCandidate | None:
    if entry[0] != 0xE5:
        return None
    attributes = entry[11]
    if attributes & 0x08:  # Volume labels and long-name entries are never files.
        return None
    if attributes & 0x10:
        return None
    first_cluster = _u16(entry, 26)
    size = _u32(entry, 28)
    reason = "The deleted entry is not a non-empty single-cluster regular-file candidate."
    recoverable = False
    if first_cluster >= 2 and first_cluster < layout.cluster_count + 2 and 0 < size <= layout.cluster_bytes:
        current_value = _fat_value(handle, layout, first_cluster)
        if current_value == 0:
            recoverable = True
            reason = "Candidate data is a single currently free cluster; contents may still be overwritten."
        else:
            reason = "The candidate cluster is currently allocated or reserved."
    return DeletedFatFileCandidate(
        slot_index=slot_index,
        display_name=_display_name(entry),
        bytes=size,
        first_cluster=first_cluster,
        cluster_bytes=layout.cluster_bytes,
        recoverable=recoverable,
        reason=reason,
    )


def list_deleted_root_files(image_path: Path | str, *, offset: int = 0,
                            token: CancellationToken | None = None) -> list[DeletedFatFileCandidate]:
    """List deleted ordinary 8.3 file slots in a FAT12/FAT16 fixed root directory."""
    image = Path(image_path)
    layout = _layout(image, offset)
    candidates: list[DeletedFatFileCandidate] = []
    with image.open("rb") as handle:
        for slot_index in range(layout.root_directory_entries):
            if token:
                token.raise_if_cancelled()
            handle.seek(layout.root_directory_offset + slot_index * 32)
            entry = _read_exact(handle, 32, "The FAT root directory is truncated.")
            if entry[0] == 0x00:
                break
            candidate = _candidate_from_slot(handle, layout, slot_index, entry)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def recover_deleted_root_file(image_path: Path | str, slot_index: int, destination: Path | str, *,
                               offset: int = 0, token: CancellationToken | None = None) -> Path:
    """Copy one revalidated recoverable candidate to a new local file without source mutation."""
    image = Path(image_path)
    target = Path(destination)
    if slot_index < 0:
        raise DiskForgeError("The deleted-file slot index must be non-negative.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The deleted-file recovery destination directory does not exist.")
    layout = _layout(image, offset)
    if slot_index >= layout.root_directory_entries:
        raise DiskForgeError("The deleted-file slot index is outside the FAT root directory.")
    temporary: Path | None = None
    try:
        with image.open("rb") as source:
            source.seek(layout.root_directory_offset + slot_index * 32)
            entry = _read_exact(source, 32, "The FAT root directory is truncated.")
            candidate = _candidate_from_slot(source, layout, slot_index, entry)
            if candidate is None:
                raise DiskForgeError("The selected FAT root-directory slot is not a deleted regular-file candidate.")
            if not candidate.recoverable:
                raise DiskForgeError(f"The selected deleted-file candidate is not recoverable: {candidate.reason}")
            data_offset = layout.volume_offset + layout.first_data_sector * layout.bytes_per_sector + (
                candidate.first_cluster - 2
            ) * layout.cluster_bytes
            if data_offset < layout.volume_offset or data_offset + candidate.bytes > layout.volume_offset + layout.volume_bytes:
                raise DiskForgeError("The deleted-file candidate data range is outside the FAT volume.")
            if token:
                token.raise_if_cancelled()
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.diskforge-recovery-", suffix=".tmp", dir=target.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as output:
                source.seek(data_offset)
                remaining = candidate.bytes
                while remaining:
                    if token:
                        token.raise_if_cancelled()
                    block = _read_exact(source, min(1024 * 1024, remaining), "The deleted-file candidate data is truncated.")
                    output.write(block)
                    remaining -= len(block)
        if token:
            token.raise_if_cancelled()
        # Hard-link promotion atomically refuses a destination that appeared after preflight.
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
