"""Read-only SAP inspection and strict, validated 256-byte-sector RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 66
_MAGIC = b"SYSTEME D'ARCHIVAGE PUKALL S.A.P. (c) Alexandre PUKALL Avril 1998"
_MAX_SOURCE_BYTES = 16 * 1024 * 1024
_SECTORS_PER_TRACK = 16
_SECTOR_SIZES = {0: 256, 1: 128, 2: 1024, 3: 512}
_CRC_TABLE = (0x0000, 0x1081, 0x2102, 0x3183, 0x4204, 0x5285, 0x6306, 0x7387,
              0x8408, 0x9489, 0xA50A, 0xB58B, 0xC60C, 0xD68D, 0xE70E, 0xF78F)


@dataclass(frozen=True)
class SapSector:
    cylinder: int
    head: int
    sector: int
    sector_size: int
    mode: str
    protection: int
    crc_valid: bool
    data: bytes


@dataclass(frozen=True)
class SapInspection:
    source: Path
    source_bytes: int
    disk_type: str
    tracks_per_side: int
    heads: int
    sectors: tuple[SapSector, ...]
    crc_error_count: int
    protected_sector_count: int
    exportable: bool
    export_reason: str
    raw_bytes: int | None


def _sap_crc(payload: bytes) -> int:
    crc = 0xFFFF
    for byte in payload:
        index = (crc ^ byte) & 0x0F
        crc = ((crc >> 4) & 0x0FFF) ^ _CRC_TABLE[index]
        index = (crc ^ (byte >> 4)) & 0x0F
        crc = ((crc >> 4) & 0x0FFF) ^ _CRC_TABLE[index]
    return crc


def _source_size(path: Path) -> int:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("SAP inspection accepts regular non-symbolic-link source files only.")
    if not (_HEADER_BYTES <= size <= _MAX_SOURCE_BYTES):
        raise DiskForgeError("The SAP source size is outside the 66-byte to 16-MiB safety range.")
    return size


def _export_geometry(sectors: tuple[SapSector, ...], tracks_per_side: int, heads: int) -> tuple[bool, str, int | None]:
    if any(item.sector_size != 256 or item.mode != "MFM" for item in sectors):
        return False, "SAP RAW export requires only regular 256-byte MFM sector records.", None
    if any(item.protection for item in sectors):
        return False, "SAP RAW export rejects protected sector records.", None
    if any(not item.crc_valid for item in sectors):
        return False, "SAP RAW export rejects sector records with CRC errors.", None
    expected_count = tracks_per_side * heads * _SECTORS_PER_TRACK
    if len(sectors) != expected_count:
        return False, "SAP sector record count does not match the declared geometry.", None
    for head in range(heads):
        for cylinder in range(tracks_per_side):
            current = [item for item in sectors if item.head == head and item.cylinder == cylinder]
            if len(current) != _SECTORS_PER_TRACK or {item.sector for item in current} != set(range(1, 17)):
                return False, "SAP sectors do not form complete unique 1-to-16 tracks.", None
    return True, "All SAP sectors are unprotected, CRC-valid 256-byte MFM records in complete tracks.", expected_count * 256


def inspect_sap(source: Path | str, token: CancellationToken | None = None) -> SapInspection:
    """Validate the full SAP record stream without changing the source image."""
    path = Path(source)
    if path.suffix.casefold() != ".sap":
        raise DiskForgeError("SAP inspection requires a .sap filename extension.")
    source_bytes = _source_size(path)
    content = path.read_bytes()
    if token:
        token.raise_if_cancelled()
    header = content[:_HEADER_BYTES]
    disk_code = header[0]
    if disk_code & 0x7C or header[1:] != _MAGIC:
        raise DiskForgeError("The SAP disk type or 66-byte Pukall signature header is invalid.")
    tracks_per_side = 40 if disk_code & 0x02 else 80
    heads = 2 if disk_code & 0x80 else 1
    density = "double density" if disk_code & 0x01 else "single density"
    disk_type = f"{tracks_per_side}-track {density}, {'double-sided' if heads == 2 else 'single-sided'}"
    position = _HEADER_BYTES
    sectors: list[SapSector] = []
    for logical_track in range(tracks_per_side * heads):
        if token:
            token.raise_if_cancelled()
        head = logical_track // tracks_per_side
        cylinder = logical_track % tracks_per_side
        for _ in range(_SECTORS_PER_TRACK):
            if position + 4 > source_bytes:
                raise DiskForgeError("An SAP sector record header is truncated.")
            record_header = content[position:position + 4]
            position += 4
            size_code, protection, declared_cylinder, sector_id = record_header
            if size_code not in _SECTOR_SIZES or not sector_id:
                raise DiskForgeError("An SAP sector record has an unsupported size/mode or sector identifier.")
            sector_size = _SECTOR_SIZES[size_code]
            if position + sector_size + 2 > source_bytes:
                raise DiskForgeError("An SAP sector data record or its CRC is truncated.")
            stored_data = content[position:position + sector_size]
            position += sector_size
            stored_crc = int.from_bytes(content[position:position + 2], "big")
            position += 2
            data = bytes(byte ^ 0xB3 for byte in stored_data)
            mode = "FM" if size_code == 1 else "MFM"
            sectors.append(SapSector(declared_cylinder, head, sector_id, sector_size, mode, protection,
                                     _sap_crc(record_header + data) == stored_crc, data))
    if position != source_bytes:
        raise DiskForgeError("The SAP file has trailing bytes after its declared complete sector stream.")
    result_sectors = tuple(sectors)
    exportable, reason, raw_bytes = _export_geometry(result_sectors, tracks_per_side, heads)
    return SapInspection(
        path, source_bytes, disk_type, tracks_per_side, heads, result_sectors,
        sum(not item.crc_valid for item in result_sectors), sum(bool(item.protection) for item in result_sectors),
        exportable, reason, raw_bytes,
    )


def export_sap_to_raw(source: Path | str, destination: Path | str,
                      token: CancellationToken | None = None) -> Path:
    """Export a fully proven regular SAP layout to a separately created RAW file."""
    source_path, target = Path(source), Path(destination)
    inspection = inspect_sap(source_path, token)
    if not inspection.exportable:
        raise DiskForgeError(inspection.export_reason)
    if source_path.resolve() == target.resolve():
        raise DiskForgeError("The SAP RAW export destination must differ from the source file.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The SAP RAW export destination directory does not exist.")
    ordered = sorted(inspection.sectors, key=lambda item: (item.head, item.cylinder, item.sector))
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.diskforge-sap-", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output_handle:
            for item in ordered:
                if token:
                    token.raise_if_cancelled()
                output_handle.write(item.data)
        if inspection.raw_bytes is None or temporary.stat().st_size != inspection.raw_bytes:
            raise DiskForgeError("The SAP RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
