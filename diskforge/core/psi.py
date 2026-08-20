"""Read-only PCE PSI inspection and strict normal-sector RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_COMMENT_BYTES = 64 * 1024
_MAX_CYLINDER = 85
_MAX_SECTOR_ID = 32
_MAX_SECTOR_BYTES = 4096
_CRC_POLY = 0x1EDC6F41
_ALLOWED = {b"TEXT", b"SECT", b"DATA", b"IBMF", b"IBMM", b"OFFS", b"TIME", b"END "}


@dataclass(frozen=True)
class PsiSector:
    cylinder: int
    head: int
    sector: int
    data_bytes: int
    compressed: bool
    data: bytes


@dataclass
class _PendingSector:
    cylinder: int
    head: int
    sector: int
    data_bytes: int
    compressed: bool
    data: bytes | None


@dataclass(frozen=True)
class PsiInspection:
    source: Path
    source_bytes: int
    default_format: int
    comment_count: int
    metadata_chunk_count: int
    sectors: tuple[PsiSector, ...]
    compressed_sector_count: int
    exportable: bool
    export_reason: str
    raw_bytes: int | None


def _crc32c_nonreflected(payload: bytes, crc: int = 0) -> int:
    """PSI's non-reflected CRC-32C update, matching the public PCE implementation."""
    value = crc & 0xFFFFFFFF
    for byte in payload:
        value ^= byte << 24
        for _ in range(8):
            value = ((value << 1) ^ _CRC_POLY) & 0xFFFFFFFF if value & 0x80000000 else (value << 1) & 0xFFFFFFFF
    return value


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("PSI inspection accepts regular non-symbolic-link source files only.")
    if not (28 <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The PSI source size is outside the 28-byte to 32-MiB safety range.")
    return size


def _read_chunk(content: bytes, position: int) -> tuple[bytes, bytes, int]:
    if position + 12 > len(content):
        raise DiskForgeError("A PSI chunk header, payload, or CRC is truncated.")
    header = content[position:position + 8]
    chunk_id = header[:4]
    size = int.from_bytes(header[4:8], "big")
    end = position + 8 + size
    if end + 4 > len(content):
        raise DiskForgeError("A PSI chunk payload or CRC is truncated.")
    payload = content[position + 8:end]
    stored_crc = int.from_bytes(content[end:end + 4], "big")
    calculated_crc = _crc32c_nonreflected(payload, _crc32c_nonreflected(header))
    if calculated_crc != stored_crc:
        raise DiskForgeError("A PSI chunk CRC is invalid.")
    return chunk_id, payload, end + 4


def _check_metadata(chunk_id: bytes, payload: bytes, last: _PendingSector | None) -> None:
    if last is None:
        raise DiskForgeError("A PSI sector metadata chunk appears before a sector record.")
    if chunk_id in {b"OFFS", b"TIME"}:
        if len(payload) != 4:
            raise DiskForgeError("A PSI position/time metadata chunk must be exactly four bytes.")
        return
    if len(payload) != 6:
        raise DiskForgeError("A PSI IBM sector metadata chunk must be exactly six bytes.")
    cylinder = payload[0]
    head, sector, size_index, status = payload[1:5]
    if status or size_index > 5 or (128 << size_index) != last.data_bytes:
        raise DiskForgeError("PSI IBM sector metadata has unsupported status or mismatched size.")
    if (cylinder, head, sector) != (last.cylinder, last.head, last.sector):
        raise DiskForgeError("PSI IBM sector metadata does not match its preceding sector record.")


def _export_geometry(sectors: tuple[PsiSector, ...]) -> tuple[bool, str, int | None]:
    if not sectors:
        return False, "PSI RAW export requires at least one complete sector record.", None
    data_sizes = {item.data_bytes for item in sectors}
    if len(data_sizes) != 1:
        return False, "PSI RAW export requires one fixed sector byte size.", None
    heads = {item.head for item in sectors}
    cylinders = {item.cylinder for item in sectors}
    if heads != set(range(max(heads) + 1)) or max(heads) > 1 or cylinders != set(range(max(cylinders) + 1)):
        return False, "PSI RAW export requires zero-based contiguous cylinder and head coordinates.", None
    expected_sector_ids: set[int] | None = None
    for cylinder in range(max(cylinders) + 1):
        for head in range(max(heads) + 1):
            current = [item for item in sectors if item.cylinder == cylinder and item.head == head]
            ids = {item.sector for item in current}
            if len(current) != len(ids) or not ids:
                return False, "PSI RAW export rejects duplicate or empty tracks.", None
            if expected_sector_ids is None:
                expected_sector_ids = set(range(1, len(ids) + 1))
            if ids != expected_sector_ids:
                return False, "PSI RAW export requires every track to use consecutive unique sector IDs starting at one.", None
    raw_bytes = len(sectors) * next(iter(data_sizes))
    return True, "All PSI sectors form a complete normal rectangular layout.", raw_bytes


def inspect_psi(source: Path | str, token: CancellationToken | None = None) -> PsiInspection:
    """Validate a deliberately narrow, fully checksummed PSI stream without mutation."""
    path = Path(source)
    if path.suffix.casefold() != ".psi":
        raise DiskForgeError("PSI inspection requires a .psi filename extension.")
    source_bytes = _source_size(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    position = 0
    chunk_id, payload, position = _read_chunk(content, position)
    if chunk_id != b"PSI " or len(payload) != 4 or int.from_bytes(payload[:2], "big") != 0:
        raise DiskForgeError("The PSI header chunk, version, or declared format is unsupported.")
    default_format = int.from_bytes(payload[2:4], "big")
    pending: _PendingSector | None = None
    sectors: list[PsiSector] = []
    seen: set[tuple[int, int, int]] = set()
    comment_count = metadata_chunk_count = 0
    ended = False
    while position < source_bytes:
        if token:
            token.raise_if_cancelled()
        chunk_id, payload, position = _read_chunk(content, position)
        if chunk_id not in _ALLOWED:
            raise DiskForgeError("PSI contains an unsupported chunk type in the strict inspection subset.")
        if chunk_id == b"END ":
            if payload:
                raise DiskForgeError("The PSI END chunk must not contain payload bytes.")
            if pending is not None and pending.data is None:
                raise DiskForgeError("A PSI sector is missing its required DATA chunk.")
            ended = True
            break
        if chunk_id == b"TEXT":
            if len(payload) > _MAX_COMMENT_BYTES:
                raise DiskForgeError("A PSI TEXT chunk exceeds the 64-KiB safety limit.")
            comment_count += 1
            continue
        if chunk_id == b"SECT":
            if pending is not None and pending.data is None:
                raise DiskForgeError("A PSI sector is missing its required DATA chunk before the next sector.")
            if len(payload) != 8:
                raise DiskForgeError("A PSI SECT chunk must be exactly eight bytes.")
            cylinder = int.from_bytes(payload[:2], "big")
            head, sector = payload[2], payload[3]
            data_bytes = int.from_bytes(payload[4:6], "big")
            flags, fill = payload[6], payload[7]
            if cylinder > _MAX_CYLINDER or head > 1 or not (1 <= sector <= _MAX_SECTOR_ID):
                raise DiskForgeError("A PSI sector coordinate is outside the strict supported geometry.")
            if not (128 <= data_bytes <= _MAX_SECTOR_BYTES) or flags not in {0, 1}:
                raise DiskForgeError("A PSI sector data size or flag set is unsupported.")
            key = (cylinder, head, sector)
            if key in seen:
                raise DiskForgeError("PSI strict inspection rejects duplicate sector coordinates and alternate sectors.")
            seen.add(key)
            pending = _PendingSector(cylinder, head, sector, data_bytes, bool(flags), bytes((fill,)) * data_bytes if flags else None)
            sectors.append(PsiSector(cylinder, head, sector, data_bytes, bool(flags), pending.data or b""))
            continue
        if chunk_id == b"DATA":
            if pending is None or pending.compressed or pending.data is not None or len(payload) != pending.data_bytes:
                raise DiskForgeError("A PSI DATA chunk is missing, duplicate, compressed, or has an unexpected byte count.")
            pending.data = payload
            sectors[-1] = PsiSector(pending.cylinder, pending.head, pending.sector, pending.data_bytes, False, payload)
            continue
        if chunk_id in {b"IBMF", b"IBMM", b"OFFS", b"TIME"}:
            _check_metadata(chunk_id, payload, pending)
            metadata_chunk_count += 1
            continue
    if not ended or position != source_bytes:
        raise DiskForgeError("The PSI stream must end at an exact, CRC-validated END chunk without trailing bytes.")
    result_sectors = tuple(sectors)
    if any(not item.data for item in result_sectors):
        raise DiskForgeError("A PSI sector is missing its required DATA or compressed-fill data.")
    exportable, reason, raw_bytes = _export_geometry(result_sectors)
    return PsiInspection(path, source_bytes, default_format, comment_count, metadata_chunk_count,
                         result_sectors, sum(item.compressed for item in result_sectors),
                         exportable, reason, raw_bytes)


def export_psi_to_raw(source: Path | str, destination: Path | str,
                      token: CancellationToken | None = None) -> Path:
    """Export only a complete normal rectangular PSI layout to a new RAW file."""
    source_path, target = Path(source), Path(destination)
    inspection = inspect_psi(source_path, token)
    if not inspection.exportable:
        raise DiskForgeError(inspection.export_reason)
    if source_path.resolve() == target.resolve():
        raise DiskForgeError("The PSI RAW export destination must differ from the source file.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The PSI RAW export destination directory does not exist.")
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.diskforge-psi-", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output_handle:
            for sector in sorted(inspection.sectors, key=lambda item: (item.cylinder, item.head, item.sector)):
                if token:
                    token.raise_if_cancelled()
                output_handle.write(sector.data)
        if inspection.raw_bytes is None or temporary.stat().st_size != inspection.raw_bytes:
            raise DiskForgeError("The PSI RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
