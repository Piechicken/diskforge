from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.eightysixf import inspect_86f
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _86f(path: Path, *, sides: int = 1, surface: bool = False) -> Path:
    entries = 512 if sides == 2 else 256
    flags = 0x1080 | (0x0008 if sides == 2 else 0) | (0x0001 if surface else 0)
    table_end = 8 + entries * 4
    content = bytearray(b"86BF\x0c\x02" + flags.to_bytes(2, "little") + b"\0" * (entries * 4))
    offsets: list[int] = []
    for logical in range(sides * 2):
        offsets.append(len(content))
        bitcells = 32 + logical
        data_bytes = ((bitcells + 15) // 16) * 2
        track_flags = 0x000A  # MFM, 250 kbps, 300 RPM
        content.extend(track_flags.to_bytes(2, "little"))
        content.extend(bitcells.to_bytes(4, "little"))
        content.extend((0).to_bytes(4, "little"))
        data = bytes((0xA0 + logical,)) * data_bytes
        content.extend(data)
        if surface:
            content.extend(bytes((0xFF,)) * data_bytes)
    for index, offset in enumerate(offsets):
        content[8 + index * 4:12 + index * 4] = offset.to_bytes(4, "little")
    assert len(content) > table_end
    path.write_bytes(content)
    return path


def test_86f_inspects_total_bitcell_single_side_tracks_and_keeps_source_unchanged(tmp_path: Path) -> None:
    source = _86f(tmp_path / "single.86f")
    before = sha256_file(source)
    inspection = inspect_86f(source)
    assert inspection.sides == 1 and len(inspection.tracks) == 2
    assert inspection.missing_track_count == 254 and inspection.total_encoded_bytes == 10
    assert inspection.tracks[1].encoding == "MFM" and inspection.tracks[1].bit_rate_kbps == 250
    assert sha256_file(source) == before


def test_86f_inspects_two_sided_surface_description_tracks(tmp_path: Path) -> None:
    inspection = inspect_86f(_86f(tmp_path / "two-sided.86f", sides=2, surface=True))
    assert inspection.sides == 2 and inspection.has_surface_description
    assert [(item.cylinder, item.head) for item in inspection.tracks] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert all(item.has_surface_description for item in inspection.tracks)


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value.__setitem__(0, 0), "magic"),
    (lambda value: value.__setitem__(6, 0), "total-bitcell"),
    (lambda value: value.extend(b"tail"), "exactly match"),
])
def test_86f_rejects_invalid_header_mode_or_trailing_layout(tmp_path: Path, mutate, message: str) -> None:
    source = _86f(tmp_path / "bad.86f")
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_86f(source)


def test_86f_rejects_non_increasing_offsets_and_invalid_track_data_extent(tmp_path: Path) -> None:
    source = _86f(tmp_path / "offset.86f")
    content = bytearray(source.read_bytes())
    first = int.from_bytes(content[8:12], "little")
    content[12:16] = first.to_bytes(4, "little")
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="strictly increasing"):
        inspect_86f(source)
    source = _86f(tmp_path / "extent.86f")
    content = bytearray(source.read_bytes())
    first = int.from_bytes(content[8:12], "little")
    content[first + 2:first + 6] = (48).to_bytes(4, "little")
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="exactly match"):
        inspect_86f(source)


def test_86f_is_signature_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source = _86f(tmp_path / "container.86f")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.EIGHTYSIXF
    assert not info.writable
    with pytest.raises(DiskForgeError, match="bitstream containers"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised = tmp_path / "not-86f.img"
    disguised.write_bytes(source.read_bytes())
    assert inspect_image(disguised).image_format != ImageFormat.EIGHTYSIXF


def test_86f_inventory_cli_sdk_and_filesystem_contract(tmp_path: Path, capsys) -> None:
    source = _86f(tmp_path / "cross-entry.86f", sides=2, surface=True)
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.EIGHTYSIXF
    assert main(["--json", "86f-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sides"] == 2 and payload["track_count"] == 4
    client = DiskForgeClient()
    assert client.inspect_86f(source).has_surface_description
    with pytest.raises(DiskForgeError, match="bitstream containers"):
        with client.filesystem(source):
            pass


def test_86f_requires_86f_extension(tmp_path: Path) -> None:
    source = _86f(tmp_path / "real.86f")
    wrong = tmp_path / "wrong.img"
    wrong.write_bytes(source.read_bytes())
    with pytest.raises(DiskForgeError, match="extension"):
        inspect_86f(wrong)
