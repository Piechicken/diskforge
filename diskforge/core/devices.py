"""Cross-platform block-device discovery and guarded image read/write workflows."""
from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Iterable

import psutil

from .compare import ComparisonResult, compare_streams
from .models import DeviceInfo, DeviceKind, OperationKind, ProgressCallback
from .storage import CancellationToken, DiskForgeError, SafetyError, stream_copy, validate_device_write, verify_equal


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
