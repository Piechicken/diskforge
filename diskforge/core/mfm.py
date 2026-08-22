"""Strict read-only inspection for the HxC MFM bitstream container.

The container stores opaque MFM/FM track byte streams.  DiskForge validates only
an intentionally narrow, reference-writer-compatible structure: a packed
``HXCMFM\\0`` header, canonical ordered track table, zero padding to 512-byte
track boundaries, non-overlapping payloads, and exact EOF.  It does not decode
sectors, infer filesystems, export RAW, or write MFM containers.
"""
from __future__ import annotations

import stat
import struct
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError

_SIGNATURE = b"HXCMFM\0"
_HEADER = struct.Struct("<7sHBHHBI")
_TRACK = struct.Struct("<HBII")
_MAX_SOURCE_BYTES = 16 * 1024 * 1024 * 1024
_MAX_TRACKS = 256
_MAX_BITRATE_KBPS = 2_000
_BLOCK_BYTES = 512
_COPY_BLOCK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class MfmTrack:
    """One verified opaque MFM track payload."""

    cylinder: int
    side: int
    offset_bytes: int
    bytes_stored: int


@dataclass(frozen=True)
class MfmInspection:
    """Validated MFM container facts without any sector or filesystem claim."""

    source: Path
    tracks: int
    sides: int
    rpm: int
    bitrate_kbps: int
    interface_type: int
    track_table_offset_bytes: int
    track_records: tuple[MfmTrack, ...]
    source_bytes: int
    padding_bytes: int


def is_hxc_mfm_header(head: bytes) -> bool:
    """Return whether a prefix has the signed, minimally plausible MFM header shape."""
    if len(head) < _HEADER.size:
        return False
    signature, tracks, sides, _rpm, bitrate, _interface_type, table_offset = _HEADER.unpack_from(head)
    return (
        signature == _SIGNATURE
        and 1 <= tracks <= _MAX_TRACKS
        and sides in {1, 2}
        and 1 <= bitrate <= _MAX_BITRATE_KBPS
        and table_offset == _HEADER.size
    )


def _round_block(value: int) -> int:
    return (value + _BLOCK_BYTES - 1) // _BLOCK_BYTES * _BLOCK_BYTES


def _require_zero_range(handle, start: int, stop: int, token: CancellationToken | None) -> None:  # type: ignore[no-untyped-def]
    """Verify padding in bounded chunks instead of materializing a large input."""
    if stop <= start:
        return
    handle.seek(start)
    remaining = stop - start
    while remaining:
        if token:
            token.raise_if_cancelled()
        chunk = handle.read(min(_COPY_BLOCK_BYTES, remaining))
        if not chunk:
            raise DiskForgeError("The MFM padding range is truncated.")
        if any(chunk):
            raise DiskForgeError("The MFM container contains non-zero bytes in a required padding range.")
        remaining -= len(chunk)


def inspect_mfm(source: Path | str, token: CancellationToken | None = None) -> MfmInspection:
    """Inspect a canonical HxC MFM bitstream container without mutating it."""
    path = Path(source)
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if path.suffix.casefold() != ".mfm":
        raise DiskForgeError("HxC MFM inspection requires a .mfm source file.")
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("HxC MFM inspection accepts regular non-symbolic-link source files only.")
    if source_bytes < _HEADER.size or source_bytes > _MAX_SOURCE_BYTES:
        raise DiskForgeError("The HxC MFM source size is outside the header-to-16-GiB safety range.")

    with path.open("rb") as handle:
        header = handle.read(_HEADER.size)
        if len(header) != _HEADER.size:
            raise DiskForgeError("The HxC MFM header is truncated.")
        signature, tracks, sides, rpm, bitrate, interface_type, table_offset = _HEADER.unpack(header)
        if signature != _SIGNATURE:
            raise DiskForgeError("The source does not begin with the HxC MFM signature.")
        if not 1 <= tracks <= _MAX_TRACKS:
            raise DiskForgeError("The HxC MFM header declares an invalid track count.")
        if sides not in {1, 2}:
            raise DiskForgeError("The HxC MFM header declares an unsupported side count.")
        if not 1 <= bitrate <= _MAX_BITRATE_KBPS:
            raise DiskForgeError("The HxC MFM header declares an invalid bitrate.")
        if table_offset != _HEADER.size:
            raise DiskForgeError("The HxC MFM track table must begin immediately after the packed header.")
        record_count = tracks * sides
        table_bytes = record_count * _TRACK.size
        table_end = table_offset + table_bytes
        if table_end > source_bytes:
            raise DiskForgeError("The HxC MFM track table is outside the source file.")
        handle.seek(table_offset)
        table = handle.read(table_bytes)
        if len(table) != table_bytes:
            raise DiskForgeError("The HxC MFM track table is truncated.")

        records: list[MfmTrack] = []
        ranges: list[tuple[int, int]] = []
        for index in range(record_count):
            if token:
                token.raise_if_cancelled()
            cylinder, side, track_bytes, track_offset = _TRACK.unpack_from(table, index * _TRACK.size)
            expected_cylinder, expected_side = divmod(index, sides)
            if (cylinder, side) != (expected_cylinder, expected_side):
                raise DiskForgeError("The HxC MFM track table must contain each cylinder/side once in canonical order.")
            if not track_bytes:
                raise DiskForgeError("The HxC MFM track table contains an empty track payload.")
            if track_offset < _round_block(table_end) or track_offset % _BLOCK_BYTES:
                raise DiskForgeError("An HxC MFM track payload does not begin at the required 512-byte boundary.")
            track_end = track_offset + track_bytes
            if track_end > source_bytes:
                raise DiskForgeError("An HxC MFM track payload range is outside the source file.")
            records.append(MfmTrack(cylinder, side, track_offset, track_bytes))
            ranges.append((track_offset, track_end))

        sorted_ranges = sorted(ranges)
        if any(next_start < current_end for (_, current_end), (next_start, _) in zip(sorted_ranges, sorted_ranges[1:])):
            raise DiskForgeError("HxC MFM track payload ranges overlap.")
        expected_start = _round_block(table_end)
        padding_bytes = expected_start - table_end
        _require_zero_range(handle, table_end, expected_start, token)
        for start, stop in sorted_ranges:
            if start != expected_start:
                raise DiskForgeError("HxC MFM track payloads must be contiguous apart from canonical zero padding.")
            expected_start = _round_block(stop)
            padding_bytes += expected_start - stop
            if expected_start > source_bytes:
                expected_start = stop
                break
            _require_zero_range(handle, stop, expected_start, token)
        if sorted_ranges[-1][1] != source_bytes:
            raise DiskForgeError("The HxC MFM source has trailing bytes after the final track payload.")

    return MfmInspection(
        path, tracks, sides, rpm, bitrate, interface_type, table_offset,
        tuple(records), source_bytes, padding_bytes,
    )
