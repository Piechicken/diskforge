"""Strict read-only inspection for canonical G71 v0 1571 GCR containers.

G71 is the published double-sided extension of the G64 layout.  This module
accepts only a signed ``GCR-1571`` version-0 container with exactly 168
half-track entries (84 per side).  It validates only container allocation
facts; GCR bytes remain opaque and no filesystem, sector decode, RAW export,
conversion, repair, or write route is exposed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
import struct

from .storage import CancellationToken, DiskForgeError


_SIGNATURE = b"GCR-1571"
_HEADER_BYTES = 12
_TRACK_ENTRIES = 168  # 84 half-track slots per side, two sides.
_MAX_STORED_TRACK_BYTES = 7928
_MAX_SOURCE_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class G71Track:
    """One structurally validated opaque double-sided GCR track allocation."""

    entry_index: int
    actual_bytes: int
    speed_kind: str
    speed_zone: int | None


@dataclass(frozen=True)
class G71Inspection:
    """Facts proven by a strict G71 v0 structure-only inspection."""

    source: Path
    source_bytes: int
    track_entries: int
    stored_track_bytes: int
    constant_speed_tracks: int
    mapped_speed_tracks: int
    tracks: tuple[G71Track, ...]


def is_g71_header(head: bytes) -> bool:
    """Return whether a prefix has the fixed signed G71 v0 header shape."""
    return (
        len(head) >= _HEADER_BYTES
        and head[:8] == _SIGNATURE
        and head[8] == 0
        and head[9] == _TRACK_ENTRIES
    )


def _ranges_do_not_overlap(ranges: list[tuple[int, int, str]]) -> None:
    """Reject overlapping structural allocations, except exact shared speed maps."""
    ordered = sorted(ranges)
    for (start, end, kind), (next_start, next_end, next_kind) in zip(ordered, ordered[1:]):
        if next_start >= end:
            continue
        same_speed_map = kind == next_kind == "speed" and start == next_start and end == next_end
        if not same_speed_map:
            raise DiskForgeError("G71 track or speed-map allocations overlap.")


def inspect_g71(source: Path | str, token: CancellationToken | None = None) -> G71Inspection:
    """Inspect one canonical double-sided G71 v0 container without mutation."""
    path = Path(source)
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if path.suffix.casefold() != ".g71":
        raise DiskForgeError("G71 inspection requires a .g71 source file.")
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("G71 inspection accepts regular non-symbolic-link source files only.")
    if not _HEADER_BYTES <= source_bytes <= _MAX_SOURCE_BYTES:
        raise DiskForgeError("G71 source size is outside the 12-byte-to-512-MiB safety range.")
    try:
        blob = path.read_bytes()
    except OSError as exc:
        raise DiskForgeError(f"Unable to read G71 image: {exc}") from exc
    if token:
        token.raise_if_cancelled()
    if not is_g71_header(blob):
        raise DiskForgeError(
            "The source does not begin with the fixed GCR-1571 version-0 signature and 168-entry layout."
        )

    track_entries = blob[9]
    stored_track_bytes = struct.unpack_from("<H", blob, 10)[0]
    if track_entries != _TRACK_ENTRIES:
        raise DiskForgeError("G71 v0 requires exactly 168 half-track entries for the two 1541 sides.")
    if not 1 <= stored_track_bytes <= _MAX_STORED_TRACK_BYTES:
        raise DiskForgeError("G71 v0 stored-track byte size is outside the 1-to-7928-byte 1541 limit.")
    table_bytes = track_entries * 4
    header_end = _HEADER_BYTES + table_bytes * 2
    if header_end > source_bytes:
        raise DiskForgeError("G71 source ends inside the double-sided track or speed table.")

    track_offsets = struct.unpack_from(f"<{track_entries}I", blob, _HEADER_BYTES)
    speed_entries = struct.unpack_from(f"<{track_entries}I", blob, _HEADER_BYTES + table_bytes)
    allocation_bytes = 2 + stored_track_bytes
    speed_map_bytes = (stored_track_bytes + 3) // 4
    ranges: list[tuple[int, int, str]] = []
    tracks: list[G71Track] = []
    referenced_ends: list[int] = [header_end]
    seen_track_offsets: set[int] = set()
    constant_speed_tracks = mapped_speed_tracks = 0

    for entry_index, (track_offset, speed_entry) in enumerate(zip(track_offsets, speed_entries)):
        if token:
            token.raise_if_cancelled()
        if not track_offset:
            if speed_entry:
                raise DiskForgeError("G71 empty track entries must have a zero speed entry.")
            continue
        if track_offset in seen_track_offsets:
            raise DiskForgeError("G71 v0 track offsets must be unique when track data is present.")
        seen_track_offsets.add(track_offset)
        track_end = track_offset + allocation_bytes
        if track_offset < header_end or track_end > source_bytes:
            raise DiskForgeError("G71 track allocation is outside source bounds.")
        actual_bytes = struct.unpack_from("<H", blob, track_offset)[0]
        if not actual_bytes or actual_bytes > stored_track_bytes:
            raise DiskForgeError("G71 track data length must be non-zero and no greater than the declared stored-track size.")
        ranges.append((track_offset, track_end, "track"))
        referenced_ends.append(track_end)

        if speed_entry <= 3:
            speed_kind = "constant"
            speed_zone: int | None = speed_entry
            constant_speed_tracks += 1
        else:
            speed_end = speed_entry + speed_map_bytes
            if speed_entry < header_end or speed_end > source_bytes:
                raise DiskForgeError("G71 speed-map allocation is outside source bounds.")
            ranges.append((speed_entry, speed_end, "speed"))
            referenced_ends.append(speed_end)
            speed_kind = "map"
            speed_zone = None
            mapped_speed_tracks += 1
        tracks.append(G71Track(entry_index, actual_bytes, speed_kind, speed_zone))

    if not tracks:
        raise DiskForgeError("G71 v0 must contain at least one stored GCR track.")
    _ranges_do_not_overlap(ranges)
    if max(referenced_ends) != source_bytes:
        raise DiskForgeError("G71 v0 source contains unreferenced trailing bytes instead of exact EOF.")

    return G71Inspection(
        path,
        source_bytes,
        track_entries,
        stored_track_bytes,
        constant_speed_tracks,
        mapped_speed_tracks,
        tuple(tracks),
    )


__all__ = ["G71Inspection", "G71Track", "inspect_g71", "is_g71_header"]
