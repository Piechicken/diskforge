"""Read-only structural validation for PCE PRI bitstream containers."""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from .psi import _crc32c_nonreflected
from .storage import CancellationToken, DiskForgeError


_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_COMMENT_BYTES = 64 * 1024
_MAX_CYLINDER = 255
_MAX_BITS = 2_000_000
_MAX_CLOCK = 4_000_000
_KNOWN_CHUNKS = {b"PRI ", b"TEXT", b"TRAK", b"DATA", b"FUZZ", b"BCLK", b"WEAK", b"END "}


@dataclass(frozen=True)
class PriTrack:
    cylinder: int
    head: int
    bit_count: int
    clock_hz: int
    data_present: bool
    fuzz_events: int
    clock_events: int
    weak_events: int


@dataclass
class _TrackState:
    cylinder: int
    head: int
    bit_count: int
    clock_hz: int
    data_present: bool = False
    fuzz_events: int = 0
    clock_events: int = 0
    weak_events: int = 0


@dataclass(frozen=True)
class PriInspection:
    source: Path
    source_bytes: int
    comment_count: int
    unknown_chunk_count: int
    tracks: tuple[PriTrack, ...]
    complete_data_track_count: int
    total_bits: int
    clock_min_hz: int | None
    clock_max_hz: int | None
    fuzz_event_count: int
    clock_event_count: int
    weak_event_count: int


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("PRI inspection accepts regular non-symbolic-link source files only.")
    if not (28 <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The PRI source size is outside the 28-byte to 32-MiB safety range.")
    return size


def _read_chunk(content: bytes, position: int) -> tuple[bytes, bytes, int]:
    if position + 12 > len(content):
        raise DiskForgeError("A PRI chunk header, payload, or CRC is truncated.")
    header = content[position:position + 8]
    chunk_id = header[:4]
    size = int.from_bytes(header[4:8], "big")
    end = position + 8 + size
    if end + 4 > len(content):
        raise DiskForgeError("A PRI chunk payload or CRC is truncated.")
    payload = content[position + 8:end]
    stored_crc = int.from_bytes(content[end:end + 4], "big")
    calculated_crc = _crc32c_nonreflected(payload, _crc32c_nonreflected(header))
    if calculated_crc != stored_crc:
        raise DiskForgeError("A PRI chunk CRC is invalid.")
    return chunk_id, payload, end + 4


def _event_count(payload: bytes, track: _TrackState, label: str) -> int:
    if len(payload) % 8:
        raise DiskForgeError(f"A PRI {label} event block must contain whole eight-byte events.")
    count = len(payload) // 8
    for offset in range(0, len(payload), 8):
        position = int.from_bytes(payload[offset:offset + 4], "big")
        if position >= track.bit_count:
            raise DiskForgeError(f"A PRI {label} event position is outside its track bit range.")
    return count


def inspect_pri(source: Path | str, token: CancellationToken | None = None) -> PriInspection:
    """Validate a PRI chunk stream without decoding its bitstream or touching source bytes."""
    path = Path(source)
    if path.suffix.casefold() != ".pri":
        raise DiskForgeError("PRI inspection requires a .pri filename extension.")
    source_bytes = _source_size(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    position = 0
    chunk_id, payload, position = _read_chunk(content, position)
    if chunk_id != b"PRI " or len(payload) != 4 or int.from_bytes(payload[:2], "big") != 0:
        raise DiskForgeError("The PRI header chunk, version, or declared header shape is unsupported.")
    tracks: dict[tuple[int, int], _TrackState] = {}
    current: _TrackState | None = None
    comments = unknown = 0
    ended = False
    while position < source_bytes:
        if token:
            token.raise_if_cancelled()
        chunk_id, payload, position = _read_chunk(content, position)
        if chunk_id == b"END ":
            if payload:
                raise DiskForgeError("The PRI END chunk must not contain payload bytes.")
            ended = True
            break
        if chunk_id == b"TEXT":
            if len(payload) > _MAX_COMMENT_BYTES:
                raise DiskForgeError("A PRI TEXT chunk exceeds the 64-KiB safety limit.")
            comments += 1
            continue
        if chunk_id == b"TRAK":
            if len(payload) != 16:
                raise DiskForgeError("A PRI TRAK chunk must be exactly sixteen bytes.")
            cylinder = int.from_bytes(payload[:4], "big")
            head = int.from_bytes(payload[4:8], "big")
            bits = int.from_bytes(payload[8:12], "big")
            clock = int.from_bytes(payload[12:16], "big")
            if cylinder > _MAX_CYLINDER or head > 1 or not (1 <= bits <= _MAX_BITS) or not (1 <= clock <= _MAX_CLOCK):
                raise DiskForgeError("A PRI track coordinate, bit count, or clock is outside the strict supported range.")
            key = (cylinder, head)
            if key in tracks:
                raise DiskForgeError("PRI strict inspection rejects duplicate track coordinates.")
            current = _TrackState(cylinder, head, bits, clock)
            tracks[key] = current
            continue
        if chunk_id == b"DATA":
            if current is None or current.data_present or len(payload) != (current.bit_count + 7) // 8:
                raise DiskForgeError("A PRI DATA chunk is orphaned, duplicate, or not the exact track byte count.")
            current.data_present = True
            continue
        if chunk_id in {b"FUZZ", b"BCLK", b"WEAK"}:
            if current is None:
                raise DiskForgeError("A PRI event chunk appears before a TRAK chunk.")
            count = _event_count(payload, current, chunk_id.decode("ascii").strip())
            if chunk_id == b"FUZZ":
                current.fuzz_events += count
            elif chunk_id == b"BCLK":
                current.clock_events += count
            else:
                current.weak_events += count
            continue
        if chunk_id not in _KNOWN_CHUNKS:
            unknown += 1
    if not ended or position != source_bytes:
        raise DiskForgeError("The PRI stream must end at an exact, CRC-validated END chunk without trailing bytes.")
    result_tracks = tuple(
        PriTrack(item.cylinder, item.head, item.bit_count, item.clock_hz, item.data_present,
                 item.fuzz_events, item.clock_events, item.weak_events)
        for item in sorted(tracks.values(), key=lambda value: (value.cylinder, value.head))
    )
    return PriInspection(
        path, source_bytes, comments, unknown, result_tracks,
        sum(item.data_present for item in result_tracks), sum(item.bit_count for item in result_tracks),
        min((item.clock_hz for item in result_tracks), default=None),
        max((item.clock_hz for item in result_tracks), default=None),
        sum(item.fuzz_events for item in result_tracks), sum(item.clock_events for item in result_tracks),
        sum(item.weak_events for item in result_tracks),
    )
