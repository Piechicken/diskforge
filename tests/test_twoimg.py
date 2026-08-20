from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file
from diskforge.core.twoimg import export_twoimg_to_raw, inspect_twoimg


def _twoimg(path: Path, *, image_format: int = 1, comment: bytes = b"note", creator: bytes = b"meta") -> tuple[Path, bytes]:
    data = bytes(range(256)) * 2
    header = bytearray(64)
    header[:4] = b"2IMG"
    header[4:8] = b"DFOR"
    header[0x08:0x0A] = (64).to_bytes(2, "little")
    header[0x0A:0x0C] = (1).to_bytes(2, "little")
    header[0x0C:0x10] = image_format.to_bytes(4, "little")
    header[0x10:0x14] = (0x800001FE).to_bytes(4, "little")
    header[0x14:0x18] = ((len(data) // 512) if image_format == 1 else 0).to_bytes(4, "little")
    header[0x18:0x1C] = (64).to_bytes(4, "little")
    header[0x1C:0x20] = len(data).to_bytes(4, "little")
    cursor = 64 + len(data)
    if comment:
        header[0x20:0x24] = cursor.to_bytes(4, "little")
        header[0x24:0x28] = len(comment).to_bytes(4, "little")
        cursor += len(comment)
    if creator:
        header[0x28:0x2C] = cursor.to_bytes(4, "little")
        header[0x2C:0x30] = len(creator).to_bytes(4, "little")
    path.write_bytes(header + data + comment + creator)
    return path, data


def test_twoimg_inspects_and_exports_validated_prodos_data_without_source_change(tmp_path: Path) -> None:
    source, data = _twoimg(tmp_path / "volume.2mg")
    before = sha256_file(source)
    inspection = inspect_twoimg(source)
    output = export_twoimg_to_raw(source, tmp_path / "volume.po")
    assert inspection.creator_id == "DFOR"
    assert inspection.format_name == "ProDOS order" and inspection.prodos_blocks == 1
    assert inspection.write_protected and inspection.volume_number == 254
    assert inspection.comment == "note" and inspection.creator_data_bytes == 4
    assert output.read_bytes() == data
    assert sha256_file(source) == before


@pytest.mark.parametrize("image_format", [0, 1])
def test_twoimg_exports_dos_and_prodos_data_formats(tmp_path: Path, image_format: int) -> None:
    source, data = _twoimg(tmp_path / f"format-{image_format}.2img", image_format=image_format, comment=b"", creator=b"")
    assert inspect_twoimg(source).exportable
    assert export_twoimg_to_raw(source, tmp_path / f"format-{image_format}.raw").read_bytes() == data


def test_twoimg_inspects_but_never_exports_nibble_stream_as_raw(tmp_path: Path) -> None:
    source, _ = _twoimg(tmp_path / "nibble.2mg", image_format=2, comment=b"", creator=b"")
    inspection = inspect_twoimg(source)
    assert not inspection.exportable and inspection.format_name == "Nibble stream"
    with pytest.raises(DiskForgeError, match="nibble-stream"):
        export_twoimg_to_raw(source, tmp_path / "wrong.raw")


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value.__setitem__(slice(0, 4), b"BAD!"), "signature"),
    (lambda value: value.__setitem__(slice(8, 10), (52).to_bytes(2, "little")), "64-byte"),
    (lambda value: value.__setitem__(slice(16, 20), (0x200).to_bytes(4, "little")), "reserved"),
    (lambda value: value.__setitem__(slice(24, 28), (65).to_bytes(4, "little")), "data blocks"),
    (lambda value: value.__setitem__(0x30, 1), "reserved header"),
])
def test_twoimg_rejects_invalid_header_or_layout(tmp_path: Path, mutate, message: str) -> None:
    source, _ = _twoimg(tmp_path / "bad.2mg", comment=b"", creator=b"")
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_twoimg(source)


def test_twoimg_is_shape_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _twoimg(tmp_path / "container.2mg", comment=b"", creator=b"")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.TWOIMG
    assert not info.writable
    with pytest.raises(DiskForgeError, match="verified 2MG"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised, _ = _twoimg(tmp_path / "not-a-2mg.img", comment=b"", creator=b"")
    assert inspect_image(disguised).image_format != ImageFormat.TWOIMG


def test_twoimg_inventory_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    source, data = _twoimg(tmp_path / "cross-entry.2img", comment=b"", creator=b"")
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.TWOIMG
    assert main(["--json", "twoimg-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["format_name"] == "ProDOS order" and payload["exportable"]
    client = DiskForgeClient()
    assert client.inspect_twoimg(source).data_bytes == len(data)
    output = client.export_twoimg_to_raw(source, tmp_path / "sdk.raw")
    assert output.destination and output.destination.read_bytes() == data
    with pytest.raises(DiskForgeError, match="verified 2MG"):
        with client.filesystem(source):
            pass


def test_twoimg_rejects_existing_or_same_destination(tmp_path: Path) -> None:
    source, _ = _twoimg(tmp_path / "source.2mg", comment=b"", creator=b"")
    output = tmp_path / "already.raw"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_twoimg_to_raw(source, output)
    with pytest.raises(DiskForgeError, match="differ"):
        export_twoimg_to_raw(source, source)
    assert output.read_bytes() == b"keep"
