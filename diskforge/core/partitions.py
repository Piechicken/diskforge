"""Partition-table inspection for raw and fixed-VHD image payloads."""
from __future__ import annotations

import binascii
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path

from .formats import detect_filesystem
from .models import DiskPartition, FileSystemType, SECTOR_SIZE
from .storage import DiskForgeError, read_sector


MBR_TYPES = {
    0x01: ("FAT12", FileSystemType.FAT12),
    0x04: ("FAT16 <32M", FileSystemType.FAT16),
    0x06: ("FAT16", FileSystemType.FAT16),
    0x0B: ("FAT32", FileSystemType.FAT32),
    0x0C: ("FAT32 LBA", FileSystemType.FAT32),
    0x07: ("NTFS/exFAT", FileSystemType.NTFS),
    0x83: ("Linux", FileSystemType.EXT),
    0xAF: ("Apple HFS", FileSystemType.HFS),
    0x82: ("Linux swap", FileSystemType.UNKNOWN),
    0xEE: ("GPT protective", FileSystemType.UNKNOWN),
}


@dataclass(frozen=True)
class GptInspection:
    """Validated GPT metadata and user-visible warnings."""

    disk_guid: str
    primary_lba: int
    backup_lba: int
    first_usable_lba: int
    last_usable_lba: int
    partitions: tuple[DiskPartition, ...]
    backup_header_valid: bool
    warnings: tuple[str, ...] = ()


def _filesystem_from_boot(path: Path, offset: int) -> FileSystemType:
    """Inspect a filesystem boot sector with the shared conservative detector."""
    size = path.stat().st_size
    if offset < 0 or offset + SECTOR_SIZE > size:
        return FileSystemType.UNKNOWN
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(min(4096, size - offset))
    return detect_filesystem(data, image_size=size - offset)


def parse_mbr(path: Path | str) -> list[DiskPartition]:
    """Parse the four primary MBR entries; extended partitions stay visible as containers."""
    target = Path(path)
    sector = read_sector(target, 0)
    if sector[510:512] != b"\x55\xaa":
        return []
    partitions: list[DiskPartition] = []
    for index in range(4):
        entry = sector[446 + index * 16:462 + index * 16]
        type_id = entry[4]
        start_lba, sectors = struct.unpack_from("<II", entry, 8)
        if type_id == 0 or sectors == 0:
            continue
        name, known_fs = MBR_TYPES.get(type_id, (f"Type 0x{type_id:02X}", FileSystemType.UNKNOWN))
        detected_fs = _filesystem_from_boot(target, start_lba * SECTOR_SIZE)
        partitions.append(DiskPartition(index + 1, start_lba, sectors, name,
                                        filesystem=detected_fs if detected_fs != FileSystemType.UNKNOWN else known_fs))
    return partitions


def _decode_gpt_name(raw: bytes) -> str:
    return raw.decode("utf-16-le", errors="replace").split("\0", 1)[0].strip()


def _guid(raw: bytes) -> str:
    try:
        return str(uuid.UUID(bytes_le=raw))
    except (ValueError, AttributeError) as exc:
        raise DiskForgeError("GPT GUID is invalid.") from exc


def _crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def _read_gpt_header(path: Path, lba: int, total_lbas: int) -> dict[str, object]:
    if lba <= 0 or lba >= total_lbas:
        raise DiskForgeError("GPT header is outside image bounds.")
    header = read_sector(path, lba)
    if header[:8] != b"EFI PART":
        raise DiskForgeError("GPT header signature is missing.")
    header_size = struct.unpack_from("<I", header, 12)[0]
    if header_size < 92 or header_size > SECTOR_SIZE:
        raise DiskForgeError("Invalid GPT header size.")
    stored_crc = struct.unpack_from("<I", header, 16)[0]
    crc_bytes = bytearray(header[:header_size])
    crc_bytes[16:20] = b"\0\0\0\0"
    if _crc32(crc_bytes) != stored_crc:
        raise DiskForgeError("GPT header CRC32 is invalid.")
    current_lba, backup_lba, first_usable, last_usable = struct.unpack_from("<QQQQ", header, 24)
    if current_lba != lba or backup_lba >= total_lbas or first_usable > last_usable:
        raise DiskForgeError("GPT header contains invalid LBA bounds.")
    entry_lba = struct.unpack_from("<Q", header, 72)[0]
    entry_count, entry_size, entry_crc = struct.unpack_from("<III", header, 80)
    if not 128 <= entry_size <= 4096 or entry_count == 0 or entry_count > 131072:
        raise DiskForgeError("Invalid GPT entry array layout.")
    byte_count = entry_count * entry_size
    if entry_lba == 0 or entry_lba * SECTOR_SIZE + byte_count > total_lbas * SECTOR_SIZE:
        raise DiskForgeError("GPT entry array is outside image bounds.")
    with path.open("rb") as handle:
        handle.seek(entry_lba * SECTOR_SIZE)
        entries = handle.read(byte_count)
    if len(entries) != byte_count:
        raise DiskForgeError("GPT entry array is truncated.")
    if _crc32(entries) != entry_crc:
        raise DiskForgeError("GPT entry array CRC32 is invalid.")
    return {
        "lba": lba,
        "backup_lba": backup_lba,
        "first_usable": first_usable,
        "last_usable": last_usable,
        "disk_guid": _guid(header[56:72]),
        "entry_count": entry_count,
        "entry_size": entry_size,
        "entries": entries,
    }


