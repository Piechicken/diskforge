from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.devices import (backup_device_mbr, inspect_device_mbr, neutralize_device_mbr,
                                    restore_device_mbr)
from diskforge.core.models import DeviceInfo, DeviceKind
from diskforge.core.storage import SafetyError


def _device_image(path: Path) -> bytes:
    sector = bytearray(512)
    sector[:32] = b"device-bootstrap" * 2
    sector[446 + 4] = 0x0C
    sector[446 + 8:446 + 12] = (2048).to_bytes(4, "little")
    sector[446 + 12:446 + 16] = (4096).to_bytes(4, "little")
    sector[510:512] = b"\x55\xaa"
    path.write_bytes(sector + b"\0" * 4096)
    return bytes(sector)


def _device(path: Path, **changes: object) -> DeviceInfo:
    fields: dict[str, object] = {
        "identifier": str(path), "display_name": "Removable test disk", "size": path.stat().st_size,
        "kind": DeviceKind.REMOVABLE, "removable": True,
    }
    fields.update(changes)
    return DeviceInfo(**fields)  # type: ignore[arg-type]


def test_device_mbr_backup_neutralize_restore_is_audited_and_readback_verified(tmp_path: Path) -> None:
    target = tmp_path / "device.img"
    original = _device_image(target)
    device = _device(target)

    inspection = inspect_device_mbr(device)
    assert inspection.device_identifier == str(target)
    assert inspection.sha256
    saved = backup_device_mbr(device, tmp_path / "original.mbr")
    assert saved.backup.read_bytes() == original

    reset = neutralize_device_mbr(device, tmp_path / "pre-reset.mbr", "ERASE")
    assert reset.operation == "neutralize"
    assert reset.verified is True
    assert target.read_bytes()[:446] == b"\0" * 446
    assert target.read_bytes()[446:512] == original[446:512]

    restored = restore_device_mbr(device, saved.backup, tmp_path / "pre-restore.mbr", "ERASE")
    assert restored.operation == "restore"
    assert restored.verified is True
    assert target.read_bytes()[:512] == original


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"system_disk": True}, "operating-system"),
        ({"mounted": True}, "mounted"),
        ({"kind": DeviceKind.PARTITION}, "whole removable or physical disk"),
        ({"kind": DeviceKind.OPTICAL}, "whole removable or physical disk"),
    ],
)
def test_device_mbr_mutations_reject_unsafe_device_snapshot(tmp_path: Path, changes: dict[str, object], message: str) -> None:
    target = tmp_path / "device.img"
    _device_image(target)
    device = _device(target, **changes)

    with pytest.raises(SafetyError, match=message):
        neutralize_device_mbr(device, tmp_path / "backup.mbr", "ERASE")


def test_device_mbr_mutations_require_exact_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "device.img"
    _device_image(target)
    device = _device(target)

    with pytest.raises(SafetyError, match="ERASE"):
        neutralize_device_mbr(device, tmp_path / "backup.mbr", "erase")
