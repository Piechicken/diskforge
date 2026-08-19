from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.devices import format_removable_fat
from diskforge.core.filesystems import FatImageFilesystem
from diskforge.core.models import DeviceInfo, DeviceKind, FileSystemType
from diskforge.core.storage import SafetyError


def _device(path: Path, **changes: object) -> DeviceInfo:
    path.write_bytes(b"\0" * (8 * 1024 * 1024))
    fields: dict[str, object] = {
        "identifier": str(path), "display_name": "Removable test media", "size": path.stat().st_size,
        "kind": DeviceKind.REMOVABLE, "removable": True,
    }
    fields.update(changes)
    return DeviceInfo(**fields)  # type: ignore[arg-type]


def test_removable_fat_format_creates_verified_reopenable_volume(tmp_path: Path) -> None:
    device = _device(tmp_path / "media.img")

    result = format_removable_fat(device, FileSystemType.FAT16, "FORMATME", "FORMAT")

    assert result.device_identifier == device.identifier
    assert result.filesystem == FileSystemType.FAT16
    assert result.label == "FORMATME"
    assert result.verified is True
    filesystem = FatImageFilesystem(device.identifier, read_only=True)
    try:
        assert filesystem.volume_label() == "FORMATME"
        assert filesystem.list_entries("/") == []
    finally:
        filesystem.close()


@pytest.mark.parametrize(
    ("changes", "confirmation", "message"),
    [
        ({"system_disk": True}, "FORMAT", "operating-system"),
        ({"mounted": True}, "FORMAT", "mounted"),
        ({"removable": False, "kind": DeviceKind.DISK}, "FORMAT", "removable"),
        ({"kind": DeviceKind.OPTICAL}, "FORMAT", "removable"),
        ({}, "format", "FORMAT"),
    ],
)
def test_removable_fat_format_rejects_unsafe_device_or_confirmation(
    tmp_path: Path, changes: dict[str, object], confirmation: str, message: str,
) -> None:
    device = _device(tmp_path / f"media-{len(changes)}-{confirmation}.img", **changes)

    with pytest.raises(SafetyError, match=message):
        format_removable_fat(device, FileSystemType.FAT16, "FORMATME", confirmation)
