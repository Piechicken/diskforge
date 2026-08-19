"""Cross-platform block-device discovery and guarded image read/write workflows."""
from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psutil

from .compare import ComparisonResult, compare_streams
from .models import DeviceInfo, DeviceKind, FileSystemType, OperationKind, ProgressCallback
from .storage import (CancellationToken, DiskForgeError, SafetyError, read_sector, stream_copy,
                      temporary_directory, validate_device_write, verify_equal, write_sector)


@dataclass(frozen=True)
class DeviceMbrInspection:
    """A non-mutating MBR snapshot bound to one discovered device identity."""

    device_identifier: str
    device_size: int
    sha256: str
    has_signature: bool


@dataclass(frozen=True)
class DeviceMbrAudit:
    """Auditable result of a guarded physical-device MBR mutation."""

    device_identifier: str
    backup: Path
    operation: str
    before_sha256: str
    after_sha256: str
    verified: bool


def _require_safe_mbr_device(device: DeviceInfo, confirmation: str | None = None) -> None:
    if device.kind not in {DeviceKind.DISK, DeviceKind.REMOVABLE}:
        raise SafetyError("MBR changes require a whole removable or physical disk, not a partition or optical medium.")
    if device.size < 512:
        raise SafetyError("The device is too small to contain an MBR sector.")
    if device.system_disk:
        raise SafetyError("Refusing to alter the operating-system disk MBR.")
    if device.mounted:
        raise SafetyError("Refusing to alter the MBR of a mounted device. Unmount it first.")
    if confirmation is not None and confirmation != "ERASE":
        raise SafetyError("Type ERASE exactly to authorize this destructive MBR operation.")


def _mbr_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_device_mbr(device: DeviceInfo) -> DeviceMbrInspection:
    """Read one device MBR without mutation and return a stable audit snapshot."""
    if device.size < 512:
        raise DiskForgeError("The device is too small to contain an MBR sector.")
    data = read_sector(device.identifier, 0)
    return DeviceMbrInspection(device.identifier, device.size, _mbr_digest(data), data[510:512] == b"\x55\xaa")


def backup_device_mbr(device: DeviceInfo, destination: Path | str) -> DeviceMbrAudit:
    """Back up one valid device MBR without changing the device."""
    _require_safe_mbr_device(device)
    before = read_sector(device.identifier, 0)
    if before[510:512] != b"\x55\xaa":
        raise DiskForgeError("MBR signature 0x55AA is missing.")
    target = Path(destination)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".partial")
    try:
        with temporary.open("wb") as handle:
            handle.write(before)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    digest = _mbr_digest(before)
    return DeviceMbrAudit(device.identifier, target, "backup", digest, digest, True)


def _validated_mbr_backup(path: Path | str) -> bytes:
    data = Path(path).read_bytes()
    if len(data) != 512 or data[510:512] != b"\x55\xaa":
        raise DiskForgeError("MBR backup must be exactly 512 bytes with signature 0x55AA.")
    return data


def _mutate_device_mbr(device: DeviceInfo, backup_destination: Path | str, confirmation: str,
                       operation: str, replacement: bytes) -> DeviceMbrAudit:
    _require_safe_mbr_device(device, confirmation)
    before = read_sector(device.identifier, 0)
    if before[510:512] != b"\x55\xaa":
        raise DiskForgeError("MBR signature 0x55AA is missing.")
    if len(replacement) != 512 or replacement[510:512] != b"\x55\xaa":
        raise DiskForgeError("Replacement MBR must be exactly 512 bytes with signature 0x55AA.")
    backup = backup_device_mbr(device, backup_destination)
    write_sector(device.identifier, 0, replacement)
    after = read_sector(device.identifier, 0)
    verified = after == replacement
    if not verified:
        raise DiskForgeError("MBR readback verification failed; the backup was preserved.")
    return DeviceMbrAudit(device.identifier, backup.backup, operation, backup.before_sha256,
                          _mbr_digest(after), verified)


def restore_device_mbr(device: DeviceInfo, backup: Path | str, backup_destination: Path | str,
                       confirmation: str) -> DeviceMbrAudit:
    """Restore a validated MBR backup only after a fresh device backup and readback."""
    return _mutate_device_mbr(device, backup_destination, confirmation, "restore", _validated_mbr_backup(backup))


def neutralize_device_mbr(device: DeviceInfo, backup_destination: Path | str,
                          confirmation: str) -> DeviceMbrAudit:
    """Clear only bootstrap bytes while preserving the selected device partition table."""
    _require_safe_mbr_device(device, confirmation)
    current = read_sector(device.identifier, 0)
    if current[510:512] != b"\x55\xaa":
        raise DiskForgeError("MBR signature 0x55AA is missing.")
    neutral = bytearray(512)
    neutral[446:] = current[446:]
    return _mutate_device_mbr(device, backup_destination, confirmation, "neutralize", bytes(neutral))


@dataclass(frozen=True)
class RemovableFormatResult:
    """Verified result of formatting an explicitly selected removable device."""

    device_identifier: str
    filesystem: FileSystemType
    label: str
    bytes_formatted: int
    verified: bool


