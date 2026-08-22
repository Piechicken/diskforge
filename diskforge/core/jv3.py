"""Strict read-only inspection and narrowly proven RAW export for JV3 images."""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError

_HEADER_SLOTS = 2901
_HEADER_BYTES = _HEADER_SLOTS * 3 + 1
_MAX_SOURCE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Jv3Sector:
    block: int
    slot: int
    cylinder: int
    head: int
    sector: int
    flags: int
    data: bytes


@dataclass(frozen=True)
class Jv3Inspection:
    source: Path
    source_bytes: int
    write_protected: bool
    header_blocks: int
    free_slots: int
    exportable: bool
    export_reason: str
    cylinders: int
    heads: int
    sectors_per_track: int
    raw_bytes: int
    sectors: tuple[Jv3Sector, ...]


def _size_for_flags(flags: int) -> int:
    # JV3 encodes nominal sector length in the two least-significant bits.
    return (256, 128, 512, 1024)[flags & 0x03]


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("JV3 inspection accepts regular non-symbolic-link source files only.")
    if not (_HEADER_BYTES <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The JV3 source size is outside the fixed-header safety range.")
    return size


def _geometry(sectors: list[Jv3Sector]) -> tuple[bool, str, int, int, int, int]:
    if not sectors:
        return False, "JV3 contains no in-use sectors.", 0, 0, 0, 0
    for sector in sectors:
        if sector.flags & 0x08:
            return False, "JV3 contains a CRC error sector.", 0, 0, 0, 0
        if sector.flags & 0x04:
            return False, "JV3 contains a non-IBM sector size.", 0, 0, 0, 0
        if sector.flags & 0xF0:
            return False, "JV3 contains unsupported sector flags.", 0, 0, 0, 0
        if len(sector.data) != 256:
            return False, "JV3 does not prove a fixed 256-byte rectangular layout.", 0, 0, 0, 0
    keys = {(entry.cylinder, entry.head, entry.sector) for entry in sectors}
    if len(keys) != len(sectors):
        return False, "JV3 does not prove a rectangular layout because sector identifiers repeat.", 0, 0, 0, 0
    cylinders = sorted({entry.cylinder for entry in sectors})
    heads = sorted({entry.head for entry in sectors})
    sector_ids = sorted({entry.sector for entry in sectors})
    if cylinders != list(range(len(cylinders))) or heads != list(range(len(heads))) or sector_ids != list(range(len(sector_ids))):
        return False, "JV3 does not prove a rectangular layout with consecutive cylinder, head, and sector identifiers.", 0, 0, 0, 0
    expected = {(cylinder, head, sector) for cylinder in cylinders for head in heads for sector in sector_ids}
    if keys != expected:
        return False, "JV3 does not prove a complete rectangular layout.", 0, 0, 0, 0
    return True, "", len(cylinders), len(heads), len(sector_ids), len(sectors) * 256


def inspect_jv3(source: Path | str, token: CancellationToken | None = None) -> Jv3Inspection:
    """Parse fixed JV3 header blocks without mutating the source."""
    path = Path(source)
    if path.suffix.casefold() != ".jv3":
        raise DiskForgeError("JV3 inspection requires a .jv3 filename extension.")
    source_bytes = _source_size(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    offset = 0
    block = 0
    sectors: list[Jv3Sector] = []
    free_slots = 0
    write_protected = False
    while offset < source_bytes:
        if token:
            token.raise_if_cancelled()
        if source_bytes - offset < _HEADER_BYTES:
            raise DiskForgeError("JV3 source ends inside a fixed header block or data area.")
        header = content[offset:offset + _HEADER_BYTES]
        marker = header[-1]
        if marker not in {0x00, 0xFF}:
            raise DiskForgeError("The JV3 write-protect marker is invalid.")
        write_protected = write_protected or marker == 0x00
        data_start = offset + _HEADER_BYTES
        data_cursor = data_start
        nominal_span = 0
        for slot in range(_HEADER_SLOTS):
            entry = header[slot * 3:slot * 3 + 3]
            cylinder, sector, flags = entry
            if cylinder == 0xFF or sector == 0xFF:
                if entry != b"\xff\xff\xff":
                    raise DiskForgeError("A free-sector free JV3 header slot must contain three 0xFF bytes.")
                free_slots += 1
                nominal_span += 256
                continue
            if flags & 0xE0:
                raise DiskForgeError("An in-use JV3 sector has unsupported reserved flag bits.")
            length = _size_for_flags(flags)
            nominal_span += length
            if data_cursor + length > source_bytes:
                raise DiskForgeError("JV3 sector data ends inside a declared payload.")
            sectors.append(Jv3Sector(block, slot, cylinder, 1 if flags & 0x10 else 0, sector, flags, content[data_cursor:data_cursor + length]))
            data_cursor += length
        block += 1
        possible_next = data_start + nominal_span
        if possible_next + _HEADER_BYTES <= source_bytes:
            offset = possible_next
            continue
        if data_cursor != source_bytes:
            raise DiskForgeError("JV3 source ends inside nominal free-sector data or has trailing bytes.")
        offset = source_bytes
    exportable, reason, cylinders, heads, sectors_per_track, raw_bytes = _geometry(sectors)
    return Jv3Inspection(path, source_bytes, write_protected, block, free_slots, exportable, reason,
                         cylinders, heads, sectors_per_track, raw_bytes, tuple(sectors))


def export_jv3_to_raw(source: Path | str, destination: Path | str,
                      token: CancellationToken | None = None) -> Path:
    """Export only a fully proven normal rectangular JV3 layout to a new RAW file."""
    inspection = inspect_jv3(source, token)
    output = Path(destination)
    if output.resolve(strict=False) == inspection.source.resolve(strict=False):
        raise DiskForgeError("JV3 RAW destination must differ from the source.")
    if output.exists():
        raise FileExistsError(output)
    if not inspection.exportable:
        raise DiskForgeError(inspection.export_reason)
    if token:
        token.raise_if_cancelled()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as handle:
            for sector in sorted(inspection.sectors, key=lambda item: (item.cylinder, item.head, item.sector)):
                if token:
                    token.raise_if_cancelled()
                handle.write(sector.data)
    except Exception:
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return output
