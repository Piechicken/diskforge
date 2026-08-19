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


class FloppyControllerFormatter:
    """Use `fdformat` only for standard Linux controller floppy nodes.

    This service intentionally does not treat USB removable disks as controller
    floppies and never passes the `--no-verify` option.
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

    def format(self, device: DeviceInfo, confirmation_phrase: str) -> FloppyFormatResult:
        report = self.capability_report()
        if not report.available:
            raise DiskForgeError(f"Controller-level floppy formatting is unavailable: {report.reason}")
        if confirmation_phrase != "FORMAT_FLOPPY":
            raise DiskForgeError("Controller-level floppy formatting requires the exact confirmation phrase FORMAT_FLOPPY.")
        if not device.removable or device.mounted or device.system_disk:
            raise DiskForgeError("Controller-level floppy formatting requires an unmounted, non-system removable device.")
        if not _STANDARD_LINUX_FLOPPY.fullmatch(device.identifier):
            raise DiskForgeError("Only standard Linux controller floppy nodes such as /dev/fd0 are accepted; USB drives are excluded.")
        command = ["fdformat", device.identifier]
        code, stdout, stderr = self._runner(command)
        if code != 0:
            raise DiskForgeError((stderr or stdout).strip() or "fdformat failed.")
        return FloppyFormatResult(device.identifier, "fdformat", verified=True)
