from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.jv3 import export_jv3_to_raw, inspect_jv3
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


_HEADERS = 2901
_HEADER_BYTES = _HEADERS * 3 + 1


def _headers(items: list[tuple[int, int, int, bytes]], *, marker: int = 0xFF) -> tuple[bytes, bytes]:
    content = bytearray(b"\xff\xff\xff" * _HEADERS + bytes((marker,)))
    data = bytearray()
    for index, (cylinder, sector, flags, payload) in enumerate(items):
        content[index * 3:index * 3 + 3] = bytes((cylinder, sector, flags))
        data.extend(payload)
    return bytes(content), bytes(data)


def _jv3(path: Path, *, second: bool = False, bad_flags: int = 0) -> Path:
    first_items = [
        (0, 0, bad_flags, b"A" * 256),
        (0, 1, bad_flags, b"B" * 256),
        (1, 0, bad_flags, b"C" * 256),
        (1, 1, bad_flags, b"D" * 256),
    ]
    first_header, first_data = _headers(first_items, marker=0xFF)
    if not second:
        path.write_bytes(first_header + first_data)
        return path
    # Force block one to consume all nominal free-sector data, then place a one-sector second block.
    full_first_data = first_data + b"\0" * ((_HEADERS - len(first_items)) * 256)
    second_header, second_data = _headers([(2, 0, bad_flags, b"E" * 256)], marker=0xFF)
    path.write_bytes(first_header + full_first_data + second_header + second_data)
    return path


def test_jv3_inspects_and_exports_normal_rectangular_data_without_mutation(tmp_path: Path) -> None:
    source = _jv3(tmp_path / "normal.jv3")
    before = sha256_file(source)
    inspection = inspect_jv3(source)
    assert not inspection.write_protected and inspection.header_blocks == 1
    assert inspection.exportable and (inspection.cylinders, inspection.heads, inspection.sectors_per_track) == (2, 1, 2)
    target = tmp_path / "export.img"
    assert export_jv3_to_raw(source, target) == target
    assert target.read_bytes() == b"A" * 256 + b"B" * 256 + b"C" * 256 + b"D" * 256
    assert sha256_file(source) == before


def test_jv3_recognizes_a_second_header_block(tmp_path: Path) -> None:
    source = _jv3(tmp_path / "extended.jv3", second=True)
    inspection = inspect_jv3(source)
    assert inspection.header_blocks == 2
    assert not inspection.exportable
    assert "rectangular" in inspection.export_reason


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value.__setitem__(_HEADERS * 3, 3), "write-protect"),
    (lambda value: value.__setitem__(0, 0xFF), "free-sector"),
    (lambda value: value.__setitem__(3 * 4 + 2, 0xF8), "free JV3"),
    (lambda value: value.extend(b"tail"), "ends inside"),
])
def test_jv3_rejects_invalid_headers_or_tail(tmp_path: Path, mutate, message: str) -> None:
    source = _jv3(tmp_path / "bad.jv3")
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_jv3(source)


def test_jv3_refuses_error_nonibm_and_nonrectangular_raw_export(tmp_path: Path) -> None:
    for name, flags, expected in [("error", 0x08, "CRC error"), ("short", 0x04, "non-IBM")]:
        source = _jv3(tmp_path / f"{name}.jv3", bad_flags=flags)
        inspection = inspect_jv3(source)
        assert not inspection.exportable and expected in inspection.export_reason
        with pytest.raises(DiskForgeError, match=expected):
            export_jv3_to_raw(source, tmp_path / f"{name}.img")
    source = _jv3(tmp_path / "nonrect.jv3")
    content = bytearray(source.read_bytes())
    content[3] = 1  # C=0,H=0,S=1 becomes a duplicate; C=1/H0/S1 is removed from layout.
    source.write_bytes(content)
    assert not inspect_jv3(source).exportable


def test_jv3_refuses_same_or_existing_destination(tmp_path: Path) -> None:
    source = _jv3(tmp_path / "source.jv3")
    with pytest.raises(DiskForgeError, match="differ"):
        export_jv3_to_raw(source, source)
    existing = tmp_path / "existing.img"; existing.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        export_jv3_to_raw(source, existing)


def test_jv3_is_shape_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source = _jv3(tmp_path / "container.jv3")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.JV3
    assert not info.writable
    with pytest.raises(DiskForgeError, match="JV3 images are read-only"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised = tmp_path / "not-jv3.img"
    disguised.write_bytes(source.read_bytes())
    assert inspect_image(disguised).image_format != ImageFormat.JV3


def test_jv3_inventory_cli_sdk_export_and_filesystem_contract(tmp_path: Path, capsys) -> None:
    source = _jv3(tmp_path / "cross-entry.jv3")
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.JV3
    assert main(["--json", "jv3-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exportable"] and payload["sectors_per_track"] == 2
    client = DiskForgeClient()
    target = tmp_path / "sdk.img"
    assert client.export_jv3_to_raw(source, target) == target
    assert target.stat().st_size == 1024
    with pytest.raises(DiskForgeError, match="JV3 images are read-only"):
        with client.filesystem(source):
            pass


def test_jv3_requires_extension(tmp_path: Path) -> None:
    source = _jv3(tmp_path / "source.jv3")
    wrong = tmp_path / "source.dsk"; wrong.write_bytes(source.read_bytes())
    with pytest.raises(DiskForgeError, match="extension"):
        inspect_jv3(wrong)
