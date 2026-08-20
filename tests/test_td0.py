from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.storage import DiskForgeError, sha256_file
from diskforge.core.td0 import _crc16, export_td0_to_raw, inspect_td0


def _header(*, comment: bytes | None = None, signature: bytes = b"TD") -> bytes:
    stepping = 0x80 if comment is not None else 0
    prefix = signature + bytes((0, 0, 0x21, 0, 1, stepping, 0, 1))
    result = prefix + _crc16(prefix).to_bytes(2, "little")
    if comment is None:
        return result
    comment_header = len(comment).to_bytes(2, "little") + bytes((124, 0, 1, 2, 3, 4))
    return result + _crc16(comment_header + comment).to_bytes(2, "little") + comment_header + comment


def _sector(cylinder: int, head: int, number: int, payload: bytes, *, size_code: int = 0,
            flags: int = 0, method: int = 0) -> bytes:
    base = bytes((cylinder, head, number, size_code, flags))
    if flags & 0x30:
        return base + bytes((_crc16(base) & 0xFF,))
    encoded = payload
    data_header = (len(encoded) + 1).to_bytes(2, "little") + bytes((method,))
    return base + bytes((_crc16(base + data_header + encoded) & 0xFF,)) + data_header + encoded


def _track(cylinder: int, head: int, sectors: list[bytes], *, single_density: bool = False) -> bytes:
    raw_head = head | (0x80 if single_density else 0)
    prefix = bytes((len(sectors), cylinder, raw_head))
    return prefix + bytes((_crc16(prefix) & 0xFF,)) + b"".join(sectors)


def _write(path: Path, tracks: list[bytes], *, comment: bytes | None = None, signature: bytes = b"TD") -> Path:
    path.write_bytes(_header(comment=comment, signature=signature) + b"".join(tracks) + b"\xff")
    return path


def test_inspect_and_export_rectangular_td0_without_source_mutation(tmp_path: Path) -> None:
    tracks: list[bytes] = []
    expected = bytearray()
    for cylinder in range(2):
        for head in range(2):
            sectors: list[bytes] = []
            for number in range(1, 3):
                payload = bytes((cylinder * 32 + head * 8 + number,)) * 128
                expected.extend(payload)
                sectors.append(_sector(cylinder, head, number, payload))
            tracks.append(_track(cylinder, head, sectors))
    source = _write(tmp_path / "normal.td0", tracks, comment=b"saved\x00disk")
    before = sha256_file(source)

    inspection = inspect_td0(source)
    assert inspection.comment == "saved\ndisk"
    assert inspection.version == "2.1"
    assert inspection.exportable
    assert (inspection.cylinders, inspection.heads, inspection.sectors_per_track, inspection.bytes_per_sector) == (2, 2, 2, 128)
    destination = export_td0_to_raw(source, tmp_path / "normal.img")

    assert destination.read_bytes() == bytes(expected)
    assert sha256_file(source) == before


def test_td0_reconstructs_repeated_pattern_and_rle_sector_encodings(tmp_path: Path) -> None:
    repeated = (64).to_bytes(2, "little") + b"AB"
    literal = b"\x00\x80" + (b"R" * 128)
    source = _write(tmp_path / "encoded.td0", [
        _track(0, 0, [
            _sector(0, 0, 1, repeated, method=1),
            _sector(0, 0, 2, literal, method=2),
        ]),
    ])
    inspection = inspect_td0(source)
    assert inspection.exportable
    destination = export_td0_to_raw(source, tmp_path / "encoded.img")
    assert destination.read_bytes() == (b"AB" * 64) + (b"R" * 128)


def test_td0_rejects_advanced_compression_and_invalid_crc(tmp_path: Path) -> None:
    advanced = _write(tmp_path / "advanced.td0", [], signature=b"td")
    with pytest.raises(DiskForgeError, match="advanced compression"):
        inspect_td0(advanced)

    corrupt = _write(tmp_path / "corrupt.td0", [_track(0, 0, [_sector(0, 0, 1, b"X" * 128)])])
    bytes_ = bytearray(corrupt.read_bytes())
    bytes_[10] ^= 0x01
    corrupt.write_bytes(bytes_)
    with pytest.raises(DiskForgeError, match="header CRC"):
        inspect_td0(corrupt)


def test_td0_reports_flagged_sector_as_not_exportable_without_flattening(tmp_path: Path) -> None:
    source = _write(tmp_path / "flagged.td0", [
        _track(0, 0, [_sector(0, 0, 1, b"D" * 128, flags=0x02)]),
    ])
    inspection = inspect_td0(source)
    assert not inspection.exportable
    assert "flagged" in inspection.export_reason
    with pytest.raises(DiskForgeError, match="cannot be safely exported"):
        export_td0_to_raw(source, tmp_path / "flagged.img")


def test_td0_rejects_trailing_data_and_existing_export_destination(tmp_path: Path) -> None:
    source = _write(tmp_path / "trailing.td0", [_track(0, 0, [_sector(0, 0, 1, b"T" * 128)])])
    source.write_bytes(source.read_bytes() + b"trailing")
    with pytest.raises(DiskForgeError, match="trailing bytes"):
        inspect_td0(source)

    valid = _write(tmp_path / "valid.td0", [_track(0, 0, [_sector(0, 0, 1, b"V" * 128)])])
    destination = tmp_path / "existing.img"
    destination.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_td0_to_raw(valid, destination)
    assert destination.read_bytes() == b"keep"
