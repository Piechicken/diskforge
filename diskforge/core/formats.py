"""Image format discovery and conversion provider abstractions.

Raw/IMG and fixed VHD are handled natively.  Sparse and virtual-machine formats
are deliberately delegated to an explicitly configured external converter such
as qemu-img; this makes the application transparent about feature availability
on every operating system instead of pretending that unsupported files are raw.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Protocol

from .models import FileSystemType, ImageFormat, ImageInfo, OperationKind, ProgressCallback
from .storage import CancellationToken, DiskForgeError, stream_copy


VHD_FOOTER_SIZE = 512
VHD_COOKIE = b"conectix"


@dataclass(frozen=True)
class VhdFooter:
    virtual_size: int
    disk_type: int
    unique_id: uuid.UUID
    timestamp: datetime


class Converter(Protocol):
    """A provider able to inspect and convert non-native virtual disk formats."""

    @property
    def available(self) -> bool: ...

    def inspect(self, path: Path) -> dict: ...

    def convert(self, source: Path, destination: Path, destination_format: ImageFormat,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> None: ...


class QemuImgConverter:
    """Optional qemu-img bridge, never downloaded or executed implicitly."""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("qemu-img")

    @property
    def available(self) -> bool:
        return bool(self.executable)

    def _run(self, args: list[str], token: CancellationToken | None = None) -> subprocess.CompletedProcess[str]:
        if not self.executable:
            raise DiskForgeError("qemu-img is not installed; this format requires the optional converter.")
        if token and token.cancelled:
            token.raise_if_cancelled()
        result = subprocess.run([self.executable, *args], check=False, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            raise DiskForgeError(result.stderr.strip() or "qemu-img conversion failed.")
        return result

    def inspect(self, path: Path) -> dict:
        result = self._run(["info", "--output=json", str(path)])
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise DiskForgeError("qemu-img returned invalid inspection data.") from exc

    def convert(self, source: Path, destination: Path, destination_format: ImageFormat,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> None:
        qemu_format = {ImageFormat.RAW: "raw", ImageFormat.IMG: "raw", ImageFormat.ISO: "raw",
                       ImageFormat.VHD: "vpc", ImageFormat.VHDX: "vhdx", ImageFormat.VMDK: "vmdk",
                       ImageFormat.QCOW2: "qcow2"}.get(destination_format)
        if not qemu_format:
            raise DiskForgeError(f"No converter mapping for {destination_format.value}.")
        self._run(["convert", "-p", "-O", qemu_format, str(source), str(destination)], token)


def _checksum(data: bytes) -> int:
    return (~sum(data) & 0xFFFFFFFF)


def _vhd_timestamp(now: datetime) -> int:
    epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
    return max(0, int((now - epoch).total_seconds()))


def _chs_geometry(size: int) -> tuple[int, int, int]:
    total_sectors = size // 512
    if total_sectors > 65535 * 16 * 255:
        total_sectors = 65535 * 16 * 255
    if total_sectors >= 65535 * 16 * 63:
        sectors, heads = 255, 16
    else:
        sectors = 17
        cylinders_times_heads = total_sectors // sectors
        heads = (cylinders_times_heads + 1023) // 1024
        if heads < 4:
            heads = 4
        if cylinders_times_heads >= heads * 1024 or heads > 16:
            sectors, heads = 31, 16
            cylinders_times_heads = total_sectors // sectors
        if cylinders_times_heads >= heads * 1024:
            sectors, heads = 63, 16
    cylinders = total_sectors // (heads * sectors)
    return min(cylinders, 65535), heads, sectors


def create_fixed_vhd(source: Path | str, destination: Path | str,
                     progress: ProgressCallback | None = None,
                     token: CancellationToken | None = None,
                     overwrite: bool = False) -> ImageInfo:
    """Create a standards-compatible fixed VHD by appending a 512-byte footer."""
    source_path, destination_path = Path(source), Path(destination)
    result = stream_copy(source_path, destination_path, OperationKind.CONVERT,
                         progress=progress, token=token, overwrite=overwrite)
    virtual_size = result.bytes_copied
    now = datetime.now(timezone.utc)
    cylinders, heads, sectors = _chs_geometry(virtual_size)
    footer = bytearray(VHD_FOOTER_SIZE)
    footer[0:8] = VHD_COOKIE
    struct.pack_into(">I", footer, 8, 0x00000002)  # features
    struct.pack_into(">I", footer, 12, 0x00010000)  # format version
    struct.pack_into(">Q", footer, 16, 0xFFFFFFFFFFFFFFFF)  # data offset for fixed disk
    struct.pack_into(">I", footer, 24, _vhd_timestamp(now))
    footer[28:32] = b"DFOR"  # original creator application
    struct.pack_into(">I", footer, 32, 0x00010000)
    footer[36:40] = b"Wi2k"
    struct.pack_into(">Q", footer, 40, virtual_size)
    struct.pack_into(">Q", footer, 48, virtual_size)
    struct.pack_into(">HBB", footer, 56, cylinders, heads, sectors)
    struct.pack_into(">I", footer, 60, 2)  # fixed disk
    footer[68:84] = uuid.uuid4().bytes
    footer[84] = 0
    footer[64:68] = b"\0\0\0\0"
    struct.pack_into(">I", footer, 64, _checksum(footer))
    with destination_path.open("ab") as handle:
        handle.write(footer)
        handle.flush()
        os.fsync(handle.fileno())
    return inspect_image(destination_path)


def parse_vhd_footer(path: Path | str) -> VhdFooter | None:
    image = Path(path)
    if image.stat().st_size < VHD_FOOTER_SIZE:
        return None
    with image.open("rb") as handle:
        handle.seek(-VHD_FOOTER_SIZE, os.SEEK_END)
        footer = handle.read(VHD_FOOTER_SIZE)
    if footer[:8] != VHD_COOKIE:
        return None
    stored_checksum = struct.unpack_from(">I", footer, 64)[0]
    candidate = bytearray(footer)
    candidate[64:68] = b"\0\0\0\0"
    if stored_checksum != _checksum(candidate):
        raise DiskForgeError("VHD footer checksum is invalid.")
    seconds = struct.unpack_from(">I", footer, 24)[0]
    created = datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp() + seconds
    return VhdFooter(
        virtual_size=struct.unpack_from(">Q", footer, 48)[0],
        disk_type=struct.unpack_from(">I", footer, 60)[0],
        unique_id=uuid.UUID(bytes=bytes(footer[68:84])),
        timestamp=datetime.fromtimestamp(created, tz=timezone.utc),
    )


def inspect_image(path: Path | str, converter: Converter | None = None) -> ImageInfo:
    """Identify formats by signature first, extension second, and filesystem hints."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(target)
    size = target.stat().st_size
    with target.open("rb") as handle:
        head = handle.read(4096)
    detected = ImageFormat.from_path(target)
    virtual_size: Optional[int] = None
    notes: list[str] = []
    if len(head) >= 0x208 and head[0x200:0x208] == b"EFI PART":
        notes.append("GPT partition table detected")
    if len(head) >= 6 and head[1:6] == b"CD001":
        detected = ImageFormat.ISO
    if head.startswith(b"QFI\xfb"):
        detected = ImageFormat.QCOW2
    if head.startswith(b"KDMV"):
        detected = ImageFormat.VMDK
    vhd = parse_vhd_footer(target) if size >= VHD_FOOTER_SIZE else None
    if vhd:
        detected = ImageFormat.VHD
        virtual_size = vhd.virtual_size
        notes.append("Fixed VHD footer validated" if vhd.disk_type == 2 else "Dynamic VHD footer detected")
    if detected in {ImageFormat.VHDX, ImageFormat.VMDK, ImageFormat.QCOW2} and converter and converter.available:
        metadata = converter.inspect(target)
        virtual_size = int(metadata.get("virtual-size", 0)) or None
        notes.append(f"Converter reports {metadata.get('format', detected.value)}")
    fs_type = detect_filesystem(head)
    writable = os.access(target, os.W_OK) and detected not in {ImageFormat.ISO, ImageFormat.DMG}
    return ImageInfo(target, detected, size, fs_type, writable=writable,
                     virtual_size=virtual_size, notes=tuple(notes))


