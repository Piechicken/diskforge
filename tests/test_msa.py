from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.msa import export_msa_to_raw, inspect_msa
from diskforge.core.storage import DiskForgeError, sha256_file


def _rle(data: bytes) -> bytes:
    output = bytearray()
    position = 0
    while position < len(data):
        value = data[position]
        end = position + 1
        while end < len(data) and data[end] == value:
            end += 1
        count = end - position
        if count >= 4 or (value == 0xE5 and count >= 1):
            output.extend((0xE5, value))
            output.extend(count.to_bytes(2, "big"))
        else:
            output.extend(data[position:end])
        position = end
    return bytes(output)


def _msa(path: Path, *, compressed: bool = False, sides: int = 2) -> tuple[Path, bytes]:
    sectors_per_track, start, end = 1, 0, 1
    header = b"\x0e\x0f" + sectors_per_track.to_bytes(2, "big") + (sides - 1).to_bytes(2, "big") + start.to_bytes(2, "big") + end.to_bytes(2, "big")
    raw = bytearray()
    blocks = bytearray()
    for cylinder in range(start, end + 1):
        for head in range(sides):
            value = (cylinder * 16 + head) & 0xFF
            data = bytes((value,)) * 256 + b"\xe5" + bytes((value,)) * 255
            raw.extend(data)
            payload = _rle(data) if compressed else data
            blocks.extend(len(payload).to_bytes(2, "big"))
            blocks.extend(payload)
    path.write_bytes(header + blocks)
    return path, bytes(raw)


def test_msa_inspects_and_exports_uncompressed_tracks_without_source_change(tmp_path: Path) -> None:
    source, raw = _msa(tmp_path / "normal.msa")
    before = sha256_file(source)
    inspection = inspect_msa(source)
    output = export_msa_to_raw(source, tmp_path / "normal.st")
    assert inspection.heads == 2 and inspection.sectors_per_track == 1
    assert inspection.compressed_track_count == 0 and inspection.raw_bytes == len(raw)
    assert output.read_bytes() == raw
    assert sha256_file(source) == before


def test_msa_decodes_e5_rle_tracks_and_preserves_actual_e5_bytes(tmp_path: Path) -> None:
    source, raw = _msa(tmp_path / "compressed.msa", compressed=True)
    inspection = inspect_msa(source)
    assert inspection.compressed_track_count == len(inspection.tracks)
    assert export_msa_to_raw(source, tmp_path / "compressed.st").read_bytes() == raw


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value.__setitem__(0, 0), "signature"),
    (lambda value: value.__setitem__(slice(4, 6), b"\0\x02"), "side count"),
    (lambda value: value.extend(b"tail"), "trailing"),
])
def test_msa_rejects_invalid_header_or_file_layout(tmp_path: Path, mutate, message: str) -> None:
    source, _ = _msa(tmp_path / "bad.msa")
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_msa(source)


def test_msa_is_signature_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _msa(tmp_path / "container.msa")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.MSA
    assert not info.writable
    with pytest.raises(DiskForgeError, match="track-validated RAW"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised, _ = _msa(tmp_path / "not-msa.img")
    assert inspect_image(disguised).image_format != ImageFormat.MSA


def test_msa_inventory_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    source, raw = _msa(tmp_path / "cross-entry.msa", compressed=True)
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.MSA
    assert main(["--json", "msa-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["raw_bytes"] == len(raw) and payload["compressed_track_count"] == payload["track_count"]
    client = DiskForgeClient()
    assert client.inspect_msa(source).heads == 2
    output = client.export_msa_to_raw(source, tmp_path / "sdk.st")
    assert output.destination and output.destination.read_bytes() == raw
    with pytest.raises(DiskForgeError, match="track-validated RAW"):
        with client.filesystem(source):
            pass


def test_msa_rejects_bad_rle_and_existing_or_same_destination(tmp_path: Path) -> None:
    source, _ = _msa(tmp_path / "bad-rle.msa", compressed=True, sides=1)
    content = bytearray(source.read_bytes())
    content[12] = 0xE5  # first compressed byte is marker; remove its remainder via declared length corruption
    content[10:12] = (1).to_bytes(2, "big")
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="RLE marker"):
        inspect_msa(source)
    source, _ = _msa(tmp_path / "source.msa")
    output = tmp_path / "already.raw"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_msa_to_raw(source, output)
    with pytest.raises(DiskForgeError, match="differ"):
        export_msa_to_raw(source, source)
    assert output.read_bytes() == b"keep"
