from __future__ import annotations

import pytest

from diskforge.core.floppy_format import FloppyControllerFormatter
from diskforge.core.models import DeviceInfo, DeviceKind
from diskforge.core.storage import DiskForgeError


def _device(identifier: str = "/dev/fd0", **changes) -> DeviceInfo:
    values = {"identifier": identifier, "display_name": "Floppy A", "size": 1_474_560,
              "kind": DeviceKind.REMOVABLE, "removable": True, "mounted": False, "system_disk": False}
    values.update(changes)
    return DeviceInfo(**values)


def test_linux_floppy_controller_format_requires_exact_safe_device_and_verified_backend() -> None:
    calls: list[list[str]] = []
    formatter = FloppyControllerFormatter(
        platform_name="Linux", which=lambda name: "/usr/sbin/fdformat" if name == "fdformat" else None,
        runner=lambda command: (calls.append(command) or (0, "format complete", "")),
    )

    report = formatter.capability_report()
    assert report.available is True
    result = formatter.format(_device(), "FORMAT_FLOPPY")
    assert result.verified is True
    assert calls == [["fdformat", "/dev/fd0"]]

    for device, phrase in [
        (_device("/dev/sdb"), "FORMAT_FLOPPY"),
        (_device(mounted=True), "FORMAT_FLOPPY"),
        (_device(system_disk=True), "FORMAT_FLOPPY"),
        (_device(), "FORMAT"),
    ]:
        with pytest.raises(DiskForgeError):
            formatter.format(device, phrase)


def test_floppy_controller_format_reports_unavailable_without_backend() -> None:
    formatter = FloppyControllerFormatter(platform_name="Darwin", which=lambda name: None)
    assert formatter.capability_report().available is False
    with pytest.raises(DiskForgeError, match="unavailable"):
        formatter.format(_device(), "FORMAT_FLOPPY")
