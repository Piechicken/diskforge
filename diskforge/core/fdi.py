"""Strict read-only structural inspection for signed FDI v2.0 containers.

FDI tracks can hold multiple representation levels.  This module deliberately
validates only documented container structure and never tries to decode,
flatten, repair, or write track content.
"""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError

_MAGIC = b"Formatted Disk Image file\r\n"
_HEADER_BASE_BYTES = 512
_TRACK_DIRECTORY_OFFSET = 152
_FIRST_DIRECTORY_CAPACITY = (_HEADER_BASE_BYTES - _TRACK_DIRECTORY_OFFSET) // 2
_EXTRA_DIRECTORY_CAPACITY = _HEADER_BASE_BYTES // 2
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_MAX_TRACKS = 4096


@dataclass(frozen=True)
class FdiTrack:
    logical_index: int
    cylinder: int
    head: int
    type_code: int
    category: str
    offset_bytes: int
    declared_bytes: int


@dataclass(frozen=True)
class FdiInspection:
    source: Path
    source_bytes: int
    header_bytes: int
    cylinders: int
    heads: int
    media_type: int
    rotation_rpm: int
    write_protected: bool
    index_synchronized: bool
    disk_tpi: int
    head_tpi: int
    creator: str
    comment: str
    blank_track_count: int
    declared_track_bytes: int
    tracks: tuple[FdiTrack, ...]


def _read_text(value: bytes) -> str:
    return value.rstrip(b"\0 ").decode("latin-1", errors="replace")


def _header_bytes(track_count: int) -> int:
    if track_count <= _FIRST_DIRECTORY_CAPACITY:
        return _HEADER_BASE_BYTES
    extra = track_count - _FIRST_DIRECTORY_CAPACITY
    blocks = (extra + _EXTRA_DIRECTORY_CAPACITY - 1) // _EXTRA_DIRECTORY_CAPACITY
    return _HEADER_BASE_BYTES * (1 + blocks)


def _track_category_and_bytes(type_code: int, size_field: int) -> tuple[str, int]:
    """Return an accepted category and exact reserved payload byte count."""
    if type_code == 0:
        if size_field:
            raise DiskForgeError("A blank FDI track must declare zero data bytes.")
        return "blank", 0
    if 1 <= type_code <= 0x0E:
        # FDI's documented Amiga DD special case uses 512-byte units; other
        # documented high-level types use 256-byte units.
        return "standard", size_field * (512 if type_code == 1 else 256)
    if 0x0F <= type_code <= 0x7F:
        raise DiskForgeError("The FDI track type is reserved or unsupported.")
    if 0x80 <= type_code <= 0xBF:
        units = ((type_code & 0x3F) << 8) | size_field
        if not units:
            raise DiskForgeError("An FDI pulse-index track must declare data bytes.")
        return "pulse-index", units * 256
    family = type_code & 0xF0
    rate = type_code & 0x0F
    if family in {0xC0, 0xD0}:
        if rate not in {*range(12), 15}:
            raise DiskForgeError("The FDI FM/GCR track bit-rate code is reserved.")
        if not size_field:
            raise DiskForgeError("An FDI raw FM/GCR track must declare data bytes.")
        return ("raw-decoded" if family == 0xC0 else "raw-data"), size_field * 256
    if family in {0xE0, 0xF0}:
        if rate not in {*range(6), 15}:
            raise DiskForgeError("The FDI MFM track bit-rate code is reserved.")
        if not size_field:
            raise DiskForgeError("An FDI raw MFM track must declare data bytes.")
        return ("raw-decoded" if family == 0xE0 else "raw-data"), size_field * 256
    raise DiskForgeError("The FDI track type is unsupported.")


