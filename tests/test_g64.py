from __future__ import annotations

from pathlib import Path
import json
import struct

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.g64 import inspect_g64, is_g64_header
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


_SIGNATURE = b"GCR-1541"


def _canonical_g64(*, mapped_speed: bool = False, entries: int = 2, stored_bytes: int = 8) -> bytes:
    header_end = 12 + entries * 8
    track_offset = header_end
    track = struct.pack("<H", 3) + b"\xff\x52\x55" + b"\xff" * (stored_bytes - 3)
    speed_map = bytes((0xE4,)) * ((stored_bytes + 3) // 4)
    speed_entry = track_offset + len(track) if mapped_speed else 3
    track_offsets = [track_offset] + [0] * (entries - 1)
    speed_entries = [speed_entry] + [0] * (entries - 1)
    return (
        _SIGNATURE + bytes((0, entries)) + struct.pack("<H", stored_bytes)
        + struct.pack(f"<{entries}I", *track_offsets)
        + struct.pack(f"<{entries}I", *speed_entries)
        + track + (speed_map if mapped_speed else b"")
    )


def _write(path: Path, blob: bytes) -> Path:
    path.write_bytes(blob)
    return path


def test_inspect_g64_validates_constant_speed_track(tmp_path: Path) -> None:
    source = _write(tmp_path / "sample.g64", _canonical_g64())

    inspected = inspect_g64(source)

    assert is_g64_header(source.read_bytes()[:12])
    assert inspected.source == source
    assert inspected.track_entries == 2
    assert inspected.stored_track_bytes == 8
    assert inspected.constant_speed_tracks == 1
    assert inspected.mapped_speed_tracks == 0
    assert inspected.tracks[0].entry_index == 0
    assert inspected.tracks[0].actual_bytes == 3
    assert inspected.tracks[0].speed_kind == "constant"
    assert inspected.tracks[0].speed_zone == 3


def test_inspect_g64_validates_variable_speed_map(tmp_path: Path) -> None:
    source = _write(tmp_path / "mapped.g64", _canonical_g64(mapped_speed=True))

    inspected = inspect_g64(source)

    assert inspected.constant_speed_tracks == 0
    assert inspected.mapped_speed_tracks == 1
    assert inspected.tracks[0].speed_kind == "map"
    assert inspected.tracks[0].speed_zone is None


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda blob: blob[:8] + b"\x01" + blob[9:], "GCR-1541 version-0"),
        (lambda blob: blob[:9] + b"\x00" + blob[10:], "track-entry count"),
        (lambda blob: blob[:10] + struct.pack("<H", 7929) + blob[12:], "stored-track byte size"),
        (lambda blob: blob[:12] + struct.pack("<I", 0) + blob[16:], "empty track"),
        (lambda blob: blob[:-1], "outside source bounds"),
        (lambda blob: blob + b"\x00", "unreferenced trailing"),
    ],
)
def test_inspect_g64_rejects_malformed_contracts(tmp_path: Path, mutate, match: str) -> None:  # type: ignore[no-untyped-def]
    source = _write(tmp_path / "broken.g64", mutate(_canonical_g64()))
    with pytest.raises(DiskForgeError, match=match):
        inspect_g64(source)


def test_inspect_g64_rejects_speed_for_empty_track(tmp_path: Path) -> None:
    blob = bytearray(_canonical_g64())
    struct.pack_into("<I", blob, 12 + 2 * 4 + 4, 2)
    source = _write(tmp_path / "speed-without-track.g64", bytes(blob))

    with pytest.raises(DiskForgeError, match="empty track"):
        inspect_g64(source)


def test_inspect_g64_rejects_overlapping_speed_map(tmp_path: Path) -> None:
    blob = bytearray(_canonical_g64(mapped_speed=True))
    header_end = 12 + 2 * 8
    struct.pack_into("<I", blob, 12 + 2 * 4, header_end)
    source = _write(tmp_path / "overlap.g64", bytes(blob))

    with pytest.raises(DiskForgeError, match="overlap"):
        inspect_g64(source)


def test_inspect_g64_rejects_wrong_suffix(tmp_path: Path) -> None:
    source = _write(tmp_path / "wrong.img", _canonical_g64())
    with pytest.raises(DiskForgeError, match=r"\.g64"):
        inspect_g64(source)


def test_g64_strict_cross_entrypoints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path / "canonical.g64", _canonical_g64(mapped_speed=True))
    before = sha256_file(source)
    inspection = inspect_g64(source)

    assert inspect_image(source).image_format == ImageFormat.G64
    assert inspect_image(source).writable is False
    assert inventory_images(tmp_path).records[0].image_format == ImageFormat.G64
    client = DiskForgeClient()
    assert client.inspect_g64(source) == inspection
    with pytest.raises(DiskForgeError, match="G64 images"):
        client.convert(source, tmp_path / "invalid.img", image_format=ImageFormat.IMG)
    with pytest.raises(DiskForgeError, match="G64 images"):
        with client.filesystem(source):
            pass
    assert main(["--json", "g64-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["track_entries"] == 2
    assert report["constant_speed_tracks"] == 0
    assert report["mapped_speed_tracks"] == 1
    assert report["tracks"] == [{"entry_index": 0, "actual_bytes": 3, "speed_kind": "map", "speed_zone": None}]
    with pytest.raises(DiskForgeError, match="G64 images"):
        convert_image(source, tmp_path / "flat.img", ImageFormat.RAW)
    assert sha256_file(source) == before


def test_main_window_routes_g64_to_dedicated_inspector(qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui import main_window as main_window_module
    from diskforge.gui.main_window import MainWindow

    source = _write(tmp_path / "route.g64", _canonical_g64())
    settings = QSettings(str(tmp_path / "g64.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    routed: list[Path] = []
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "Disk images"))
    monkeypatch.setattr(window, "inspect_g64_image", lambda value=None: routed.append(value))

    window.open_image()
    assert routed == [source]
