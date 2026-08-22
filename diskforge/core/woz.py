"""Strict read-only inspection for canonical WOZ 2.0/2.1 disk containers.

This inspector accepts only signed ``WOZ2`` files with INFO version 2 or 3 and
verifies the published little-endian header, optional file CRC-32, canonical
INFO/TMAP/TRKS layout, track-map references, allocated track ranges, optional
FLUX mapping, and bounded UTF-8 META syntax.  It intentionally keeps bit and
flux payloads opaque: no sector decoding, filesystem session, RAW export,
conversion, repair, or write path is exposed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
import struct
import zlib

from .storage import CancellationToken, DiskForgeError

_SIGNATURE = b"WOZ2\xff\x0a\x0d\x0a"
_INFO = b"INFO"
_TMAP = b"TMAP"
_TRKS = b"TRKS"
_FLUX = b"FLUX"
_META = b"META"
_WRIT = b"WRIT"
_HEADER_BYTES = 12
_INFO_BYTES = 60
_TRACK_MAP_BYTES = 160
_TRACK_TABLE_BYTES = 160 * 8
_TRACK_DATA_OFFSET = 3 * 512
_BLOCK_BYTES = 512
_MAX_SOURCE_BYTES = 512 * 1024 * 1024
_MAX_CHUNKS = 65_536
_MAX_CHUNK_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class WozTrack:
    """One structurally validated opaque WOZ2 track allocation."""

    index: int
    starting_block: int
    block_count: int
    encoded_count: int
    kind: str


@dataclass(frozen=True)
class WozInspection:
    """Facts proven by a strict WOZ2 structure-only inspection."""

    source: Path
    source_bytes: int
    crc_checked: bool
    info_version: int
    disk_type: int
    disk_sides: int
    write_protected: bool
    synchronized: bool
    cleaned: bool
    creator: str
    optimal_bit_timing: int
    chunks: int
    metadata_entries: int
    unknown_chunks: int
    bit_tracks: tuple[WozTrack, ...]
    flux_tracks: tuple[WozTrack, ...]


def is_woz2_header(head: bytes) -> bool:
    """Return whether a prefix has the fixed signed WOZ2 header shape."""
    return len(head) >= _HEADER_BYTES and head[:8] == _SIGNATURE


def _require_utf8(value: bytes, *, context: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiskForgeError(f"{context} is not valid UTF-8.") from exc


def _parse_metadata(payload: bytes) -> int:
    """Validate the documented tab-delimited META grammar and count rows."""
    if not payload:
        return 0
    if payload.startswith(b"\xef\xbb\xbf"):
        raise DiskForgeError("WOZ META must not contain a UTF-8 BOM.")
    text = _require_utf8(payload, context="WOZ META")
    if not text.endswith("\n"):
        raise DiskForgeError("WOZ META must terminate every row with a linefeed.")
    seen: set[str] = set()
    entries = 0
    for row in text[:-1].split("\n"):
        if not row or "\r" in row or row.count("\t") != 1:
            raise DiskForgeError("WOZ META rows must contain exactly one tab-delimited non-empty key/value pair.")
        key, value = row.split("\t")
        if not key or key in seen or "\t" in value or "\n" in value:
            raise DiskForgeError("WOZ META contains an empty, duplicate, or malformed key/value entry.")
        seen.add(key)
        entries += 1
    return entries


def _require_info(payload: bytes) -> tuple[int, int, int, bool, bool, bool, str, int, int, int]:
    """Validate the fixed INFO v2/v3 fields and return needed facts."""
    if len(payload) != _INFO_BYTES:
        raise DiskForgeError("WOZ2 INFO chunk must contain exactly 60 bytes.")
    version, disk_type, write_protected, synchronized, cleaned = payload[:5]
    if version not in {2, 3}:
        raise DiskForgeError("WOZ2 inspector accepts only published INFO versions 2 and 3.")
    if disk_type not in {1, 2}:
        raise DiskForgeError("WOZ2 INFO declares an unsupported disk type.")
    if any(value not in {0, 1} for value in (write_protected, synchronized, cleaned)):
        raise DiskForgeError("WOZ2 INFO boolean flags must be zero or one.")
    creator_bytes = payload[5:37]
    # Creator is a fixed-width UTF-8 field with space padding.  Its actual
    # value may legitimately contain internal spaces (for example, the
    # official reference samples use a two-word producer name), so only
    # normalize trailing padding rather than trying to infer where it begins.
    creator = _require_utf8(creator_bytes, context="WOZ2 INFO creator").rstrip(" ")
    disk_sides = payload[37]
    boot_sector = payload[38]
    optimal_timing = payload[39]
    _compatible_hardware, _required_ram, largest_bit_track = struct.unpack_from("<HHH", payload, 40)
    flux_block, largest_flux_track = struct.unpack_from("<HH", payload, 46)
    valid_sides = disk_sides == 1 if disk_type == 1 else disk_sides in {1, 2}
    if not valid_sides:
        raise DiskForgeError("WOZ2 INFO disk type and side count are inconsistent.")
    if boot_sector not in {0, 1, 2, 3} or (disk_type == 2 and boot_sector):
        raise DiskForgeError("WOZ2 INFO declares an invalid boot-sector format for its disk type.")
    if not optimal_timing:
        raise DiskForgeError("WOZ2 INFO optimal bit timing must be non-zero.")
    if version == 2 and (flux_block or largest_flux_track):
        raise DiskForgeError("WOZ2 INFO version 2 must not declare WOZ 2.1 FLUX fields.")
    if version == 3 and bool(flux_block) != bool(largest_flux_track):
        raise DiskForgeError("WOZ2 INFO version 3 must declare both FLUX block fields or neither.")
    return (version, disk_type, disk_sides, bool(write_protected), bool(synchronized), bool(cleaned),
            creator, optimal_timing, largest_bit_track, flux_block, largest_flux_track)


def _ranges_for_tracks(
    table: bytes,
    *,
    source_bytes: int,
    trks_start: int,
    trks_end: int,
    references: bytes,
    kind: str,
) -> tuple[dict[int, tuple[int, int, int]], list[tuple[int, int]]]:
    """Validate one map's references and return referenced TRKS records/ranges."""
    used = sorted({entry for entry in references if entry != 0xFF})
    records: dict[int, tuple[int, int, int]] = {}
    ranges: list[tuple[int, int]] = []
    for index in used:
        start_block, block_count, encoded_count = struct.unpack_from("<HHI", table, index * 8)
        if not start_block or not block_count or not encoded_count:
            raise DiskForgeError(f"WOZ2 {kind} map references an unused TRKS entry {index}.")
        start = start_block * _BLOCK_BYTES
        stop = start + block_count * _BLOCK_BYTES
        if start < _TRACK_DATA_OFFSET or start < trks_start or stop > trks_end or stop > source_bytes:
            raise DiskForgeError(f"WOZ2 TRKS entry {index} referenced by {kind} is outside the allocated track-data area.")
        capacity = block_count * _BLOCK_BYTES
        if encoded_count > (capacity if kind == "flux" else capacity * 8):
            raise DiskForgeError(f"WOZ2 TRKS entry {index} has an encoded length beyond its allocated blocks.")
        records[index] = (start_block, block_count, encoded_count)
        ranges.append((start, stop))
    return records, ranges


