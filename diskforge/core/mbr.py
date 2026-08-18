"""Auditable MBR backup, restore and neutral reset for image files.

The reset operation intentionally writes only a neutral, non-bootable bootstrap
region while preserving the existing partition table and signature.  DiskForge
does not redistribute operating-system bootstrap code.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import SECTOR_SIZE
from .storage import DiskForgeError, read_sector, write_sector


_MBR_PARTITION_OFFSET = 446
_MBR_SIGNATURE = b"\x55\xaa"


@dataclass(frozen=True)
class MbrBackup:
    source: Path
    backup: Path
    sha256: str
    created_at: datetime


def _require_confirmation(confirmation: str) -> None:
    if confirmation != "ERASE":
        raise DiskForgeError("MBR modification requires the exact confirmation phrase ERASE.")


def read_mbr(path: Path | str) -> bytes:
    """Read exactly one MBR sector and require the conventional signature."""
    data = read_sector(path, 0)
    if len(data) != SECTOR_SIZE:
        raise DiskForgeError("MBR sector is truncated.")
    if data[510:512] != _MBR_SIGNATURE:
        raise DiskForgeError("MBR signature 0x55AA is missing.")
    return data


def backup_mbr(path: Path | str, destination: Path | str | None = None) -> MbrBackup:
    """Create an fsynced standalone 512-byte MBR backup without mutating source."""
    source = Path(path)
    data = read_mbr(source)
    backup = Path(destination) if destination else source.with_name(source.name + ".mbr.bak")
    backup.parent.mkdir(parents=True, exist_ok=True)
    temporary = backup.with_name(backup.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, backup)
    return MbrBackup(source, backup, hashlib.sha256(data).hexdigest(), datetime.now(timezone.utc))


def _read_backup(path: Path | str) -> bytes:
    data = Path(path).read_bytes()
    if len(data) != SECTOR_SIZE or data[510:512] != _MBR_SIGNATURE:
        raise DiskForgeError("MBR backup must be exactly 512 bytes with signature 0x55AA.")
    return data


def restore_mbr(target: Path | str, backup: Path | str, confirmation: str) -> MbrBackup:
    """Restore a previously saved MBR after first taking a fresh backup."""
    _require_confirmation(confirmation)
    replacement = _read_backup(backup)
    current = backup_mbr(target)
    write_sector(target, 0, replacement)
    return current


def reset_mbr_to_neutral(target: Path | str, confirmation: str) -> MbrBackup:
    """Remove bootstrap code while preserving partition entries and signature."""
    _require_confirmation(confirmation)
    current = read_mbr(target)
    backup = backup_mbr(target)
    neutral = bytearray(SECTOR_SIZE)
    neutral[_MBR_PARTITION_OFFSET:SECTOR_SIZE] = current[_MBR_PARTITION_OFFSET:SECTOR_SIZE]
    neutral[510:512] = _MBR_SIGNATURE
    write_sector(target, 0, bytes(neutral))
    return backup
