from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.scp import inspect_scp, is_scp_floppy_header
from diskforge.core.storage import DiskForgeError


def _track(index: int, *, revolutions: int = 1, malformed: str | None = None) -> bytes:
    header_bytes = 4 + 12 * revolutions
    content = bytearray(b"TRK" + bytes((index,)))
    flux_offset = header_bytes
    for revolution in range(revolutions):
        offset = header_bytes if malformed == "overlap" and revolution else flux_offset
        words = 4
        content.extend((8_000_000 + revolution).to_bytes(4, "little"))
        content.extend(words.to_bytes(4, "little"))
        content.extend(offset.to_bytes(4, "little"))
        flux_offset += 2 * words
    for revolution in range(revolutions):
        content.extend(bytes((index, revolution)) * 4)
    return bytes(content)


def _scp(*, heads: int = 1, start: int = 0, end: int = 0, revolutions: int = 1,
         flags: int = 0, malformed: str | None = None) -> bytes:
    indices = list(range(start, end + 1))
    if heads == 1:
        indices = [index for index in indices if index % 2 == 0]
    elif heads == 2:
        indices = [index for index in indices if index % 2 == 1]
    tracks = [(index, _track(index, revolutions=revolutions, malformed=malformed)) for index in indices]
    content = bytearray(0x2B0)
    content[:3] = b"SCP"
    content[3] = 0x25
    content[4] = 0x30
    content[5] = revolutions
    content[6:8] = bytes((start, end))
    content[8] = flags
    content[9] = 0
    content[10] = heads
    content[11] = 0
    offset = 0x2B0
    for index, track in tracks:
        content[0x10 + index * 4:0x14 + index * 4] = offset.to_bytes(4, "little")
        content.extend(track)
        offset += len(track)
    content[12:16] = (sum(content[0x10:]) & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(content)


def test_scp_validates_standard_track_table_and_flux_ranges(tmp_path: Path) -> None:
    source = tmp_path / "capture.scp"
    source.write_bytes(_scp(heads=0, start=0, end=1, revolutions=2))

    inspection = inspect_scp(source)

    assert inspection.revolutions_per_track == 2
    assert inspection.heads == 0 and inspection.resolution_ns == 25
    assert [(track.logical_index, track.cylinder, track.head, len(track.revolutions)) for track in inspection.tracks] == [
        (0, 0, 0, 2), (1, 0, 1, 2),
    ]
    assert inspection.total_flux_bytes == 32
    assert is_scp_floppy_header(source.read_bytes()[:16])


@pytest.mark.parametrize("mutate, pattern", [
    (lambda value: value.__setitem__(0, ord("X")), "header"),
    (lambda value: value.__setitem__(5, 0), "header"),
    (lambda value: value.__setitem__(8, 0x10), "header"),
    (lambda value: value.__setitem__(9, 8), "header"),
    (lambda value: value.__setitem__(-1, value[-1] ^ 1), "checksum"),
])
def test_scp_rejects_invalid_standard_header_and_checksum(tmp_path: Path, mutate, pattern: str) -> None:  # type: ignore[no-untyped-def]
    content = bytearray(_scp())
    mutate(content)
    source = tmp_path / "invalid.scp"
    source.write_bytes(content)

    with pytest.raises(DiskForgeError, match=pattern):
        inspect_scp(source)


def test_scp_rejects_bad_track_header_overlap_and_truncation(tmp_path: Path) -> None:
    bad_header = bytearray(_scp())
    bad_header[0x2B0:0x2B3] = b"BAD"
    bad_header[12:16] = (sum(bad_header[0x10:]) & 0xFFFFFFFF).to_bytes(4, "little")
    source = tmp_path / "bad-header.scp"
    source.write_bytes(bad_header)
    with pytest.raises(DiskForgeError, match="marker"):
        inspect_scp(source)

    overlap = tmp_path / "overlap.scp"
    overlap.write_bytes(_scp(revolutions=2, malformed="overlap"))
    with pytest.raises(DiskForgeError, match="overlap"):
        inspect_scp(overlap)

    truncated = tmp_path / "truncated.scp"
    truncated.write_bytes(_scp()[:-1])
    with pytest.raises(DiskForgeError):
        inspect_scp(truncated)


def test_scp_is_shape_recognized_read_only_and_available_across_safe_entry_points(tmp_path: Path, capsys) -> None:
    source = tmp_path / "cross-entry.scp"
    source.write_bytes(_scp(heads=0, start=0, end=1))

    info = inspect_image(source)
    assert info.image_format == ImageFormat.SCP and not info.writable
    disguised = tmp_path / "cross-entry.img"
    disguised.write_bytes(source.read_bytes())
    assert inspect_image(disguised).image_format != ImageFormat.SCP
    with pytest.raises(DiskForgeError, match="SCP images are read-only"):
        convert_image(source, tmp_path / "wrong.raw", ImageFormat.RAW)
    report = inventory_images(tmp_path)
    assert any(record.image_format == ImageFormat.SCP for record in report.records)
    assert main(["--json", "scp-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["revolutions_per_track"] == 1 and len(payload["tracks"]) == 2 and payload["total_flux_bytes"] == 16
    client = DiskForgeClient()
    assert client.inspect_scp(source).total_flux_bytes == 16
    with pytest.raises(DiskForgeError, match="SCP images are read-only"):
        with client.filesystem(source):
            pass


def test_scp_requires_extension(tmp_path: Path) -> None:
    source = tmp_path / "capture.img"
    source.write_bytes(_scp())
    with pytest.raises(DiskForgeError, match="extension"):
        inspect_scp(source)
