from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.copyqm import _masked_crc32, export_copyqm_to_raw, inspect_copyqm
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _copyqm(path: Path, *, repeated: bool = False, comment: bytes = b"note") -> tuple[Path, bytes]:
    raw = (b"A" * 128 + bytes(range(128)) * 3) if repeated else bytes(range(256)) * 2
    header = bytearray(133)
    header[:3] = b"CQ\x14"
    header[0x03:0x05] = (128).to_bytes(2, "little")
    header[0x05] = 1
    header[0x06:0x08] = (1).to_bytes(2, "little")
    header[0x08] = 2
    header[0x09:0x0B] = (16).to_bytes(2, "little")
    header[0x0B:0x0D] = (4).to_bytes(2, "little")
    header[0x0D] = 0xF0
    header[0x0E:0x10] = (1).to_bytes(2, "little")
    header[0x10:0x12] = (4).to_bytes(2, "little")
    header[0x12:0x14] = (1).to_bytes(2, "little")
    header[0x1C:0x1C + len(b"Test floppy")] = b"Test floppy"
    header[0x58:0x5C] = bytes((0, 0, 1, 1))
    header[0x5C:0x60] = _masked_crc32(raw).to_bytes(4, "little")
    header[0x60:0x60 + len(b"VOLUME")]= b"VOLUME"
    header[0x6F:0x71] = len(comment).to_bytes(2, "little")
    header[0x71] = 0
    header[0x74] = 1
    if repeated:
        payload = (-128).to_bytes(2, "little", signed=True) + b"A" + (384).to_bytes(2, "little", signed=True) + raw[128:]
    else:
        payload = (len(raw)).to_bytes(2, "little", signed=True) + raw
    header[0x84] = (-sum(header)) & 0xFF
    path.write_bytes(header + comment + payload)
    return path, raw


def test_copyqm_inspects_and_exports_header_and_crc_verified_raw_without_source_change(tmp_path: Path) -> None:
    source, raw = _copyqm(tmp_path / "normal.qm")
    before = sha256_file(source)
    inspection = inspect_copyqm(source)
    output = export_copyqm_to_raw(source, tmp_path / "normal.img")
    assert inspection.comment == "note" and inspection.media_description == "Test floppy"
    assert inspection.volume_label == "VOLUME" and inspection.raw_bytes == len(raw)
    assert (inspection.tracks, inspection.heads, inspection.sectors_per_track, inspection.sector_size) == (1, 1, 4, 128)
    assert inspection.data_crc == inspection.calculated_crc
    assert output.read_bytes() == raw
    assert sha256_file(source) == before


def test_copyqm_decodes_repeated_and_literal_rle_runs(tmp_path: Path) -> None:
    source, raw = _copyqm(tmp_path / "rle.qm", repeated=True)
    assert export_copyqm_to_raw(source, tmp_path / "rle.raw").read_bytes() == raw


@pytest.mark.parametrize("mutate, message, repair_header_checksum", [
    (lambda value: value.__setitem__(0, 0), "signature header", False),
    (lambda value: value.__setitem__(0x58, 1), "standard DOS", True),
    (lambda value: value.__setitem__(0x5A, 0), "partial-track", True),
    (lambda value: value.__setitem__(0x5C, value[0x5C] ^ 0xFF), "CRC", True),
])
def test_copyqm_rejects_invalid_header_geometry_or_crc(tmp_path: Path, mutate, message: str,
                                                        repair_header_checksum: bool) -> None:
    source, _ = _copyqm(tmp_path / "bad.qm")
    content = bytearray(source.read_bytes())
    mutate(content)
    if repair_header_checksum:
        content[0x84] = 0
        content[0x84] = (-sum(content[:133])) & 0xFF
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_copyqm(source)


def test_copyqm_is_signature_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _copyqm(tmp_path / "container.qm")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.COPYQM
    assert not info.writable
    with pytest.raises(DiskForgeError, match="checksum-verified CopyQM"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised, _ = _copyqm(tmp_path / "not-copyqm.img")
    assert inspect_image(disguised).image_format != ImageFormat.COPYQM


def test_copyqm_inventory_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    source, raw = _copyqm(tmp_path / "cross-entry.qm")
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.COPYQM
    assert main(["--json", "copyqm-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["raw_bytes"] == len(raw) and payload["data_crc"] == payload["calculated_crc"]
    client = DiskForgeClient()
    assert client.inspect_copyqm(source).sector_size == 128
    output = client.export_copyqm_to_raw(source, tmp_path / "sdk.raw")
    assert output.destination and output.destination.read_bytes() == raw
    with pytest.raises(DiskForgeError, match="checksum-verified CopyQM"):
        with client.filesystem(source):
            pass


def test_copyqm_rejects_existing_or_same_destination(tmp_path: Path) -> None:
    source, _ = _copyqm(tmp_path / "source.qm")
    output = tmp_path / "already.raw"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_copyqm_to_raw(source, output)
    with pytest.raises(DiskForgeError, match="differ"):
        export_copyqm_to_raw(source, source)
    assert output.read_bytes() == b"keep"
