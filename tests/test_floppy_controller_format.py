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


def test_linux_ufi_usb_floppy_requires_discovery_explicit_capacity_and_verification() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str]) -> tuple[int, str, str]:
        calls.append(command)
        if command[1] == "-i":
            return 0, "UFI floppy supported capacities: 737280 1474560\n", ""
        return 0, "verification complete", ""

    formatter = FloppyControllerFormatter(
        platform_name="Linux", which=lambda name: "/usr/sbin/ufiformat" if name == "ufiformat" else None,
        runner=runner,
    )
    device = _device("/dev/sg4")
    assert formatter.usb_capability_report().available is True
    assert formatter.discover_usb(device).supported_capacities == (737280, 1474560)
    result = formatter.format_usb(device, 1474560, "FORMAT_FLOPPY")
    assert result.backend == "ufiformat"
    assert result.verified is True
    assert calls == [
        ["ufiformat", "-i", "/dev/sg4"],
        ["ufiformat", "-i", "/dev/sg4"],
        ["ufiformat", "-f", "1474560", "-V", "/dev/sg4"],
    ]


def test_ufi_usb_floppy_rejects_block_device_unknown_capacity_and_unsafe_requests() -> None:
    formatter = FloppyControllerFormatter(
        platform_name="Linux", which=lambda name: "/usr/sbin/ufiformat" if name == "ufiformat" else None,
        runner=lambda command: (0, "supported capacities: 1474560", ""),
    )
    with pytest.raises(DiskForgeError, match="generic-SCSI"):
        formatter.discover_usb(_device("/dev/sdb"))
    with pytest.raises(DiskForgeError, match="selected capacity"):
        formatter.format_usb(_device("/dev/sg4"), 737280, "FORMAT_FLOPPY")
    with pytest.raises(DiskForgeError, match="exact confirmation"):
        formatter.format_usb(_device("/dev/sg4"), 1474560, "FORMAT")
    with pytest.raises(DiskForgeError):
        formatter.discover_usb(_device("/dev/sg4", mounted=True))