def format_removable_fat(device: DeviceInfo, filesystem: FileSystemType, label: str,
                         confirmation: str) -> RemovableFormatResult:
    """Reformat a selected removable block device as a fresh FAT volume.

    This is deliberately a volume-level format created from a fresh, verified
    FAT image.  It is not a controller-level floppy track formatter and does
    not claim to reproduce proprietary low-level sector layouts.
    """
    if device.kind != DeviceKind.REMOVABLE or not device.removable:
        raise SafetyError("Formatting is available only for an explicitly selected removable device.")
    if device.system_disk:
        raise SafetyError("Refusing to format the operating-system disk.")
    if device.mounted:
        raise SafetyError("Refusing to format a mounted device. Unmount it first.")
    if confirmation != "FORMAT":
        raise SafetyError("Type FORMAT exactly to authorize this destructive operation.")
    if device.size <= 0 or device.size % 512:
        raise DiskForgeError("The removable device must report a positive 512-byte-aligned capacity.")
    if filesystem not in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        raise DiskForgeError("Only FAT12, FAT16 and FAT32 removable formats are supported.")

    # Build a complete filesystem off-device first.  This prevents a formatter
    # failure from leaving a partially initialized physical medium.
    from .filesystems import FatImageFilesystem, create_fat_image

    with temporary_directory("diskforge-format-") as stage:
        prepared = stage / "formatted.img"
        create_fat_image(prepared, device.size, filesystem, label)
        stream_copy(prepared, device.identifier, OperationKind.FORMAT_DEVICE,
                    limit=device.size, overwrite=True)

    filesystem_view = FatImageFilesystem(device.identifier, read_only=True)
    try:
        verified = filesystem_view.volume_label() == label.strip().upper()
    finally:
        filesystem_view.close()
    if not verified:
        raise DiskForgeError("Formatted device did not reopen with the requested FAT volume label.")
    return RemovableFormatResult(device.identifier, filesystem, label.strip().upper(), device.size, True)


def list_devices() -> list[DeviceInfo]:
    """Discover candidate disks without requiring elevated permissions.

    Platform APIs vary substantially.  This implementation presents reliable
    partition/mount information everywhere and treats unrecognised raw disks as
    unavailable rather than manufacturing a risky device identifier.
    """
    system = platform.system()
    if system == "Windows":
        return _windows_devices()
    if system == "Darwin":
        return _macos_devices()
    return _linux_devices()


def _linux_devices() -> list[DeviceInfo]:
    result: list[DeviceInfo] = []
    try:
        command = ["lsblk", "--json", "--bytes", "--output", "NAME,PATH,SIZE,TYPE,RM,MOUNTPOINTS,MODEL"]
        payload = subprocess.run(command, check=False, capture_output=True, text=True).stdout
        import json
        records = json.loads(payload).get("blockdevices", []) if payload else []
    except Exception:
        records = []
    system_mounts = {"/", "/boot", "/usr", "/var"}

    def visit(record: dict, parent_system: bool = False) -> None:
        path = record.get("path") or f"/dev/{record.get('name', '')}"
        mountpoints = tuple(item for item in record.get("mountpoints", []) if item)
        kind = (DeviceKind.OPTICAL if record.get("type") == "rom" else DeviceKind.REMOVABLE if bool(record.get("rm"))
                else DeviceKind.PARTITION if record.get("type") == "part" else DeviceKind.DISK)
        system_disk = parent_system or any(mount in system_mounts for mount in mountpoints)
        if record.get("type") in {"disk", "part", "rom"}:
            result.append(DeviceInfo(path, record.get("model") or record.get("name") or path,
                                     int(record.get("size") or 0), kind,
                                     removable=bool(record.get("rm")), mounted=bool(mountpoints),
                                     mountpoints=mountpoints, model=record.get("model") or "",
                                     system_disk=system_disk))
        for child in record.get("children", []) or []:
            visit(child, system_disk)
    for item in records:
        visit(item)

    # `ufiformat` needs a generic-SCSI node rather than the corresponding
    # `/dev/sdX` block node.  Only surface such a node when sysfs binds it to a
    # removable block device already discovered above; the formatter must still
    # run `ufiformat -i` and reject any device that does not prove to be UFI.
    by_identifier = {item.identifier: item for item in result}
    for generic in Path("/sys/class/scsi_generic").glob("sg*"):
        block_nodes = list((generic / "device" / "block").glob("*"))
        for block_node in block_nodes:
            parent = by_identifier.get(f"/dev/{block_node.name}")
            if parent is None or not parent.removable:
                continue
            identifier = f"/dev/{generic.name}"
            if identifier not in by_identifier:
                result.append(DeviceInfo(identifier, f"{parent.display_name} — generic SCSI UFI probe",
                                         parent.size, DeviceKind.REMOVABLE, removable=True,
                                         mounted=parent.mounted, mountpoints=parent.mountpoints,
                                         model=parent.model, system_disk=parent.system_disk))
                by_identifier[identifier] = result[-1]
            break
    return result


