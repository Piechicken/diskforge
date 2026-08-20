"""Read-only Atari ST MSA inspection and strict track-by-track RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 10
_MAGIC = b"\x0e\x0f"
_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_RAW_BYTES = 8 * 1024 * 1024
_MAX_SECTORS_PER_TRACK = 32
_MAX_TRACK = 85


@dataclass(frozen=True)
class MsaTrack:
    cylinder: int
    head: int
    stored_bytes: int
    compressed: bool
    data: bytes


@dataclass(frozen=True)
class MsaInspection:
    source: Path
    source_bytes: int
    sectors_per_track: int
    heads: int
    start_track: int
    end_track: int
    tracks: tuple[MsaTrack, ...]
    compressed_track_count: int
    raw_bytes: int


def _u16be(value: bytes) -> int:
    return int.from_bytes(value, "big")


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("MSA inspection accepts regular non-symbolic-link source files only.")
    if not (_HEADER_BYTES <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The MSA source size is outside the 10-byte to 32-MiB safety range.")
    return size


def _decode_track(payload: bytes, expected_bytes: int) -> bytes:
    output = bytearray()
    position = 0
    while position < len(payload):
        value = payload[position]
        position += 1
        if value != 0xE5:
            if len(output) >= expected_bytes:
                raise DiskForgeError("MSA compressed track expands beyond the declared sector geometry.")
            output.append(value)
            continue
        if position + 3 > len(payload):
            raise DiskForgeError("An MSA E5 RLE marker is truncated.")
        repeated = payload[position]
        count = _u16be(payload[position + 1:position + 3])
        position += 3
        if not count:
            raise DiskForgeError("An MSA E5 RLE marker has a zero run length.")
        if len(output) + count > expected_bytes:
            raise DiskForgeError("MSA compressed track expands beyond the declared sector geometry.")
        output.extend(bytes((repeated,)) * count)
    if len(output) != expected_bytes:
        raise DiskForgeError("MSA compressed track does not decode to its exact declared sector geometry.")
    return bytes(output)


def inspect_msa(source: Path | str, token: CancellationToken | None = None) -> MsaInspection:
    """Validate and decode every MSA track without changing source bytes."""
    path = Path(source)
    if path.suffix.casefold() != ".msa":
        raise DiskForgeError("MSA inspection requires a .msa filename extension.")
    source_bytes = _source_size(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    header = content[:_HEADER_BYTES]
    if header[:2] != _MAGIC:
        raise DiskForgeError("The MSA 0E0F signature header is invalid.")
    sectors_per_track = _u16be(header[2:4])
    sides_minus_one = _u16be(header[4:6])
    start_track = _u16be(header[6:8])
    end_track = _u16be(header[8:10])
    if not (1 <= sectors_per_track <= _MAX_SECTORS_PER_TRACK) or sides_minus_one not in {0, 1}:
        raise DiskForgeError("The MSA sector-per-track or side count is outside the supported range.")
    if start_track > end_track or end_track > _MAX_TRACK:
        raise DiskForgeError("The MSA start/end track range is invalid or outside the supported range.")
    heads = sides_minus_one + 1
    expected_track_bytes = sectors_per_track * 512
    track_count = (end_track - start_track + 1) * heads
    raw_bytes = expected_track_bytes * track_count
    if raw_bytes > _MAX_RAW_BYTES:
        raise DiskForgeError("The MSA declared decoded RAW size exceeds the 8-MiB safety limit.")
    position = _HEADER_BYTES
    tracks: list[MsaTrack] = []
    for cylinder in range(start_track, end_track + 1):
        for head in range(heads):
            if token:
                token.raise_if_cancelled()
            if position + 2 > source_bytes:
                raise DiskForgeError("An MSA track data-length field is truncated.")
            stored_bytes = _u16be(content[position:position + 2])
            position += 2
            if not stored_bytes or stored_bytes > expected_track_bytes or position + stored_bytes > source_bytes:
                raise DiskForgeError("An MSA track data block is outside the declared sector-geometry bounds.")
            payload = content[position:position + stored_bytes]
            position += stored_bytes
            if stored_bytes == expected_track_bytes:
                data = payload
                compressed = False
            else:
                data = _decode_track(payload, expected_track_bytes)
                compressed = True
            tracks.append(MsaTrack(cylinder, head, stored_bytes, compressed, data))
    if position != source_bytes:
        raise DiskForgeError("The MSA file has trailing bytes after all declared track blocks.")
    result_tracks = tuple(tracks)
    return MsaInspection(path, source_bytes, sectors_per_track, heads, start_track, end_track,
                         result_tracks, sum(item.compressed for item in result_tracks), raw_bytes)


def export_msa_to_raw(source: Path | str, destination: Path | str,
                      token: CancellationToken | None = None) -> Path:
    """Export fully decoded, structurally validated MSA tracks to a new RAW image."""
    source_path, target = Path(source), Path(destination)
    inspection = inspect_msa(source_path, token)
    if source_path.resolve() == target.resolve():
        raise DiskForgeError("The MSA RAW export destination must differ from the source file.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The MSA RAW export destination directory does not exist.")
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.diskforge-msa-", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output_handle:
            for track in inspection.tracks:
                if token:
                    token.raise_if_cancelled()
                output_handle.write(track.data)
        if temporary.stat().st_size != inspection.raw_bytes:
            raise DiskForgeError("The MSA RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
