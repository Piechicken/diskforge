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
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Protocol

from .models import FileSystemType, ImageFormat, ImageInfo, OperationKind, Progress, ProgressCallback
from .storage import CancellationToken, DiskForgeError, stream_copy


VHD_FOOTER_SIZE = 512
VHD_COOKIE = b"conectix"
ZIP_IMAGE_MAX_BYTES = 2 * 1024 * 1024 * 1024
ZIP_DIRECT_IMAGE_SUFFIXES = frozenset({".img", ".ima", ".bin", ".dd", ".dmf", ".iso", ".hfs"})


@dataclass(frozen=True)
class VhdFooter:
    virtual_size: int
    disk_type: int
    unique_id: uuid.UUID
    timestamp: datetime


@dataclass(frozen=True)
class EditableFixedVhdCopy:
    """An independently created fixed-VHD copy approved for FAT file edits."""

    source: Path
    destination: Path
    virtual_size: int


@dataclass(frozen=True)
class DynamicVhdExport:
    """A validated dynamic VHD produced from an independently editable raw FAT image."""

    source: Path
    destination: Path
    virtual_size: int


@dataclass(frozen=True)
class LegacyZipImage:
    """A ZIP-compatible legacy compressed image with exactly one raw payload."""

    source: Path
    destination: Path
    payload_name: str
    payload_size: int


@dataclass(frozen=True)
class ZipImagePayload:
    """A safely materialized single image payload from a read-only ZIP container."""

    source: Path
    destination: Path
    payload_name: str
    payload_size: int


