from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.deployment import execute_fat_deployment, prepare_fat_deployment
from diskforge.core.filesystems import create_fat_image
from diskforge.core.models import DeviceInfo, DeviceKind, FileSystemType
from diskforge.core.storage import DiskForgeError


def test_prepare_fat_deployment_creates_reviewable_mbr_plan(tmp_path: Path) -> None:
    source = create_fat_image(tmp_path / "source.img", 32 * 1024 * 1024, FileSystemType.FAT16, "DEPLOY")
    device = DeviceInfo("/dev/example", "Example removable disk", 64 * 1024 * 1024, DeviceKind.REMOVABLE, removable=True)
    plan = prepare_fat_deployment(source, tmp_path / "prepared.img", device=device)
    assert plan.prepared_image.is_file()
    sector = plan.prepared_image.read_bytes()[:512]
    assert sector[:446] == b"\x00" * 446
    assert sector[446 + 4] == 0x06
    assert sector[510:512] == b"\x55\xAA"
    assert plan.partition_start_lba > 0
    assert plan.requires_confirmation


def test_deployment_rejects_small_device_and_wrong_phrase(tmp_path: Path) -> None:
    source = create_fat_image(tmp_path / "source.img", 32 * 1024 * 1024, FileSystemType.FAT16, "DEPLOY")
    tiny = DeviceInfo("/dev/tiny", "Tiny", 1024, DeviceKind.REMOVABLE, removable=True)
    with pytest.raises(DiskForgeError, match="larger"):
        prepare_fat_deployment(source, tmp_path / "too-large.img", device=tiny)
    plan = prepare_fat_deployment(source, tmp_path / "prepared.img")
    with pytest.raises(DiskForgeError, match="Select a removable"):
        execute_fat_deployment(plan, "ERASE")
