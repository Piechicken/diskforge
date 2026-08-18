from __future__ import annotations

import json
from types import SimpleNamespace

from diskforge.core.devices import _linux_devices
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
