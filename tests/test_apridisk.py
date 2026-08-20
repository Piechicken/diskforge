from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.apridisk import export_apridisk_to_raw, inspect_apridisk
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


_MAGIC = b"ACT Apricot disk image\x1a\x04"


def _record(item_type: int, payload: bytes, *, compression: int = 0x9E90,
            head: int = 0, sector: int = 0, cylinder: int = 0) -> bytes:
    return (item_type.to_bytes(4, "little") + compression.to_bytes(2, "little") + (16).to_bytes(2, "little")
            + len(payload).to_bytes(4, "little") + bytes((head, sector)) + cylinder.to_bytes(2, "little") + payload)


def _apridisk(path: Path, *, rle: bool = False, deleted: bool = False) -> tuple[Path, bytes]:
    header = _MAGIC + b"\0" * (128 - len(_MAGIC))
    expected = bytearray()
    records = [_record(0xE31D0003, b"creator"), _record(0xE31D0002, b"first\rsecond\0")]
    if deleted:
        records.append(_record(0xE31D0000, b"old"))
    for cylinder in range(2):
        for head in range(2):
            for sector in range(1, 3):
                value = (cylinder * 32 + head * 16 + sector) & 0xFF
                data = bytes((value,)) * 128
                expected.extend(data)
                if rle:
                    records.append(_record(0xE31D0001, (128).to_bytes(2, "little") + bytes((value,)),
                                           compression=0x3E5A, head=head, sector=sector, cylinder=cylinder))
                else:
                    records.append(_record(0xE31D0001, data, head=head, sector=sector, cylinder=cylinder))
    path.write_bytes(header + b"".join(records))
    return path, bytes(expected)


def test_apridisk_inspects_uncompressed_rectangle_and_exports_sorted_raw(tmp_path: Path) -> None:
    source, raw = _apridisk(tmp_path / "normal.dsk")
    before = sha256_file(source)
    inspection = inspect_apridisk(source)
    output = export_apridisk_to_raw(source, tmp_path / "normal.raw")
    assert inspection.exportable and (inspection.cylinders, inspection.heads, inspection.sectors_per_track) == (2, 2, 2)
    assert inspection.bytes_per_sector == 128 and inspection.raw_bytes == len(raw)
    assert inspection.comment == "first\nsecond" and inspection.creator_data_bytes == 7
    assert output.read_bytes() == raw
    assert sha256_file(source) == before


def test_apridisk_decodes_rle_sectors_before_strict_raw_export(tmp_path: Path) -> None:
    source, raw = _apridisk(tmp_path / "rle.dsk", rle=True)
    inspection = inspect_apridisk(source)
    assert inspection.exportable and all(item.compressed for item in inspection.sectors)
    assert export_apridisk_to_raw(source, tmp_path / "rle.raw").read_bytes() == raw


def test_apridisk_inspects_but_does_not_export_deleted_record_stream(tmp_path: Path) -> None:
    source, _ = _apridisk(tmp_path / "deleted.dsk", deleted=True)
    inspection = inspect_apridisk(source)
    assert not inspection.exportable and inspection.deleted_records == 1
    with pytest.raises(DiskForgeError, match="Deleted"):
        export_apridisk_to_raw(source, tmp_path / "wrong.raw")


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value.__setitem__(0, 0), "signature"),
    (lambda value: value.__setitem__(128 + 6, 17), "extended record headers"),
    (lambda value: value.__setitem__(128 + 4, 0), "compression marker"),
    (lambda value: value.__setitem__(128 + 12, 1), "creator records"),
])
def test_apridisk_rejects_invalid_header_or_record(tmp_path: Path, mutate, message: str) -> None:
    source, _ = _apridisk(tmp_path / "bad.dsk")
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_apridisk(source)


def test_apridisk_is_signature_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _apridisk(tmp_path / "container.dsk")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.APRIDISK
    assert not info.writable
    with pytest.raises(DiskForgeError, match="strict APRIDISK"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised, _ = _apridisk(tmp_path / "not-signed.img")
    assert inspect_image(disguised).image_format != ImageFormat.APRIDISK


def test_apridisk_inventory_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    source, raw = _apridisk(tmp_path / "cross-entry.dsk")
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.APRIDISK
    assert main(["--json", "apridisk-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exportable"] and payload["raw_bytes"] == len(raw)
    client = DiskForgeClient()
    assert client.inspect_apridisk(source).sectors_per_track == 2
    output = client.export_apridisk_to_raw(source, tmp_path / "sdk.raw")
    assert output.destination and output.destination.read_bytes() == raw
    with pytest.raises(DiskForgeError, match="strict APRIDISK"):
        with client.filesystem(source):
            pass


def test_apridisk_rejects_existing_or_same_destination(tmp_path: Path) -> None:
    source, _ = _apridisk(tmp_path / "source.dsk")
    output = tmp_path / "already.raw"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_apridisk_to_raw(source, output)
    with pytest.raises(DiskForgeError, match="differ"):
        export_apridisk_to_raw(source, source)
    assert output.read_bytes() == b"keep"
