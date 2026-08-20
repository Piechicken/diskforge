from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.dc42 import export_dc42_data_to_raw, inspect_dc42
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _checksum(data: bytes) -> int:
    assert len(data) % 2 == 0
    value = 0
    for index in range(0, len(data), 2):
        value = (value + int.from_bytes(data[index:index + 2], "big")) & 0xFFFFFFFF
        value = ((value >> 1) | ((value & 1) << 31)) & 0xFFFFFFFF
    return value


def _dc42(path: Path, *, tags: bytes = b"") -> tuple[Path, bytes]:
    data = bytes(range(256)) * 2
    if tags:
        assert len(tags) >= 12 and len(tags) % 2 == 0
    header = bytearray(0x54)
    name = b"DiskForge"
    header[0] = len(name)
    header[1:1 + len(name)] = name
    header[0x40:0x44] = len(data).to_bytes(4, "big")
    header[0x44:0x48] = len(tags).to_bytes(4, "big")
    header[0x48:0x4C] = _checksum(data).to_bytes(4, "big")
    header[0x4C:0x50] = (_checksum(tags[12:]) if tags else 0).to_bytes(4, "big")
    header[0x50] = 2
    header[0x51] = 0x22
    header[0x52:0x54] = b"\x01\x00"
    path.write_bytes(header + data + tags)
    return path, data


def test_inspect_and_export_checksum_validated_dc42_data_fork(tmp_path: Path) -> None:
    tags = b"ignored-first" + b"\x00" + b"\x12\x34" * 3
    source, data = _dc42(tmp_path / "disk.dc42", tags=tags)
    before = sha256_file(source)
    inspection = inspect_dc42(source)
    output = export_dc42_data_to_raw(source, tmp_path / "disk.raw")
    assert inspection.name == "DiskForge"
    assert inspection.data_bytes == len(data) and inspection.tag_bytes == len(tags)
    assert output.read_bytes() == data
    assert sha256_file(source) == before


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value.__setitem__(0x52, 0), "private word"),
    (lambda value: value.__setitem__(slice(0x40, 0x44), b"\0\0\0\0"), "data fork size"),
    (lambda value: value.__setitem__(0x54, 0xFF), "checksum"),
])
def test_dc42_rejects_invalid_header_or_checksum(tmp_path: Path, mutate, message: str) -> None:
    source, _ = _dc42(tmp_path / "bad.dc42")
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_dc42(source)


def test_dc42_is_shape_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _dc42(tmp_path / "container.dc42")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.DC42
    assert not info.writable
    with pytest.raises(DiskForgeError, match="verified DC42"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised, _ = _dc42(tmp_path / "not-signed.img")
    assert inspect_image(disguised).image_format != ImageFormat.DC42


def test_dc42_inventory_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    source, data = _dc42(tmp_path / "cross-entry.dc42")
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.DC42
    assert main(["--json", "dc42-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data_bytes"] == len(data) and payload["tag_bytes"] == 0
    client = DiskForgeClient()
    assert client.inspect_dc42(source).name == "DiskForge"
    output = client.export_dc42_data_to_raw(source, tmp_path / "sdk.raw")
    assert output.destination and output.destination.read_bytes() == data
    with pytest.raises(DiskForgeError, match="verified DC42"):
        with client.filesystem(source):
            pass


def test_dc42_rejects_existing_and_same_destination(tmp_path: Path) -> None:
    source, _ = _dc42(tmp_path / "source.dc42")
    existing = tmp_path / "existing.raw"
    existing.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_dc42_data_to_raw(source, existing)
    with pytest.raises(DiskForgeError, match="differ"):
        export_dc42_data_to_raw(source, source)
    assert existing.read_bytes() == b"keep"
