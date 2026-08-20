from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.sap import _MAGIC, _sap_crc, export_sap_to_raw, inspect_sap
from diskforge.core.storage import DiskForgeError, sha256_file


def _sap(path: Path, *, protection: int = 0, bad_crc: bool = False, size_code: int = 0) -> tuple[Path, bytes]:
    disk_code = 2  # 40-track single-sided single density
    header = bytes((disk_code,)) + _MAGIC
    raw = bytearray()
    records = bytearray()
    sector_size = {0: 256, 1: 128, 2: 1024, 3: 512}[size_code]
    for cylinder in range(40):
        for sector in range(1, 17):
            data = bytes(((cylinder * 16 + sector) & 0xFF,)) * sector_size
            record_header = bytes((size_code, protection, cylinder, sector))
            crc = _sap_crc(record_header + data)
            if bad_crc and cylinder == 0 and sector == 1:
                crc ^= 0xFFFF
            records.extend(record_header)
            records.extend(byte ^ 0xB3 for byte in data)
            records.extend(crc.to_bytes(2, "big"))
            if size_code == 0:
                raw.extend(data)
    path.write_bytes(header + records)
    return path, bytes(raw)


def test_sap_inspects_and_exports_crc_valid_regular_layout_without_source_change(tmp_path: Path) -> None:
    source, raw = _sap(tmp_path / "normal.sap")
    before = sha256_file(source)
    inspection = inspect_sap(source)
    output = export_sap_to_raw(source, tmp_path / "normal.img")
    assert inspection.exportable and inspection.disk_type.startswith("40-track single density")
    assert inspection.heads == 1 and inspection.tracks_per_side == 40
    assert inspection.crc_error_count == inspection.protected_sector_count == 0
    assert inspection.raw_bytes == len(raw) == 40 * 16 * 256
    assert output.read_bytes() == raw
    assert sha256_file(source) == before


@pytest.mark.parametrize("kwargs, message", [
    ({"protection": 1}, "protected"),
    ({"bad_crc": True}, "CRC errors"),
    ({"size_code": 3}, "256-byte MFM"),
])
def test_sap_inspects_but_rejects_non_regular_layout_for_raw_export(tmp_path: Path, kwargs, message: str) -> None:
    source, _ = _sap(tmp_path / "restricted.sap", **kwargs)
    inspection = inspect_sap(source)
    assert not inspection.exportable
    with pytest.raises(DiskForgeError, match=message):
        export_sap_to_raw(source, tmp_path / "wrong.raw")


def test_sap_rejects_bad_header_and_trailing_data(tmp_path: Path) -> None:
    source, _ = _sap(tmp_path / "bad.sap")
    content = bytearray(source.read_bytes())
    content[1] = 0
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="signature"):
        inspect_sap(source)
    source, _ = _sap(tmp_path / "trailing.sap")
    source.write_bytes(source.read_bytes() + b"tail")
    with pytest.raises(DiskForgeError, match="trailing"):
        inspect_sap(source)


def test_sap_is_signature_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _sap(tmp_path / "container.sap")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.SAP
    assert not info.writable
    with pytest.raises(DiskForgeError, match="CRC-validated SAP"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised, _ = _sap(tmp_path / "not-sap.img")
    assert inspect_image(disguised).image_format != ImageFormat.SAP


def test_sap_inventory_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    source, raw = _sap(tmp_path / "cross-entry.sap")
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.SAP
    assert main(["--json", "sap-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exportable"] and payload["raw_bytes"] == len(raw)
    client = DiskForgeClient()
    assert client.inspect_sap(source).crc_error_count == 0
    output = client.export_sap_to_raw(source, tmp_path / "sdk.raw")
    assert output.destination and output.destination.read_bytes() == raw
    with pytest.raises(DiskForgeError, match="CRC-validated SAP"):
        with client.filesystem(source):
            pass


def test_sap_rejects_existing_or_same_destination(tmp_path: Path) -> None:
    source, _ = _sap(tmp_path / "source.sap")
    output = tmp_path / "already.raw"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_sap_to_raw(source, output)
    with pytest.raises(DiskForgeError, match="differ"):
        export_sap_to_raw(source, source)
    assert output.read_bytes() == b"keep"
