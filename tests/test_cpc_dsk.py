from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.cpc_dsk import CpcDskKind, export_cpc_dsk_to_raw, inspect_cpc_dsk
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import CancellationToken, DiskForgeError, OperationCancelled, sha256_file


_STANDARD_SIGNATURE = b"MV - CPCEMU Disk-File\r\nDisk-Info\r\n"
_EXTENDED_SIGNATURE = b"EXTENDED CPC DSK File\r\nDisk-Info\r\n"
_TRACK_SIGNATURE = b"Track-Info\r\n"


def _track_block(
    physical_track: int,
    physical_side: int,
    payloads: list[bytes],
    *,
    kind: CpcDskKind,
    sector_ids: list[int] | None = None,
    status1: int = 0,
    status2: int = 0,
    header_track: int | None = None,
    header_side: int | None = None,
    actual_lengths: list[int] | None = None,
) -> bytes:
    sector_ids = sector_ids or list(range(1, len(payloads) + 1))
    assert len(sector_ids) == len(payloads)
    n = 1
    sector_bytes = 128 << n
    assert all(len(payload) == sector_bytes for payload in payloads)
    actual_lengths = actual_lengths or [sector_bytes] * len(payloads)
    data_bytes = sum(actual_lengths if kind == CpcDskKind.EXTENDED else [sector_bytes] * len(payloads))
    block_bytes = (0x100 + data_bytes + 0xFF) & ~0xFF
    block = bytearray(block_bytes)
    block[:len(_TRACK_SIGNATURE)] = _TRACK_SIGNATURE
    block[0x10] = physical_track if header_track is None else header_track
    block[0x11] = physical_side if header_side is None else header_side
    block[0x14] = n
    block[0x15] = len(payloads)
    cursor = 0x100
    for index, (sector_id, payload, actual) in enumerate(zip(sector_ids, payloads, actual_lengths)):
        descriptor = 0x18 + index * 8
        block[descriptor:descriptor + 6] = bytes([physical_track, physical_side, sector_id, n, status1, status2])
        if kind == CpcDskKind.EXTENDED:
            block[descriptor + 6:descriptor + 8] = actual.to_bytes(2, "little")
            block[cursor:cursor + actual] = payload[:actual]
            cursor += actual
        else:
            block[cursor:cursor + sector_bytes] = payload
            cursor += sector_bytes
    return bytes(block)


def _dsk(path: Path, *, kind: CpcDskKind = CpcDskKind.STANDARD, cylinders: int = 2,
         sides: int = 1, mutate_header=None, mutate_blocks=None) -> tuple[Path, bytes]:
    blocks: list[bytes] = []
    expected = bytearray()
    for cylinder in range(cylinders):
        for side in range(sides):
            payloads = [bytes([0x10 + cylinder * 0x20 + side * 0x08 + sector]) * 256 for sector in range(2)]
            expected.extend(b"".join(payloads))
            blocks.append(_track_block(cylinder, side, payloads, kind=kind))
    if mutate_blocks is not None:
        blocks = mutate_blocks(blocks)
    header = bytearray(0x100)
    header[:34] = _STANDARD_SIGNATURE if kind == CpcDskKind.STANDARD else _EXTENDED_SIGNATURE
    header[0x22:0x30] = b"DiskForgeTest".ljust(14, b" ")
    header[0x30] = cylinders
    header[0x31] = sides
    if kind == CpcDskKind.STANDARD:
        assert len({len(block) for block in blocks}) == 1
        header[0x32:0x34] = len(blocks[0]).to_bytes(2, "little")
    else:
        for index, block in enumerate(blocks):
            header[0x34 + index] = len(block) // 0x100
    if mutate_header is not None:
        mutate_header(header)
    path.write_bytes(bytes(header) + b"".join(blocks))
    return path, bytes(expected)


def test_inspect_and_export_standard_cpc_dsk(tmp_path: Path) -> None:
    source, expected = _dsk(tmp_path / "standard.dsk")
    before = sha256_file(source)

    inspection = inspect_cpc_dsk(source)
    output = export_cpc_dsk_to_raw(source, tmp_path / "standard.raw")

    assert inspection.kind == CpcDskKind.STANDARD
    assert inspection.creator == "DiskForgeTest"
    assert inspection.exportable
    assert (inspection.cylinders, inspection.sides, inspection.sectors_per_track, inspection.bytes_per_sector) == (2, 1, 2, 256)
    assert inspection.raw_bytes == len(expected)
    assert output.read_bytes() == expected
    assert sha256_file(source) == before


def test_extended_cpc_dsk_preserves_physical_cylinder_side_descriptor_order(tmp_path: Path) -> None:
    source, expected = _dsk(tmp_path / "extended.dsk", kind=CpcDskKind.EXTENDED, cylinders=2, sides=2)

    inspection = inspect_cpc_dsk(source)
    output = export_cpc_dsk_to_raw(source, tmp_path / "extended.raw")

    assert inspection.kind == CpcDskKind.EXTENDED
    assert inspection.exportable
    assert [(track.physical_track, track.physical_side) for track in inspection.tracks] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert output.read_bytes() == expected


