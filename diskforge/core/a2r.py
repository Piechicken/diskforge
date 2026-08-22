"""Strict read-only inspection for published A2R 3.x flux-image containers.

A2R capture payloads remain opaque.  This module validates documented container
framing and capture-entry boundaries only; it deliberately does not decode
flux, bitstreams, sectors, or filesystems and exposes no export/write path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from .storage import DiskForgeError


_A2R3_HEADER = b"A2R3\xff\x0a\x0d\x0a"
_INFO = b"INFO"
_RWCP = b"RWCP"
_SLVD = b"SLVD"
_META = b"META"
_MAX_CHUNKS = 65_536
_MAX_CHUNK_BYTES = 512 * 1024 * 1024
_MAX_ENTRIES = 65_536


@dataclass(frozen=True)
class A2rCapture:
    """One bounded raw-capture entry, without interpreting flux timing."""

    location: int
    capture_type: int
    index_signals: int
    data_bytes: int


@dataclass(frozen=True)
class A2rSolvedTrack:
    """One bounded solved-track entry, without interpreting flux timing."""

    location: int
    index_signals: int
    data_bytes: int
    mirror_outward: int
    mirror_inward: int


@dataclass(frozen=True)
class A2rInspection:
    """Facts proven by a strict A2R 3.x container inspection."""

    source: Path
    source_bytes: int
    chunks: int
    drive_type: int
    creator: str
    write_protected: bool
    synchronized: bool
    hard_sector_count: int
    raw_capture_chunks: int
    solved_flux_chunks: int
    captures: tuple[A2rCapture, ...]
    solved_tracks: tuple[A2rSolvedTrack, ...]
    metadata_entries: int
    unknown_chunks: int


def is_a2r3_header(head: bytes) -> bool:
    """Return whether ``head`` begins with the published A2R 3.x signature."""
    return len(head) >= len(_A2R3_HEADER) and head[:len(_A2R3_HEADER)] == _A2R3_HEADER


def _require_utf8(payload: bytes, *, context: str) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise DiskForgeError(f"{context} must not contain a UTF-8 BOM.")
    if b"\0" in payload:
        raise DiskForgeError(f"{context} must not contain NUL bytes.")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiskForgeError(f"{context} must be valid UTF-8.") from exc


def _parse_metadata(payload: bytes) -> int:
    """Validate documented tab-delimited A2R META grammar and count rows."""
    if not payload:
        return 0
    text = _require_utf8(payload, context="A2R META")
    if not text.endswith("\n"):
        raise DiskForgeError("A2R META must terminate every row with a linefeed.")
    keys: set[str] = set()
    rows = text[:-1].split("\n")
    for row in rows:
        if row.count("\t") != 1:
            raise DiskForgeError("A2R META rows must contain exactly one tab separator.")
        key, value = row.split("\t")
        if not key or any(character in key for character in "|\t\n"):
            raise DiskForgeError("A2R META contains an invalid key.")
        if any(character in value for character in "\t\n"):
            raise DiskForgeError("A2R META value contains a prohibited control separator.")
        if key in keys:
            raise DiskForgeError(f"A2R META repeats key {key!r}.")
        keys.add(key)
    return len(rows)


def _parse_rwcp(payload: bytes, captures: list[A2rCapture]) -> None:
    """Validate one RWCP chunk while preserving all stream data as opaque bytes."""
    if len(payload) < 17:
        raise DiskForgeError("A2R RWCP chunk is too short for its header and final X marker.")
    if payload[0] != 1:
        raise DiskForgeError("Only published A2R RWCP version 1 is accepted.")
    resolution = struct.unpack_from("<I", payload, 1)[0]
    if resolution == 0:
        raise DiskForgeError("A2R RWCP resolution must be non-zero.")
    if any(payload[5:16]):
        raise DiskForgeError("A2R RWCP reserved header bytes must be zero.")

    offset = 16
    while True:
        if offset >= len(payload):
            raise DiskForgeError("A2R RWCP is missing its final X capture marker.")
        mark = payload[offset]
        if mark == 0x58:
            if offset + 1 != len(payload):
                raise DiskForgeError("A2R RWCP has trailing bytes after its final X capture marker.")
            return
        if mark != 0x43:
            raise DiskForgeError(f"A2R RWCP has invalid capture marker 0x{mark:02X} at byte {offset}.")
        if len(captures) >= _MAX_ENTRIES:
            raise DiskForgeError(f"A2R image exceeds {_MAX_ENTRIES} capture-entry safety limit.")
        if len(payload) - offset < 5:
            raise DiskForgeError("A2R RWCP ends inside a capture header.")
        capture_type = payload[offset + 1]
        if capture_type not in {1, 2, 3}:
            raise DiskForgeError("A2R RWCP capture type must be timing, bits, or xtiming.")
        location = struct.unpack_from("<H", payload, offset + 2)[0]
        index_count = payload[offset + 4]
        offset += 5
        index_end = offset + index_count * 4
        if index_end > len(payload):
            raise DiskForgeError("A2R RWCP index-signal array exceeds chunk bounds.")
        indexes = struct.unpack_from(f"<{index_count}I", payload, offset) if index_count else ()
        if any(right < left for left, right in zip(indexes, indexes[1:])):
            raise DiskForgeError("A2R RWCP index signals must be non-decreasing.")
        offset = index_end
        if len(payload) - offset < 4:
            raise DiskForgeError("A2R RWCP ends before a capture-data length.")
        data_bytes = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        if data_bytes > len(payload) - offset:
            raise DiskForgeError("A2R RWCP capture data exceeds chunk bounds.")
        offset += data_bytes
        captures.append(A2rCapture(location, capture_type, index_count, data_bytes))


def _parse_slvd(payload: bytes, tracks: list[A2rSolvedTrack], locations: set[int]) -> None:
    """Validate one SLVD chunk while preserving solved flux data as opaque bytes."""
    if len(payload) < 12:
        raise DiskForgeError("A2R SLVD chunk is too short for its header and final X marker.")
    if payload[0] != 2:
        raise DiskForgeError("Only published A2R SLVD version 2 is accepted.")
    resolution = struct.unpack_from("<I", payload, 1)[0]
    if resolution == 0:
        raise DiskForgeError("A2R SLVD resolution must be non-zero.")
    if any(payload[5:11]):
        raise DiskForgeError("A2R SLVD reserved header bytes must be zero.")

    # Published SLVD header: version (1) + resolution (4) + six reserved
    # bytes.  Unlike RWCP, it has no additional five-byte reserved extension.
    offset = 11
    while True:
        if offset >= len(payload):
            raise DiskForgeError("A2R SLVD is missing its final X track marker.")
        mark = payload[offset]
        if mark == 0x58:
            if offset + 1 != len(payload):
                raise DiskForgeError("A2R SLVD has trailing bytes after its final X track marker.")
            return
        if mark != 0x54:
            raise DiskForgeError(f"A2R SLVD has invalid track marker 0x{mark:02X} at byte {offset}.")
        if len(tracks) >= _MAX_ENTRIES:
            raise DiskForgeError(f"A2R image exceeds {_MAX_ENTRIES} solved-track safety limit.")
        if len(payload) - offset < 12:
            raise DiskForgeError("A2R SLVD ends inside a track header.")
        location = struct.unpack_from("<H", payload, offset + 1)[0]
        if location in locations:
            raise DiskForgeError(f"A2R SLVD repeats solved-track location {location}.")
        mirror_outward, mirror_inward = payload[offset + 3], payload[offset + 4]
        if any(payload[offset + 5:offset + 11]):
            raise DiskForgeError("A2R SLVD reserved track-header bytes must be zero.")
        index_count = payload[offset + 11]
        offset += 12
        index_end = offset + index_count * 4
        if index_end > len(payload):
            raise DiskForgeError("A2R SLVD index-signal array exceeds chunk bounds.")
        indexes = struct.unpack_from(f"<{index_count}I", payload, offset) if index_count else ()
        if any(right < left for left, right in zip(indexes, indexes[1:])):
            raise DiskForgeError("A2R SLVD index signals must be non-decreasing.")
        offset = index_end
        if len(payload) - offset < 4:
            raise DiskForgeError("A2R SLVD ends before a flux-data length.")
        data_bytes = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        if data_bytes > len(payload) - offset:
            raise DiskForgeError("A2R SLVD flux data exceeds chunk bounds.")
        offset += data_bytes
        locations.add(location)
        tracks.append(A2rSolvedTrack(location, index_count, data_bytes, mirror_outward, mirror_inward))


def inspect_a2r(source: Path) -> A2rInspection:
    """Validate a canonical A2R 3.x container without changing ``source``.

    The accepted contract requires the published A2R3 signature and first INFO
    chunk.  RWCP and SLVD payloads are structurally bounded; their capture
    bytes remain opaque and no disk-sector or filesystem semantics are inferred.
    """
    source = Path(source)
    if source.suffix.casefold() != ".a2r":
        raise DiskForgeError("A2R inspection requires a .a2r source file.")
    try:
        blob = source.read_bytes()
    except OSError as exc:
        raise DiskForgeError(f"Unable to read A2R image: {exc}") from exc
    if len(blob) < 53:
        raise DiskForgeError("A2R image is too short for the required header and INFO chunk.")
    if not is_a2r3_header(blob):
        raise DiskForgeError("A2R image does not have the published A2R3 signature.")

    offset = len(_A2R3_HEADER)
    chunks = raw_capture_chunks = solved_flux_chunks = metadata_entries = unknown_chunks = 0
    info_seen = meta_seen = False
    drive_type = hard_sector_count = 0
    creator = ""
    write_protected = synchronized = False
    captures: list[A2rCapture] = []
    solved_tracks: list[A2rSolvedTrack] = []
    solved_locations: set[int] = set()

    while offset < len(blob):
        if chunks >= _MAX_CHUNKS:
            raise DiskForgeError(f"A2R image exceeds {_MAX_CHUNKS} chunk safety limit.")
        if len(blob) - offset < 8:
            raise DiskForgeError("A2R image ends inside a chunk header.")
        chunk_id = blob[offset:offset + 4]
        declared_size = struct.unpack_from("<I", blob, offset + 4)[0]
        if declared_size > _MAX_CHUNK_BYTES:
            raise DiskForgeError(f"A2R chunk {chunk_id!r} exceeds the {_MAX_CHUNK_BYTES} byte safety limit.")
        data_start = offset + 8
        end = data_start + declared_size
        if end > len(blob):
            raise DiskForgeError(f"A2R chunk {chunk_id!r} exceeds source bounds.")
        payload = blob[data_start:end]
        chunks += 1

        if not info_seen:
            if chunk_id != _INFO or declared_size != 37:
                raise DiskForgeError("A2R image must begin with exactly one 37-byte INFO chunk.")
            if payload[0] != 1:
                raise DiskForgeError("Only published A2R INFO version 1 is accepted.")
            creator = _require_utf8(payload[1:33], context="A2R INFO creator").rstrip(" ")
            drive_type = payload[33]
            if drive_type not in range(1, 9):
                raise DiskForgeError("A2R INFO declares an unsupported drive type.")
            if payload[34] not in {0, 1} or payload[35] not in {0, 1}:
                raise DiskForgeError("A2R INFO write-protected and synchronized fields must be zero or one.")
            write_protected, synchronized, hard_sector_count = bool(payload[34]), bool(payload[35]), payload[36]
            info_seen = True
        elif chunk_id == _INFO:
            raise DiskForgeError("A2R image contains a duplicate INFO chunk.")
        elif chunk_id == _RWCP:
            raw_capture_chunks += 1
            _parse_rwcp(payload, captures)
        elif chunk_id == _SLVD:
            solved_flux_chunks += 1
            _parse_slvd(payload, solved_tracks, solved_locations)
        elif chunk_id == _META:
            if meta_seen:
                raise DiskForgeError("A2R image contains a duplicate META chunk.")
            metadata_entries = _parse_metadata(payload)
            meta_seen = True
        else:
            unknown_chunks += 1
        offset = end

    if not info_seen:
        raise DiskForgeError("A2R INFO chunk is missing.")
    return A2rInspection(
        source=source,
        source_bytes=len(blob),
        chunks=chunks,
        drive_type=drive_type,
        creator=creator,
        write_protected=write_protected,
        synchronized=synchronized,
        hard_sector_count=hard_sector_count,
        raw_capture_chunks=raw_capture_chunks,
        solved_flux_chunks=solved_flux_chunks,
        captures=tuple(captures),
        solved_tracks=tuple(solved_tracks),
        metadata_entries=metadata_entries,
        unknown_chunks=unknown_chunks,
    )


__all__ = ["A2rCapture", "A2rInspection", "A2rSolvedTrack", "inspect_a2r", "is_a2r3_header"]
