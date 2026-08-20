"""Read-only APRIDISK inspection and strict rectangular-sector RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 128
_MAGIC = b"ACT Apricot disk image\x1a\x04"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_RECORDS = 200_000
_MAX_RECORD_BYTES = 1024 * 1024
_MAX_AUXILIARY_BYTES = 64 * 1024
_MAX_RAW_BYTES = 1024 * 1024 * 1024
_SECTOR_SIZES = {128, 256, 512, 1024}
_ITEM_DELETED = 0xE31D0000
_ITEM_SECTOR = 0xE31D0001
_ITEM_COMMENT = 0xE31D0002
_ITEM_CREATOR = 0xE31D0003
_COMPRESSION_NONE = 0x9E90
_COMPRESSION_RLE = 0x3E5A


@dataclass(frozen=True)
class ApriDiskSector:
    cylinder: int
    head: int
    sector: int
    data: bytes
    compressed: bool


@dataclass(frozen=True)
class ApriDiskInspection:
    source: Path
    source_bytes: int
    sectors: tuple[ApriDiskSector, ...]
    deleted_records: int
    comment: str
    creator_data_bytes: int
    exportable: bool
    export_reason: str
    cylinders: int | None
    heads: int | None
    sectors_per_track: int | None
    bytes_per_sector: int | None
    raw_bytes: int | None


def _u16(value: bytes) -> int:
    return int.from_bytes(value, "little")


def _u32(value: bytes) -> int:
    return int.from_bytes(value, "little")


def _read_exact(handle: BinaryIO, length: int, message: str) -> bytes:
    value = handle.read(length)
    if len(value) != length:
        raise DiskForgeError(message)
    return value


def _decode_rle(payload: bytes) -> bytes:
    if len(payload) % 3:
        raise DiskForgeError("An APRIDISK RLE sector has an incomplete count-and-byte tuple.")
    decoded = bytearray()
    for index in range(0, len(payload), 3):
        count = _u16(payload[index:index + 2])
        if not count:
            raise DiskForgeError("An APRIDISK RLE sector has a zero repeat count.")
        if len(decoded) + count > max(_SECTOR_SIZES):
            raise DiskForgeError("An APRIDISK RLE sector expands beyond the maximum supported sector size.")
        decoded.extend(payload[index + 2:index + 3] * count)
    if len(decoded) not in _SECTOR_SIZES:
        raise DiskForgeError("An APRIDISK RLE sector does not decode to a supported 128/256/512/1024-byte sector.")
    return bytes(decoded)


def _geometry(sectors: tuple[ApriDiskSector, ...], deleted_records: int) -> tuple[bool, str, int | None, int | None, int | None, int | None, int | None]:
    if deleted_records:
        return False, "Deleted APRIDISK records are present; no unambiguous current sector layout is proven.", None, None, None, None, None
    if not sectors:
        return False, "No APRIDISK sector records are available.", None, None, None, None, None
    sizes = {len(item.data) for item in sectors}
    if len(sizes) != 1:
        return False, "APRIDISK sector sizes are mixed.", None, None, None, None, None
    bytes_per_sector = next(iter(sizes))
    by_key = {(item.cylinder, item.head, item.sector): item for item in sectors}
    if len(by_key) != len(sectors):
        return False, "APRIDISK C/H/S records are duplicated.", None, None, None, None, None
    cylinders = sorted({item.cylinder for item in sectors})
    heads = sorted({item.head for item in sectors})
    if cylinders != list(range(len(cylinders))) or heads != list(range(len(heads))):
        return False, "APRIDISK cylinder or head identifiers are not contiguous from zero.", None, None, None, None, None
    layouts = {tuple(sorted(item.sector for item in sectors if item.cylinder == cylinder and item.head == head))
               for cylinder in cylinders for head in heads}
    if len(layouts) != 1:
        return False, "APRIDISK tracks do not share one rectangular sector layout.", None, None, None, None, None
    sector_ids = next(iter(layouts))
    if not sector_ids or sector_ids != tuple(range(1, len(sector_ids) + 1)):
        return False, "APRIDISK sector identifiers are not contiguous from one.", None, None, None, None, None
    expected_count = len(cylinders) * len(heads) * len(sector_ids)
    if expected_count != len(sectors):
        return False, "APRIDISK C/H/S records contain holes.", None, None, None, None, None
    raw_bytes = expected_count * bytes_per_sector
    if raw_bytes > _MAX_RAW_BYTES:
        return False, "APRIDISK rectangular data exceeds the 1-GiB RAW export safety limit.", None, None, None, None, None
    return True, "All APRIDISK sectors form a normal rectangular C/H/S layout.", len(cylinders), len(heads), len(sector_ids), bytes_per_sector, raw_bytes


def inspect_apridisk(source: Path | str, token: CancellationToken | None = None) -> ApriDiskInspection:
    """Inspect an APRIDISK record stream without changing source bytes."""
    path = Path(source)
    if path.suffix.casefold() != ".dsk":
        raise DiskForgeError("APRIDISK inspection requires a .dsk filename extension.")
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("APRIDISK inspection accepts regular non-symbolic-link source files only.")
    if source_bytes < _HEADER_BYTES or source_bytes > _MAX_SOURCE_BYTES:
        raise DiskForgeError("The APRIDISK source size is outside the 128-byte to 2-GiB safety range.")
    sectors: list[ApriDiskSector] = []
    deleted_records = 0
    comment = ""
    creator_data_bytes = 0
    comments_seen = 0
    creators_seen = 0
    with path.open("rb") as handle:
        header = _read_exact(handle, _HEADER_BYTES, "The APRIDISK header is truncated.")
        if header != _MAGIC + b"\0" * (_HEADER_BYTES - len(_MAGIC)):
            raise DiskForgeError("The APRIDISK 128-byte signature header is invalid.")
        records_seen = 0
        while handle.tell() < source_bytes:
            if token:
                token.raise_if_cancelled()
            records_seen += 1
            if records_seen > _MAX_RECORDS:
                raise DiskForgeError("The APRIDISK record count exceeds the 200000-record safety limit.")
            record_header = _read_exact(handle, 16, "An APRIDISK record header is truncated.")
            item_type = _u32(record_header[0:4])
            compression = _u16(record_header[4:6])
            header_size = _u16(record_header[6:8])
            data_size = _u32(record_header[8:12])
            head, sector, cylinder = record_header[12], record_header[13], _u16(record_header[14:16])
            if item_type not in {_ITEM_DELETED, _ITEM_SECTOR, _ITEM_COMMENT, _ITEM_CREATOR}:
                raise DiskForgeError("The APRIDISK record item type is not supported.")
            if compression not in {_COMPRESSION_NONE, _COMPRESSION_RLE}:
                raise DiskForgeError("The APRIDISK record compression marker is not supported.")
            if header_size != 16:
                raise DiskForgeError("APRIDISK extended record headers are deliberately unsupported.")
            if not data_size or data_size > _MAX_RECORD_BYTES:
                raise DiskForgeError("The APRIDISK record data size is outside the supported safety range.")
            payload = _read_exact(handle, data_size, "An APRIDISK record payload is truncated.")
            if item_type == _ITEM_DELETED:
                deleted_records += 1
                continue
            if item_type in {_ITEM_COMMENT, _ITEM_CREATOR}:
                if compression != _COMPRESSION_NONE or head or sector or cylinder:
                    raise DiskForgeError("APRIDISK comment and creator records must be uncompressed with zero IDs.")
                if data_size > _MAX_AUXILIARY_BYTES:
                    raise DiskForgeError("APRIDISK comment or creator data exceeds the 64-KiB safety limit.")
                if item_type == _ITEM_COMMENT:
                    comments_seen += 1
                    if comments_seen > 1 or not payload.endswith(b"\0"):
                        raise DiskForgeError("APRIDISK requires at most one NUL-terminated comment record.")
                    comment = payload[:-1].decode("ascii", errors="replace").replace("\r", "\n")
                else:
                    creators_seen += 1
                    if creators_seen > 1:
                        raise DiskForgeError("APRIDISK requires at most one creator record.")
                    creator_data_bytes = data_size
                continue
            if head not in {0, 1} or not sector or cylinder > 255:
                raise DiskForgeError("An APRIDISK sector record has an unsupported C/H/S identifier.")
            if compression == _COMPRESSION_NONE:
                if data_size not in _SECTOR_SIZES:
                    raise DiskForgeError("An uncompressed APRIDISK sector is not 128, 256, 512, or 1024 bytes.")
                data = payload
            else:
                data = _decode_rle(payload)
            sectors.append(ApriDiskSector(cylinder, head, sector, data, compression == _COMPRESSION_RLE))
    ordered_sectors = tuple(sorted(sectors, key=lambda item: (item.cylinder, item.head, item.sector)))
    exportable, reason, cylinders, heads, sectors_per_track, bytes_per_sector, raw_bytes = _geometry(ordered_sectors, deleted_records)
    return ApriDiskInspection(
        path, source_bytes, ordered_sectors, deleted_records, comment, creator_data_bytes,
        exportable, reason, cylinders, heads, sectors_per_track, bytes_per_sector, raw_bytes,
    )


def export_apridisk_to_raw(source: Path | str, destination: Path | str,
                            token: CancellationToken | None = None) -> Path:
    """Export a strictly proven APRIDISK C/H/S rectangle to a new RAW image."""
    source_path, target = Path(source), Path(destination)
    inspection = inspect_apridisk(source_path, token)
    if not inspection.exportable:
        raise DiskForgeError(inspection.export_reason)
    if source_path.resolve() == target.resolve():
        raise DiskForgeError("The APRIDISK RAW export destination must differ from the source file.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The APRIDISK RAW export destination directory does not exist.")
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.diskforge-apridisk-", suffix=".tmp", dir=target.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output_handle:
            for item in inspection.sectors:
                if token:
                    token.raise_if_cancelled()
                output_handle.write(item.data)
        if inspection.raw_bytes is None or temporary.stat().st_size != inspection.raw_bytes:
            raise DiskForgeError("The APRIDISK RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