def _macos_devices() -> list[DeviceInfo]:
    result: list[DeviceInfo] = []
    try:
        import json
        payload = subprocess.run(["diskutil", "list", "-plist"], check=False,
                                 capture_output=True).stdout
        # plist parsing is safe and part of the standard library.
        import plistlib
        records = plistlib.loads(payload).get("AllDisksAndPartitions", [])
    except Exception:
        records = []
    for item in records:
        identifier = item.get("DeviceIdentifier", "")
        if not identifier:
            continue
        try:
            import plistlib
            info_payload = subprocess.run(["diskutil", "info", "-plist", f"/dev/{identifier}"], check=False,
                                          capture_output=True).stdout
            info = plistlib.loads(info_payload) if info_payload else {}
        except Exception:
            info = {}
        probe = " ".join(str(info.get(key, "")) for key in ("Content", "MediaType", "DeviceProtocol", "BusProtocol")).lower()
        is_optical = any(token in probe for token in ("cd", "dvd", "optical", "bd"))
        result.append(DeviceInfo(
            f"/dev/{identifier}", item.get("VolumeName") or info.get("VolumeName") or identifier,
            int(info.get("TotalSize") or item.get("Size") or 0), DeviceKind.OPTICAL if is_optical else DeviceKind.DISK,
            removable=bool(info.get("RemovableMediaOrExternalDevice")), mounted=bool(info.get("Mounted")),
            model=str(info.get("MediaName") or item.get("Content") or ""),
        ))
        for child in item.get("Partitions", []) or []:
            child_id = child.get("DeviceIdentifier", "")
            result.append(DeviceInfo(f"/dev/{child_id}", child.get("VolumeName") or child_id,
                                     int(child.get("Size") or 0), DeviceKind.PARTITION))
    return result


def _windows_devices() -> list[DeviceInfo]:
    result: list[DeviceInfo] = []
    try:
        command = ["powershell", "-NoProfile", "-Command",
                   "Get-Disk | Select-Object Number,FriendlyName,Size,IsBoot,IsSystem,BusType | ConvertTo-Json -Compress"]
        payload = subprocess.run(command, check=False, capture_output=True, text=True).stdout.strip()
        import json
        records = json.loads(payload) if payload else []
        if isinstance(records, dict):
            records = [records]
    except Exception:
        records = []
    for item in records:
        number = int(item.get("Number", -1))
        if number < 0:
            continue
        bus_type = str(item.get("BusType", "")).upper()
        result.append(DeviceInfo(
            identifier=f"\\\\.\\PhysicalDrive{number}",
            display_name=item.get("FriendlyName") or f"PhysicalDrive{number}",
            size=int(item.get("Size") or 0), kind=DeviceKind.OPTICAL if bus_type in {"CDROM", "CD-ROM", "OPTICAL"} else DeviceKind.DISK,
            removable=bus_type == "USB" or bus_type in {"CDROM", "CD-ROM", "OPTICAL"},
            model=item.get("FriendlyName") or "",
            system_disk=bool(item.get("IsBoot")) or bool(item.get("IsSystem")),
        ))
    return result


def read_device_to_image(device: DeviceInfo, destination: Path | str,
                         progress: ProgressCallback | None = None,
                         token: CancellationToken | None = None,
                         overwrite: bool = False) -> Path:
    """Create a byte-exact image from a selected block device."""
    if device.size <= 0:
        raise DiskForgeError("The device size is not available. Refresh device discovery with appropriate permissions.")
    stream_copy(device.identifier, destination, OperationKind.READ_DEVICE, limit=device.size,
                progress=progress, token=token, overwrite=overwrite)
    return Path(destination)


def compare_image_with_device(image: Path | str, device: DeviceInfo,
                              progress: ProgressCallback | None = None,
                              token: CancellationToken | None = None) -> ComparisonResult:
    """Compare an image with a selected device without writing either endpoint."""
    source = Path(image)
    if not source.is_file():
        raise FileNotFoundError(source)
    if device.size <= 0:
        raise DiskForgeError("The device size is not available. Refresh device discovery with appropriate permissions.")
    return compare_streams(source, device.identifier, bytes_to_compare=source.stat().st_size,
                           progress=progress, token=token)


def write_image_to_device(image: Path | str, device: DeviceInfo, confirmation_phrase: str,
                          progress: ProgressCallback | None = None,
                          token: CancellationToken | None = None,
                          verify_after_write: bool = True) -> bool:
    """Write an image only after strict capacity, mount and phrase checks."""
    source = Path(image)
    validate_device_write(device.identifier, source.stat().st_size, device.size, confirmation_phrase,
                          is_system_disk=device.system_disk, mounted=device.mounted)
    stream_copy(source, device.identifier, OperationKind.WRITE_DEVICE, limit=source.stat().st_size,
                progress=progress, token=token, overwrite=True)
    return not verify_after_write or verify_equal(source, device.identifier, source.stat().st_size,
                                                  progress=progress, token=token)
