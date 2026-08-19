"""Controlled, read-only image mounting through explicit operating-system backends."""
from __future__ import annotations

import plistlib
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .storage import DiskForgeError


CommandRunner = Callable[[list[str]], tuple[int, str, str]]


@dataclass(frozen=True)
class ImageMountCapability:
    platform: str
    backend: str | None
    available: bool
    read_only: bool
    reason: str

    def as_mapping(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "backend": self.backend,
            "available": self.available,
            "read_only": self.read_only,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ImageMountSession:
    image: Path
    platform: str
    device: str | None
    mount_point: Path | None
    read_only: bool = True


class ImageMountManager:
    """Mount images read-only only, without drivers, daemon state, or shell interpolation."""

    def __init__(self, *, platform_name: str | None = None,
                 which: Callable[[str], str | None] = shutil.which,
                 runner: CommandRunner | None = None) -> None:
        self.platform_name = platform_name or platform.system()
        self._which = which
        self._runner = runner or self._run_subprocess

    @staticmethod
    def _run_subprocess(command: list[str]) -> tuple[int, str, str]:
        completed = subprocess.run(command, check=False, text=True, capture_output=True)
        return completed.returncode, completed.stdout, completed.stderr

    def capability_report(self) -> ImageMountCapability:
        if self.platform_name == "Windows":
            executable = self._which("powershell") or self._which("powershell.exe")
            if executable:
                return ImageMountCapability("Windows", executable, True, True,
                                            "Windows PowerShell read-only image mounting is available.")
            return ImageMountCapability("Windows", None, False, True,
                                        "PowerShell is unavailable; DiskForge cannot mount images on this system.")
        if self.platform_name == "Darwin":
            executable = self._which("hdiutil")
            if executable:
                return ImageMountCapability("macOS", executable, True, True,
                                            "hdiutil read-only image mounting is available.")
            return ImageMountCapability("macOS", None, False, True,
                                        "hdiutil is unavailable; DiskForge cannot mount images on this system.")
        if self.platform_name == "Linux":
            executable = self._which("udisksctl")
            if executable:
                return ImageMountCapability("Linux", executable, True, True,
                                            "udisksctl read-only loop mounting is available.")
            return ImageMountCapability("Linux", None, False, True,
                                        "udisksctl is unavailable; install or enable the system storage service to mount images.")
        return ImageMountCapability(self.platform_name, None, False, True,
                                    "This platform has no supported read-only image mount backend.")

    def _require_available(self) -> ImageMountCapability:
        report = self.capability_report()
        if not report.available:
            raise DiskForgeError(f"Read-only image mounting is unavailable: {report.reason}")
        return report

    @staticmethod
    def _quoted_powershell(value: Path | str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    @staticmethod
    def _ensure_success(command: list[str], result: tuple[int, str, str]) -> str:
        code, stdout, stderr = result
        if code != 0:
            detail = (stderr or stdout).strip() or f"exit status {code}"
            raise DiskForgeError(f"System mount backend failed: {detail}")
        return stdout

    def mount(self, image: Path | str) -> ImageMountSession:
        report = self._require_available()
        target = Path(image)
        if not target.is_file():
            raise FileNotFoundError(target)
        if self.platform_name == "Linux":
            return self._mount_linux(target)
        if self.platform_name == "Windows":
            return self._mount_windows(target)
        if self.platform_name == "Darwin":
            return self._mount_macos(target)
        raise DiskForgeError(f"Unsupported mount platform: {report.platform}")

    def _mount_linux(self, image: Path) -> ImageMountSession:
        loop_output = self._ensure_success(
            ["udisksctl", "loop-setup", "--read-only", "--file", str(image)],
            self._runner(["udisksctl", "loop-setup", "--read-only", "--file", str(image)]),
        )
        match = re.search(r"\bas\s+(/dev/[^\s.]+)", loop_output)
        if not match:
            raise DiskForgeError("udisksctl did not report a loop device for the mounted image.")
        device = match.group(1)
        try:
            command = ["udisksctl", "mount", "--block-device", device, "--options", "ro"]
            mounted_output = self._ensure_success(command, self._runner(command))
            mount_match = re.search(r"\bat\s+(.+?)(?:\.\s*$|$)", mounted_output.strip())
            if not mount_match:
                raise DiskForgeError("udisksctl did not report a mount point for the image.")
            return ImageMountSession(image, "Linux", device, Path(mount_match.group(1).strip()), True)
        except Exception:
            cleanup = ["udisksctl", "loop-delete", "--block-device", device]
            self._runner(cleanup)
            raise

    def _mount_windows(self, image: Path) -> ImageMountSession:
        script = (
            "$ErrorActionPreference='Stop'; "
            f"$disk=Mount-DiskImage -ImagePath {self._quoted_powershell(image)} -Access ReadOnly -PassThru; "
            "($disk | Get-DiskImage | Get-Disk | Get-Partition | Get-Volume | "
            "Where-Object { $_.DriveLetter } | Select-Object -First 1 -ExpandProperty DriveLetter)"
        )
        command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
        output = self._ensure_success(command, self._runner(command)).strip()
        drive = next((line.strip().rstrip(":") for line in output.splitlines() if line.strip()), "")
        mount_point = Path(f"{drive}:/") if drive else None
        return ImageMountSession(image, "Windows", None, mount_point, True)

    def _mount_macos(self, image: Path) -> ImageMountSession:
        command = ["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(image)]
        output = self._ensure_success(command, self._runner(command))
        try:
            payload = plistlib.loads(output.encode("utf-8"))
        except (plistlib.InvalidFileException, ValueError) as exc:
            raise DiskForgeError("hdiutil did not return a valid mount description.") from exc
        entities = payload.get("system-entities", []) if isinstance(payload, dict) else []
        for entity in entities:
            if isinstance(entity, dict) and entity.get("dev-entry"):
                device = str(entity["dev-entry"])
                mount = entity.get("mount-point")
                return ImageMountSession(image, "macOS", device, Path(str(mount)) if mount else None, True)
        raise DiskForgeError("hdiutil did not report a device for the mounted image.")

    def unmount(self, session: ImageMountSession) -> None:
        if not session.read_only:
            raise DiskForgeError("DiskForge only manages read-only image mount sessions.")
        if session.platform == "Linux":
            if not session.device:
                raise DiskForgeError("Linux mount session has no loop device.")
            unmount = ["udisksctl", "unmount", "--block-device", session.device]
            self._ensure_success(unmount, self._runner(unmount))
            delete = ["udisksctl", "loop-delete", "--block-device", session.device]
            self._ensure_success(delete, self._runner(delete))
            return
        if session.platform == "Windows":
            script = f"Dismount-DiskImage -ImagePath {self._quoted_powershell(session.image)}"
            command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
            self._ensure_success(command, self._runner(command))
            return
        if session.platform == "macOS":
            if not session.device:
                raise DiskForgeError("macOS mount session has no device identifier.")
            command = ["hdiutil", "detach", session.device]
            self._ensure_success(command, self._runner(command))
            return
        raise DiskForgeError(f"Unsupported mount platform: {session.platform}")
