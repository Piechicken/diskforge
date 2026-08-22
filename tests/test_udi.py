from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError
from diskforge.core.udi import _udi_crc32, inspect_udi, is_udi_v10_header


def _udi(*, cylinders: int = 1, sides: int = 1, extended: bytes = b"", tracks: list[tuple[int, bytes, bytes]] | None = None) -> bytes:
    tracks = tracks or [(0, b"abc", b"\x05")] * (cylinders * sides)
    assert len(tracks) == cylinders * sides
    payload = bytearray(b"UDI!" + b"\x00\x00\x00\x00" + bytes((0, cylinders - 1, sides - 1, 0)) + len(extended).to_bytes(4, "little"))
    payload.extend(extended)
    for track_type, data, clock in tracks:
        assert len(clock) == (len(data) + 7) // 8
        payload.extend(bytes((track_type,)))
        payload.extend(len(data).to_bytes(2, "little"))
        payload.extend(data)
        payload.extend(clock)
    payload[4:8] = len(payload).to_bytes(4, "little")
    return bytes(payload) + _udi_crc32(bytes(payload)).to_bytes(4, "little")


def test_udi_v10_validates_interleaved_tracks_extensions_and_crc(tmp_path: Path) -> None:
    source = tmp_path / "disk.udi"
    source.write_bytes(_udi(
        cylinders=2, sides=2, extended=b"extension",
        tracks=[
            (0, b"a", b"\x01"), (0, b"bc", b"\x03"),
            (0, b"def", b"\x05"), (0, b"ghij", b"\x0f"),
        ],
    ))

    inspection = inspect_udi(source)

    assert inspection.cylinders == 2
    assert inspection.sides == 2
    assert inspection.extended_header_bytes == len(b"extension")
    assert [(track.cylinder, track.head, track.data_bytes) for track in inspection.tracks] == [
        (0, 0, 1), (0, 1, 2), (1, 0, 3), (1, 1, 4),
    ]
    assert inspection.total_track_bytes == 10
    assert inspection.clock_mark_count == 9
    assert is_udi_v10_header(source.read_bytes()[:16])


@pytest.mark.parametrize("mutate, pattern", [
    (lambda value: value.__setitem__(0, ord("u")), "signature"),
    (lambda value: value.__setitem__(8, 1), "header"),
    (lambda value: value.__setitem__(10, 2), "side count"),
    (lambda value: value.__setitem__(16, 1), "track type"),
    (lambda value: value.__setitem__(22, 0xF8), "unused final bits"),
    (lambda value: value.__setitem__(4, (value[4] + 1) & 0xFF), "declared file size"),
    (lambda value: value.__setitem__(-1, value[-1] ^ 1), "CRC32"),
])
def test_udi_v10_rejects_invalid_header_track_shape_and_crc(tmp_path: Path, mutate, pattern: str) -> None:  # type: ignore[no-untyped-def]
    content = bytearray(_udi())
    mutate(content)
    source = tmp_path / "invalid.udi"
    source.write_bytes(content)

    with pytest.raises(DiskForgeError, match=pattern):
        inspect_udi(source)


def test_udi_v10_is_shape_recognized_read_only_and_available_across_safe_entry_points(tmp_path: Path, capsys) -> None:
    source = tmp_path / "cross-entry.udi"
    source.write_bytes(_udi(cylinders=2, sides=1))

    info = inspect_image(source)
    assert info.image_format == ImageFormat.UDI and not info.writable
    disguised = tmp_path / "cross-entry.img"
    disguised.write_bytes(source.read_bytes())
    assert inspect_image(disguised).image_format != ImageFormat.UDI
    with pytest.raises(DiskForgeError, match="UDI images are read-only"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    report = inventory_images(tmp_path)
    assert any(record.image_format == ImageFormat.UDI for record in report.records)
    assert main(["--json", "udi-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cylinders"] == 2 and payload["sides"] == 1 and len(payload["tracks"]) == 2
    client = DiskForgeClient()
    assert client.inspect_udi(source).total_track_bytes == 6
    with pytest.raises(DiskForgeError, match="UDI images are read-only"):
        with client.filesystem(source):
            pass


def test_udi_v10_rejects_truncated_track_and_trailing_bytes(tmp_path: Path) -> None:
    content = _udi()
    truncated = tmp_path / "truncated.udi"
    truncated.write_bytes(content[:-5])
    with pytest.raises(DiskForgeError):
        inspect_udi(truncated)

    trailing = tmp_path / "trailing.udi"
    trailing.write_bytes(content[:-4] + b"x" + content[-4:])
    with pytest.raises(DiskForgeError, match="declared file size"):
        inspect_udi(trailing)
