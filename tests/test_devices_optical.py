from __future__ import annotations

import json
from types import SimpleNamespace

from diskforge.core.devices import _linux_devices, _macos_devices, _windows_devices
from diskforge.core.models import DeviceKind


def test_linux_rom_device_is_marked_optical(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "blockdevices": [{
            "name": "sr0", "path": "/dev/sr0", "size": "734003200", "type": "rom", "rm": False,
            "mountpoints": [], "model": "Optical Drive",
        }],
    }
    monkeypatch.setattr(
        "diskforge.core.devices.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)),
    )
    devices = _linux_devices()
    assert len(devices) == 1
    assert devices[0].kind == DeviceKind.OPTICAL
    assert devices[0].identifier == "/dev/sr0"


def test_macos_optical_device_has_size_and_read_only_kind(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import plistlib

    listing = plistlib.dumps({"AllDisksAndPartitions": [{"DeviceIdentifier": "disk4", "VolumeName": "Install CD"}]})
    details = plistlib.dumps({"TotalSize": 734003200, "MediaType": "DVD-ROM", "Mounted": True, "RemovableMediaOrExternalDevice": True})
    calls = iter((SimpleNamespace(stdout=listing), SimpleNamespace(stdout=details)))
    monkeypatch.setattr("diskforge.core.devices.subprocess.run", lambda *args, **kwargs: next(calls))

    devices = _macos_devices()

    assert len(devices) == 1
    assert devices[0].kind == DeviceKind.OPTICAL
    assert devices[0].size == 734003200
    assert devices[0].removable


def test_windows_cdrom_device_is_marked_optical(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = [{"Number": 3, "FriendlyName": "USB DVD", "Size": 734003200, "BusType": "CDROM", "IsBoot": False, "IsSystem": False}]
    monkeypatch.setattr("diskforge.core.devices.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)))

    devices = _windows_devices()

    assert len(devices) == 1
    assert devices[0].kind == DeviceKind.OPTICAL
    assert devices[0].removable
