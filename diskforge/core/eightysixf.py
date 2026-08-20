"""Read-only structural validation for a deliberately narrow 86F v2.12 subset."""
from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_MAX_BITCELLS = 1_000_000


@dataclass(frozen=True)
class EightySixFTrack:
    logical_index: int
    cylinder: int
    head: int
    offset: int
    bitcells: int
    index_hole: int
    encoding: str
    bit_rate_kbps: int
    rpm: int
    data_bytes: int
    has_surface_description: bool


@dataclass(frozen=True)
class EightySixFInspection:
    source: Path
    source_bytes: int
    disk_flags: int
    sides: int
    has_surface_description: bool
    table_entries: int
    tracks: tuple[EightySixFTrack, ...]
    missing_track_count: int
    total_bitcells: int
    total_encoded_bytes: int


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("86F inspection accepts regular non-symbolic-link source files only.")
    if not (1032 <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The 86F source size is outside the 1,032-byte to 32-MiB safety range.")
    return size


def _disk_flags(content: bytes) -> tuple[int, int, bool]:
    if content[:4] != b"86BF" or content[4:6] != b"\x0c\x02":
        raise DiskForgeError("The 86F magic or v2.12 version bytes are invalid.")
    flags = int.from_bytes(content[6:8], "little")
    if flags & ~0x1FFF:
        raise DiskForgeError("The 86F disk flags contain reserved bits.")
    if flags & 0x0100 or flags & 0x0600:
        raise DiskForgeError("Zoned 86F media is outside the strict fixed-RPM inspection subset.")
    if flags & 0x0060 or not (flags & 0x0080 and flags & 0x1000):
        raise DiskForgeError("86F inspection requires total-bitcell mode without RPM shift.")
    sides = 2 if flags & 0x0008 else 1
    return flags, sides, bool(flags & 0x0001)


def _track_flags(value: int) -> tuple[str, int, int]:
    if value & ~0x00FF:
        raise DiskForgeError("An 86F track flags field contains reserved bits.")
    rpm_code = (value >> 5) & 0x07
    if rpm_code not in {0, 1}:
        raise DiskForgeError("An 86F track RPM field is outside the strict supported values.")
    encoding_code = (value >> 3) & 0x03
    encoding = ("FM", "MFM", "M2FM", "GCR")[encoding_code]
    rate_code = value & 0x07
    rates = {0: 500, 1: 300, 2: 250, 3: 1000, 5: 2000}
    if rate_code not in rates:
        raise DiskForgeError("An 86F track bit-rate code is unsupported.")
    return encoding, rates[rate_code], 360 if rpm_code else 300


def inspect_86f(source: Path | str, token: CancellationToken | None = None) -> EightySixFInspection:
    """Validate the documented fixed-RPM total-bitcell 86F v2.12 subset without mutation."""
    path = Path(source)
    if path.suffix.casefold() != ".86f":
        raise DiskForgeError("86F inspection requires a .86f filename extension.")
    source_bytes = _source_size(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    flags, sides, has_surface = _disk_flags(content)
    entries = 512 if sides == 2 else 256
    table_end = 8 + 4 * entries
    if source_bytes < table_end + 12:
        raise DiskForgeError("The 86F offset table or first track record is truncated.")
    offsets = tuple(int.from_bytes(content[8 + 4 * item:12 + 4 * item], "little") for item in range(entries))
    if offsets[0] == 0 or (sides == 2 and offsets[1] == 0):
        raise DiskForgeError("86F requires a present track 0 side 0 and, for two-sided media, track 0 side 1.")
    present = [(index, offset) for index, offset in enumerate(offsets) if offset]
    previous = table_end - 1
    for _, offset in present:
        if offset < table_end or offset <= previous or offset >= source_bytes:
            raise DiskForgeError("86F track offsets must be table-external, strictly increasing, and in range.")
        previous = offset
    tracks: list[EightySixFTrack] = []
    for number, (logical, offset) in enumerate(present):
        if token:
            token.raise_if_cancelled()
        boundary = present[number + 1][1] if number + 1 < len(present) else source_bytes
        if offset + 10 > boundary:
            raise DiskForgeError("An 86F track header is truncated or overlaps the next track.")
        track_flags = int.from_bytes(content[offset:offset + 2], "little")
        bitcells = int.from_bytes(content[offset + 2:offset + 6], "little")
        index_hole = int.from_bytes(content[offset + 6:offset + 10], "little")
        if not (16 <= bitcells <= _MAX_BITCELLS) or index_hole >= bitcells:
            raise DiskForgeError("An 86F total-bitcell count or index-hole position is outside the strict supported range.")
        encoding, rate, rpm = _track_flags(track_flags)
        data_bytes = ((bitcells + 15) // 16) * 2
        expected = 10 + data_bytes * (2 if has_surface else 1)
        if boundary - offset != expected:
            raise DiskForgeError("An 86F track range does not exactly match its total-bitcell and surface-data declaration.")
        tracks.append(EightySixFTrack(logical, logical // sides, logical % sides, offset, bitcells,
                                      index_hole, encoding, rate, rpm, data_bytes, has_surface))
    return EightySixFInspection(path, source_bytes, flags, sides, has_surface, entries, tuple(tracks),
                                entries - len(tracks), sum(item.bitcells for item in tracks),
                                sum(item.data_bytes for item in tracks))
