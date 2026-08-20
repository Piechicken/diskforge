"""Read-only CPC standard/extended DSK inspection and deliberately strict RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from .storage import CancellationToken, DiskForgeError


_STANDARD_SIGNATURE = b"MV - CPCEMU Disk-File\r\nDisk-Info\r\n"
_EXTENDED_SIGNATURE = b"EXTENDED CPC DSK File\r\nDisk-Info\r\n"
_TRACK_SIGNATURE = b"Track-Info\r\n"
_HEADER_BYTES = 0x100
_MAX_SOURCE_BYTES = 16 * 1024 * 1024 * 1024
_MAX_CYLINDERS = 85
_MAX_SIDES = 2
_MAX_TRACKS = _MAX_CYLINDERS * _MAX_SIDES
_MAX_SECTORS_PER_TRACK = 64
_MAX_SECTOR_SIZE_CODE = 7
_MAX_RAW_BYTES = 2 * 1024 * 1024 * 1024


class CpcDskKind(str, Enum):
    STANDARD = "standard"
    EXTENDED = "extended"


@dataclass(frozen=True)
class CpcDskSector:
    """One sector descriptor and its immutable payload extent in the source container."""

    physical_track: int
    physical_side: int
    c: int
    h: int
    r: int
    n: int
    status1: int
    status2: int
    allocated_bytes: int
    actual_bytes: int
    data_offset: int


@dataclass(frozen=True)
class CpcDskTrack:
    """One declared physical track/side slot in a CPC DSK container."""

    physical_track: int
    physical_side: int
    block_bytes: int
    header_track: int
    header_side: int
    sector_size_code: int
    sector_count: int
    data_rate: int
    recording_mode: int
    sectors: tuple[CpcDskSector, ...]


@dataclass(frozen=True)
class CpcDskInspection:
    """Bounded structural report and proof status for a potential RAW export."""

    source: Path
    kind: CpcDskKind
    creator: str
    tracks: tuple[CpcDskTrack, ...]
    source_bytes: int
    exportable: bool
    export_reason: str
    cylinders: int | None
    sides: int | None
    sectors_per_track: int | None
    bytes_per_sector: int | None
    raw_bytes: int | None


def _read_exact(handle: BinaryIO, size: int, message: str) -> bytes:
    value = handle.read(size)
    if len(value) != size:
        raise DiskForgeError(message)
    return value


def _require_regular_source(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("CPC DSK inspection accepts regular non-symbolic-link source files only.")
    if size > _MAX_SOURCE_BYTES:
        raise DiskForgeError("The CPC DSK source exceeds the 16-GiB safety limit.")
    if size < _HEADER_BYTES:
        raise DiskForgeError("The CPC DSK file is too short to contain its 256-byte disk information block.")
    return size


def _decode_creator(value: bytes) -> str:
    return value.rstrip(b"\0 ").decode("ascii", errors="replace")


def _kind_from_header(header: bytes) -> CpcDskKind:
    if header.startswith(_STANDARD_SIGNATURE):
        return CpcDskKind.STANDARD
    if header.startswith(_EXTENDED_SIGNATURE):
        return CpcDskKind.EXTENDED
    raise DiskForgeError("The source does not begin with a CPC standard or extended DSK signature.")


def _read_track_block(handle: BinaryIO, block_bytes: int, offset: int, source_bytes: int) -> bytes:
    if block_bytes < _HEADER_BYTES or block_bytes % _HEADER_BYTES:
        raise DiskForgeError("The CPC DSK track block size must be a nonzero multiple of 256 bytes.")
    if offset + block_bytes > source_bytes:
        raise DiskForgeError("The CPC DSK file ends inside a declared track block.")
    return _read_exact(handle, block_bytes, "The CPC DSK file ends inside a declared track block.")


def _parse_track(block: bytes, *, kind: CpcDskKind, physical_track: int,
                 physical_side: int, file_offset: int,
                 token: CancellationToken | None) -> CpcDskTrack:
    if block[:len(_TRACK_SIGNATURE)] != _TRACK_SIGNATURE:
        raise DiskForgeError("A CPC DSK track block is missing its Track-Info signature.")
    header_track = block[0x10]
    header_side = block[0x11]
    data_rate = block[0x12]
    recording_mode = block[0x13]
    track_n = block[0x14]
    sector_count = block[0x15]
    if track_n > _MAX_SECTOR_SIZE_CODE:
        raise DiskForgeError("The CPC DSK track uses an unsupported sector-size code.")
    if not sector_count or sector_count > _MAX_SECTORS_PER_TRACK:
        raise DiskForgeError("The CPC DSK track declares an invalid sector count.")
    descriptor_end = 0x18 + sector_count * 8
    if descriptor_end > _HEADER_BYTES:
        raise DiskForgeError("The CPC DSK sector descriptor list exceeds its 256-byte track header.")
    data_cursor = _HEADER_BYTES
    sectors: list[CpcDskSector] = []
    fixed_bytes = 128 << track_n
    for index in range(sector_count):
        if token:
            token.raise_if_cancelled()
        descriptor = 0x18 + index * 8
        c, h, r, n, status1, status2 = block[descriptor:descriptor + 6]
        if n > _MAX_SECTOR_SIZE_CODE:
            raise DiskForgeError("The CPC DSK sector uses an unsupported sector-size code.")
        logical_bytes = 128 << n
        if kind == CpcDskKind.STANDARD:
            if n != track_n:
                raise DiskForgeError("A standard CPC DSK track contains mixed sector-size codes.")
            allocated_bytes = fixed_bytes
            actual_bytes = logical_bytes
        else:
            actual_bytes = int.from_bytes(block[descriptor + 6:descriptor + 8], "little")
            if not actual_bytes:
                raise DiskForgeError("An extended CPC DSK sector declares zero data bytes.")
            allocated_bytes = actual_bytes
        if data_cursor + allocated_bytes > len(block):
            raise DiskForgeError("The CPC DSK sector data exceeds its declared track block.")
        sectors.append(CpcDskSector(
            physical_track, physical_side, c, h, r, n, status1, status2,
            allocated_bytes, actual_bytes, file_offset + data_cursor,
        ))
        data_cursor += allocated_bytes
    return CpcDskTrack(
        physical_track, physical_side, len(block), header_track, header_side, track_n,
        sector_count, data_rate, recording_mode, tuple(sectors),
    )


def _parse(path: Path, token: CancellationToken | None = None) -> tuple[CpcDskKind, str, tuple[CpcDskTrack, ...], int, int]:
    source_bytes = _require_regular_source(path)
    tracks: list[CpcDskTrack] = []
    with path.open("rb") as handle:
        header = _read_exact(handle, _HEADER_BYTES, "The CPC DSK disk information block is truncated.")
        kind = _kind_from_header(header)
        cylinders = header[0x30]
        sides = header[0x31]
        if not cylinders or cylinders > _MAX_CYLINDERS:
            raise DiskForgeError("The CPC DSK declares an invalid cylinder count.")
        if sides not in {1, 2}:
            raise DiskForgeError("The CPC DSK declares an unsupported side count.")
        track_slots = cylinders * sides
        if track_slots > _MAX_TRACKS or 0x34 + track_slots > _HEADER_BYTES:
            raise DiskForgeError("The CPC DSK track table exceeds the disk information block.")
        if kind == CpcDskKind.STANDARD:
            declared_size = int.from_bytes(header[0x32:0x34], "little")
            if declared_size < _HEADER_BYTES or declared_size % _HEADER_BYTES:
                raise DiskForgeError("The standard CPC DSK declares an invalid fixed track size.")
            sizes = [declared_size] * track_slots
        else:
            sizes = [header[0x34 + index] * _HEADER_BYTES for index in range(track_slots)]
            if any(size == 0 for size in sizes):
                raise DiskForgeError("The CPC extended DSK contains an unformatted track slot.")
        expected_bytes = _HEADER_BYTES + sum(sizes)
        if expected_bytes != source_bytes:
            raise DiskForgeError("The CPC DSK declared track blocks do not exactly match the source file length.")
        offset = _HEADER_BYTES
        for index, block_bytes in enumerate(sizes):
            if token:
                token.raise_if_cancelled()
            physical_track, physical_side = divmod(index, sides)
            block = _read_track_block(handle, block_bytes, offset, source_bytes)
            tracks.append(_parse_track(
                block, kind=kind, physical_track=physical_track, physical_side=physical_side,
                file_offset=offset, token=token,
            ))
            offset += block_bytes
    return kind, _decode_creator(header[0x22:0x30]), tuple(tracks), cylinders, sides


def _raw_proof(tracks: tuple[CpcDskTrack, ...], cylinders: int, sides: int) -> tuple[bool, str, int | None, int | None, int | None]:
    if not tracks:
        return False, "The CPC DSK contains no formatted track blocks.", None, None, None
    expected_track_count = cylinders * sides
    if len(tracks) != expected_track_count:
        return False, "The CPC DSK does not contain every declared physical track/side block.", None, None, None
    first = tracks[0]
    sectors_per_track = first.sector_count
    if not sectors_per_track:
        return False, "The CPC DSK first track declares no sectors.", None, None, None
    bytes_per_sector = 128 << first.sector_size_code
    expected_ids = tuple(range(1, sectors_per_track + 1))
    for index, track in enumerate(tracks):
        physical_track, physical_side = divmod(index, sides)
        if (track.physical_track, track.physical_side) != (physical_track, physical_side):
            return False, "The CPC DSK track positions are not in physical cylinder/side order.", None, None, None
        if (track.header_track, track.header_side) != (physical_track, physical_side):
            return False, "A CPC DSK Track-Info coordinate differs from its physical block position.", None, None, None
        if track.sector_count != sectors_per_track:
            return False, "The CPC DSK tracks do not have a uniform sector count.", None, None, None
        if track.sector_size_code != first.sector_size_code:
            return False, "The CPC DSK tracks do not have a fixed sector-size code.", None, None, None
        if tuple(sector.r for sector in track.sectors) != expected_ids:
            return False, "The CPC DSK sector identifiers are not consecutive 1..N.", None, None, None
        for sector in track.sectors:
            if (sector.c, sector.h) != (physical_track, physical_side):
                return False, "A CPC DSK sector C/H differs from its physical track/side position.", None, None, None
            if sector.status1 or sector.status2:
                return False, "The CPC DSK contains a sector with a nonzero controller status.", None, None, None
            if sector.n != first.sector_size_code:
                return False, "The CPC DSK contains mixed sector-size codes.", None, None, None
            if sector.actual_bytes != bytes_per_sector or sector.allocated_bytes != bytes_per_sector:
                return False, "The CPC DSK contains short, long, or multi-copy sector data.", None, None, None
    raw_bytes = cylinders * sides * sectors_per_track * bytes_per_sector
    if raw_bytes <= 0 or raw_bytes > _MAX_RAW_BYTES:
        return False, "The proven CPC DSK RAW output size is outside the 1-byte to 2-GiB safety range.", None, None, None
    return True, "The CPC DSK has a complete normal-data rectangular CHS layout.", sectors_per_track, bytes_per_sector, raw_bytes


def inspect_cpc_dsk(source: Path | str, token: CancellationToken | None = None) -> CpcDskInspection:
    """Inspect a signed CPC standard/extended DSK container without mutating it."""
    path = Path(source)
    kind, creator, tracks, cylinders, sides = _parse(path, token)
    exportable, reason, sectors_per_track, bytes_per_sector, raw_bytes = _raw_proof(tracks, cylinders, sides)
    return CpcDskInspection(
        path, kind, creator, tracks, path.stat().st_size, exportable, reason,
        cylinders if exportable else None, sides if exportable else None,
        sectors_per_track, bytes_per_sector, raw_bytes,
    )


def _copy_sector(source: BinaryIO, output: BinaryIO, sector: CpcDskSector,
                 token: CancellationToken | None) -> None:
    source.seek(sector.data_offset)
    remaining = sector.actual_bytes
    while remaining:
        if token:
            token.raise_if_cancelled()
        block = _read_exact(source, min(1024 * 1024, remaining), "The CPC DSK sector payload is truncated.")
        output.write(block)
        remaining -= len(block)


def export_cpc_dsk_to_raw(source: Path | str, destination: Path | str,
                           token: CancellationToken | None = None) -> Path:
    """Write a new RAW file only after a CPC DSK layout has been strictly proven."""
    source_path = Path(source)
    destination_path = Path(destination)
    inspection = inspect_cpc_dsk(source_path, token)
    if not inspection.exportable:
        raise DiskForgeError(f"The CPC DSK cannot be safely exported to RAW: {inspection.export_reason}")
    if source_path.resolve() == destination_path.resolve():
        raise DiskForgeError("The CPC DSK RAW export destination must differ from the source file.")
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(destination_path)
    if not destination_path.parent.is_dir():
        raise DiskForgeError("The CPC DSK RAW export destination directory does not exist.")
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.diskforge-cpc-dsk-", suffix=".tmp", dir=destination_path.parent,
        )
        temporary = Path(temporary_name)
        with source_path.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            for track in inspection.tracks:
                if token:
                    token.raise_if_cancelled()
                for sector in track.sectors:
                    _copy_sector(input_handle, output_handle, sector, token)
        if temporary.stat().st_size != inspection.raw_bytes:
            raise DiskForgeError("The CPC DSK RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, destination_path)
        temporary.unlink()
        temporary = None
        return destination_path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