def detect_filesystem(head: bytes) -> FileSystemType:
    """Recognize non-invasive boot-sector and ISO signatures."""
    if len(head) >= 6 and head[1:6] == b"CD001":
        return FileSystemType.ISO9660
    if len(head) >= 90:
        marker = head[82:90].strip().upper()
        if marker.startswith(b"FAT32"):
            return FileSystemType.FAT32
    if len(head) >= 62 and (head[54:62].strip().upper().startswith(b"FAT") or head[82:90].strip().upper().startswith(b"FAT")):
        # Derive FAT12/FAT16 from BPB cluster count instead of trusting a display label.
        bytes_per_sector = int.from_bytes(head[11:13], "little")
        sectors_per_cluster = head[13]
        reserved = int.from_bytes(head[14:16], "little")
        fat_count = head[16]
        root_entries = int.from_bytes(head[17:19], "little")
        total_sectors = int.from_bytes(head[19:21], "little") or int.from_bytes(head[32:36], "little")
        fat_sectors = int.from_bytes(head[22:24], "little") or int.from_bytes(head[36:40], "little")
        if bytes_per_sector and sectors_per_cluster and total_sectors and fat_sectors:
            root_dir_sectors = (root_entries * 32 + bytes_per_sector - 1) // bytes_per_sector
            data_sectors = total_sectors - (reserved + fat_count * fat_sectors + root_dir_sectors)
            clusters = data_sectors // sectors_per_cluster
            return FileSystemType.FAT12 if clusters < 4085 else FileSystemType.FAT16
        return FileSystemType.FAT16
    if len(head) >= 11 and head[3:11] == b"NTFS    ":
        return FileSystemType.NTFS
    if len(head) >= 1082 and head[1080:1082] == b"\x53\xef":
        return FileSystemType.EXT
    return FileSystemType.UNKNOWN


def convert_image(source: Path | str, destination: Path | str, destination_format: ImageFormat,
                  converter: Converter | None = None,
                  progress: ProgressCallback | None = None,
                  token: CancellationToken | None = None,
                  overwrite: bool = False) -> ImageInfo:
    """Perform native simple conversions or route virtual formats to qemu-img."""
    source_path, destination_path = Path(source), Path(destination)
    source_info = inspect_image(source_path, converter)
    if destination_format in {ImageFormat.RAW, ImageFormat.IMG}:
        source_limit = source_info.virtual_size if source_info.image_format == ImageFormat.VHD else None
        stream_copy(source_path, destination_path, OperationKind.CONVERT, limit=source_limit,
                    progress=progress, token=token, overwrite=overwrite)
    elif destination_format == ImageFormat.VHD and source_info.image_format in {ImageFormat.RAW, ImageFormat.IMG}:
        create_fixed_vhd(source_path, destination_path, progress, token, overwrite)
    elif converter and converter.available:
        if destination_path.exists() and not overwrite:
            raise FileExistsError(destination_path)
        converter.convert(source_path, destination_path, destination_format, progress, token)
    else:
        raise DiskForgeError(
            f"Conversion to {destination_format.value} requires qemu-img. Configure it in Preferences."
        )
    return inspect_image(destination_path, converter)