@dataclass(frozen=True)
class ConverterCapabilityReport:
    """A transparent capability report for an explicitly configured converter."""

    adapter: str
    available: bool
    executable: str | None
    formats: tuple[str, ...]
    reason: str

    def as_mapping(self) -> dict[str, object]:
        return {
            "adapter": self.adapter,
            "available": self.available,
            "executable": self.executable,
            "formats": list(self.formats),
            "reason": self.reason,
        }


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
        return bool(self.executable and (Path(self.executable).is_file() or shutil.which(self.executable)))

    def capability_report(self) -> ConverterCapabilityReport:
        """Describe optional virtual-disk support without invoking conversions."""
        formats = (ImageFormat.VHDX.value, ImageFormat.VMDK.value, ImageFormat.QCOW2.value)
        if not self.available:
            location = self.executable or "qemu-img"
            return ConverterCapabilityReport(
                "qemu-img", False, self.executable, formats,
                f"Optional qemu-img converter is not installed or not executable: {location}.",
            )
        return ConverterCapabilityReport(
            "qemu-img", True, self.executable, formats,
            "Configured optional converter is available. Conversion is executed only after an explicit user action.",
        )

    def _run(self, args: list[str], token: CancellationToken | None = None) -> subprocess.CompletedProcess[str]:
        if not self.available or not self.executable:
            raise DiskForgeError("qemu-img is not installed; this format requires the optional converter.")
        if token:
            token.raise_if_cancelled()
        command = [self.executable, *args]
        process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                if token and token.cancelled:
                    process.terminate()
                    try:
                        process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                    token.raise_if_cancelled()
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        if result.returncode:
            raise DiskForgeError(result.stderr.strip() or "qemu-img conversion failed.")
        return result

    def inspect(self, path: Path) -> dict:
        result = self._run(["info", "--output=json", str(path)])
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise DiskForgeError("qemu-img returned invalid inspection data.") from exc

    def create_dynamic_vhd(self, source: Path, destination: Path,
                           token: CancellationToken | None = None) -> None:
        """Convert a raw image to a dynamic VHD using QEMU's documented VPC options."""
        self._run(["convert", "-p", "-O", "vpc", "-o", "subformat=dynamic,block_state_zero=on",
                   str(source), str(destination)], token)

    def convert(self, source: Path, destination: Path, destination_format: ImageFormat,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> None:
        qemu_format = {ImageFormat.RAW: "raw", ImageFormat.IMG: "raw", ImageFormat.IMA: "raw", ImageFormat.ISO: "raw",
                       ImageFormat.VHD: "vpc", ImageFormat.VHDX: "vhdx", ImageFormat.VMDK: "vmdk",
                       ImageFormat.QCOW2: "qcow2"}.get(destination_format)
        if not qemu_format:
            raise DiskForgeError(f"No converter mapping for {destination_format.value}.")
        self._run(["convert", "-p", "-O", qemu_format, str(source), str(destination)], token)


class Dmg2ImgConverter:
    """Optional DMG-to-raw bridge, used only after explicit user configuration.

    The adapter deliberately supports conversion into a new output file only. It
    does not mount a DMG, alter the source, or claim HFS browsing/writing support.
    """

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("dmg2img")

    @property
    def available(self) -> bool:
        return bool(self.executable and (Path(self.executable).is_file() or shutil.which(self.executable)))

    def capability_report(self) -> ConverterCapabilityReport:
        formats = ("dmg-to-raw-hfsplus",)
        if not self.available:
            location = self.executable or "dmg2img"
            return ConverterCapabilityReport(
                "dmg2img", False, self.executable, formats,
                f"Optional dmg2img adapter is not installed or not executable: {location}.",
            )
        return ConverterCapabilityReport(
            "dmg2img", True, self.executable, formats,
            "Configured optional adapter can convert a DMG into a new raw HFS+ image; no DMG write or mount operation is provided.",
        )

    def convert(self, source: Path | str, destination: Path | str, *, overwrite: bool = False,
                token: CancellationToken | None = None) -> Path:
        if not self.available or not self.executable:
            raise DiskForgeError("dmg2img is not installed; DMG conversion requires the optional adapter.")
        input_path, output_path = Path(source), Path(destination)
        if not input_path.is_file():
            raise FileNotFoundError(input_path)
        if output_path.exists() and not overwrite:
            raise FileExistsError(output_path)
        if token:
            token.raise_if_cancelled()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(f".{output_path.name}.dmg2img.partial")
        temporary.unlink(missing_ok=True)
        process = subprocess.Popen([self.executable, "-i", str(input_path), "-o", str(temporary)],
                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    if token and token.cancelled:
                        process.terminate()
                        try:
                            process.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        token.raise_if_cancelled()
            if process.returncode:
                raise DiskForgeError(stderr.strip() or "dmg2img conversion failed.")
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise DiskForgeError("dmg2img completed without creating a usable output image.")
            if output_path.exists() and overwrite:
                output_path.unlink()
            os.replace(temporary, output_path)
            return output_path
        finally:
            temporary.unlink(missing_ok=True)


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


def validate_fixed_vhd_fat(path: Path | str):
    """Validate a fixed VHD and return the FAT layout of its data region.

    The VHD footer is outside the virtual disk data.  This guard prevents callers
    from treating a dynamic VHD or malformed footer as a writable flat image.
    """
    from .fat_layouts import FatImageLayout

    target = Path(path)
    footer = parse_vhd_footer(target)
    if footer is None or footer.disk_type != 2:
        raise DiskForgeError("Only fixed VHD files with a valid footer can be edited natively.")
    if target.stat().st_size != footer.virtual_size + VHD_FOOTER_SIZE:
        raise DiskForgeError("Fixed VHD size does not match its validated footer.")
    with target.open("rb") as handle:
        boot = handle.read(4096)
    return FatImageLayout.from_boot_sector(boot, footer.virtual_size, require_geometry=False)


def create_editable_fixed_vhd_copy(source: Path | str, destination: Path | str, *, overwrite: bool = False,
                                   progress: ProgressCallback | None = None,
                                   token: CancellationToken | None = None) -> EditableFixedVhdCopy:
    """Create an independent fixed-VHD FAT copy for a subsequent editable session.

    The source remains untouched.  The copy is validated before and after the
    stream copy, so an accidental data/footer size change cannot be presented as
    a usable editable VHD.
    """
    origin, output = Path(source), Path(destination)
    if origin.resolve() == output.resolve():
        raise DiskForgeError("Choose a different output file for an editable fixed-VHD copy.")
    layout = validate_fixed_vhd_fat(origin)
    stream_copy(origin, output, OperationKind.CONVERT, progress=progress, token=token, overwrite=overwrite)
    copied = validate_fixed_vhd_fat(output)
    if copied != layout:
        raise DiskForgeError("The copied fixed VHD FAT layout did not validate consistently.")
    return EditableFixedVhdCopy(origin, output, layout.size_bytes)


def _legacy_zip_payload(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    if len(entries) != 1:
        raise DiskForgeError("A legacy compressed image must contain exactly one regular payload.")
    entry = entries[0]
    normal_name = entry.filename.replace("\\", "/")
    if not normal_name or "/" in normal_name or Path(normal_name).name != normal_name:
        raise DiskForgeError("Legacy compressed image contains an unsafe payload name.")
    if entry.flag_bits & 0x1:
        raise DiskForgeError("Encrypted legacy compressed images are not supported.")
    if entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise DiskForgeError("Legacy compressed image uses an unsupported ZIP compression method.")
    return entry


def _zip_image_payload(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    """Return the only safe directly-browsable image payload from a regular ZIP."""
    entries = archive.infolist()
    if len(entries) != 1 or entries[0].is_dir():
        raise DiskForgeError("A ZIP image container must contain exactly one regular image payload.")
    entry = entries[0]
    name = entry.filename
    if (not name or "\x00" in name or name in {".", ".."} or "/" in name or "\\" in name
            or ":" in name or Path(name).name != name):
        raise DiskForgeError("ZIP image container contains an unsafe payload name.")
    if entry.flag_bits & 0x1:
        raise DiskForgeError("Encrypted ZIP image containers are not supported.")
    if entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise DiskForgeError("ZIP image container uses an unsupported compression method.")
    if entry.file_size <= 0 or entry.file_size > ZIP_IMAGE_MAX_BYTES:
        raise DiskForgeError("ZIP image payload size is empty or exceeds the safety limit.")
    if Path(name).suffix.lower() not in ZIP_DIRECT_IMAGE_SUFFIXES:
        raise DiskForgeError("ZIP image payload does not use a supported directly-browsable image extension.")
    return entry


def extract_zip_image_payload(source: Path | str, destination: Path | str, *,
                              progress: ProgressCallback | None = None,
                              token: CancellationToken | None = None) -> ZipImagePayload:
    """Safely materialize one directly-browsable ZIP payload into a new local file."""
    origin, output = Path(source), Path(destination)
    if ImageFormat.from_path(origin) != ImageFormat.ZIP:
        raise DiskForgeError("ZIP image extraction requires a .zip container.")
    if not origin.is_file():
        raise FileNotFoundError(origin)
    if not zipfile.is_zipfile(origin):
        raise DiskForgeError("ZIP image container is not a valid ZIP archive.")
    if output.exists():
        raise FileExistsError(output)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(origin) as archive:
            entry = _zip_image_payload(archive)
            temporary.parent.mkdir(parents=True, exist_ok=True)
            transferred = 0
            with archive.open(entry, "r") as source_handle, temporary.open("wb") as target_handle:
                while block := source_handle.read(1024 * 1024):
                    if token:
                        token.raise_if_cancelled()
                    target_handle.write(block)
                    transferred += len(block)
                    if progress:
                        progress(Progress(OperationKind.OPEN, transferred, entry.file_size, f"Extracting {entry.filename}"))
            if transferred != entry.file_size or temporary.stat().st_size != entry.file_size:
                raise DiskForgeError("ZIP image payload was truncated during extraction.")
        os.replace(temporary, output)
        return ZipImagePayload(origin, output, entry.filename, entry.file_size)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def create_legacy_zip_image(source: Path | str, destination: Path | str, image_format: ImageFormat,
                            *, overwrite: bool = False) -> LegacyZipImage:
    """Create a conservative ZIP-compatible IMZ/WLZ-style single-image container."""
    origin, output = Path(source), Path(destination)
    if image_format not in {ImageFormat.IMZ, ImageFormat.WLZ}:
        raise DiskForgeError("Legacy ZIP image creation requires IMZ or WLZ output format.")
    if not origin.is_file():
        raise FileNotFoundError(origin)
    if origin.resolve() == output.resolve():
        raise DiskForgeError("Choose a different output file for a legacy compressed image.")
    if output.exists() and not overwrite:
        raise FileExistsError(output)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.write(origin, arcname=origin.name)
        with zipfile.ZipFile(temporary) as archive:
            entry = _legacy_zip_payload(archive)
            if entry.file_size != origin.stat().st_size:
                raise DiskForgeError("Legacy compressed image payload size does not match its source.")
        if output.exists() and overwrite:
            output.unlink()
        os.replace(temporary, output)
        return LegacyZipImage(origin, output, origin.name, origin.stat().st_size)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def extract_legacy_zip_image(source: Path | str, destination: Path | str) -> LegacyZipImage:
    """Extract the only safe ZIP-compatible legacy payload to a caller-owned path."""
    origin, output = Path(source), Path(destination)
    image_format = ImageFormat.from_path(origin)
    if image_format not in {ImageFormat.IMZ, ImageFormat.WLZ}:
        raise DiskForgeError("Legacy ZIP extraction requires an IMZ or WLZ image.")
    if not zipfile.is_zipfile(origin):
        raise DiskForgeError("Legacy compressed image is not a valid ZIP-compatible container.")
    if output.exists():
        raise FileExistsError(output)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(origin) as archive:
            entry = _legacy_zip_payload(archive)
            temporary.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry, "r") as source_handle, temporary.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle, length=8 * 1024 * 1024)
            if temporary.stat().st_size != entry.file_size:
                raise DiskForgeError("Legacy compressed image payload was truncated during extraction.")
        os.replace(temporary, output)
        return LegacyZipImage(origin, output, entry.filename, entry.file_size)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def create_dynamic_vhd_from_raw(source: Path | str, destination: Path | str, converter: QemuImgConverter,
                                *, overwrite: bool = False,
                                token: CancellationToken | None = None) -> DynamicVhdExport:
    """Export a FAT raw work image as a separately validated dynamic VHD.

    Dynamic VHD allocation tables cannot be edited as flat sectors.  This service
    therefore accepts a user-editable raw FAT work image and delegates only the
    final container construction to an explicitly configured qemu-img adapter.
    """
    from .fat_layouts import FatImageLayout

    origin, output = Path(source), Path(destination)
    if origin.resolve() == output.resolve():
        raise DiskForgeError("Choose a different output file for a dynamic VHD export.")
    if output.exists() and not overwrite:
        raise FileExistsError(output)
    with origin.open("rb") as handle:
        boot = handle.read(4096)
    layout = FatImageLayout.from_boot_sector(boot, origin.stat().st_size, require_geometry=False)
    if not converter.available:
        raise DiskForgeError("Dynamic VHD export requires an explicitly configured qemu-img converter.")
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        converter.create_dynamic_vhd(origin, temporary, token)
        footer = parse_vhd_footer(temporary)
        if footer is None or footer.disk_type != 3:
            raise DiskForgeError("qemu-img did not produce a validated dynamic VHD footer.")
        if footer.virtual_size != layout.size_bytes:
            raise DiskForgeError("Dynamic VHD virtual size does not match the verified FAT work image.")
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists() and overwrite:
            output.unlink()
        os.replace(temporary, output)
        return DynamicVhdExport(origin, output, footer.virtual_size)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


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
    if head.startswith((b"TD", b"td")):
        detected = ImageFormat.TD0
    vhd = parse_vhd_footer(target) if size >= VHD_FOOTER_SIZE else None
    if vhd:
        detected = ImageFormat.VHD
        virtual_size = vhd.virtual_size
        notes.append("Fixed VHD footer validated" if vhd.disk_type == 2 else "Dynamic VHD footer detected")
    if detected in {ImageFormat.VHDX, ImageFormat.VMDK, ImageFormat.QCOW2} and converter and converter.available:
        metadata = converter.inspect(target)
        virtual_size = int(metadata.get("virtual-size", 0)) or None
        notes.append(f"Converter reports {metadata.get('format', detected.value)}")
    fs_type = detect_filesystem(head, image_size=size)
    writable = os.access(target, os.W_OK) and detected not in {ImageFormat.ISO, ImageFormat.DMG, ImageFormat.ZIP, ImageFormat.TD0}
    return ImageInfo(target, detected, size, fs_type, writable=writable,
                     virtual_size=virtual_size, notes=tuple(notes))


_FAT_SECTOR_SIZES = {512, 1024, 2048, 4096}
_FAT_CLUSTER_SIZES = {1, 2, 4, 8, 16, 32, 64, 128}


def _fat_bpb_filesystem(head: bytes, image_size: int | None) -> FileSystemType | None:
    """Validate a FAT BPB without relying on the optional display-label field.

    Older DOS media commonly omits the FAT12/FAT16 string at offsets 54–61.  A
    recognised BPB must therefore stand on its own: valid jump and boot
    signature, internally consistent geometry, a recognised media descriptor,
    and—when present in the inspected prefix—the corresponding FAT reserved
    entry.  These checks avoid treating arbitrary raw data as a filesystem.
    """
    if len(head) < 512 or head[0] not in {0xEB, 0xE9} or head[510:512] != b"\x55\xaa":
        return None
    bytes_per_sector = int.from_bytes(head[11:13], "little")
    sectors_per_cluster = head[13]
    reserved = int.from_bytes(head[14:16], "little")
    fat_count = head[16]
    root_entries = int.from_bytes(head[17:19], "little")
    total_sectors = int.from_bytes(head[19:21], "little") or int.from_bytes(head[32:36], "little")
    fat_sectors = int.from_bytes(head[22:24], "little") or int.from_bytes(head[36:40], "little")
    media = head[21]
    if bytes_per_sector not in _FAT_SECTOR_SIZES or sectors_per_cluster not in _FAT_CLUSTER_SIZES:
        return None
    if reserved < 1 or fat_count not in {1, 2} or total_sectors < 1 or fat_sectors < 1:
        return None
    if media != 0xF0 and not 0xF8 <= media <= 0xFF:
        return None
    if image_size is not None:
        if image_size < bytes_per_sector or image_size % bytes_per_sector or total_sectors > image_size // bytes_per_sector:
            return None
    root_dir_sectors = (root_entries * 32 + bytes_per_sector - 1) // bytes_per_sector
    data_sectors = total_sectors - (reserved + fat_count * fat_sectors + root_dir_sectors)
    if data_sectors <= 0:
        return None
    fat_offset = reserved * bytes_per_sector
    # FAT12 stores two reserved entries in three bytes.  The standard form is
    # ``media FF FF``; pyfatfs also emits ``media 0F FF``.  Both preserve the
    # required low-nibble end marker, so accept either while retaining the
    # matching-media-byte check.
    if fat_offset + 3 <= len(head) and (head[fat_offset] != media or head[fat_offset + 1] & 0x0F != 0x0F):
        return None
    clusters = data_sectors // sectors_per_cluster
    if clusters < 1:
        return None
    if clusters < 4085:
        return FileSystemType.FAT12
    if clusters < 65525:
        return FileSystemType.FAT16
    return FileSystemType.FAT32


def detect_filesystem(head: bytes, image_size: int | None = None) -> FileSystemType:
    """Recognize non-invasive filesystem signatures and validated FAT BPBs."""
    if len(head) >= 6 and head[1:6] == b"CD001":
        return FileSystemType.ISO9660
    fat_filesystem = _fat_bpb_filesystem(head, image_size)
    if fat_filesystem is not None:
        return fat_filesystem
    if len(head) >= 11 and head[3:11] == b"NTFS    ":
        return FileSystemType.NTFS
    if len(head) >= 1082 and head[1080:1082] == b"\x53\xef":
        return FileSystemType.EXT
    # The Macintosh volume header / Master Directory Block starts at byte 1024.
    # Keep classic HFS and HFS+ distinct because Sleuth Kit accepts different
    # explicit filesystem selectors for their read-only parsers.
    if len(head) >= 1026 and head[1024:1026] == b"BD":
        return FileSystemType.HFS
    if len(head) >= 1026 and head[1024:1026] in {b"H+", b"HX"}:
        return FileSystemType.HFS_PLUS
    return FileSystemType.UNKNOWN


def convert_image(source: Path | str, destination: Path | str, destination_format: ImageFormat,
                  converter: Converter | None = None,
                  progress: ProgressCallback | None = None,
                  token: CancellationToken | None = None,
                  overwrite: bool = False) -> ImageInfo:
    """Perform native simple conversions or route virtual formats to qemu-img."""
    source_path, destination_path = Path(source), Path(destination)
    source_info = inspect_image(source_path, converter)
    if source_info.image_format == ImageFormat.ZIP:
        raise DiskForgeError("ZIP image containers are read-only; extract or browse the single payload instead of converting the container.")
    if source_info.image_format == ImageFormat.TD0:
        raise DiskForgeError("TD0 images are read-only sector containers; use strict TD0 RAW export only after inspection proves a rectangular layout.")
    if destination_format in {ImageFormat.RAW, ImageFormat.IMG, ImageFormat.IMA}:
        source_limit = source_info.virtual_size if source_info.image_format == ImageFormat.VHD else None
        stream_copy(source_path, destination_path, OperationKind.CONVERT, limit=source_limit,
                    progress=progress, token=token, overwrite=overwrite)
    elif destination_format == ImageFormat.VHD and source_info.image_format in {ImageFormat.RAW, ImageFormat.IMG, ImageFormat.IMA}:
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
