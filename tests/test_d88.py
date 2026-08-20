from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.d88 import export_d88_to_raw, inspect_d88
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _d88(path: Path) -> tuple[Path, bytes]:
    """Create one 0x2A0-header D88 disk with two 256-byte sectors on track 0/head 0."""
    header_bytes = 0x2A0
    payloads = [b"A" * 256, b"B" * 256]
    track = bytearray()
    for record, payload in enumerate(payloads, start=1):
        sector = bytearray(16)
        sector[0:4] = bytes([0, 0, record, 1])
        sector[4:6] = (2).to_bytes(2, "little")
        sector[14:16] = len(payload).to_bytes(2, "little")
        track.extend(sector)
        track.extend(payload)
    header = bytearray(header_bytes)
    header[:8] = b"DiskF0rg"
    header[0x20:0x24] = header_bytes.to_bytes(4, "little")
    header[0x1C:0x20] = (header_bytes + len(track)).to_bytes(4, "little")
    path.write_bytes(header + track)
    return path, b"".join(payloads)


def test_d88_inspects_and_exports_one_proven_track(tmp_path: Path) -> None:
    source, expected = _d88(tmp_path / "disk.d88")
    inspection = inspect_d88(source)
    output = export_d88_to_raw(source, tmp_path / "disk.raw")
    assert inspection.exportable
    assert inspection.raw_bytes == len(expected)
    assert output.read_bytes() == expected


def test_d88_signature_shape_is_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _d88(tmp_path / "container.d88")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.D88
    assert not info.writable
    with pytest.raises(DiskForgeError, match="read-only sector containers"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)


def test_inventory_recognizes_d88_as_read_only_container(tmp_path: Path) -> None:
    source, _ = _d88(tmp_path / "inventory.d88")
    report = inventory_images(tmp_path)
    assert len(report.records) == 1
    assert report.records[0].relative_path == source.name
    assert report.records[0].image_format == ImageFormat.D88
    assert report.records[0].filesystem.value == "Unknown"


def test_cli_inspects_and_exports_strict_d88_raw(tmp_path: Path, capsys) -> None:
    source, expected = _d88(tmp_path / "cli.d88")
    before = sha256_file(source)
    assert main(["--json", "d88-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["exportable"] is True and report["raw_bytes"] == len(expected)
    destination = tmp_path / "cli.raw"
    assert main(["--json", "convert-d88", str(source), str(destination)]) == 0
    assert json.loads(capsys.readouterr().out)["destination"] == str(destination)
    assert destination.read_bytes() == expected and sha256_file(source) == before


def test_sdk_inspects_exports_and_rejects_d88_filesystem_session(tmp_path: Path) -> None:
    source, expected = _d88(tmp_path / "sdk.d88")
    client = DiskForgeClient()
    assert client.inspect_d88(source).exportable
    result = client.export_d88_to_raw(source, tmp_path / "sdk.raw")
    assert result.destination is not None and result.destination.read_bytes() == expected
    with pytest.raises(DiskForgeError, match="read-only sector containers"):
        with client.filesystem(source):
            pass


@pytest.mark.parametrize("offset", [7, 8])
def test_d88_status_or_deleted_sector_is_not_exportable(tmp_path: Path, offset: int) -> None:
    source, _ = _d88(tmp_path / "flagged.d88")
    before = sha256_file(source)
    data = bytearray(source.read_bytes())
    data[0x2A0 + offset] = 0x10
    source.write_bytes(data)
    inspection = inspect_d88(source)
    assert not inspection.exportable
    with pytest.raises(DiskForgeError, match="non-normal"):
        export_d88_to_raw(source, tmp_path / "flagged.raw")
    assert sha256_file(source) != before  # mutation establishes the flagged fixture before inspection.


def test_d88_export_rejects_existing_destination_without_source_mutation(tmp_path: Path) -> None:
    source, _ = _d88(tmp_path / "source.d88")
    before = sha256_file(source)
    destination = tmp_path / "existing.raw"
    destination.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_d88_to_raw(source, destination)
    assert destination.read_bytes() == b"keep"
    assert sha256_file(source) == before


def test_d88_rejects_multidisk_or_trailing_data(tmp_path: Path) -> None:
    source, _ = _d88(tmp_path / "bad.d88")
    source.write_bytes(source.read_bytes() + b"tail")
    with pytest.raises(DiskForgeError, match="multi-disk or trailing"):
        inspect_d88(source)
