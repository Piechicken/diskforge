from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.compare import compare_streams
from diskforge.core.devices import compare_image_with_device
from diskforge.core.models import DeviceInfo, DeviceKind
from diskforge.core.storage import DiskForgeError


def test_compare_streams_reports_first_difference_and_hashes(tmp_path: Path) -> None:
    first = tmp_path / "first.img"
    second = tmp_path / "second.img"
    first.write_bytes(b"abc" + b"x" * 4096)
    second.write_bytes(b"abc" + b"y" + b"x" * 4095)

    result = compare_streams(first, second)

    assert result.equal is False
    assert result.first_difference == 3
    assert result.reason == "bytes differ"
    assert result.bytes_compared == first.stat().st_size
    assert result.source_sha256 != result.destination_sha256


def test_compare_streams_reports_size_and_respects_limit(tmp_path: Path) -> None:
    first = tmp_path / "first.img"
    second = tmp_path / "second.img"
    first.write_bytes(b"same" + b"tail")
    second.write_bytes(b"same")

    size_result = compare_streams(first, second)
    assert size_result.equal is False
    assert size_result.first_difference is None
    assert size_result.reason == "endpoint sizes differ"

    limited = compare_streams(first, second, bytes_to_compare=4)
    assert limited.equal is True
    assert limited.bytes_compared == 4


def test_compare_image_with_file_backed_device_is_read_only(tmp_path: Path) -> None:
    image = tmp_path / "image.img"
    device_file = tmp_path / "device.bin"
    image.write_bytes(b"image bytes")
    device_file.write_bytes(b"image bytes" + b"\0" * 1024)
    device = DeviceInfo(str(device_file), "test device", device_file.stat().st_size, DeviceKind.REMOVABLE)

    result = compare_image_with_device(image, device)

    assert result.equal is True
    assert device_file.read_bytes().startswith(b"image bytes")
    with pytest.raises(DiskForgeError, match="size is not available"):
        compare_image_with_device(image, DeviceInfo(str(device_file), "unknown", 0, DeviceKind.DISK))
