from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.imd import export_imd_to_raw, inspect_imd
from diskforge.core.storage import DiskForgeError, sha256_file


def _imd(description: bytes, tracks: list[bytes]) -> bytes:
    return b"IMD " + description + b"\x1a" + b"".join(tracks)


def _track(cylinder: int, head: int, sector_size_code: int, numbers: bytes,
           records: list[tuple[int, bytes]]) -> bytes:
    assert len(numbers) == len(records)
    payload = bytes((0, cylinder, head, len(numbers), sector_size_code)) + numbers
    for data_type, data in records:
        payload += bytes((data_type,)) + data
    return payload


def test_imd_inspection_and_proven_raw_export_preserve_source(tmp_path: Path) -> None:
    first_sector = bytes(range(128))
    source = tmp_path / "uniform.imd"
    source.write_bytes(_imd(
        b"1.18 test\r\n",
        [_track(0, 0, 0, b"\x01\x02", [(1, first_sector), (2, b"Z")])],
    ))
    before = sha256_file(source)

    inspection = inspect_imd(source)
    assert inspection.description == "IMD 1.18 test\r\n"
    assert inspection.exportable
    assert (inspection.cylinders, inspection.heads, inspection.sectors_per_track, inspection.bytes_per_sector) == (1, 1, 2, 128)
    assert inspection.raw_bytes == 256

    destination = tmp_path / "uniform.img"
    assert export_imd_to_raw(source, destination) == destination
    assert destination.read_bytes() == first_sector + b"Z" * 128
    assert sha256_file(source) == before


@pytest.mark.parametrize("source_bytes,reason", [
    (b"IMD incomplete", "missing its 0x1A"),
    (_imd(b"x", [_track(0, 0, 0, b"\x01", [(3, bytes(128))])]), "missing, deleted, or bad"),
    (_imd(b"x", [bytes((0, 0, 0x80, 1, 0)) + b"\x01\x00\x01" + bytes(128)]), "optional cylinder/head maps"),
    (_imd(b"x", [
        _track(0, 0, 0, b"\x01", [(1, bytes(128))]),
        _track(1, 1, 0, b"\x01", [(1, bytes(128))]),
    ]), "rectangular CHS"),
])
def test_imd_unsafe_or_ambiguous_layouts_are_not_exportable(
    tmp_path: Path, source_bytes: bytes, reason: str,
) -> None:
    source = tmp_path / "unsafe.imd"
    source.write_bytes(source_bytes)
    if source_bytes.startswith(b"IMD incomplete"):
        with pytest.raises(DiskForgeError, match=reason):
            inspect_imd(source)
        return
    inspection = inspect_imd(source)
    assert inspection.exportable is False
    assert reason in inspection.export_reason
    with pytest.raises(DiskForgeError, match="cannot be safely exported"):
        export_imd_to_raw(source, tmp_path / "blocked.img")


def test_imd_rejects_trailing_data_duplicate_tracks_and_existing_output(tmp_path: Path) -> None:
    normal = _track(0, 0, 0, b"\x01", [(1, bytes(128))])
    trailing = tmp_path / "trailing.imd"
    trailing.write_bytes(_imd(b"x", [normal]) + b"\x00")
    with pytest.raises(DiskForgeError, match="track header"):
        inspect_imd(trailing)

    duplicate = tmp_path / "duplicate.imd"
    duplicate.write_bytes(_imd(b"x", [normal, normal]))
    with pytest.raises(DiskForgeError, match="duplicate"):
        inspect_imd(duplicate)

    source = tmp_path / "valid.imd"
    source.write_bytes(_imd(b"x", [normal]))
    destination = tmp_path / "already.img"
    destination.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_imd_to_raw(source, destination)
    assert destination.read_bytes() == b"keep"
