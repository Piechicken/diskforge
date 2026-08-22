"""Strict read-only inspection for canonical P64 v0 1541 flux-pulse containers.

The published P64 range-coded NRZI pulse stream is deliberately opaque here.
This module proves container framing, CRCs, HTP coordinate uniqueness and bounded
range-stream allocation only; it does not decode pulses, GCR, or sectors and
never exposes RAW export, filesystem access, conversion, repair, or writing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
import struct
import zlib

from .storage import CancellationToken, DiskForgeError


_SIGNATURE = b"P64-1541"
_HEADER_BYTES = 24
_CHUNK_HEADER_BYTES = 12
_DONE = b"DONE"
_HTP_PREFIX = b"HTP"
_MAX_SOURCE_BYTES = 512 * 1024 * 1024
_MAX_CHUNKS = 512
_MAX_TRACKS = 256
_MAX_RANGE_STREAM_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class P64Track:
    """One structurally validated opaque range-coded P64 half-track."""

    half_track_index: int
    side: int
    pulses: int
    encoded_bytes: int


@dataclass(frozen=True)
class P64Inspection:
    """Facts proven by strict P64 v0 structural inspection."""

    source: Path
    source_bytes: int
    flags: int
    chunks: int
    tracks: tuple[P64Track, ...]


def is_p64_header(head: bytes) -> bool:
    """Return whether a prefix has the fixed P64 v0 signature and version."""
    return len(head) >= 12 and head[:8] == _SIGNATURE and struct.unpack_from("<I", head, 8)[0] == 0


def _crc32(data: bytes) -> int:
    """Return the published conventional unsigned CRC-32 value."""
    return zlib.crc32(data) & 0xFFFFFFFF


def inspect_p64(source: Path | str, token: CancellationToken | None = None) -> P64Inspection:
    """Inspect one canonical P64 v0 container without mutating ``source``.

    The accepted subset follows the published canonical framing exactly: a v0
    little-endian header with only defined flag bits, an exact CRC-protected
    chunk stream, unique HTP half-track/side coordinates, a bounded HTP range
    stream whose declared byte count matches its payload, and a final empty
    DONE chunk. Range-coded NRZI data remains opaque by design.
    """
    path = Path(source)
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if path.suffix.casefold() != ".p64":
        raise DiskForgeError("P64 inspection requires a .p64 source file.")
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("P64 inspection accepts regular non-symbolic-link source files only.")
    if not _HEADER_BYTES + _CHUNK_HEADER_BYTES <= source_bytes <= _MAX_SOURCE_BYTES:
        raise DiskForgeError("P64 source size is outside the 36-byte-to-512-MiB safety range.")
    try:
        blob = path.read_bytes()
    except OSError as exc:
        raise DiskForgeError(f"Unable to read P64 image: {exc}") from exc
    if token:
        token.raise_if_cancelled()
    if not is_p64_header(blob):
        raise DiskForgeError("The source does not begin with the fixed P64-1541 version-0 signature.")

    flags, stream_bytes, expected_stream_crc = struct.unpack_from("<III", blob, 12)
    if flags & ~0x3:
        raise DiskForgeError("P64 v0 contains non-zero reserved header flag bits.")
    if stream_bytes != source_bytes - _HEADER_BYTES:
        raise DiskForgeError("P64 header chunk-stream size does not match the exact source length.")
    stream = blob[_HEADER_BYTES:]
    if _crc32(stream) != expected_stream_crc:
        raise DiskForgeError("P64 whole chunk-stream CRC-32 does not match the header.")

    offset = _HEADER_BYTES
    chunks = 0
    ended = False
    coordinates: set[tuple[int, int]] = set()
    tracks: list[P64Track] = []
    while offset < source_bytes:
        if token:
            token.raise_if_cancelled()
        if chunks >= _MAX_CHUNKS:
            raise DiskForgeError(f"P64 source exceeds the {_MAX_CHUNKS}-chunk safety limit.")
        if source_bytes - offset < _CHUNK_HEADER_BYTES:
            raise DiskForgeError("P64 source ends inside a chunk header.")
        chunk_id = blob[offset:offset + 4]
        payload_bytes, expected_crc = struct.unpack_from("<II", blob, offset + 4)
        if payload_bytes > _MAX_RANGE_STREAM_BYTES + 8:
            raise DiskForgeError("P64 chunk payload exceeds the structural safety limit.")
        payload_start = offset + _CHUNK_HEADER_BYTES
        chunk_end = payload_start + payload_bytes
        if chunk_end > source_bytes:
            raise DiskForgeError("P64 chunk payload exceeds source bounds.")
        payload = blob[payload_start:chunk_end]
        if _crc32(payload) != expected_crc:
            raise DiskForgeError(f"P64 chunk {chunk_id!r} CRC-32 does not match its payload.")
        chunks += 1

        if chunk_id == _DONE:
            if payload_bytes != 0:
                raise DiskForgeError("P64 DONE chunk must have zero payload bytes.")
            if chunk_end != source_bytes:
                raise DiskForgeError("P64 source has trailing bytes after its DONE chunk.")
            ended = True
            break
        if not chunk_id.startswith(_HTP_PREFIX):
            raise DiskForgeError(f"P64 contains unsupported chunk {chunk_id!r}; canonical inspection accepts only HTPx and DONE.")
        if len(tracks) >= _MAX_TRACKS:
            raise DiskForgeError(f"P64 source exceeds the {_MAX_TRACKS}-track safety limit.")
        if payload_bytes < 12:
            raise DiskForgeError("P64 HTP chunk is too short for counts and a range-decoder seed.")
        pulse_count, encoded_bytes = struct.unpack_from("<II", payload)
        if pulse_count == 0:
            raise DiskForgeError("P64 HTP pulse count must be non-zero in the canonical inspection subset.")
        if not 4 <= encoded_bytes <= _MAX_RANGE_STREAM_BYTES:
            raise DiskForgeError("P64 HTP range-encoded stream is outside the 4-byte-to-64-MiB safety range.")
        if encoded_bytes != payload_bytes - 8:
            raise DiskForgeError("P64 HTP range-encoded byte count does not match the chunk payload.")
        index_byte = chunk_id[3]
        coordinate = (index_byte & 0x7F, index_byte >> 7)
        if coordinate in coordinates:
            raise DiskForgeError("P64 source repeats an HTP half-track and side coordinate.")
        coordinates.add(coordinate)
        tracks.append(P64Track(coordinate[0], coordinate[1], pulse_count, encoded_bytes))
        offset = chunk_end

    if not ended:
        raise DiskForgeError("P64 source is missing its final empty DONE chunk.")
    return P64Inspection(path, source_bytes, flags, chunks, tuple(tracks))


__all__ = ["P64Inspection", "P64Track", "inspect_p64", "is_p64_header"]
