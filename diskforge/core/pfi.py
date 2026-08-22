"""Strict read-only inspection for published PCE PFI flux-image containers.

PFI track payloads remain opaque flux pulse streams.  This module verifies the
container grammar and bounded pulse-token syntax only; it deliberately neither
decodes sectors nor exposes RAW export, filesystem access, conversion, or
writing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from .storage import DiskForgeError


_PFI_HEADER = b"PFI "
_TEXT = b"TEXT"
_TRAK = b"TRAK"
_INDX = b"INDX"
_DATA = b"DATA"
_END = b"END "
_CRC_POLY = 0x1EDC6F41
_MAX_CHUNKS = 65_536
_MAX_TRACKS = 512
_MAX_CHUNK_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class PfiTrack:
    """One structurally validated PFI track context."""

    cylinder: int
    head: int
    clock_rate: int
    index_count: int
    data_chunks: int
    data_bytes: int
    pulse_count: int


@dataclass(frozen=True)
class PfiInspection:
    """Facts proven by a strict PFI container inspection."""

    source: Path
    source_bytes: int
    chunks: int
    comments: int
    unknown_chunks: int
    tracks: tuple[PfiTrack, ...]


def _pfi_crc32(data: bytes) -> int:
    """Return the PFI big-endian CRC-32 (poly 0x1EDC6F41, initial zero)."""
    crc = 0
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ _CRC_POLY) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def _require_pulse_stream(data: bytes, *, context: str) -> int:
    """Validate bounded PFI pulse tokens without interpreting their timing."""
    offset = 0
    pulses = 0
    while offset < len(data):
        token = data[offset]
        if token == 0:
            raise DiskForgeError(f"{context} contains invalid zero pulse token at byte {offset}.")
        extra = 2 if token == 1 else 3 if token == 2 else 4 if token == 3 else 1 if 4 <= token <= 7 else 0
        if offset + 1 + extra > len(data):
            raise DiskForgeError(f"{context} ends inside a variable-length pulse token at byte {offset}.")
        offset += 1 + extra
        pulses += 1
    return pulses


def is_pfi_header(head: bytes) -> bool:
    """Return whether ``head`` has the published PFI v0 first-chunk shape."""
    return len(head) >= 12 and head[:4] == _PFI_HEADER and head[4:8] == b"\x00\x00\x00\x04" and head[8:12] == b"\x00\x00\x00\x00"


def inspect_pfi(source: Path) -> PfiInspection:
    """Validate a canonical PFI v0 container without changing ``source``.

    The accepted contract is deliberately stricter than a permissive loader:
    the PFI header is first and unique; PFI v0 chunk CRCs must validate; each
    track coordinate is unique; data and index chunks require a preceding
    track; one data chunk is permitted per track; END is zero-length and final.
    Unknown post-header chunks are verified and reported but not interpreted.
    """
    source = Path(source)
    try:
        blob = source.read_bytes()
    except OSError as exc:
        raise DiskForgeError(f"Unable to read PFI image: {exc}") from exc
    if len(blob) < 28:
        raise DiskForgeError("PFI image is too short for a header and END chunk.")

    offset = 0
    chunks = comments = unknown_chunks = 0
    header_seen = False
    ended = False
    active: dict[str, int] | None = None
    tracks: list[dict[str, int]] = []
    coordinates: set[tuple[int, int]] = set()

    while offset < len(blob):
        if chunks >= _MAX_CHUNKS:
            raise DiskForgeError(f"PFI image exceeds {_MAX_CHUNKS} chunk safety limit.")
        if len(blob) - offset < 12:
            raise DiskForgeError("PFI image ends inside a chunk header or CRC.")
        chunk_id = blob[offset:offset + 4]
        declared_size = struct.unpack_from(">I", blob, offset + 4)[0]
        if declared_size > _MAX_CHUNK_BYTES:
            raise DiskForgeError(f"PFI chunk {chunk_id!r} exceeds the {_MAX_CHUNK_BYTES} byte safety limit.")
        end = offset + 8 + declared_size + 4
        if end > len(blob):
            raise DiskForgeError(f"PFI chunk {chunk_id!r} exceeds source bounds.")
        payload = blob[offset + 8:offset + 8 + declared_size]
        expected_crc = struct.unpack_from(">I", blob, offset + 8 + declared_size)[0]
        actual_crc = _pfi_crc32(blob[offset:offset + 8 + declared_size])
        if expected_crc != actual_crc:
            raise DiskForgeError(f"PFI chunk {chunk_id!r} CRC does not match the published PFI CRC-32.")
        chunks += 1

        if not header_seen:
            if chunk_id != _PFI_HEADER or declared_size != 4:
                raise DiskForgeError("PFI image must begin with exactly one 4-byte PFI header chunk.")
            version = struct.unpack(">I", payload)[0]
            if version != 0:
                raise DiskForgeError(f"PFI version {version} is unsupported; only published version 0 is accepted.")
            header_seen = True
        elif chunk_id == _PFI_HEADER:
            raise DiskForgeError("PFI image contains a duplicate header chunk.")
        elif chunk_id == _END:
            if declared_size != 0:
                raise DiskForgeError("PFI END chunk must have zero payload bytes.")
            if end != len(blob):
                raise DiskForgeError("PFI image has trailing data after the END chunk.")
            ended = True
            break
        elif chunk_id == _TEXT:
            comments += 1
        elif chunk_id == _TRAK:
            if declared_size != 12:
                raise DiskForgeError("PFI TRAK chunk must contain exactly cylinder, head, and clock-rate fields.")
            cylinder, head, clock_rate = struct.unpack(">III", payload)
            if clock_rate == 0:
                raise DiskForgeError("PFI TRAK clock rate must be non-zero.")
            coordinate = (cylinder, head)
            if coordinate in coordinates:
                raise DiskForgeError(f"PFI image repeats track coordinate C{cylinder} H{head}.")
            if len(tracks) >= _MAX_TRACKS:
                raise DiskForgeError(f"PFI image exceeds {_MAX_TRACKS} track safety limit.")
            coordinates.add(coordinate)
            active = {"cylinder": cylinder, "head": head, "clock_rate": clock_rate, "index_count": 0,
                      "data_chunks": 0, "data_bytes": 0, "pulse_count": 0}
            tracks.append(active)
        elif chunk_id == _INDX:
            if active is None:
                raise DiskForgeError("PFI INDX chunk appears before a TRAK chunk.")
            if declared_size % 4:
                raise DiskForgeError("PFI INDX chunk size must be a multiple of four bytes.")
            positions = struct.unpack(f">{declared_size // 4}I", payload) if payload else ()
            if any(right < left for left, right in zip(positions, positions[1:])):
                raise DiskForgeError("PFI INDX positions must be non-decreasing within a track.")
            active["index_count"] += len(positions)
        elif chunk_id == _DATA:
            if active is None:
                raise DiskForgeError("PFI DATA chunk appears before a TRAK chunk.")
            if active["data_chunks"]:
                raise DiskForgeError("PFI track contains more than one DATA chunk; this strict inspector rejects overwrite ambiguity.")
            active["data_chunks"] = 1
            active["data_bytes"] = declared_size
            active["pulse_count"] = _require_pulse_stream(payload, context=f"PFI track C{active['cylinder']} H{active['head']} DATA")
        else:
            unknown_chunks += 1
        offset = end

    if not header_seen:
        raise DiskForgeError("PFI header chunk is missing.")
    if not ended:
        raise DiskForgeError("PFI image is missing its final END chunk.")

    return PfiInspection(
        source=source,
        source_bytes=len(blob),
        chunks=chunks,
        comments=comments,
        unknown_chunks=unknown_chunks,
        tracks=tuple(PfiTrack(**track) for track in tracks),
    )


__all__ = ["PfiInspection", "PfiTrack", "inspect_pfi", "is_pfi_header"]
