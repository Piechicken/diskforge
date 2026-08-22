"""Strict read-only structural inspection for standard floppy SuperCard Pro images.

SCP is a flux container.  This module only validates a conservative documented
floppy subset and never attempts to turn flux timing into sectors, raw media,
or a writable filesystem.
"""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 0x10
_TRACK_TABLE_ENTRIES = 168
_TRACK_TABLE_BYTES = _TRACK_TABLE_ENTRIES * 4
_TABLE_END = _HEADER_BYTES + _TRACK_TABLE_BYTES
_MAX_SOURCE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ScpRevolution:
    duration_ticks: int
    flux_words: int
    flux_offset: int


@dataclass(frozen=True)
class ScpTrack:
    logical_index: int
    cylinder: int
    head: int
    offset: int
    revolutions: tuple[ScpRevolution, ...]
    flux_bytes: int


@dataclass(frozen=True)
class ScpInspection:
    source: Path
    source_bytes: int
    version: int
    disk_type: int
    start_track: int
    end_track: int
    revolutions_per_track: int
    flags: int
    heads: int
    resolution_ns: int
    checksum: int
    tracks: tuple[ScpTrack, ...]
    total_flux_bytes: int


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("SCP inspection accepts regular non-symbolic-link source files only.")
    if not (_TABLE_END <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The SCP source size is outside the 688-byte to 64-MiB safety range.")
    return size


def is_scp_floppy_header(header: bytes) -> bool:
    """Return whether a prefix has a conservative identifiable standard-SCP shape."""
    if len(header) < _HEADER_BYTES or header[:3] != b"SCP":
        return False
    flags = header[8]
    return (
        1 <= header[5] <= 5
        and header[6] <= header[7] < _TRACK_TABLE_ENTRIES
        and not (flags & 0x70)  # reject writable, footer, and extended media modes
        and header[9] == 0
        and header[10] in {0, 1, 2}
        and header[4] >> 4 <= 8
    )


def _expected_parity(heads: int, logical_index: int) -> bool:
    if heads == 1:
        return logical_index % 2 == 0
    if heads == 2:
        return logical_index % 2 == 1
    return True


def inspect_scp(source: Path | str, token: CancellationToken | None = None) -> ScpInspection:
    """Validate a documented floppy SCP flux layout without decoding or mutation."""
    path = Path(source)
    if path.suffix.casefold() != ".scp":
        raise DiskForgeError("SCP inspection requires a .scp filename extension.")
    source_bytes = _source_size(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    if not is_scp_floppy_header(content[:_HEADER_BYTES]):
        raise DiskForgeError("The SCP header, standard floppy flags, track range, heads, or flux-word width is invalid.")
    version = content[3]
    disk_type = content[4]
    revolutions_per_track = content[5]
    start_track, end_track = content[6], content[7]
    flags, heads = content[8], content[10]
    resolution_ns = 25 * (content[11] + 1)
    checksum = int.from_bytes(content[12:16], "little")
    if (sum(content[_HEADER_BYTES:]) & 0xFFFFFFFF) != checksum:
        raise DiskForgeError("The SCP header checksum does not match data from the track table through EOF.")
    offsets = tuple(int.from_bytes(content[_HEADER_BYTES + 4 * index:_HEADER_BYTES + 4 * index + 4], "little")
                    for index in range(_TRACK_TABLE_ENTRIES))
    present = [(index, offset) for index, offset in enumerate(offsets) if offset]
    if not present:
        raise DiskForgeError("The SCP track data table must reference at least one track data header.")
    seen_offsets: set[int] = set()
    for index, offset in present:
        if not start_track <= index <= end_track or not _expected_parity(heads, index):
            raise DiskForgeError("An SCP table references a track outside its declared range or selected head.")
        if offset < _TABLE_END or offset >= source_bytes or offset in seen_offsets:
            raise DiskForgeError("SCP track data header offsets must be table-external, in range, and unique.")
        seen_offsets.add(offset)
    ordered_offsets = sorted(seen_offsets)
    boundaries = {offset: ordered_offsets[position + 1] if position + 1 < len(ordered_offsets) else source_bytes
                  for position, offset in enumerate(ordered_offsets)}
    tracks: list[ScpTrack] = []
    for index, offset in present:
        if token:
            token.raise_if_cancelled()
        boundary = boundaries[offset]
        header_bytes = 4 + 12 * revolutions_per_track
        if offset + header_bytes > boundary:
            raise DiskForgeError("An SCP track data header is truncated or overlaps the following track.")
        if content[offset:offset + 3] != b"TRK" or content[offset + 3] != index:
            raise DiskForgeError("An SCP track data header marker or logical track index does not match its table entry.")
        revolutions: list[ScpRevolution] = []
        ranges: list[tuple[int, int]] = []
        for revolution in range(revolutions_per_track):
            position = offset + 4 + 12 * revolution
            duration = int.from_bytes(content[position:position + 4], "little")
            words = int.from_bytes(content[position + 4:position + 8], "little")
            relative_offset = int.from_bytes(content[position + 8:position + 12], "little")
            flux_start = offset + relative_offset
            flux_end = flux_start + 2 * words
            if not duration or not words or relative_offset < header_bytes or flux_start < offset + header_bytes or flux_end > boundary:
                raise DiskForgeError("An SCP revolution duration, flux-word count, or flux range is outside its track boundary.")
            ranges.append((flux_start, flux_end))
            revolutions.append(ScpRevolution(duration, words, relative_offset))
        for previous, current in zip(sorted(ranges), sorted(ranges)[1:]):
            if previous[1] > current[0]:
                raise DiskForgeError("SCP revolution flux ranges must not overlap.")
        tracks.append(ScpTrack(index, index // 2, index % 2, offset, tuple(revolutions), sum(2 * item.flux_words for item in revolutions)))
    return ScpInspection(
        path, source_bytes, version, disk_type, start_track, end_track, revolutions_per_track, flags,
        heads, resolution_ns, checksum, tuple(sorted(tracks, key=lambda item: item.logical_index)),
        sum(track.flux_bytes for track in tracks),
    )
