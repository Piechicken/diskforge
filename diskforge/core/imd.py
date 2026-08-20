"""Read-only ImageDisk (IMD) inspection and conservative RAW export.

IMD can faithfully represent irregular media. This module therefore separates
inspection from export: all parsed records can be reported, while a new RAW
file is produced only for layouts whose CHS ordering and sector payloads are
fully determined without guesswork.
"""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .storage import CancellationToken, DiskForgeError


_MAX_HEADER_BYTES = 64 * 1024
_MAX_TRACKS = 4096
_MAX_SECTORS = 262_144
_MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
_NORMAL_TYPES = {1, 2}
_KNOWN_TYPES = set(range(9))


@dataclass(frozen=True)
class ImdSector:
    """Metadata and immutable source location for one IMD sector payload."""

    number: int
    size_bytes: int
    data_type: int
    data_offset: int | None

    @property
    def is_compressed(self) -> bool:
        return self.data_type in {2, 4, 6, 8}

    @property
    def is_exportable(self) -> bool:
        return self.data_type in _NORMAL_TYPES


@dataclass(frozen=True)
class ImdTrack:
    """One IMD track record, without loading its payload bytes into memory."""

    mode: int
    cylinder: int
    head: int
    sectors: tuple[ImdSector, ...]
    has_optional_maps: bool


@dataclass(frozen=True)
class ImdInspection:
    """A bounded IMD structural report and optional strict RAW-export proof."""

    source: Path
    description: str
    tracks: tuple[ImdTrack, ...]
    source_bytes: int
    exportable: bool
    export_reason: str
    cylinders: int | None
    heads: int | None
    sectors_per_track: int | None
    bytes_per_sector: int | None
    raw_bytes: int | None


def _read_exact(handle: BinaryIO, size: int, message: str) -> bytes:
    value = handle.read(size)
    if len(value) != size:
        raise DiskForgeError(message)
    return value


def _require_regular_source(path: Path) -> None:
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        raise
    if not stat.S_ISREG(mode):
        raise DiskForgeError("IMD inspection accepts regular source files only.")


def _read_description(handle: BinaryIO) -> str:
    prefix = _read_exact(handle, 4, "The IMD file is too short to contain its signature.")
    if prefix != b"IMD ":
        raise DiskForgeError("The source does not begin with an IMD signature.")
    description = bytearray(prefix)
    while len(description) < _MAX_HEADER_BYTES:
        value = _read_exact(handle, 1, "The IMD text header is missing its 0x1A terminator.")
        if value == b"\x1a":
            return description.decode("ascii", errors="replace")
        description.extend(value)
    raise DiskForgeError("The IMD text header exceeds the 64 KiB safety limit.")


def _parse_tracks(path: Path, token: CancellationToken | None = None) -> tuple[str, tuple[ImdTrack, ...]]:
    _require_regular_source(path)
    tracks: list[ImdTrack] = []
    coordinates: set[tuple[int, int]] = set()
    total_sectors = 0
    with path.open("rb") as handle:
        description = _read_description(handle)
        while True:
            if token:
                token.raise_if_cancelled()
            start = handle.tell()
            first = handle.read(1)
            if not first:
                break
            handle.seek(start)
            if len(tracks) >= _MAX_TRACKS:
                raise DiskForgeError("The IMD file exceeds the 4096-track safety limit.")
            mode, cylinder, raw_head, sector_count, size_code = _read_exact(
                handle, 5, "The IMD file ends inside a track header."
            )
            if mode > 5:
                raise DiskForgeError("The IMD track uses an unsupported recording mode.")
            if not sector_count:
                raise DiskForgeError("The IMD track declares zero sectors.")
            has_optional_maps = bool(raw_head & 0xC0)
            if size_code > 6:
                raise DiskForgeError("The IMD track uses an unsupported or variable sector-size code.")
            head = raw_head & 0x3F
            coordinate = (cylinder, head)
            if coordinate in coordinates:
                raise DiskForgeError("The IMD file contains a duplicate cylinder/head track record.")
            coordinates.add(coordinate)
            total_sectors += sector_count
            if total_sectors > _MAX_SECTORS:
                raise DiskForgeError("The IMD file exceeds the 262144-sector safety limit.")
            size_bytes = 128 << size_code
            numbers = _read_exact(handle, sector_count, "The IMD sector-number map is truncated.")
            if raw_head & 0x80:
                _read_exact(handle, sector_count, "The IMD cylinder map is truncated.")
            if raw_head & 0x40:
                _read_exact(handle, sector_count, "The IMD head map is truncated.")
            sectors: list[ImdSector] = []
            for number in numbers:
                if token:
                    token.raise_if_cancelled()
                data_type = _read_exact(handle, 1, "The IMD file ends before a sector data type.")[0]
                if data_type not in _KNOWN_TYPES:
                    raise DiskForgeError("The IMD file contains an unknown sector data type.")
                if data_type == 0:
                    sectors.append(ImdSector(number, size_bytes, data_type, None))
                    continue
                data_offset = handle.tell()
                encoded_bytes = 1 if data_type in {2, 4, 6, 8} else size_bytes
                _read_exact(handle, encoded_bytes, "The IMD sector payload is truncated.")
                sectors.append(ImdSector(number, size_bytes, data_type, data_offset))
            tracks.append(ImdTrack(mode, cylinder, head, tuple(sectors), has_optional_maps))
    return description, tuple(tracks)


