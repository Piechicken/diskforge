from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.psi import _crc32c_nonreflected, export_psi_to_raw, inspect_psi
from diskforge.core.storage import DiskForgeError, sha256_file


def _chunk(chunk_id: bytes, payload: bytes) -> bytes:
    header = chunk_id + len(payload).to_bytes(4, "big")
    return header + payload + _crc32c_nonreflected(payload, _crc32c_nonreflected(header)).to_bytes(4, "big")


def _psi(path: Path, *, compressed: bool = False, metadata: bool = False) -> tuple[Path, bytes]:
    content = bytearray(_chunk(b"PSI ", b"\0\0\x02\0"))
    raw = bytearray()
    for cylinder in range(2):
        for head in range(2):
            for sector in range(1, 3):
                value = (cylinder * 32 + head * 8 + sector) & 0xFF
                data = bytes((value,)) * 128 if compressed and sector == 1 else bytes((value,)) * 64 + bytes((value ^ 0xFF,)) * 64
                flags = 1 if compressed and sector == 1 else 0
                payload = cylinder.to_bytes(2, "big") + bytes((head, sector)) + len(data).to_bytes(2, "big") + bytes((flags, value))
                content.extend(_chunk(b"SECT", payload))
                if metadata:
                    size_index = 0
                    content.extend(_chunk(b"IBMM", bytes((cylinder, head, sector, size_index, 0, 0))))
                    content.extend(_chunk(b"TIME", b"\0\0\0\0"))
                if not flags:
                    content.extend(_chunk(b"DATA", data))
                raw.extend(data)
    content.extend(_chunk(b"END ", b""))
    path.write_bytes(content)
    return path, bytes(raw)


def test_psi_inspects_crc_valid_standard_chunks_and_exports_rectangular_raw_without_source_change(tmp_path: Path) -> None:
    source, raw = _psi(tmp_path / "normal.psi", metadata=True)
    before = sha256_file(source)
    inspection = inspect_psi(source)
    output = export_psi_to_raw(source, tmp_path / "normal.img")
    assert inspection.exportable and inspection.default_format == 0x0200
    assert len(inspection.sectors) == 8 and inspection.metadata_chunk_count == 16
    assert inspection.raw_bytes == len(raw) and output.read_bytes() == raw
    assert sha256_file(source) == before


def test_psi_decodes_compressed_fill_sectors(tmp_path: Path) -> None:
    source, raw = _psi(tmp_path / "compressed.psi", compressed=True)
    inspection = inspect_psi(source)
    assert inspection.compressed_sector_count == 4
    assert export_psi_to_raw(source, tmp_path / "compressed.raw").read_bytes() == raw


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value.__setitem__(0, 0), "CRC"),
    (lambda value: value.extend(b"tail"), "trailing"),
])
def test_psi_rejects_invalid_chunk_crc_or_layout(tmp_path: Path, mutate, message: str) -> None:
    source, _ = _psi(tmp_path / "bad.psi")
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_psi(source)


def test_psi_rejects_unsupported_sector_flags_after_rechecksumming_chunk(tmp_path: Path) -> None:
    source, _ = _psi(tmp_path / "bad-flags.psi")
    content = bytearray(source.read_bytes())
    chunk_start = content.index(b"SECT")
    content[chunk_start + 14] = 0x04
    header_and_payload = bytes(content[chunk_start:chunk_start + 16])
    content[chunk_start + 16:chunk_start + 20] = _crc32c_nonreflected(header_and_payload).to_bytes(4, "big")
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="flag set"):
        inspect_psi(source)


def test_psi_is_signature_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _psi(tmp_path / "container.psi")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.PSI
    assert not info.writable
    with pytest.raises(DiskForgeError, match="block-validated RAW"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised, _ = _psi(tmp_path / "not-psi.img")
    assert inspect_image(disguised).image_format != ImageFormat.PSI


def test_psi_inventory_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    source, raw = _psi(tmp_path / "cross-entry.psi", compressed=True)
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.PSI
    assert main(["--json", "psi-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exportable"] and payload["raw_bytes"] == len(raw)
    client = DiskForgeClient()
    assert client.inspect_psi(source).compressed_sector_count == 4
    output = client.export_psi_to_raw(source, tmp_path / "sdk.raw")
    assert output.destination and output.destination.read_bytes() == raw
    with pytest.raises(DiskForgeError, match="block-validated RAW"):
        with client.filesystem(source):
            pass


def test_psi_rejects_missing_data_and_existing_or_same_destination(tmp_path: Path) -> None:
    source, _ = _psi(tmp_path / "missing.psi")
    content = source.read_bytes()
    data_index = content.index(b"DATA")
    data_chunk_size = 8 + int.from_bytes(content[data_index + 4:data_index + 8], "big") + 4
    source.write_bytes(content[:data_index] + content[data_index + data_chunk_size:])
    with pytest.raises(DiskForgeError, match="missing"):
        inspect_psi(source)
    source, _ = _psi(tmp_path / "source.psi")
    output = tmp_path / "already.raw"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_psi_to_raw(source, output)
    with pytest.raises(DiskForgeError, match="differ"):
        export_psi_to_raw(source, source)
    assert output.read_bytes() == b"keep"
