"""Strict capability-gated controller-level floppy formatting backends."""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from .models import DeviceInfo
from .storage import DiskForgeError


CommandRunner = Callable[[list[str]], tuple[int, str, str]]
_STANDARD_LINUX_FLOPPY = re.compile(r"^/dev/fd[01](?:[dDhH]\d+)?$")
_UFI_SG_DEVICE = re.compile(r"^/dev/sg\d+$")
_UFI_CAPACITY = re.compile(r"(?<!\d)(\d{3,10})(?:\s*(?:bytes?|B))?(?!\d)", re.IGNORECASE)


@dataclass(frozen=True)
class FloppyFormatCapability:
    platform: str
    backend: str | None
    available: bool
    reason: str

    def as_mapping(self) -> dict[str, object]:
        return {"platform": self.platform, "backend": self.backend, "available": self.available, "reason": self.reason}


@dataclass(frozen=True)
class FloppyFormatResult:
    identifier: str
    backend: str
    verified: bool


@dataclass(frozen=True)
class UfiFloppyDiscovery:
    identifier: str
    supported_capacities: tuple[int, ...]
    raw_report: str


class FloppyControllerFormatter:
    """Run verified Linux floppy format backends behind strict device gates.

    ``fdformat`` accepts only standard controller nodes.  ``ufiformat`` accepts
    only an explicit generic-SCSI ``/dev/sgN`` node after the tool has reported
    it as a UFI device and the caller has deliberately selected a supported
    capacity.  Neither backend is exposed through unattended batch or SDK APIs.
    """

    def __init__(self, *, platform_name: str | None = None,
                 which: Callable[[str], str | None] = shutil.which,
                 runner: CommandRunner | None = None) -> None:
        self.platform_name = platform_name or platform.system()
        self._which = which
        self._runner = runner or self._run_subprocess

    @staticmethod
    def _run_subprocess(command: list[str]) -> tuple[int, str, str]:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        return completed.returncode, completed.stdout, completed.stderr

    def capability_report(self) -> FloppyFormatCapability:
        if self.platform_name != "Linux":
            return FloppyFormatCapability(self.platform_name, None, False,
                                          "No verified controller-level floppy format backend is available on this platform.")
        executable = self._which("fdformat")
        if not executable:
            return FloppyFormatCapability("Linux", None, False,
                                          "fdformat is unavailable; controller-level floppy formatting cannot be performed.")
        return FloppyFormatCapability("Linux", executable, True,
                                      "fdformat is available for standard Linux controller floppy devices; USB drives are excluded.")

    def usb_capability_report(self) -> FloppyFormatCapability:
        if self.platform_name != "Linux":
            return FloppyFormatCapability(self.platform_name, None, False,
                                          "No verified UFI USB floppy format backend is available on this platform.")
        executable = self._which("ufiformat")
        if not executable:
            return FloppyFormatCapability("Linux", None, False,
                                          "ufiformat is unavailable; UFI USB floppy formatting cannot be performed.")
        return FloppyFormatCapability("Linux", executable, True,
                                      "ufiformat is available only for detected UFI USB floppy generic-SCSI devices.")

    @staticmethod
    def _safe_removable(device: DeviceInfo) -> None:
        if not device.removable or device.mounted or device.system_disk:
            raise DiskForgeError("Floppy formatting requires an unmounted, non-system removable device.")

    def format(self, device: DeviceInfo, confirmation_phrase: str) -> FloppyFormatResult:
        report = self.capability_report()
        if not report.available:
            raise DiskForgeError(f"Controller-level floppy formatting is unavailable: {report.reason}")
        if confirmation_phrase != "FORMAT_FLOPPY":
            raise DiskForgeError("Controller-level floppy formatting requires the exact confirmation phrase FORMAT_FLOPPY.")
        self._safe_removable(device)
        if not _STANDARD_LINUX_FLOPPY.fullmatch(device.identifier):
            raise DiskForgeError("Only standard Linux controller floppy nodes such as /dev/fd0 are accepted; USB drives are excluded.")
        code, stdout, stderr = self._runner(["fdformat", device.identifier])
        if code != 0:
            raise DiskForgeError((stderr or stdout).strip() or "fdformat failed.")
        return FloppyFormatResult(device.identifier, "fdformat", verified=True)

    def discover_usb(self, device: DeviceInfo) -> UfiFloppyDiscovery:
        report = self.usb_capability_report()
        if not report.available:
            raise DiskForgeError(f"UFI USB floppy formatting is unavailable: {report.reason}")
        self._safe_removable(device)
        if not _UFI_SG_DEVICE.fullmatch(device.identifier):
            raise DiskForgeError("UFI USB formatting requires an explicitly discovered generic-SCSI node such as /dev/sg0; block devices are rejected.")
        code, stdout, stderr = self._runner(["ufiformat", "-i", device.identifier])
        if code != 0:
            raise DiskForgeError((stderr or stdout).strip() or "ufiformat discovery failed.")
        capacities = tuple(sorted({int(value) for value in _UFI_CAPACITY.findall(stdout)}))
        if not capacities:
            raise DiskForgeError("ufiformat did not report a supported UFI floppy capacity; the device is rejected.")
        return UfiFloppyDiscovery(device.identifier, capacities, stdout)

    def format_usb(self, device: DeviceInfo, capacity: int, confirmation_phrase: str) -> FloppyFormatResult:
        if confirmation_phrase != "FORMAT_FLOPPY":
            raise DiskForgeError("UFI USB floppy formatting requires the exact confirmation phrase FORMAT_FLOPPY.")
        discovery = self.discover_usb(device)
        if capacity not in discovery.supported_capacities:
            raise DiskForgeError("The selected capacity was not reported by ufiformat for this UFI floppy device.")
        code, stdout, stderr = self._runner(["ufiformat", "-f", str(capacity), "-V", device.identifier])
        if code != 0:
            raise DiskForgeError((stderr or stdout).strip() or "ufiformat failed.")
        return FloppyFormatResult(device.identifier, "ufiformat", verified=True)
