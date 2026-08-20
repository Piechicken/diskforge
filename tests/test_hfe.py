from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.hfe import inspect_hfe
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _hfe(path: Path, *, magic: bytes = b"HXCPICFE", second_offset: int = 3) -> Path:
    header = bytearray(512)
    header[:8] = magic
    header[8] = 0 if magic == b"HXCPICFE" else 0
    header[9] = 2
    header[10] = 2
    header[11] = 0
    header[12:14] = (250).to_bytes(2, "little")
    header[14:16] = (300).to_bytes(2, "little")
    header[16] = 0
    header[18:20] = (1).to_bytes(2, "little")
    header[20] = 0
    lut = bytearray(512)
    lut[0:4] = (2).to_bytes(2, "little") + (512).to_bytes(2, "little")
    lut[4:8] = second_offset.to_bytes(2, "little") + (256).to_bytes(2, "little")
    path.write_bytes(header + lut + b"A" * 512 + b"B" * 512)
    return path


def test_hfe_inspects_v1_container_without_decoding_bitstreams(tmp_path: Path) -> None:
    source = _hfe(tmp_path / "disk.hfe")
    before = sha256_file(source)
    inspection = inspect_hfe(source)
    assert inspection.version == "v1/v2"
    assert inspection.tracks == 2 and inspection.sides == 2
    assert inspection.bitrate_kbps == 250 and inspection.rpm == 300
    assert inspection.write_protected
    assert [item.offset_bytes for item in inspection.track_records] == [1024, 1536]
    assert inspection.unreferenced_bytes == 504
    assert sha256_file(source) == before


def test_hfe_is_signature_recognized_read_only_and_not_convertible(tmp_path: Path) -> None:
    source = _hfe(tmp_path / "container.hfe")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.HFE
    assert not info.writable
    with pytest.raises(DiskForgeError, match="bitstream containers"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)


def test_inventory_recognizes_hfe_as_read_only_bitstream_container(tmp_path: Path) -> None:
    source = _hfe(tmp_path / "inventory.hfe")
    report = inventory_images(tmp_path)
    assert len(report.records) == 1
    assert report.records[0].relative_path == source.name
    assert report.records[0].image_format == ImageFormat.HFE
    assert report.records[0].filesystem.value == "Unknown"


def test_cli_inspects_hfe_structure_without_source_mutation(tmp_path: Path, capsys) -> None:
    source = _hfe(tmp_path / "cli.hfe")
    before = sha256_file(source)
    assert main(["--json", "hfe-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["tracks"] == 2 and report["track_records"][0]["offset"] == 1024
    assert sha256_file(source) == before


def test_sdk_inspects_hfe_and_rejects_filesystem_session(tmp_path: Path) -> None:
    source = _hfe(tmp_path / "sdk.hfe")
    client = DiskForgeClient()
    assert client.inspect_hfe(source).tracks == 2
    with pytest.raises(DiskForgeError, match="bitstream containers"):
        with client.filesystem(source):
            pass


def test_hfe_inspects_v3_signature(tmp_path: Path) -> None:
    assert inspect_hfe(_hfe(tmp_path / "v3.hfe", magic=b"HXCHFEV3")).version == "v3"


@pytest.mark.parametrize("mutate, message", [
    (lambda data: data.__setitem__(slice(0, 8), b"NOT-HFE!"), "signature"),
    (lambda data: data.__setitem__(9, 0), "track count"),
    (lambda data: data.__setitem__(slice(512 + 4, 512 + 6), (2).to_bytes(2, "little")), "overlap"),
    (lambda data: data.__setitem__(slice(18, 20), (9).to_bytes(2, "little")), "lookup table"),
])
def test_hfe_rejects_invalid_header_or_lut(tmp_path: Path, mutate, message: str) -> None:
    source = _hfe(tmp_path / "bad.hfe")
    data = bytearray(source.read_bytes())
    mutate(data)
    source.write_bytes(data)
    with pytest.raises(DiskForgeError, match=message):
        inspect_hfe(source)
