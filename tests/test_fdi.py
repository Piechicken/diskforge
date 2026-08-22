from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.fdi import inspect_fdi
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _fdi(path: Path, descriptors: list[tuple[int, int]], *, last_track: int = 0,
         last_head: int = 0, flags: int = 0) -> Path:
    track_count = (last_track + 1) * (last_head + 1)
    assert len(descriptors) == track_count
    header_blocks = 1 if track_count <= 180 else 1 + ((track_count - 180 + 255) // 256)
    header = bytearray(header_blocks * 512)
    header[:27] = b"Formatted Disk Image file\r\n"
    header[27:57] = b"DiskForge FDI regression".ljust(30, b" ")
    header[57:59] = b"\r\n"
    header[59:139] = b"FDI v2 structural fixture".ljust(80, b" ")
    header[139] = 0x1A
    header[140:142] = b"\0\x02"
    header[142:144] = last_track.to_bytes(2, "big")
    header[144] = last_head
    header[145] = 2
    header[146] = 300 - 128
    header[147] = flags
    header[148:150] = b"\0\0"
    payload = bytearray()
    for index, (type_code, size_field) in enumerate(descriptors):
        offset = 152 + index * 2
        header[offset:offset + 2] = bytes((type_code, size_field))
        if type_code == 0:
            continue
        if type_code == 1:
            count = size_field * 512
        elif 0x80 <= type_code <= 0xBF:
            count = (((type_code & 0x3F) << 8) | size_field) * 256
        else:
            count = size_field * 256
        payload.extend(bytes((index + 1,)) * count)
    path.write_bytes(header + payload)
    return path


def test_fdi_v20_inspects_big_endian_header_track_directory_and_payload_bounds(tmp_path: Path) -> None:
    source = _fdi(tmp_path / "fixture.fdi", [(0, 0), (5, 1), (0xC2, 1), (0xF4, 1)], last_track=1, last_head=1, flags=3)
    before = sha256_file(source)

    inspection = inspect_fdi(source)

    assert (inspection.cylinders, inspection.heads) == (2, 2)
    assert inspection.header_bytes == 512
    assert inspection.write_protected and inspection.index_synchronized
    assert inspection.blank_track_count == 1
    assert inspection.declared_track_bytes == 768
    assert [track.category for track in inspection.tracks] == ["blank", "standard", "raw-decoded", "raw-data"]
    assert [track.offset_bytes for track in inspection.tracks] == [512, 512, 768, 1024]
    assert sha256_file(source) == before


@pytest.mark.parametrize("mutate, message", [
    (lambda content: content.__setitem__(152 + 1, 1), "blank FDI track"),
    (lambda content: content.__setitem__(152 + 2, 0x0F), "reserved"),
    (lambda content: content.__setitem__(160, 1), "padding"),
    (lambda content: content.extend(b"tail"), "trailing bytes"),
])
def test_fdi_rejects_malformed_directory_padding_and_eof(tmp_path: Path, mutate, message: str) -> None:
    source = _fdi(tmp_path / "bad.fdi", [(0, 0), (5, 1)], last_track=1)
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_fdi(source)


def test_fdi_rejects_bad_signature_version_geometry_and_truncated_payload(tmp_path: Path) -> None:
    source = _fdi(tmp_path / "bad.fdi", [(5, 1)])
    content = bytearray(source.read_bytes())
    content[0] = ord("X")
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="signature"):
        inspect_fdi(source)
    source = _fdi(tmp_path / "version.fdi", [(5, 1)])
    content = bytearray(source.read_bytes()); content[141] = 1; source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="version"):
        inspect_fdi(source)
    source = _fdi(tmp_path / "geometry.fdi", [(5, 1)])
    content = bytearray(source.read_bytes()); content[144] = 2; source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="head count"):
        inspect_fdi(source)
    source = _fdi(tmp_path / "truncated.fdi", [(5, 1)])
    source.write_bytes(source.read_bytes()[:-1])
    with pytest.raises(DiskForgeError, match="exceeds"):
        inspect_fdi(source)


def test_fdi_cross_entry_contract_is_read_only_and_shape_recognized(tmp_path: Path, capsys) -> None:
    source = _fdi(tmp_path / "cross-entry.fdi", [(0, 0), (5, 1)], last_track=1)
    info = inspect_image(source)
    assert info.image_format == ImageFormat.FDI
    assert not info.writable
    with pytest.raises(DiskForgeError, match="FDI images are read-only"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.FDI
    assert main(["--json", "fdi-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cylinders"] == 2 and payload["declared_track_bytes"] == 256
    assert DiskForgeClient().inspect_fdi(source).tracks[1].type_code == 5
    with pytest.raises(DiskForgeError, match="FDI images are read-only"):
        with DiskForgeClient().filesystem(source):
            pass
    disguised = tmp_path / "cross-entry.img"
    disguised.write_bytes(source.read_bytes())
    assert inspect_image(disguised).image_format != ImageFormat.FDI
