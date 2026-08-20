from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.pri import inspect_pri
from diskforge.core.psi import _crc32c_nonreflected
from diskforge.core.storage import DiskForgeError, sha256_file


def _chunk(chunk_id: bytes, payload: bytes) -> bytes:
    header = chunk_id + len(payload).to_bytes(4, "big")
    return header + payload + _crc32c_nonreflected(payload, _crc32c_nonreflected(header)).to_bytes(4, "big")


def _pri(path: Path, *, missing_data: bool = False) -> Path:
    content = bytearray(_chunk(b"PRI ", b"\0\0\0\0"))
    for cylinder, head in ((0, 0), (0, 1)):
        bits, clock = 16, 250_000
        content.extend(_chunk(b"TRAK", cylinder.to_bytes(4, "big") + head.to_bytes(4, "big") + bits.to_bytes(4, "big") + clock.to_bytes(4, "big")))
        if not missing_data or head == 0:
            content.extend(_chunk(b"DATA", bytes((cylinder + head + 0xA5, 0x5A))))
        content.extend(_chunk(b"FUZZ", (2).to_bytes(4, "big") + (1).to_bytes(4, "big")))
        content.extend(_chunk(b"BCLK", (3).to_bytes(4, "big") + (125_000).to_bytes(4, "big")))
        content.extend(_chunk(b"WEAK", (4).to_bytes(4, "big") + (0xFF).to_bytes(4, "big")))
    content.extend(_chunk(b"TEXT", b"\nbitstream metadata\n"))
    content.extend(_chunk(b"END ", b""))
    path.write_bytes(content)
    return path


def test_pri_inspects_checksums_bitstream_tracks_events_and_source_remains_unchanged(tmp_path: Path) -> None:
    source = _pri(tmp_path / "normal.pri")
    before = sha256_file(source)
    inspection = inspect_pri(source)
    assert len(inspection.tracks) == inspection.complete_data_track_count == 2
    assert inspection.total_bits == 32 and (inspection.clock_min_hz, inspection.clock_max_hz) == (250_000, 250_000)
    assert (inspection.fuzz_event_count, inspection.clock_event_count, inspection.weak_event_count) == (2, 2, 2)
    assert sha256_file(source) == before


def test_pri_reports_tracks_without_data_but_never_claims_raw_export(tmp_path: Path) -> None:
    inspection = inspect_pri(_pri(tmp_path / "missing-data.pri", missing_data=True))
    assert len(inspection.tracks) == 2 and inspection.complete_data_track_count == 1
    assert not inspection.tracks[1].data_present


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value.__setitem__(0, 0), "CRC"),
    (lambda value: value.extend(b"tail"), "trailing"),
])
def test_pri_rejects_bad_crc_or_layout(tmp_path: Path, mutate, message: str) -> None:
    source = _pri(tmp_path / "bad.pri")
    content = bytearray(source.read_bytes())
    mutate(content)
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match=message):
        inspect_pri(source)


def test_pri_rejects_event_outside_track_bit_range_after_rechecksumming(tmp_path: Path) -> None:
    source = _pri(tmp_path / "bad-event.pri")
    content = bytearray(source.read_bytes())
    chunk_start = content.index(b"FUZZ")
    content[chunk_start + 8:chunk_start + 12] = (16).to_bytes(4, "big")
    header_and_payload = bytes(content[chunk_start:chunk_start + 16])
    content[chunk_start + 16:chunk_start + 20] = _crc32c_nonreflected(header_and_payload).to_bytes(4, "big")
    source.write_bytes(content)
    with pytest.raises(DiskForgeError, match="outside"):
        inspect_pri(source)


def test_pri_is_signature_recognized_read_only_and_not_generically_convertible(tmp_path: Path) -> None:
    source = _pri(tmp_path / "container.pri")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.PRI
    assert not info.writable
    with pytest.raises(DiskForgeError, match="bitstream containers"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    disguised = tmp_path / "not-pri.img"
    disguised.write_bytes(source.read_bytes())
    assert inspect_image(disguised).image_format != ImageFormat.PRI


def test_pri_inventory_cli_sdk_and_filesystem_contract(tmp_path: Path, capsys) -> None:
    source = _pri(tmp_path / "cross-entry.pri")
    report = inventory_images(tmp_path)
    assert report.records[0].image_format == ImageFormat.PRI
    assert main(["--json", "pri-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["track_count"] == 2 and payload["total_bits"] == 32
    client = DiskForgeClient()
    assert client.inspect_pri(source).weak_event_count == 2
    with pytest.raises(DiskForgeError, match="bitstream containers"):
        with client.filesystem(source):
            pass


def test_pri_rejects_duplicate_track_and_requires_pri_suffix(tmp_path: Path) -> None:
    source = _pri(tmp_path / "duplicate.pri")
    content = source.read_bytes()
    first_track = content.index(b"TRAK")
    second_track = content.index(b"TRAK", first_track + 4)
    changed = bytearray(content)
    changed[second_track + 8:second_track + 16] = changed[first_track + 8:first_track + 16]
    header_and_payload = bytes(changed[second_track:second_track + 24])
    changed[second_track + 24:second_track + 28] = _crc32c_nonreflected(header_and_payload).to_bytes(4, "big")
    source.write_bytes(changed)
    with pytest.raises(DiskForgeError, match="duplicate"):
        inspect_pri(source)
    wrong = tmp_path / "not-pri.img"
    wrong.write_bytes(_pri(tmp_path / "copy.pri").read_bytes())
    with pytest.raises(DiskForgeError, match="extension"):
        inspect_pri(wrong)
