from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.mfm import inspect_mfm
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError

_HEADER = struct.Struct("<7sHBHHBI")
_TRACK = struct.Struct("<HBII")
_BLOCK = 512


def _round_block(value: int) -> int:
    return (value + _BLOCK - 1) // _BLOCK * _BLOCK


def _mfm(path: Path, *, tracks: int = 2, sides: int = 2) -> Path:
    records: list[tuple[int, int, bytes, int]] = []
    table_end = _HEADER.size + tracks * sides * _TRACK.size
    offset = _round_block(table_end)
    for cylinder in range(tracks):
        for side in range(sides):
            payload = bytes([0x4E + side]) * (17 + cylinder + side)
            records.append((cylinder, side, payload, offset))
            offset = _round_block(offset + len(payload))
    data = bytearray(_HEADER.pack(b"HXCMFM\0", tracks, sides, 300, 250, 0, _HEADER.size))
    for cylinder, side, payload, track_offset in records:
        data.extend(_TRACK.pack(cylinder, side, len(payload), track_offset))
    data.extend(b"\0" * (_round_block(len(data)) - len(data)))
    for index, (_, _, payload, track_offset) in enumerate(records):
        assert len(data) == track_offset
        data.extend(payload)
        if index != len(records) - 1:
            data.extend(b"\0" * (_round_block(len(data)) - len(data)))
    path.write_bytes(data)
    return path


def test_mfm_core_recognizes_only_canonical_structure(tmp_path: Path) -> None:
    image = _mfm(tmp_path / "sample.mfm")

    inspection = inspect_mfm(image)

    assert (inspection.tracks, inspection.sides, inspection.rpm, inspection.bitrate_kbps) == (2, 2, 300, 250)
    assert [(item.cylinder, item.side, item.bytes_stored) for item in inspection.track_records] == [
        (0, 0, 17), (0, 1, 18), (1, 0, 18), (1, 1, 19),
    ]
    assert inspection.padding_bytes > 0

    nonzero_padding = tmp_path / "nonzero-padding.mfm"
    data = bytearray(image.read_bytes())
    data[_HEADER.size + 4 * _TRACK.size + 1] = 1
    nonzero_padding.write_bytes(data)
    with pytest.raises(DiskForgeError, match="non-zero bytes"):
        inspect_mfm(nonzero_padding)

    duplicate_coordinate = tmp_path / "duplicate-coordinate.mfm"
    data = bytearray(image.read_bytes())
    data[_HEADER.size:_HEADER.size + _TRACK.size] = _TRACK.pack(0, 1, 17, _round_block(_HEADER.size + 4 * _TRACK.size))
    duplicate_coordinate.write_bytes(data)
    with pytest.raises(DiskForgeError, match="canonical order"):
        inspect_mfm(duplicate_coordinate)

    trailing = tmp_path / "trailing.mfm"
    trailing.write_bytes(image.read_bytes() + b"x")
    with pytest.raises(DiskForgeError, match="trailing bytes"):
        inspect_mfm(trailing)


def test_mfm_cross_entry_read_only_contract(tmp_path: Path, capsys) -> None:
    image = _mfm(tmp_path / "sample.mfm", tracks=1, sides=2)
    destination = tmp_path / "unexpected.img"

    info = inspect_image(image)
    assert info.image_format == ImageFormat.MFM
    assert not info.writable
    with pytest.raises(DiskForgeError, match="read-only bitstream"):
        convert_image(image, destination, ImageFormat.RAW)

    inventory = inventory_images(tmp_path)
    assert [record.image_format for record in inventory.records] == [ImageFormat.MFM]

    assert main(["--json", "mfm-info", str(image)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["tracks"] == 1
    assert report["sides"] == 2
    assert len(report["track_records"]) == 2

    client = DiskForgeClient()
    assert len(client.inspect_mfm(image).track_records) == 2
    with pytest.raises(DiskForgeError, match="read-only bitstream"):
        with client.filesystem(image):
            pass
