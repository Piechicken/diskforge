from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.mounts import ImageMountManager
from diskforge.core.storage import DiskForgeError


def _runner(calls: list[list[str]], outputs: list[tuple[int, str, str]]):
    def run(command: list[str]) -> tuple[int, str, str]:
        calls.append(command)
        return outputs.pop(0)
    return run


def test_linux_read_only_mount_and_unmount_use_controlled_udisksctl_sequence(tmp_path: Path) -> None:
    image = tmp_path / "disk.img"
    image.write_bytes(b"disk")
    calls: list[list[str]] = []
    manager = ImageMountManager(
        platform_name="Linux", which=lambda command: "/usr/bin/udisksctl" if command == "udisksctl" else None,
        runner=_runner(calls, [
            (0, "Mapped file /tmp/disk.img as /dev/loop7.\n", ""),
            (0, "Mounted /dev/loop7 at /media/disk.\n", ""),
            (0, "Unmounted /dev/loop7.\n", ""),
            (0, "Deleted /dev/loop7.\n", ""),
        ]),
    )

    report = manager.capability_report()
    assert report.available is True
    session = manager.mount(image)
    assert session.read_only is True
    assert session.device == "/dev/loop7"
    assert session.mount_point == Path("/media/disk")
    manager.unmount(session)

    assert calls == [
        ["udisksctl", "loop-setup", "--read-only", "--file", str(image)],
        ["udisksctl", "mount", "--block-device", "/dev/loop7", "--options", "ro"],
        ["udisksctl", "unmount", "--block-device", "/dev/loop7"],
        ["udisksctl", "loop-delete", "--block-device", "/dev/loop7"],
    ]


def test_mount_rejects_missing_backend_and_nonexistent_image(tmp_path: Path) -> None:
    manager = ImageMountManager(platform_name="Linux", which=lambda command: None)
    report = manager.capability_report()
    assert report.available is False
    with pytest.raises(DiskForgeError, match="unavailable"):
        manager.mount(tmp_path / "missing.img")


def test_windows_mount_command_is_read_only_and_unmount_uses_dismount(tmp_path: Path) -> None:
    image = tmp_path / "disk.vhd"
    image.write_bytes(b"disk")
    calls: list[list[str]] = []
    manager = ImageMountManager(
        platform_name="Windows", which=lambda command: "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        runner=_runner(calls, [
            (0, "E:\n", ""),
            (0, "", ""),
        ]),
    )

    session = manager.mount(image)
    assert session.mount_point == Path("E:/")
    assert "-Access" in calls[0][-1] and "ReadOnly" in calls[0][-1]
    manager.unmount(session)
    assert "Dismount-DiskImage" in calls[1][-1]


def test_macos_mount_and_unmount_use_read_only_hdiutil(tmp_path: Path) -> None:
    image = tmp_path / "disk.dmg"
    image.write_bytes(b"disk")
    calls: list[list[str]] = []
    plist = """<?xml version=\"1.0\" encoding=\"UTF-8\"?><plist version=\"1.0\"><dict><key>system-entities</key><array><dict><key>dev-entry</key><string>/dev/disk9</string><key>mount-point</key><string>/Volumes/Disk</string></dict></array></dict></plist>"""
    manager = ImageMountManager(
        platform_name="Darwin", which=lambda command: "/usr/bin/hdiutil" if command == "hdiutil" else None,
        runner=_runner(calls, [(0, plist, ""), (0, "", "")]),
    )

    session = manager.mount(image)
    assert session.device == "/dev/disk9"
    assert session.mount_point == Path("/Volumes/Disk")
    assert calls[0][:4] == ["hdiutil", "attach", "-readonly", "-nobrowse"]
    manager.unmount(session)
    assert calls[1] == ["hdiutil", "detach", "/dev/disk9"]