@pytest.mark.parametrize("mutate_header, mutate_blocks, message", [
    (lambda header: header.__setitem__(slice(0, 8), b"NOT-DSK!"), None, "signature"),
    (lambda header: header.__setitem__(0x30, 0), None, "cylinder count"),
    (lambda header: header.__setitem__(0x31, 3), None, "side count"),
    (lambda header: header.__setitem__(slice(0x32, 0x34), (0x400).to_bytes(2, "little")), None, "exactly match"),
])
def test_cpc_dsk_rejects_invalid_header_or_declared_file_extent(
    tmp_path: Path, mutate_header, mutate_blocks, message: str,
) -> None:
    source, _ = _dsk(tmp_path / "invalid.dsk", mutate_header=mutate_header, mutate_blocks=mutate_blocks)
    with pytest.raises(DiskForgeError, match=message):
        inspect_cpc_dsk(source)


def test_cpc_dsk_rejects_unformatted_extended_track_slot(tmp_path: Path) -> None:
    source, _ = _dsk(
        tmp_path / "unformatted.dsk", kind=CpcDskKind.EXTENDED,
        mutate_header=lambda header: header.__setitem__(0x34, 0),
    )
    with pytest.raises(DiskForgeError, match="unformatted"):
        inspect_cpc_dsk(source)


@pytest.mark.parametrize("mutate_blocks, message", [
    (lambda blocks: [bytes(bytearray(blocks[0][:0x1C]) + b"\x01" + blocks[0][0x1D:]), *blocks[1:]], "nonzero controller status"),
    (lambda blocks: [bytes(bytearray(blocks[0][:0x22]) + b"\x01" + blocks[0][0x23:]), *blocks[1:]], "consecutive"),
    (lambda blocks: [bytes(bytearray(blocks[0][:0x10]) + b"\x07" + blocks[0][0x11:]), *blocks[1:]], "Track-Info coordinate"),
])
def test_cpc_dsk_inspection_reports_nonexportable_structural_layouts(
    tmp_path: Path, mutate_blocks, message: str,
) -> None:
    source, _ = _dsk(tmp_path / "nonexportable.dsk", mutate_blocks=mutate_blocks)
    inspection = inspect_cpc_dsk(source)
    assert not inspection.exportable
    with pytest.raises(DiskForgeError, match=message):
        export_cpc_dsk_to_raw(source, tmp_path / "out.raw")


def test_extended_cpc_dsk_rejects_short_sector_data_for_raw_export(tmp_path: Path) -> None:
    def short_sector(blocks: list[bytes]) -> list[bytes]:
        block = bytearray(blocks[0])
        block[0x1E:0x20] = (128).to_bytes(2, "little")
        return [bytes(block), *blocks[1:]]

    source, _ = _dsk(tmp_path / "short.dsk", kind=CpcDskKind.EXTENDED, mutate_blocks=short_sector)
    inspection = inspect_cpc_dsk(source)
    assert not inspection.exportable
    assert "short" in inspection.export_reason


def test_cpc_dsk_format_is_signature_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source, _ = _dsk(tmp_path / "container.dsk", kind=CpcDskKind.EXTENDED)
    info = inspect_image(source)
    assert info.image_format == ImageFormat.CPC_DSK
    assert not info.writable
    with pytest.raises(DiskForgeError, match="read-only sector containers"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)


def test_inventory_recognizes_signed_cpc_dsk_as_read_only_container(tmp_path: Path) -> None:
    source, _ = _dsk(tmp_path / "inventory.dsk")
    report = inventory_images(tmp_path)
    assert len(report.records) == 1
    record = report.records[0]
    assert record.relative_path == source.name
    assert record.image_format == ImageFormat.CPC_DSK
    assert record.filesystem.value == "Unknown"


def test_cli_inspects_and_exports_strict_cpc_dsk_raw(tmp_path: Path, capsys) -> None:
    source, expected = _dsk(tmp_path / "cli.dsk", kind=CpcDskKind.EXTENDED)
    before = sha256_file(source)
    assert main(["--json", "cpc-dsk-info", str(source)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["kind"] == "extended"
    assert inspection["exportable"] is True
    assert inspection["raw_bytes"] == len(expected)

    destination = tmp_path / "cli.raw"
    assert main(["--json", "convert-cpc-dsk", str(source), str(destination)]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["destination"] == str(destination)
    assert destination.read_bytes() == expected
    assert sha256_file(source) == before


def test_sdk_inspects_exports_and_rejects_cpc_dsk_filesystem_session(tmp_path: Path) -> None:
    source, expected = _dsk(tmp_path / "sdk.dsk")
    client = DiskForgeClient()
    inspection = client.inspect_cpc_dsk(source)
    assert inspection.exportable
    output = client.export_cpc_dsk_to_raw(source, tmp_path / "sdk.raw")
    assert output.destination is not None and output.destination.read_bytes() == expected
    with pytest.raises(DiskForgeError, match="read-only sector containers"):
        with client.filesystem(source):
            pass


def test_cpc_dsk_export_rejects_existing_same_path_and_cancellation(tmp_path: Path) -> None:
    source, _ = _dsk(tmp_path / "source.dsk")
    existing = tmp_path / "existing.raw"
    existing.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_cpc_dsk_to_raw(source, existing)
    with pytest.raises(DiskForgeError, match="differ"):
        export_cpc_dsk_to_raw(source, source)
    token = CancellationToken()
    token.cancel()
    cancelled = tmp_path / "cancelled.raw"
    with pytest.raises(OperationCancelled):
        export_cpc_dsk_to_raw(source, cancelled, token)
    assert not cancelled.exists()
