"""Restricted read-only structural validation for native DMK bitstream containers.

DMK stores controller-level track bytes alongside per-track IDAM offsets.  This
module validates only the native container layout and IDAM directory; it does
not decode sectors, flatten tracks to RAW, or mutate source bytes.
"""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 16
_IDAM_TABLE_BYTES = 128
_MAX_TRACKS = 255
_MAX_TRACK_BYTES = 0x2940
_MAX_SOURCE_BYTES = _HEADER_BYTES + _MAX_TRACKS * 2 * _MAX_TRACK_BYTES
_ALLOWED_FLAGS = 0xD0


@dataclass(frozen=True)
class DmkTrack:
    """A validated opaque DMK track with its controller IDAM-directory facts."""

    index: int
    cylinder: int
    head: int
    offset: int
    idam_count: int
    double_density_idam_count: int


@dataclass(frozen=True)
class DmkInspection:
    """Validated metadata for a native DMK container without sector claims."""

    source: Path
    source_bytes: int
    tracks: int
    sides: int
    track_length: int
    write_protected: bool
    single_density_size: bool
    ignore_density: bool
    track_records: tuple[DmkTrack, ...]
    total_idams: int
    double_density_idams: int


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("DMK inspection accepts regular non-symbolic-link source files only.")
    if not (_HEADER_BYTES + _IDAM_TABLE_BYTES <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The DMK source size is outside the strict native-container safety range.")
    return size


def _header(content: bytes, source_bytes: int) -> tuple[int, int, int, bool, bool, bool]:
    if len(content) < _HEADER_BYTES:
        raise DiskForgeError("The DMK disk header is truncated.")
    write_protect, tracks = content[0], content[1]
    track_length = int.from_bytes(content[2:4], "little")
    flags = content[4]
    native_marker = content[12:16]
    if write_protect not in {0x00, 0xFF}:
        raise DiskForgeError("The DMK write-protect field must be 0x00 or 0xFF.")
    if not (1 <= tracks <= _MAX_TRACKS):
        raise DiskForgeError("The DMK header declares an invalid track count.")
    if not (_IDAM_TABLE_BYTES < track_length <= _MAX_TRACK_BYTES):
        raise DiskForgeError("The DMK header declares an unsupported track-image length.")
    if flags & ~_ALLOWED_FLAGS:
        raise DiskForgeError("The DMK header contains unknown option-flag bits.")
    if content[5:12] != b"\0" * 7:
        raise DiskForgeError("The DMK reserved header bytes must be zero in the strict native subset.")
    if native_marker == b"\x12\x34\x56\x78":
        raise DiskForgeError("DMK real-drive specification files are not disk-image containers.")
    if native_marker != b"\0" * 4:
        raise DiskForgeError("The DMK native-format marker bytes must be zero.")
    sides = 1 if flags & 0x10 else 2
    expected = _HEADER_BYTES + tracks * sides * track_length
    if source_bytes != expected:
        raise DiskForgeError("The DMK file size does not exactly match its declared native track layout.")
    return tracks, sides, track_length, write_protect == 0xFF, bool(flags & 0x40), bool(flags & 0x80)


def _track_idams(track: bytes) -> tuple[int, int]:
    """Validate a 64-entry IDAM offset table without interpreting track bytes."""
    previous = _IDAM_TABLE_BYTES - 1
    terminated = False
    count = double_density = 0
    for entry in range(0, _IDAM_TABLE_BYTES, 2):
        pointer = int.from_bytes(track[entry:entry + 2], "little")
        if pointer == 0:
            terminated = True
            continue
        if terminated:
            raise DiskForgeError("DMK IDAM pointers must be contiguous and zero-filled after the terminator.")
        if pointer & 0x4000:
            raise DiskForgeError("DMK IDAM pointers use the undefined bit-14 flag.")
        offset = pointer & 0x3FFF
        if not (_IDAM_TABLE_BYTES <= offset < len(track)):
            raise DiskForgeError("A DMK IDAM pointer is outside its track-data range.")
        if offset <= previous:
            raise DiskForgeError("DMK IDAM pointers must be strictly ascending.")
        if track[offset] != 0xFE:
            raise DiskForgeError("A DMK IDAM pointer does not reference an ID address mark byte.")
        previous = offset
        count += 1
        double_density += bool(pointer & 0x8000)
    return count, double_density


def inspect_dmk(source: Path | str, token: CancellationToken | None = None) -> DmkInspection:
    """Validate a native DMK layout without decoding sectors or modifying source bytes."""
    path = Path(source)
    if path.suffix.casefold() != ".dmk":
        raise DiskForgeError("DMK inspection requires a .dmk filename extension.")
    source_bytes = _source_size(path)
    with path.open("rb") as handle:
        header = handle.read(_HEADER_BYTES)
        tracks, sides, track_length, protected, single_density, ignore_density = _header(header, source_bytes)
        records: list[DmkTrack] = []
        total_idams = double_density_idams = 0
        for index in range(tracks * sides):
            if token:
                token.raise_if_cancelled()
            track = handle.read(track_length)
            if len(track) != track_length:
                raise DiskForgeError("A DMK track image is truncated.")
            idams, dd_idams = _track_idams(track)
            records.append(DmkTrack(index, index // sides, index % sides, _HEADER_BYTES + index * track_length, idams, dd_idams))
            total_idams += idams
            double_density_idams += dd_idams
        if handle.read(1):
            raise DiskForgeError("The DMK source contains unexpected trailing bytes.")
    return DmkInspection(path, source_bytes, tracks, sides, track_length, protected, single_density,
                         ignore_density, tuple(records), total_idams, double_density_idams)
