"""Bounded read-only inspection and strict RAW export for ordinary TeleDisk TD0.

TD0 can represent variable geometry, missing data, deleted data, and error sectors.
This module therefore reports ordinary uncompressed records but creates a RAW
file only after proving that flattening does not invent ordering or contents.
Advanced-compressed ``td`` files are recognized and explicitly rejected.
"""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .storage import CancellationToken, DiskForgeError


_MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_COMMENT_BYTES = 64 * 1024
_MAX_TRACKS = 4096
_MAX_SECTORS = 262_144
_MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
_MAX_ENCODED_BYTES = 64 * 1024
_CRC_POLYNOMIAL = 0xA097
_NO_DATA_FLAGS = 0x30
_EXPORT_BLOCKING_FLAGS = 0x77


@dataclass(frozen=True)
class Td0Sector:
    """Metadata and immutable source location for one TD0 sector record."""

    cylinder: int
    head: int
    number: int
    size_code: int
    flags: int
    method: int | None
    data_offset: int | None
    encoded_bytes: int

    @property
    def size_bytes(self) -> int:
        return 128 << self.size_code

    @property
    def has_data(self) -> bool:
        return self.data_offset is not None

    @property
    def is_exportable(self) -> bool:
        return self.has_data and self.flags == 0 and self.method in {0, 1, 2}


@dataclass(frozen=True)
class Td0Track:
    """One physical TD0 track and its immutable sector metadata."""

    cylinder: int
    head: int
    single_density: bool
    sectors: tuple[Td0Sector, ...]


@dataclass(frozen=True)
class Td0Inspection:
    """A bounded TD0 report and optional proof for deterministic RAW export."""

    source: Path
    version: str
    data_rate_kbps: int | None
    drive_type: int
    sides: int
    comment: str | None
    tracks: tuple[Td0Track, ...]
    source_bytes: int
    exportable: bool
    export_reason: str
    cylinders: int | None
    heads: int | None
    sectors_per_track: int | None
    bytes_per_sector: int | None
    raw_bytes: int | None


@dataclass(frozen=True)
class _Td0Header:
    version: str
    data_rate_kbps: int | None
    drive_type: int
    stepping: int
    sides: int
    has_comment: bool


def _read_exact(handle: BinaryIO, size: int, message: str) -> bytes:
    value = handle.read(size)
    if len(value) != size:
        raise DiskForgeError(message)
    return value


def _require_regular_source(path: Path) -> None:
    try:
        source_stat = path.lstat()
    except FileNotFoundError:
        raise
    if path.is_symlink() or not stat.S_ISREG(source_stat.st_mode):
        raise DiskForgeError("TD0 inspection accepts regular non-symlink source files only.")
    if source_stat.st_size <= 0 or source_stat.st_size > _MAX_SOURCE_BYTES:
        raise DiskForgeError("The TD0 source size is outside the 1-byte to 2-GiB safety range.")