def inspect_woz(source: Path | str, token: CancellationToken | None = None) -> WozInspection:
    """Inspect one canonical WOZ 2.0/2.1 container without mutating it."""
    path = Path(source)
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if path.suffix.casefold() != ".woz":
        raise DiskForgeError("WOZ2 inspection requires a .woz source file.")
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("WOZ2 inspection accepts regular non-symbolic-link source files only.")
    if not _HEADER_BYTES <= source_bytes <= _MAX_SOURCE_BYTES:
        raise DiskForgeError("WOZ2 source size is outside the 12-byte-to-512-MiB safety range.")
    try:
        blob = path.read_bytes()
    except OSError as exc:
        raise DiskForgeError(f"Unable to read WOZ2 image: {exc}") from exc
    if token:
        token.raise_if_cancelled()
    if not is_woz2_header(blob):
        raise DiskForgeError("The source does not begin with the fixed WOZ2 signature.")
    expected_crc = struct.unpack_from("<I", blob, 8)[0]
    if expected_crc and expected_crc != zlib.crc32(blob[_HEADER_BYTES:]) & 0xFFFFFFFF:
        raise DiskForgeError("WOZ2 file CRC-32 does not match the published payload CRC.")

    offset = _HEADER_BYTES
    chunks = metadata_entries = unknown_chunks = 0
    info: tuple[int, int, int, bool, bool, bool, str, int, int, int, int] | None = None
    tmap: bytes | None = None
    flux_map: bytes | None = None
    flux_chunk_offset: int | None = None
    trks_payload: bytes | None = None
    trks_start = trks_end = 0
    seen: set[bytes] = set()
    while offset < source_bytes:
        if token:
            token.raise_if_cancelled()
        if chunks >= _MAX_CHUNKS or source_bytes - offset < 8:
            raise DiskForgeError("WOZ2 source ends inside a chunk header or exceeds the chunk safety limit.")
        chunk_id = blob[offset:offset + 4]
        declared_size = struct.unpack_from("<I", blob, offset + 4)[0]
        if declared_size > _MAX_CHUNK_BYTES:
            raise DiskForgeError("WOZ2 chunk exceeds the 512-MiB per-chunk safety limit.")
        data_start = offset + 8
        end = data_start + declared_size
        if end > source_bytes:
            raise DiskForgeError(f"WOZ2 chunk {chunk_id!r} exceeds source bounds.")
        payload = blob[data_start:end]
        chunks += 1
        if chunks == 1:
            if chunk_id != _INFO:
                raise DiskForgeError("WOZ2 INFO must be the first chunk.")
            info = _require_info(payload)
        elif chunk_id in {_INFO, _TMAP, _TRKS, _FLUX, _META} and chunk_id in seen:
            raise DiskForgeError(f"WOZ2 contains a duplicate required or optional singleton chunk {chunk_id!r}.")
        elif chunk_id == _TMAP:
            if info is None or chunks != 2 or declared_size != _TRACK_MAP_BYTES:
                raise DiskForgeError("WOZ2 TMAP must directly follow INFO and contain exactly 160 bytes.")
            tmap = payload
        elif chunk_id == _TRKS:
            if tmap is None or chunks != 3 or declared_size < _TRACK_TABLE_BYTES:
                raise DiskForgeError("WOZ2 TRKS must directly follow TMAP and contain the fixed 160-entry track table.")
            if data_start != 256:
                raise DiskForgeError("WOZ2 canonical TRKS data must begin at byte 256.")
            trks_payload, trks_start, trks_end = payload, data_start, end
        elif chunk_id == _FLUX:
            if declared_size != _TRACK_MAP_BYTES:
                raise DiskForgeError("WOZ2 FLUX must contain exactly 160 map bytes.")
            flux_map = payload
            flux_chunk_offset = offset
        elif chunk_id == _META:
            metadata_entries = _parse_metadata(payload)
        elif chunk_id not in {_WRIT}:
            unknown_chunks += 1
        seen.add(chunk_id)
        offset = end

    if info is None or tmap is None or trks_payload is None:
        raise DiskForgeError("WOZ2 requires canonical INFO, TMAP, and TRKS chunks.")
    (version, disk_type, disk_sides, write_protected, synchronized, cleaned, creator,
     optimal_timing, largest_bit_track, flux_block, largest_flux_track) = info
    if bool(flux_block) != bool(flux_map):
        raise DiskForgeError("WOZ2 INFO FLUX block declaration does not match the presence of a FLUX chunk.")
    if flux_map is not None:
        if version != 3:
            raise DiskForgeError("WOZ2 FLUX requires INFO version 3.")
        if flux_chunk_offset is None or flux_chunk_offset != flux_block * _BLOCK_BYTES:
            raise DiskForgeError("WOZ2 INFO FLUX block does not point to the FLUX chunk boundary.")
        if any(bits != 0xFF and flux != 0xFF for bits, flux in zip(tmap, flux_map)):
            raise DiskForgeError("WOZ2 maps one physical location to both BITS and FLUX track data.")

    table = trks_payload[:_TRACK_TABLE_BYTES]
    bit_records, bit_ranges = _ranges_for_tracks(
        table, source_bytes=source_bytes, trks_start=trks_start, trks_end=trks_end,
        references=tmap, kind="bits",
    )
    flux_records, flux_ranges = _ranges_for_tracks(
        table, source_bytes=source_bytes, trks_start=trks_start, trks_end=trks_end,
        references=flux_map or bytes([0xFF]) * _TRACK_MAP_BYTES, kind="flux",
    )
    if set(bit_records) & set(flux_records):
        raise DiskForgeError("WOZ2 TRKS entries cannot be simultaneously referenced as BITS and FLUX data.")
    ranges = sorted(bit_ranges + flux_ranges)
    if any(next_start < current_stop for (_, current_stop), (next_start, _) in zip(ranges, ranges[1:])):
        raise DiskForgeError("WOZ2 referenced TRKS payload ranges overlap.")
    if any(table[index * 8:index * 8 + 8] != b"\0" * 8 for index in range(160)
           if index not in set(bit_records) | set(flux_records)):
        raise DiskForgeError("WOZ2 TRKS contains an unreferenced non-empty track record.")
    observed_largest_bit = max((record[1] for record in bit_records.values()), default=0)
    observed_largest_flux = max((record[1] for record in flux_records.values()), default=0)
    if largest_bit_track != observed_largest_bit:
        raise DiskForgeError("WOZ2 INFO largest bit track does not match referenced TRKS allocations.")
    if flux_map is not None and largest_flux_track != observed_largest_flux:
        raise DiskForgeError("WOZ2 INFO largest flux track does not match referenced TRKS allocations.")

    bit_tracks = tuple(WozTrack(index, *record, "bits") for index, record in sorted(bit_records.items()))
    flux_tracks = tuple(WozTrack(index, *record, "flux") for index, record in sorted(flux_records.items()))
    return WozInspection(
        path, source_bytes, bool(expected_crc), version, disk_type, disk_sides, write_protected,
        synchronized, cleaned, creator, optimal_timing, chunks, metadata_entries, unknown_chunks,
        bit_tracks, flux_tracks,
    )


__all__ = ["WozInspection", "WozTrack", "inspect_woz", "is_woz2_header"]
