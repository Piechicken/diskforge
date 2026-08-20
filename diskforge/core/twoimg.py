"""Read-only Apple II 2MG/2IMG inspection and verified data-block RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .storage import CancellationToken, DiskForgeError


_HEADER_BYTES = 64
_MAX_SOURCE_BYTES = 16 * 1024 * 1024 * 1024
_MAX_DATA_BYTES = 2 * 1024 * 1024 * 1024
_MAX_AUXILIARY_BYTES = 64 * 1024 * 1024
_COMMENT_PREVIEW_BYTES = 64 * 1024
_FORMAT_NAMES = {0: "DOS order", 1: "ProDOS order", 2: "Nibble stream"}
_ALLOWED_FLAG_BITS = 0x800001FF


@dataclass(frozen=True)
class TwoImgInspection:
    source: Path
    creator_id: str
    image_format: int
    format_name: str
    write_protected: bool
    volume_number: int | None
    data_bytes: int
    prodos_blocks: int
    comment: str
    comment_bytes: int
    creator_data_bytes: int
    source_bytes: int
    exportable: bool
    export_reason: str


def _u16(header: bytes, offset: int) -> int:
    return int.from_bytes(header[offset:offset + 2], "little")


def _u32(header: bytes, offset: int) -> int:
    return int.from_bytes(header[offset:offset + 4], "little")


def _read_preview(handle: BinaryIO, offset: int, length: int) -> str:
    if not length:
        return ""
    handle.seek(offset)
    preview = handle.read(min(length, _COMMENT_PREVIEW_BYTES))
    if len(preview) != min(length, _COMMENT_PREVIEW_BYTES):
        raise DiskForgeError("The 2MG comment block is truncated.")
    suffix = "…" if length > _COMMENT_PREVIEW_BYTES else ""
    return preview.decode("utf-8", errors="replace") + suffix


def _validate_chunk(offset: int, length: int, cursor: int, label: str) -> int:
    if not offset and not length:
        return cursor
    if not offset or not length:
        raise DiskForgeError(f"The 2MG {label} offset and length must either both be zero or both be nonzero.")
    if length > _MAX_AUXILIARY_BYTES:
        raise DiskForgeError(f"The 2MG {label} block exceeds the 64-MiB safety limit.")
    if offset != cursor:
        raise DiskForgeError(f"The 2MG {label} block must immediately follow the preceding block.")
    return cursor + length


def inspect_twoimg(source: Path | str, token: CancellationToken | None = None) -> TwoImgInspection:
    """Validate a standard 2MG/2IMG container without changing source bytes."""
    path = Path(source)
    if path.suffix.casefold() not in {".2mg", ".2img"}:
        raise DiskForgeError("2MG inspection requires a .2mg or .2img filename extension.")
    try:
        mode = path.lstat().st_mode
        source_bytes = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("2MG inspection accepts regular non-symbolic-link source files only.")
    if source_bytes < _HEADER_BYTES or source_bytes > _MAX_SOURCE_BYTES:
        raise DiskForgeError("The 2MG source size is outside the 64-byte to 16-GiB safety range.")
    if token:
        token.raise_if_cancelled()
    with path.open("rb") as handle:
        header = handle.read(_HEADER_BYTES)
        if len(header) != _HEADER_BYTES:
            raise DiskForgeError("The 2MG header is truncated.")
        if header[0:4] != b"2IMG":
            raise DiskForgeError("The 2MG signature is not 2IMG.")
        if _u16(header, 0x08) != _HEADER_BYTES:
            raise DiskForgeError("Only standard 64-byte 2MG headers are supported.")
        if _u16(header, 0x0A) != 1:
            raise DiskForgeError("Only 2MG format version 1 is supported.")
        image_format = _u32(header, 0x0C)
        if image_format not in _FORMAT_NAMES:
            raise DiskForgeError("The 2MG image data format is not DOS order, ProDOS order, or nibble stream.")
        flags = _u32(header, 0x10)
        if flags & ~_ALLOWED_FLAG_BITS:
            raise DiskForgeError("The 2MG flags use reserved bits.")
        if not flags & 0x100 and flags & 0xFF:
            raise DiskForgeError("The 2MG volume-number bits require the volume-present flag.")
        volume_number = flags & 0xFF if flags & 0x100 else None
        if volume_number is not None and volume_number > 254:
            raise DiskForgeError("The 2MG volume number exceeds the supported 0–254 range.")
        blocks = _u32(header, 0x14)
        data_offset = _u32(header, 0x18)
        data_bytes = _u32(header, 0x1C)
        comment_offset, comment_bytes = _u32(header, 0x20), _u32(header, 0x24)
        creator_offset, creator_data_bytes = _u32(header, 0x28), _u32(header, 0x2C)
        if header[0x30:0x40] != b"\0" * 16:
            raise DiskForgeError("The 2MG reserved header bytes must be zero.")
        if data_offset != _HEADER_BYTES:
            raise DiskForgeError("Only standard 2MG data blocks at offset 64 are supported.")
        if not data_bytes or data_bytes > _MAX_DATA_BYTES:
            raise DiskForgeError("The 2MG data block size is outside the 1-byte to 2-GiB safety range.")
        if image_format == 1:
            if data_bytes % 512 or not blocks or blocks * 512 != data_bytes:
                raise DiskForgeError("The 2MG ProDOS block count does not exactly match the 512-byte data block.")
        elif blocks:
            raise DiskForgeError("The 2MG ProDOS block count must be zero for DOS-order and nibble images.")
        data_end = data_offset + data_bytes
        comment_end = _validate_chunk(comment_offset, comment_bytes, data_end, "comment")
        final_end = _validate_chunk(creator_offset, creator_data_bytes, comment_end, "creator-data")
        if final_end != source_bytes:
            raise DiskForgeError("The 2MG data and optional blocks do not exactly match the source file length.")
        comment = _read_preview(handle, comment_offset, comment_bytes)
    exportable = image_format in {0, 1}
    reason = ("DOS-order or ProDOS-order data block is validated for lossless RAW export."
              if exportable else "Nibble-stream data is inspected but is not a RAW sector export.")
    return TwoImgInspection(
        path, header[4:8].decode("ascii", errors="replace"), image_format, _FORMAT_NAMES[image_format],
        bool(flags & 0x80000000), volume_number, data_bytes, blocks, comment, comment_bytes,
        creator_data_bytes, source_bytes, exportable, reason,
    )


def export_twoimg_to_raw(source: Path | str, destination: Path | str,
                         token: CancellationToken | None = None) -> Path:
    """Copy a structurally validated DOS/ProDOS 2MG data block into a new RAW file."""
    source_path, target = Path(source), Path(destination)
    inspection = inspect_twoimg(source_path, token)
    if not inspection.exportable:
        raise DiskForgeError("2MG nibble-stream data cannot be exported as a RAW sector image.")
    if source_path.resolve() == target.resolve():
        raise DiskForgeError("The 2MG RAW export destination must differ from the source file.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The 2MG RAW export destination directory does not exist.")
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.diskforge-2mg-", suffix=".tmp", dir=target.parent,
        )
        temporary = Path(temporary_name)
        with source_path.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            input_handle.seek(_HEADER_BYTES)
            remaining = inspection.data_bytes
            while remaining:
                if token:
                    token.raise_if_cancelled()
                block = input_handle.read(min(1024 * 1024, remaining))
                if not block:
                    raise DiskForgeError("The 2MG data block is truncated.")
                output_handle.write(block)
                remaining -= len(block)
        if temporary.stat().st_size != inspection.data_bytes:
            raise DiskForgeError("The 2MG RAW export produced an unexpected byte count.")
        if token:
            token.raise_if_cancelled()
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
