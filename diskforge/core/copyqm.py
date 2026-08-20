"""Read-only CopyQM inspection and checksum-verified RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 133
_MAGIC = b"CQ\x14"
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_MAX_COMMENT_BYTES = 64 * 1024
_MAX_RAW_BYTES = 16 * 1024 * 1024
_MAX_ZERO_RUNS = 4096
_ALLOWED_SECTOR_SIZES = {128, 256, 512, 1024}


def _make_crc_table() -> tuple[int, ...]:
    table: list[int] = []
    for value in range(256):
        remainder = value
        for _ in range(8):
            remainder = (remainder >> 1) ^ (0xEDB88320 if remainder & 1 else 0)
        table.append(remainder & 0xFFFFFFFF)
    return tuple(table)


_CRC32R_TABLE = _make_crc_table()


@dataclass(frozen=True)
class CopyQmInspection:
    source: Path
    source_bytes: int
    comment: str
    media_description: str
    volume_label: str
    sector_size: int
    sectors_per_track: int
    heads: int
    tracks: int
    total_sectors: int
    density: str
    data_crc: int
    calculated_crc: int
    raw_bytes: int


def _u16(value: bytes) -> int:
    return int.from_bytes(value, "little")


def _u32(value: bytes) -> int:
    return int.from_bytes(value, "little")


def _masked_crc32(data: bytes, token: CancellationToken | None = None) -> int:
    crc = 0
    for offset, byte in enumerate(data):
        if token and offset % 65536 == 0:
            token.raise_if_cancelled()
        crc = _CRC32R_TABLE[(byte ^ crc) & 0x3F] ^ (crc >> 8)
    return crc & 0xFFFFFFFF


def _decode_rle(payload: bytes, expected_size: int, token: CancellationToken | None = None) -> bytes:
    output = bytearray()
    position = 0
    zero_runs = 0
    while len(output) < expected_size:
        if token:
            token.raise_if_cancelled()
        if position + 2 > len(payload):
            raise DiskForgeError("CopyQM RLE data ends before the required RAW byte count.")
        length = int.from_bytes(payload[position:position + 2], "little", signed=True)
        position += 2
        if length == 0:
            zero_runs += 1
            if zero_runs > _MAX_ZERO_RUNS:
                raise DiskForgeError("CopyQM RLE data contains too many zero-length runs.")
            continue
        zero_runs = 0
        if length < 0:
            count = -length
            if position >= len(payload):
                raise DiskForgeError("A CopyQM repeated RLE run has no repeated byte.")
            data = payload[position:position + 1] * count
            position += 1
        else:
            count = length
            if position + count > len(payload):
                raise DiskForgeError("A CopyQM literal RLE run is truncated.")
            data = payload[position:position + count]
            position += count
        if len(output) + count > expected_size:
            raise DiskForgeError("CopyQM RLE data expands beyond the declared fixed geometry.")
        output.extend(data)
    if position != len(payload):
        raise DiskForgeError("CopyQM RLE data has trailing bytes after the declared fixed geometry.")
    return bytes(output)


def _text(value: bytes) -> str:
    return value.rstrip(b"\0 ").decode("latin-1", errors="replace")


def _validate_source(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("CopyQM inspection accepts regular non-symbolic-link source files only.")
    if not (_HEADER_BYTES <= source_bytes <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The CopyQM source size is outside the 133-byte to 64-MiB safety range.")
    return source_bytes


def inspect_copyqm(source: Path | str, token: CancellationToken | None = None) -> CopyQmInspection:
    """Validate a compact CopyQM DOS image completely without source mutation."""
    path = Path(source)
    if path.suffix.casefold() != ".qm":
        raise DiskForgeError("CopyQM inspection requires a .qm filename extension.")
    source_bytes = _validate_source(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    header = content[:_HEADER_BYTES]
    if header[:3] != _MAGIC or sum(header) & 0xFF:
        raise DiskForgeError("The CopyQM 133-byte signature header or checksum is invalid.")
    sector_size = _u16(header[0x03:0x05])
    total_sectors = _u16(header[0x0B:0x0D])
    sectors_per_track = _u16(header[0x10:0x12])
    heads = _u16(header[0x12:0x14])
    hidden_sectors = _u32(header[0x14:0x18])
    extended_total = _u32(header[0x18:0x1C])
    image_type = header[0x58]
    density_value = header[0x59]
    used_tracks, tracks = header[0x5A], header[0x5B]
    expected_crc = _u32(header[0x5C:0x60])
    comment_bytes = _u16(header[0x6F:0x71])
    first_sector_minus_one, interleave, skew = header[0x71], header[0x74], header[0x75]
    if image_type != 0:
        raise DiskForgeError("Only standard DOS CopyQM images are supported; blind and HFS image types are rejected.")
    if density_value not in {0, 1, 2}:
        raise DiskForgeError("The CopyQM density marker is invalid.")
    if sector_size not in _ALLOWED_SECTOR_SIZES or not (1 <= sectors_per_track <= 63) or heads not in {1, 2}:
        raise DiskForgeError("The CopyQM fixed sector geometry is outside the supported range.")
    if not (1 <= tracks <= 84) or used_tracks != tracks:
        raise DiskForgeError("CopyQM partial-track images are deliberately unsupported.")
    if hidden_sectors or extended_total:
        raise DiskForgeError("CopyQM extended or hidden-sector layouts are deliberately unsupported.")
    expected_sectors = tracks * heads * sectors_per_track
    if total_sectors != expected_sectors:
        raise DiskForgeError("CopyQM total sectors do not match its fixed tracks, heads, and sectors-per-track geometry.")
    if first_sector_minus_one or interleave not in {0, 1} or skew:
        raise DiskForgeError("CopyQM sector base, interleave, or skew is outside the safe RAW export subset.")
    raw_bytes = expected_sectors * sector_size
    if raw_bytes > _MAX_RAW_BYTES:
        raise DiskForgeError("CopyQM fixed geometry exceeds the 16-MiB RAW export safety limit.")
    if comment_bytes > _MAX_COMMENT_BYTES or _HEADER_BYTES + comment_bytes >= source_bytes:
        raise DiskForgeError("CopyQM comment length is outside the safe file-layout range.")
    comment_payload = content[_HEADER_BYTES:_HEADER_BYTES + comment_bytes]
    decoded = _decode_rle(content[_HEADER_BYTES + comment_bytes:], raw_bytes, token)
    calculated_crc = _masked_crc32(decoded, token)
    if not expected_crc or expected_crc != calculated_crc:
        raise DiskForgeError("The CopyQM data CRC is absent or does not match the fully decoded data.")
    density = {0: "DD", 1: "HD", 2: "ED"}[density_value]
    return CopyQmInspection(
        path, source_bytes, _text(comment_payload), _text(header[0x1C:0x58]), _text(header[0x60:0x6B]),
        sector_size, sectors_per_track, heads, tracks, total_sectors, density, expected_crc, calculated_crc, raw_bytes,
    )


def export_copyqm_to_raw(source: Path | str, destination: Path | str,
                         token: CancellationToken | None = None) -> Path:
    """Export a fully validated CopyQM stream to a separately created RAW file."""
    source_path, target = Path(source), Path(destination)
    inspection = inspect_copyqm(source_path, token)
    if source_path.resolve() == target.resolve():
        raise DiskForgeError("The CopyQM RAW export destination must differ from the source file.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The CopyQM RAW export destination directory does not exist.")
    content = source_path.read_bytes()
    comment_bytes = _u16(content[0x6F:0x71])
    raw = _decode_rle(content[_HEADER_BYTES + comment_bytes:], inspection.raw_bytes, token)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.diskforge-copyqm-", suffix=".tmp", dir=target.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output_handle:
            output_handle.write(raw)
        if temporary.stat().st_size != inspection.raw_bytes:
            raise DiskForgeError("The CopyQM RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