def _validate_header(content: bytes, path: Path) -> tuple[int, int, int, int, int, int, int]:
    if content[:len(_MAGIC)] != _MAGIC:
        raise DiskForgeError("The FDI file signature is invalid.")
    if content[57:59] != b"\r\n" or content[139] != 0x1A:
        raise DiskForgeError("The FDI creator/comment header fields are invalid.")
    if content[140:142] != b"\x00\x02":
        raise DiskForgeError("Only big-endian FDI version 2.0 is supported.")
    last_track = int.from_bytes(content[142:144], "big")
    last_head = content[144]
    if last_head not in {0, 1}:
        raise DiskForgeError("The FDI v2.0 head count is outside the strict inspection subset.")
    track_count = (last_track + 1) * (last_head + 1)
    if not (1 <= track_count <= _MAX_TRACKS):
        raise DiskForgeError("The FDI v2.0 track directory is outside the strict inspection range.")
    media_type = content[145]
    if media_type > 3:
        raise DiskForgeError("The FDI v2.0 media type is invalid.")
    rotation_rpm = content[146] + 128
    if not (128 <= rotation_rpm <= 600):
        raise DiskForgeError("The FDI v2.0 rotation speed is outside the strict inspection range.")
    flags = content[147]
    if flags & ~0x03:
        raise DiskForgeError("The FDI v2.0 flags contain reserved bits.")
    disk_tpi, head_tpi = content[148], content[149]
    if disk_tpi > 5 or head_tpi > 5:
        raise DiskForgeError("The FDI v2.0 TPI fields are invalid.")
    header_bytes = _header_bytes(track_count)
    if len(content) < header_bytes:
        raise DiskForgeError("The FDI source ends inside its track directory header.")
    if path.suffix.casefold() != ".fdi":
        raise DiskForgeError("FDI inspection requires a .fdi filename extension.")
    return track_count, last_track + 1, last_head + 1, media_type, rotation_rpm, flags, header_bytes


def inspect_fdi(source: Path | str, token: CancellationToken | None = None) -> FdiInspection:
    """Validate documented FDI v2.0 structure without decoding or mutation."""
    path = Path(source)
    if path.suffix.casefold() != ".fdi":
        raise DiskForgeError("FDI inspection requires a .fdi filename extension.")
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("FDI inspection accepts regular non-symbolic-link source files only.")
    if not (_HEADER_BASE_BYTES <= source_bytes <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The FDI source size is outside the v2.0 safety range.")
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    track_count, cylinders, heads, media_type, rotation_rpm, flags, header_bytes = _validate_header(content, path)
    tracks: list[FdiTrack] = []
    declared_track_bytes = 0
    blank_track_count = 0
    data_offset = header_bytes
    for logical_index in range(track_count):
        if token:
            token.raise_if_cancelled()
        descriptor_offset = _TRACK_DIRECTORY_OFFSET + logical_index * 2
        type_code, size_field = content[descriptor_offset:descriptor_offset + 2]
        category, declared_bytes = _track_category_and_bytes(type_code, size_field)
        if data_offset + declared_bytes > source_bytes:
            raise DiskForgeError("An FDI track payload exceeds the source file bounds.")
        if category == "blank":
            blank_track_count += 1
        tracks.append(FdiTrack(
            logical_index=logical_index,
            cylinder=logical_index // heads,
            head=logical_index % heads,
            type_code=type_code,
            category=category,
            offset_bytes=data_offset,
            declared_bytes=declared_bytes,
        ))
        data_offset += declared_bytes
        declared_track_bytes += declared_bytes
    # Unused directory bytes in the allocated header are reserved and must be
    # zero.  This validates padding without interpreting track content.
    directory_end = _TRACK_DIRECTORY_OFFSET + track_count * 2
    if content[directory_end:header_bytes] != b"\0" * (header_bytes - directory_end):
        raise DiskForgeError("The FDI track-directory padding contains non-zero reserved bytes.")
    if data_offset != source_bytes:
        raise DiskForgeError("The FDI source has trailing bytes beyond declared track payloads.")
    return FdiInspection(
        source=path,
        source_bytes=source_bytes,
        header_bytes=header_bytes,
        cylinders=cylinders,
        heads=heads,
        media_type=media_type,
        rotation_rpm=rotation_rpm,
        write_protected=bool(flags & 0x01),
        index_synchronized=bool(flags & 0x02),
        disk_tpi=content[148],
        head_tpi=content[149],
        creator=_read_text(content[27:57]),
        comment=_read_text(content[59:139]),
        blank_track_count=blank_track_count,
        declared_track_bytes=declared_track_bytes,
        tracks=tuple(tracks),
    )