def _raw_proof(tracks: tuple[ImdTrack, ...]) -> tuple[bool, str, int | None, int | None, int | None, int | None, int | None]:
    if not tracks:
        return False, "The IMD file contains no track records.", None, None, None, None, None
    first = tracks[0]
    sectors_per_track = len(first.sectors)
    bytes_per_sector = first.sectors[0].size_bytes
    expected_numbers = tuple(range(1, sectors_per_track + 1))
    if tuple(item.number for item in first.sectors) != expected_numbers:
        return False, "The IMD sector numbers are not consecutive 1..N.", None, None, None, None, None
    for track in tracks:
        if track.has_optional_maps:
            return False, "The IMD track uses optional cylinder/head maps and cannot be safely flattened.", None, None, None, None, None
        if len(track.sectors) != sectors_per_track:
            return False, "The IMD tracks do not have a uniform sector count.", None, None, None, None, None
        if tuple(item.number for item in track.sectors) != expected_numbers:
            return False, "The IMD sector numbers are not consecutive 1..N.", None, None, None, None, None
        if any(item.size_bytes != bytes_per_sector for item in track.sectors):
            return False, "The IMD tracks do not have a fixed sector size.", None, None, None, None, None
        if any(not item.is_exportable for item in track.sectors):
            return False, "The IMD contains missing, deleted, or bad sector data and cannot be flattened safely.", None, None, None, None, None
    cylinder_values = {track.cylinder for track in tracks}
    head_values = {track.head for track in tracks}
    cylinders = max(cylinder_values) + 1
    heads = max(head_values) + 1
    if cylinder_values != set(range(cylinders)) or head_values != set(range(heads)):
        return False, "The IMD cylinder/head coordinates do not begin at zero and cannot form a RAW layout.", None, None, None, None, None
    coordinates = {(track.cylinder, track.head) for track in tracks}
    expected_coordinates = {(cylinder, head) for cylinder in range(cylinders) for head in range(heads)}
    if coordinates != expected_coordinates:
        return False, "The IMD tracks do not form a complete rectangular CHS layout.", None, None, None, None, None
    raw_bytes = cylinders * heads * sectors_per_track * bytes_per_sector
    if raw_bytes <= 0 or raw_bytes > _MAX_OUTPUT_BYTES:
        return False, "The proven IMD RAW output size is outside the 1-byte to 2-GiB safety range.", None, None, None, None, None
    return True, "The IMD has a complete normal-data rectangular CHS layout.", cylinders, heads, sectors_per_track, bytes_per_sector, raw_bytes


def inspect_imd(source: Path | str, token: CancellationToken | None = None) -> ImdInspection:
    """Parse an IMD file without mutation and report whether strict RAW export is possible."""
    path = Path(source)
    description, tracks = _parse_tracks(path, token)
    proof = _raw_proof(tracks)
    return ImdInspection(path, description, tracks, path.stat().st_size, *proof)


def _copy_sector(source: BinaryIO, output: BinaryIO, sector: ImdSector,
                 token: CancellationToken | None) -> None:
    if token:
        token.raise_if_cancelled()
    if sector.data_offset is None:
        raise DiskForgeError("The selected IMD sector has no data payload.")
    source.seek(sector.data_offset)
    if sector.is_compressed:
        output.write(_read_exact(source, 1, "The compressed IMD sector payload is truncated.") * sector.size_bytes)
        return
    remaining = sector.size_bytes
    while remaining:
        if token:
            token.raise_if_cancelled()
        block = _read_exact(source, min(1024 * 1024, remaining), "The IMD sector payload is truncated.")
        output.write(block)
        remaining -= len(block)


def export_imd_to_raw(source: Path | str, destination: Path | str,
                      token: CancellationToken | None = None) -> Path:
    """Export a strictly proven rectangular IMD layout to a new RAW file without overwrite."""
    source_path = Path(source)
    destination_path = Path(destination)
    inspection = inspect_imd(source_path, token)
    if not inspection.exportable:
        raise DiskForgeError(f"The IMD cannot be safely exported to RAW: {inspection.export_reason}")
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(destination_path)
    if source_path.resolve() == destination_path.resolve():
        raise DiskForgeError("The IMD RAW export destination must differ from the source file.")
    if not destination_path.parent.is_dir():
        raise DiskForgeError("The IMD RAW export destination directory does not exist.")
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.diskforge-imd-", suffix=".tmp", dir=destination_path.parent,
        )
        temporary = Path(temporary_name)
        by_coordinate = {(track.cylinder, track.head): track for track in inspection.tracks}
        with source_path.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            for cylinder in range(inspection.cylinders or 0):
                for head in range(inspection.heads or 0):
                    track = by_coordinate[(cylinder, head)]
                    for sector in track.sectors:
                        _copy_sector(input_handle, output_handle, sector, token)
        if temporary.stat().st_size != inspection.raw_bytes:
            raise DiskForgeError("The IMD RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, destination_path)
        temporary.unlink()
        temporary = None
        return destination_path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
