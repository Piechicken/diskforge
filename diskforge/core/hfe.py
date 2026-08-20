"""Restricted read-only HFE bitstream-container inspection.

HFE carries controller-specific bit-cell streams.  This module validates the
container only; it deliberately provides no sector decoding, RAW export, or
write operation.
"""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 512
_BLOCK_BYTES = 512
_MAX_SOURCE_BYTES = 16 * 1024 * 1024 * 1024
_MAX_TRACKS = 164
_MAGICS = {b"HXCPICFE": "v1/v2", b"HXCHFEV3": "v3"}


@dataclass(frozen=True)
class HfeTrack:
    """A bounded HFE track bitstream record; payload semantics are intentionally opaque."""

    index: int
    offset_bytes: int
    declared_bytes: int
    stored_bytes: int
    side_count: int


@dataclass(frozen=True)
class HfeInspection:
    """Validated HFE container metadata without any claim about sector content."""

    source: Path
    version: str
    revision: int
    tracks: int
    sides: int
    track_encoding: int
    bitrate_kbps: int
    rpm: int
    interface_mode: int
    write_protected: bool
    track_list_offset_bytes: int
    track_records: tuple[HfeTrack, ...]
    source_bytes: int
    unreferenced_bytes: int


def _round_block(value: int) -> int:
    return (value + _BLOCK_BYTES - 1) // _BLOCK_BYTES * _BLOCK_BYTES


def inspect_hfe(source: Path | str, token: CancellationToken | None = None) -> HfeInspection:
    """Validate an HFE bitstream container without decoding or mutating its streams."""
    path = Path(source)
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("HFE inspection accepts regular non-symbolic-link source files only.")
    if source_bytes < _HEADER_BYTES or source_bytes > _MAX_SOURCE_BYTES:
        raise DiskForgeError("The HFE source size is outside the 512-byte to 16-GiB safety range.")
    with path.open("rb") as handle:
        header = handle.read(_HEADER_BYTES)
        if len(header) != _HEADER_BYTES:
            raise DiskForgeError("The HFE header is truncated.")
        magic = header[:8]
        version = _MAGICS.get(magic)
        if version is None:
            raise DiskForgeError("The source does not begin with an HFE v1/v2 or v3 signature.")
        revision = header[8]
        tracks, sides = header[9], header[10]
        if not tracks or tracks > _MAX_TRACKS:
            raise DiskForgeError("The HFE header declares an invalid track count.")
        if sides not in {1, 2}:
            raise DiskForgeError("The HFE header declares an unsupported side count.")
        lut_block = int.from_bytes(header[0x12:0x14], "little")
        lut_offset = lut_block * _BLOCK_BYTES
        lut_bytes = tracks * 4
        if not lut_block or lut_offset < _HEADER_BYTES or lut_offset + lut_bytes > source_bytes:
            raise DiskForgeError("The HFE track lookup table is outside the source file.")
        handle.seek(lut_offset)
        lut = handle.read(lut_bytes)
        if len(lut) != lut_bytes:
            raise DiskForgeError("The HFE track lookup table is truncated.")
    records: list[HfeTrack] = []
    ranges: list[tuple[int, int]] = []
    for index in range(tracks):
        if token:
            token.raise_if_cancelled()
        entry = index * 4
        block_offset = int.from_bytes(lut[entry:entry + 2], "little")
        declared_bytes = int.from_bytes(lut[entry + 2:entry + 4], "little")
        offset_bytes = block_offset * _BLOCK_BYTES
        stored_bytes = _round_block(declared_bytes)
        if not block_offset or not declared_bytes:
            raise DiskForgeError("The HFE track lookup table contains a zero offset or length.")
        if offset_bytes < _HEADER_BYTES or offset_bytes + stored_bytes > source_bytes:
            raise DiskForgeError("An HFE track bitstream range is outside the source file.")
        ranges.append((offset_bytes, offset_bytes + stored_bytes))
        records.append(HfeTrack(index, offset_bytes, declared_bytes, stored_bytes, sides))
    ranges.sort()
    if any(next_start < end for (_, end), (next_start, _) in zip(ranges, ranges[1:])):
        raise DiskForgeError("The HFE track bitstream ranges overlap.")
    # Count intervals rather than allocating an address map; a source can be as
    # large as 16 GiB, so per-byte bookkeeping would defeat the safety limit.
    merged = sorted([(0, _HEADER_BYTES), (lut_offset, lut_offset + lut_bytes), *ranges])
    covered = 0
    end = 0
    for start, stop in merged:
        if stop <= end:
            continue
        covered += stop - max(start, end)
        end = max(end, stop)
    return HfeInspection(
        path, version, revision, tracks, sides, header[11], int.from_bytes(header[12:14], "little"),
        int.from_bytes(header[14:16], "little"), header[16], header[20] == 0,
        lut_offset, tuple(records), source_bytes, source_bytes - covered,
    )
