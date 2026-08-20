"""Read-only Disk Copy 4.2 (DC42) inspection and verified data-fork RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 0x54
_MAX_SOURCE_BYTES = 16 * 1024 * 1024 * 1024
_MAX_DATA_BYTES = 2 * 1024 * 1024 * 1024
_MAX_TAG_BYTES = 1024 * 1024 * 1024


@dataclass(frozen=True)
class Dc42Inspection:
    source: Path
    name: str
    data_bytes: int
    tag_bytes: int
    data_checksum: int
    tag_checksum: int
    encoding: int
    format_byte: int
    source_bytes: int


def _checksum(handle: BinaryIO, offset: int, size: int, *, skip: int,
              token: CancellationToken | None) -> int:
    if size % 2:
        raise DiskForgeError("The DC42 section has an odd byte length and cannot use its 16-bit checksum.")
    handle.seek(offset + skip)
    remaining = size - skip
    value = 0
    carry: bytes = b""
    while remaining:
        if token:
            token.raise_if_cancelled()
        block = handle.read(min(1024 * 1024, remaining))
        if not block:
            raise DiskForgeError("The DC42 section is truncated.")
        remaining -= len(block)
        block = carry + block
        if len(block) % 2:
            carry, block = block[-1:], block[:-1]
        for index in range(0, len(block), 2):
            value = (value + int.from_bytes(block[index:index + 2], "big")) & 0xFFFFFFFF
            value = ((value >> 1) | ((value & 1) << 31)) & 0xFFFFFFFF
    if carry:
        raise DiskForgeError("The DC42 checksum stream ended on an odd byte.")
    return value


def inspect_dc42(source: Path | str, token: CancellationToken | None = None) -> Dc42Inspection:
    """Validate a DC42 data fork and checksums without changing source or tags."""
    path = Path(source)
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("DC42 inspection accepts regular non-symbolic-link source files only.")
    if source_bytes < _HEADER_BYTES or source_bytes > _MAX_SOURCE_BYTES:
        raise DiskForgeError("The DC42 source size is outside the 84-byte to 16-GiB safety range.")
    with path.open("rb") as handle:
        header = handle.read(_HEADER_BYTES)
        if len(header) != _HEADER_BYTES:
            raise DiskForgeError("The DC42 header is truncated.")
        name_length = header[0]
        if name_length > 63:
            raise DiskForgeError("The DC42 Pascal image name length exceeds 63 bytes.")
        if int.from_bytes(header[0x52:0x54], "big") != 0x0100:
            raise DiskForgeError("The DC42 private word is not 0x0100.")
        data_bytes = int.from_bytes(header[0x40:0x44], "big")
        tag_bytes = int.from_bytes(header[0x44:0x48], "big")
        data_checksum = int.from_bytes(header[0x48:0x4C], "big")
        tag_checksum = int.from_bytes(header[0x4C:0x50], "big")
        if not data_bytes or data_bytes > _MAX_DATA_BYTES:
            raise DiskForgeError("The DC42 data fork size is outside the 1-byte to 2-GiB safety range.")
        if tag_bytes > _MAX_TAG_BYTES or (tag_bytes and tag_bytes < 12):
            raise DiskForgeError("The DC42 tag fork size is outside the supported safety range.")
        if _HEADER_BYTES + data_bytes + tag_bytes != source_bytes:
            raise DiskForgeError("The DC42 declared data and tag forks do not exactly match the source file length.")
        actual_data_checksum = _checksum(handle, _HEADER_BYTES, data_bytes, skip=0, token=token)
        if actual_data_checksum != data_checksum:
            raise DiskForgeError("The DC42 data fork checksum does not match the header.")
        if tag_bytes:
            actual_tag_checksum = _checksum(handle, _HEADER_BYTES + data_bytes, tag_bytes, skip=12, token=token)
            if actual_tag_checksum != tag_checksum:
                raise DiskForgeError("The DC42 tag fork checksum does not match the header.")
        elif tag_checksum:
            raise DiskForgeError("A DC42 file without tags must store a zero tag checksum.")
    return Dc42Inspection(path, header[1:1 + name_length].decode("mac_roman", errors="replace"), data_bytes,
                          tag_bytes, data_checksum, tag_checksum, header[0x50], header[0x51], source_bytes)


def export_dc42_data_to_raw(source: Path | str, destination: Path | str,
                             token: CancellationToken | None = None) -> Path:
    """Export only a fully checksum-validated DC42 data fork to a new RAW file."""
    source_path, target = Path(source), Path(destination)
    inspection = inspect_dc42(source_path, token)
    if source_path.resolve() == target.resolve():
        raise DiskForgeError("The DC42 RAW export destination must differ from the source file.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The DC42 RAW export destination directory does not exist.")
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.diskforge-dc42-", suffix=".tmp", dir=target.parent)
        temporary = Path(name)
        with source_path.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            input_handle.seek(_HEADER_BYTES)
            remaining = inspection.data_bytes
            while remaining:
                if token:
                    token.raise_if_cancelled()
                block = input_handle.read(min(1024 * 1024, remaining))
                if not block:
                    raise DiskForgeError("The DC42 data fork is truncated.")
                output_handle.write(block)
                remaining -= len(block)
        if temporary.stat().st_size != inspection.data_bytes:
            raise DiskForgeError("The DC42 RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
