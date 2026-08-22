"""Strict read-only inspection for canonical G64 v0 1541 bitstream containers.

The inspector accepts only ``GCR-1541`` version-0 containers.  It validates the
published little-endian header, track and speed tables, fixed per-track storage
allocations, optional speed maps, non-overlap, and exact EOF.  GCR bytes remain
opaque: no GCR/sector decoding, filesystem session, RAW export, conversion,
repair, or write route is exposed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
import struct

from .storage import CancellationToken, DiskForgeError

_SIGNATURE = b"GCR-1541"
_HEADER_BYTES = 12
_MAX_TRACK_ENTRIES = 84  # 42 physical tracks plus half tracks for a 1541.
_MAX_STORED_TRACK_BYTES = 7928
_MAX_SOURCE_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class G64Track:
    """One structurally validated opaque GCR track allocation."""

    entry_index: int
    actual_bytes: int
    speed_kind: str
    speed_zone: int | None


@dataclass(frozen=True)
class G64Inspection:
    """Facts proven by a strict G64 v0 structure-only inspection."""

    source: Path
    source_bytes: int
    track_entries: int
    stored_track_bytes: int
    constant_speed_tracks: int
    mapped_speed_tracks: int
    tracks: tuple[G64Track, ...]


def is_g64_header(head: bytes) -> bool:
    """Return whether a prefix has the fixed signed G64 v0 header shape."""
    return len(head) >= _HEADER_BYTES and head[:8] == _SIGNATURE and head[8] == 0


def _ranges_do_not_overlap(ranges: list[tuple[int, int, str]]) -> None:
    """Reject overlapping structural allocations, except exact shared speed maps."""
    ordered = sorted(ranges)
    for (start, end, kind), (next_start, next_end, next_kind) in zip(ordered, ordered[1:]):
        if next_start >= end:
            continue
        same_speed_map = kind == next_kind == "speed" and start == next_start and end == next_end
        if not same_speed_map:
            raise DiskForgeError("G64 track or speed-map allocations overlap.")


def inspect_g64(source: Path | str, token: CancellationToken | None = None) -> G64Inspection:
    """Inspect one canonical G64 v0 1541 container without mutating it."""
    path = Path(source)
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if path.suffix.casefold() != ".g64":
        raise DiskForgeError("G64 inspection requires a .g64 source file.")
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("G64 inspection accepts regular non-symbolic-link source files only.")
    if not _HEADER_BYTES <= source_bytes <= _MAX_SOURCE_BYTES:
        raise DiskForgeError("G64 source size is outside the 12-byte-to-512-MiB safety range.")
    try:
        blob = path.read_bytes()
    except OSError as exc:
        raise DiskForgeError(f"Unable to read G64 image: {exc}") from exc
    if token:
        token.raise_if_cancelled()
    if not is_g64_header(blob):
        raise DiskForgeError("The source does not begin with the fixed GCR-1541 version-0 signature.")

    track_entries = blob[9]
    stored_track_bytes = struct.unpack_from("<H", blob, 10)[0]
    if not 1 <= track_entries <= _MAX_TRACK_ENTRIES:
        raise DiskForgeError("G64 v0 track-entry count must be from 1 through 84.")
    if not 1 <= stored_track_bytes <= _MAX_STORED_TRACK_BYTES:
        raise DiskForgeError("G64 v0 stored-track byte size is outside the 1-to-7928-byte 1541 limit.")
    table_bytes = track_entries * 4
    header_end = _HEADER_BYTES + table_bytes * 2
    if header_end > source_bytes:
        raise DiskForgeError("G64 source ends inside the track or speed table.")

    track_offsets = struct.unpack_from(f"<{track_entries}I", blob, _HEADER_BYTES)
    speed_entries = struct.unpack_from(f"<{track_entries}I", blob, _HEADER_BYTES + table_bytes)
    allocation_bytes = 2 + stored_track_bytes
    speed_map_bytes = (stored_track_bytes + 3) // 4
    ranges: list[tuple[int, int, str]] = []
    tracks: list[G64Track] = []
    referenced_ends: list[int] = [header_end]
    seen_track_offsets: set[int] = set()
    constant_speed_tracks = mapped_speed_tracks = 0

    for entry_index, (track_offset, speed_entry) in enumerate(zip(track_offsets, speed_entries)):
        if token:
            token.raise_if_cancelled()
        if not track_offset:
            if speed_entry:
                raise DiskForgeError("G64 empty track entries must have a zero speed entry.")
            continue
        if track_offset in seen_track_offsets:
            raise DiskForgeError("G64 v0 track offsets must be unique when track data is present.")
        seen_track_offsets.add(track_offset)
        track_end = track_offset + allocation_bytes
        if track_offset < header_end or track_end > source_bytes:
            raise DiskForgeError("G64 track allocation is outside source bounds.")
        actual_bytes = struct.unpack_from("<H", blob, track_offset)[0]
        if not actual_bytes or actual_bytes > stored_track_bytes:
            raise DiskForgeError("G64 track data length must be non-zero and no greater than the declared stored-track size.")
        ranges.append((track_offset, track_end, "track"))
        referenced_ends.append(track_end)

        if speed_entry <= 3:
            speed_kind = "constant"
            speed_zone: int | None = speed_entry
            constant_speed_tracks += 1
        else:
            speed_end = speed_entry + speed_map_bytes
            if speed_entry < header_end or speed_end > source_bytes:
                raise DiskForgeError("G64 speed-map allocation is outside source bounds.")
            ranges.append((speed_entry, speed_end, "speed"))
            referenced_ends.append(speed_end)
            speed_kind = "map"
            speed_zone = None
            mapped_speed_tracks += 1
        tracks.append(G64Track(entry_index, actual_bytes, speed_kind, speed_zone))

    if not tracks:
        raise DiskForgeError("G64 v0 must contain at least one stored GCR track.")
    _ranges_do_not_overlap(ranges)
    if max(referenced_ends) != source_bytes:
        raise DiskForgeError("G64 v0 source contains unreferenced trailing bytes instead of exact EOF.")

    return G64Inspection(
        path, source_bytes, track_entries, stored_track_bytes,
        constant_speed_tracks, mapped_speed_tracks, tuple(tracks),
    )


__all__ = ["G64Inspection", "G64Track", "inspect_g64", "is_g64_header"]