def _crc16(data: bytes, initial: int = 0) -> int:
    """Compute the TD0 A097 CRC with the documented non-reflected bit order."""
    crc = initial & 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (_CRC_POLYNOMIAL if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def _parse_header(handle: BinaryIO) -> _Td0Header:
    raw = _read_exact(handle, 12, "The TD0 file is too short to contain its 12-byte header.")
    signature = raw[:2]
    if signature == b"td":
        raise DiskForgeError("TD0 advanced compression is recognized but not supported for safe inspection.")
    if signature != b"TD":
        raise DiskForgeError("The source does not begin with an ordinary TD0 signature.")
    if raw[2] != 0:
        raise DiskForgeError("TD0 multi-volume sequences are not supported.")
    expected_crc = int.from_bytes(raw[10:12], "little")
    if _crc16(raw[:10]) != expected_crc:
        raise DiskForgeError("The TD0 header CRC does not match.")
    rate_code = raw[5] & 0x03
    rate = {0: 250, 1: 300, 2: 500}.get(rate_code)
    return _Td0Header(
        version=f"{raw[4] >> 4}.{raw[4] & 0x0F}", data_rate_kbps=rate,
        drive_type=raw[6], stepping=raw[7] & 0x03, sides=1 if raw[9] == 1 else 2,
        has_comment=bool(raw[7] & 0x80),
    )


def _parse_comment(handle: BinaryIO, token: CancellationToken | None) -> str:
    raw = _read_exact(handle, 10, "The TD0 comment header is truncated.")
    expected_crc = int.from_bytes(raw[:2], "little")
    length = int.from_bytes(raw[2:4], "little")
    if length > _MAX_COMMENT_BYTES:
        raise DiskForgeError("The TD0 comment exceeds the 64 KiB safety limit.")
    if token:
        token.raise_if_cancelled()
    payload = _read_exact(handle, length, "The TD0 comment data is truncated.")
    if _crc16(raw[2:] + payload) != expected_crc:
        raise DiskForgeError("The TD0 comment CRC does not match.")
    return payload.replace(b"\x00", b"\n").decode("ascii", errors="replace").rstrip("\n")


def _decode_sector_data(method: int, encoded: bytes, size_bytes: int) -> bytes:
    if method == 0:
        if len(encoded) != size_bytes:
            raise DiskForgeError("The TD0 raw sector data length does not match its size code.")
        return encoded
    output = bytearray()
    position = 0
    if method == 1:
        while position < len(encoded):
            if position + 4 > len(encoded):
                raise DiskForgeError("The TD0 repeated-pattern sector data is truncated.")
            count = int.from_bytes(encoded[position:position + 2], "little")
            pattern = encoded[position + 2:position + 4]
            position += 4
            if count == 0 or len(output) + count * 2 > size_bytes:
                raise DiskForgeError("The TD0 repeated-pattern sector data exceeds its declared size.")
            output.extend(pattern * count)
    elif method == 2:
        while position < len(encoded):
            if position + 2 > len(encoded):
                raise DiskForgeError("The TD0 RLE sector data is truncated.")
            marker, count = encoded[position], encoded[position + 1]
            position += 2
            if marker == 0:
                if count == 0 or position + count > len(encoded) or len(output) + count > size_bytes:
                    raise DiskForgeError("The TD0 RLE literal block exceeds its declared size.")
                output.extend(encoded[position:position + count])
                position += count
            else:
                fragment_length = marker * 2
                if count == 0 or position + fragment_length > len(encoded) or len(output) + fragment_length * count > size_bytes:
                    raise DiskForgeError("The TD0 RLE repeat block exceeds its declared size.")
                output.extend(encoded[position:position + fragment_length] * count)
                position += fragment_length
    else:
        raise DiskForgeError("The TD0 sector uses an unsupported data encoding method.")
    if position != len(encoded) or len(output) != size_bytes:
        raise DiskForgeError("The TD0 decoded sector data does not exactly match its declared size.")
    return bytes(output)


def _parse_tracks(path: Path, token: CancellationToken | None = None) -> tuple[_Td0Header, str | None, tuple[Td0Track, ...]]:
    _require_regular_source(path)
    tracks: list[Td0Track] = []
    coordinates: set[tuple[int, int]] = set()
    total_sectors = 0
    with path.open("rb") as handle:
        header = _parse_header(handle)
        comment = _parse_comment(handle, token) if header.has_comment else None
        while True:
            if token:
                token.raise_if_cancelled()
            first = _read_exact(handle, 1, "The TD0 track list is missing its 0xFF terminator.")[0]
            if first == 0xFF:
                if handle.read(1):
                    raise DiskForgeError("The TD0 file contains trailing bytes after the track terminator.")
                break
            if len(tracks) >= _MAX_TRACKS:
                raise DiskForgeError("The TD0 file exceeds the 4096-track safety limit.")
            track_tail = _read_exact(handle, 3, "The TD0 file ends inside a track header.")
            track_raw = bytes((first,)) + track_tail
            sector_count, cylinder, raw_head, stored_crc = track_raw
            if sector_count == 0:
                raise DiskForgeError("The TD0 track declares zero sectors.")
            if _crc16(track_raw[:3]) & 0xFF != stored_crc:
                raise DiskForgeError("A TD0 track header CRC does not match.")
            head = raw_head & 0x01
            coordinate = (cylinder, head)
            if coordinate in coordinates:
                raise DiskForgeError("The TD0 file contains a duplicate physical cylinder/head track record.")
            coordinates.add(coordinate)
            total_sectors += sector_count
            if total_sectors > _MAX_SECTORS:
                raise DiskForgeError("The TD0 file exceeds the 262144-sector safety limit.")
            sectors: list[Td0Sector] = []
            for _ in range(sector_count):
                if token:
                    token.raise_if_cancelled()
                sector_raw = _read_exact(handle, 6, "The TD0 file ends inside a sector header.")
                logical_cylinder, logical_head, number, size_code, flags, stored_sector_crc = sector_raw
                if size_code > 6:
                    raise DiskForgeError("The TD0 sector uses an unsupported size code.")
                size_bytes = 128 << size_code
                method: int | None = None
                data_offset: int | None = None
                encoded_bytes = 0
                crc_data = sector_raw[:5]
                if not flags & _NO_DATA_FLAGS:
                    data_header = _read_exact(handle, 3, "The TD0 sector data header is truncated.")
                    block_size = int.from_bytes(data_header[:2], "little")
                    method = data_header[2]
                    if block_size == 0 or block_size - 1 > _MAX_ENCODED_BYTES:
                        raise DiskForgeError("The TD0 sector data block length is outside the safety limit.")
                    encoded_bytes = block_size - 1
                    data_offset = handle.tell()
                    encoded = _read_exact(handle, encoded_bytes, "The TD0 sector data block is truncated.")
                    _decode_sector_data(method, encoded, size_bytes)
                    crc_data += data_header + encoded
                if _crc16(crc_data) & 0xFF != stored_sector_crc:
                    raise DiskForgeError("A TD0 sector CRC does not match.")
                sectors.append(Td0Sector(
                    logical_cylinder, logical_head, number, size_code, flags, method, data_offset, encoded_bytes,
                ))
            tracks.append(Td0Track(cylinder, head, bool(raw_head & 0x80), tuple(sectors)))
    return header, comment, tuple(tracks)


def _raw_proof(tracks: tuple[Td0Track, ...]) -> tuple[bool, str, int | None, int | None, int | None, int | None, int | None]:
    if not tracks:
        return False, "The TD0 file contains no track records.", None, None, None, None, None
    first = tracks[0]
    sectors_per_track = len(first.sectors)
    bytes_per_sector = first.sectors[0].size_bytes
    expected_numbers = tuple(range(1, sectors_per_track + 1))
    for track in tracks:
        if track.single_density:
            return False, "The TD0 contains a single-density track and cannot be safely flattened.", None, None, None, None, None
        if len(track.sectors) != sectors_per_track:
            return False, "The TD0 tracks do not have a uniform sector count.", None, None, None, None, None
        if tuple(sector.number for sector in track.sectors) != expected_numbers:
            return False, "The TD0 sector numbers are not consecutive 1..N.", None, None, None, None, None
        for sector in track.sectors:
            if sector.size_bytes != bytes_per_sector:
                return False, "The TD0 tracks do not have a fixed sector size.", None, None, None, None, None
            if sector.cylinder != track.cylinder or sector.head != track.head:
                return False, "The TD0 logical sector coordinates do not match physical track coordinates.", None, None, None, None, None
            if not sector.is_exportable:
                return False, "The TD0 contains flagged, missing, or unsupported sector data and cannot be flattened safely.", None, None, None, None, None
    cylinders_seen = {track.cylinder for track in tracks}
    heads_seen = {track.head for track in tracks}
    cylinders, heads = max(cylinders_seen) + 1, max(heads_seen) + 1
    if cylinders_seen != set(range(cylinders)) or heads_seen != set(range(heads)):
        return False, "The TD0 cylinder/head coordinates do not begin at zero and cannot form a RAW layout.", None, None, None, None, None
    if {(track.cylinder, track.head) for track in tracks} != {(cylinder, head) for cylinder in range(cylinders) for head in range(heads)}:
        return False, "The TD0 tracks do not form a complete rectangular CHS layout.", None, None, None, None, None
    raw_bytes = cylinders * heads * sectors_per_track * bytes_per_sector
    if raw_bytes <= 0 or raw_bytes > _MAX_OUTPUT_BYTES:
        return False, "The proven TD0 RAW output size is outside the 1-byte to 2-GiB safety range.", None, None, None, None, None
    return True, "The TD0 has a complete unflagged rectangular CHS layout.", cylinders, heads, sectors_per_track, bytes_per_sector, raw_bytes


def inspect_td0(source: Path | str, token: CancellationToken | None = None) -> Td0Inspection:
    """Inspect ordinary TD0 records without changing the source file."""
    path = Path(source)
    header, comment, tracks = _parse_tracks(path, token)
    proof = _raw_proof(tracks)
    return Td0Inspection(
        path, header.version, header.data_rate_kbps, header.drive_type, header.sides, comment,
        tracks, path.stat().st_size, *proof,
    )


def _copy_sector(source: BinaryIO, output: BinaryIO, sector: Td0Sector,
                 token: CancellationToken | None) -> None:
    if token:
        token.raise_if_cancelled()
    if sector.data_offset is None or sector.method is None:
        raise DiskForgeError("The selected TD0 sector has no exportable data payload.")
    source.seek(sector.data_offset)
    encoded = _read_exact(source, sector.encoded_bytes, "The TD0 sector data block is truncated during export.")
    payload = _decode_sector_data(sector.method, encoded, sector.size_bytes)
    output.write(payload)


def export_td0_to_raw(source: Path | str, destination: Path | str,
                      token: CancellationToken | None = None) -> Path:
    """Export a strictly proven ordinary TD0 layout to a new RAW file without overwrite."""
    source_path, destination_path = Path(source), Path(destination)
    inspection = inspect_td0(source_path, token)
    if not inspection.exportable:
        raise DiskForgeError(f"The TD0 cannot be safely exported to RAW: {inspection.export_reason}")
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(destination_path)
    if source_path.resolve() == destination_path.resolve():
        raise DiskForgeError("The TD0 RAW export destination must differ from the source file.")
    if not destination_path.parent.is_dir():
        raise DiskForgeError("The TD0 RAW export destination directory does not exist.")
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.diskforge-td0-", suffix=".tmp", dir=destination_path.parent,
        )
        temporary = Path(temporary_name)
        by_coordinate = {(track.cylinder, track.head): track for track in inspection.tracks}
        with source_path.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            for cylinder in range(inspection.cylinders or 0):
                for head in range(inspection.heads or 0):
                    for sector in by_coordinate[(cylinder, head)].sectors:
                        _copy_sector(input_handle, output_handle, sector, token)
        if temporary.stat().st_size != inspection.raw_bytes:
            raise DiskForgeError("The TD0 RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, destination_path)
        temporary.unlink()
        temporary = None
        return destination_path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
