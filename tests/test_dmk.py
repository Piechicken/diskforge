from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.dmk import inspect_dmk
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError


def _dmk(path: Path, *, tracks: int = 2, sides: int = 2, track_length: int = 0x1900,
         flags: int = 0, write_protect: int = 0, malformed: str | None = None) -> Path:
    if sides == 1:
        flags |= 0x10
    header = bytearray(16)
    header[0] = write_protect
    header[1] = tracks
    header[2:4] = track_length.to_bytes(2, "little")
    header[4] = flags
    if malformed == "real-drive":
        header[12:16] = b"\x12\x34\x56\x78"
    if malformed == "reserved":
        header[5] = 1
    body = bytearray()
    for index in range(tracks * sides):
        track = bytearray(track_length)
        if malformed != "empty":
            first, second = 0x80, 0x100
            if malformed == "undefined-flag":
                first |= 0x4000
            elif index % 2:
                first |= 0x8000
            if malformed == "out-of-range":
                first = track_length
            if malformed == "unordered":
                first, second = second, first
            track[0:2] = first.to_bytes(2, "little")
            track[2:4] = second.to_bytes(2, "little")
            if malformed != "out-of-range":
                track[first & 0x3FFF] = 0xFE if malformed != "wrong-mark" else 0x00
            track[second & 0x3FFF] = 0xFE
            if malformed == "noncontiguous":
                track[4:6] = b"\0\0"
                track[6:8] = (0x180).to_bytes(2, "little")
                track[0x180] = 0xFE
        body.extend(track)
    path.write_bytes(header + body + (b"trailing" if malformed == "trailing" else b""))
    return path


def test_dmk_inspects_native_interleaved_tracks_and_idams(tmp_path: Path) -> None:
    source = _dmk(tmp_path / "mixed.dmk", tracks=2, sides=2, flags=0xC0, write_protect=0xFF)

    result = inspect_dmk(source)

    assert (result.tracks, result.sides, result.track_length) == (2, 2, 0x1900)
    assert result.write_protected and result.single_density_size and result.ignore_density
    assert result.source_bytes == 16 + 4 * 0x1900
    assert [item.offset for item in result.track_records] == [16, 16 + 0x1900, 16 + 2 * 0x1900, 16 + 3 * 0x1900]
    assert [item.idam_count for item in result.track_records] == [2, 2, 2, 2]
    assert result.total_idams == 8
    assert result.double_density_idams == 2


@pytest.mark.parametrize("malformed, pattern", [
    ("real-drive", "real-drive"), ("reserved", "reserved"), ("undefined-flag", "bit-14"),
    ("out-of-range", "outside"), ("unordered", "ascending"), ("wrong-mark", "address mark"),
    ("noncontiguous", "contiguous"), ("trailing", "does not exactly match"),
])
def test_dmk_rejects_invalid_native_header_and_idam_layout(tmp_path: Path, malformed: str, pattern: str) -> None:
    source = _dmk(tmp_path / f"{malformed}.dmk", malformed=malformed)

    with pytest.raises(DiskForgeError, match=pattern):
        inspect_dmk(source)


def test_dmk_is_shape_recognized_read_only_and_available_across_safe_entry_points(tmp_path: Path, capsys) -> None:
    source = _dmk(tmp_path / "cross-entry.dmk")
    info = inspect_image(source)
    assert info.image_format == ImageFormat.DMK and not info.writable
    disguised = tmp_path / "cross-entry.img"
    disguised.write_bytes(source.read_bytes())
    assert inspect_image(disguised).image_format != ImageFormat.DMK
    with pytest.raises(DiskForgeError, match="DMK images are read-only"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    report = inventory_images(tmp_path, options=None)
    assert any(record.image_format == ImageFormat.DMK for record in report.records)
    assert main(["--json", "dmk-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tracks"] == 2 and payload["sides"] == 2 and payload["total_idams"] == 8
    client = DiskForgeClient()
    assert client.inspect_dmk(source).total_idams == 8
    with pytest.raises(DiskForgeError, match="DMK images are read-only"):
        with client.filesystem(source):
            pass


def test_dmk_validates_extension_regular_source_and_short_layout(tmp_path: Path) -> None:
    source = _dmk(tmp_path / "single.dmk", tracks=1, sides=1, malformed="empty")
    result = inspect_dmk(source)
    assert result.total_idams == 0 and len(result.track_records) == 1
    wrong_suffix = tmp_path / "single.img"
    wrong_suffix.write_bytes(source.read_bytes())
    with pytest.raises(DiskForgeError, match="extension"):
        inspect_dmk(wrong_suffix)
    source.write_bytes(source.read_bytes()[:-1])
    with pytest.raises(DiskForgeError, match="does not exactly match"):
        inspect_dmk(source)
