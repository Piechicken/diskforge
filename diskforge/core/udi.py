"""Strict read-only validation for the original UDI v1.0 bitstream container.

This module deliberately validates only the documented uppercase ``UDI!`` v1.0
MFM-track representation.  It does not turn track bytes into sectors or RAW
media, because address marks, MFM decoding, CRC state, and protection details
remain encoded in the bitstream.
"""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_EXTENDED_HEADER_BYTES = 1024 * 1024


@dataclass(frozen=True)
class UdiTrack:
    """One v1.0 MFM track in on-disk alternate cylinder/side order."""

    index: int
    cylinder: int
    head: int
    data_bytes: int
    clock_mark_count: int


@dataclass(frozen=True)
class UdiInspection:
    """Validated facts from a v1.0 UDI container; no sector interpretation."""

    source: Path
    source_bytes: int
    cylinders: int
    sides: int
    extended_header_bytes: int
    tracks: tuple[UdiTrack, ...]
    total_track_bytes: int
    clock_mark_count: int
    crc32: int


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("UDI inspection accepts regular non-symbolic-link source files only.")
    if not (23 <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The UDI source size is outside the 23-byte to 32-MiB safety range.")
    return size


def _udi_crc32(data: bytes) -> int:
    """Implement the CRC32 loop published with the original UDI v1.0 format."""
    crc = 0xFFFFFFFF
    for value in data:
        crc ^= 0xFFFFFFFF ^ value
        for _ in range(8):
            mask = 0xFFFFFFFF if (crc & 1) else 0
            crc = ((crc >> 1) ^ (0xEDB88320 & mask)) & 0xFFFFFFFF
        crc ^= 0xFFFFFFFF
    return crc & 0xFFFFFFFF


def is_udi_v10_header(header: bytes) -> bool:
    """Return whether a supplied prefix has the strict identifiable v1.0 header shape."""
    if len(header) < 16 or header[:4] != b"UDI!":
        return False
    declared_size = int.from_bytes(header[4:8], "little")
    extended_size = int.from_bytes(header[12:16], "little")
    return (
        header[8] == 0
        and header[10] in {0, 1}
        and header[11] == 0
        and 19 <= declared_size <= _MAX_SOURCE_BYTES - 4
        and extended_size <= _MAX_EXTENDED_HEADER_BYTES
    )


def inspect_udi(source: Path | str, token: CancellationToken | None = None) -> UdiInspection:
    """Validate the original UDI v1.0 track container without decoding tracks."""
    path = Path(source)
    if path.suffix.casefold() != ".udi":
        raise DiskForgeError("UDI inspection requires a .udi filename extension.")
    source_bytes = _source_size(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    if not is_udi_v10_header(content[:16]):
        raise DiskForgeError("The UDI signature, v1.0 header fields, or supported side count is invalid.")
    declared_size = int.from_bytes(content[4:8], "little")
    if declared_size != source_bytes - 4:
        raise DiskForgeError("The UDI declared file size does not match the exact source length.")
    cylinders = content[9] + 1
    sides = content[10] + 1
    extended_header_bytes = int.from_bytes(content[12:16], "little")
    position = 16 + extended_header_bytes
    data_end = source_bytes - 4
    if position > data_end:
        raise DiskForgeError("The UDI extended header exceeds the verified file data range.")
    tracks: list[UdiTrack] = []
    for index in range(cylinders * sides):
        if token:
            token.raise_if_cancelled()
        if position + 3 > data_end:
            raise DiskForgeError("A UDI v1.0 track header is truncated.")
        if content[position] != 0:
            raise DiskForgeError("UDI strict inspection supports only documented v1.0 MFM track type 0x00.")
        track_bytes = int.from_bytes(content[position + 1:position + 3], "little")
        clock_bytes = (track_bytes + 7) // 8
        track_end = position + 3 + track_bytes + clock_bytes
        if track_end > data_end:
            raise DiskForgeError("A UDI v1.0 track payload or clock-bit map is truncated.")
        clock_map = content[position + 3 + track_bytes:track_end]
        remainder = track_bytes % 8
        if remainder and clock_map and clock_map[-1] & ~((1 << remainder) - 1):
            raise DiskForgeError("A UDI v1.0 clock-bit map contains nonzero unused final bits.")
        tracks.append(UdiTrack(index, index // sides, index % sides, track_bytes, sum(byte.bit_count() for byte in clock_map)))
        position = track_end
    if position != data_end:
        raise DiskForgeError("The UDI v1.0 track stream has trailing or unaccounted bytes before its CRC32.")
    stored_crc = int.from_bytes(content[data_end:source_bytes], "little")
    calculated_crc = _udi_crc32(content[:data_end])
    if calculated_crc != stored_crc:
        raise DiskForgeError("The UDI v1.0 file CRC32 is invalid.")
    return UdiInspection(
        path, source_bytes, cylinders, sides, extended_header_bytes, tuple(tracks),
        sum(track.data_bytes for track in tracks), sum(track.clock_mark_count for track in tracks), stored_crc,
    )