def inspect_gpt(path: Path | str) -> GptInspection | None:
    """Validate primary GPT and, when possible, its backup before listing partitions."""
    target = Path(path)
    total_lbas = target.stat().st_size // SECTOR_SIZE
    if total_lbas < 3:
        return None
    try:
        first_sector = read_sector(target, 1)
    except DiskForgeError:
        return None
    if first_sector[:8] != b"EFI PART":
        return None
    primary = _read_gpt_header(target, 1, total_lbas)
    warnings: list[str] = []
    backup_valid = False
    try:
        backup = _read_gpt_header(target, int(primary["backup_lba"]), total_lbas)
        if backup["backup_lba"] != 1 or backup["disk_guid"] != primary["disk_guid"]:
            raise DiskForgeError("GPT backup header does not match the primary header.")
        backup_valid = True
    except DiskForgeError as exc:
        warnings.append(f"Backup GPT validation failed: {exc}")
    entries = primary["entries"]
    entry_count, entry_size = int(primary["entry_count"]), int(primary["entry_size"])
    first_usable, last_usable = int(primary["first_usable"]), int(primary["last_usable"])
    partitions: list[DiskPartition] = []
    extents: list[tuple[int, int]] = []
    for index in range(entry_count):
        entry = entries[index * entry_size:(index + 1) * entry_size]
        if entry[:16] == b"\0" * 16:
            continue
        first_lba, last_lba = struct.unpack_from("<QQ", entry, 32)
        if first_lba < first_usable or last_lba > last_usable or last_lba < first_lba:
            raise DiskForgeError(f"GPT partition {index + 1} has invalid bounds.")
        for previous_first, previous_last in extents:
            if not (last_lba < previous_first or first_lba > previous_last):
                raise DiskForgeError(f"GPT partition {index + 1} overlaps another partition.")
        extents.append((first_lba, last_lba))
        fs = _filesystem_from_boot(target, first_lba * SECTOR_SIZE)
        partitions.append(DiskPartition(index + 1, first_lba, last_lba - first_lba + 1,
                                        _guid(entry[:16]), _decode_gpt_name(entry[56:128]), fs))
    return GptInspection(str(primary["disk_guid"]), 1, int(primary["backup_lba"]), first_usable,
                         last_usable, tuple(partitions), backup_valid, tuple(warnings))


def parse_gpt(path: Path | str) -> list[DiskPartition]:
    """Return GPT partitions after strict primary-header and entry-array validation."""
    inspection = inspect_gpt(path)
    return list(inspection.partitions) if inspection else []


def list_partitions(path: Path | str) -> list[DiskPartition]:
    """Prefer GPT when present, otherwise return MBR primary partitions."""
    gpt = parse_gpt(path)
    return gpt if gpt else parse_mbr(path)


def select_partition(path: Path | str, index: int) -> DiskPartition:
    """Return one validated MBR/GPT partition by its stable one-based table index."""
    if index <= 0:
        raise DiskForgeError("Partition index must be a positive table index.")
    for partition in list_partitions(path):
        if partition.index == index:
            return partition
    raise DiskForgeError(f"Partition {index} does not exist in this image.")


def fat_partition_offset(path: Path | str, *, partition_index: int | None = None) -> int:
    """Return a FAT volume offset, optionally from an explicitly selected partition.

    A superfloppy has no partition index and continues to resolve to offset zero
    for backwards compatibility.  Partitioned images may opt into explicit
    selection so multi-volume media is never silently opened at the wrong FAT
    volume.
    """
    target = Path(path)
    direct = _filesystem_from_boot(target, 0)
    if partition_index is not None:
        if direct in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
            raise DiskForgeError("A superfloppy image has no selectable partition index.")
        partition = select_partition(target, partition_index)
        if partition.filesystem not in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
            raise DiskForgeError(f"Partition {partition_index} is not a FAT filesystem.")
        return partition.offset
    if direct in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        return 0
    for partition in list_partitions(target):
        if partition.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
            return partition.offset
    raise DiskForgeError("No FAT filesystem was found in this image.")
