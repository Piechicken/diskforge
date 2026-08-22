from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.a2r import inspect_a2r, is_a2r3_header
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


_HEADER = b"A2R3\xff\x0a\x0d\x0a"


def _chunk(chunk_id: bytes, payload: bytes) -> bytes:
    assert len(chunk_id) == 4
    return chunk_id + struct.pack("<I", len(payload)) + payload


def _info(*, drive_type: int = 1) -> bytes:
    creator = b"DiskForge tests".ljust(32, b" ")
    return bytes((1,)) + creator + bytes((drive_type, 0, 1, 0))


def _rwcp(*, terminate: bool = True, reserved: bytes = b"\0" * 11) -> bytes:
    capture = b"C" + bytes((1,)) + struct.pack("<H", 0) + bytes((1,)) + struct.pack("<I", 250) + struct.pack("<I", 3) + b"\x10\x20\x30"
    return bytes((1,)) + struct.pack("<I", 62_500) + reserved + capture + (b"X" if terminate else b"")


def _slvd(*, location: int = 1) -> bytes:
    track = b"T" + struct.pack("<H", location) + bytes((0, 0)) + b"\0" * 6 + bytes((1,)) + struct.pack("<I", 500) + struct.pack("<I", 2) + b"\x40\x50"
    return bytes((2,)) + struct.pack("<I", 62_500) + b"\0" * 6 + track + b"X"


def _canonical_a2r(*, metadata: bytes = b"title\tExample\n") -> bytes:
    return _HEADER + _chunk(b"INFO", _info()) + _chunk(b"RWCP", _rwcp()) + _chunk(b"SLVD", _slvd()) + _chunk(b"META", metadata)


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def test_a2r3_strict_core_accepts_bounded_capture_and_solved_flux(tmp_path: Path) -> None:
    source = _write(tmp_path / "canonical.a2r", _canonical_a2r())
    inspection = inspect_a2r(source)

    assert is_a2r3_header(source.read_bytes()[:8])
    assert inspection.source == source
    assert inspection.chunks == 4
    assert inspection.creator == "DiskForge tests"
    assert inspection.drive_type == 1
    assert inspection.synchronized is True
    assert inspection.raw_capture_chunks == 1
    assert inspection.solved_flux_chunks == 1
    assert inspection.metadata_entries == 1
    assert inspection.captures[0].location == 0
    assert inspection.captures[0].data_bytes == 3
    assert inspection.solved_tracks[0].location == 1
    assert inspection.solved_tracks[0].data_bytes == 2


@pytest.mark.parametrize(
    ("name", "payload", "message"),
    [
        ("a2r2.a2r", b"A2R2\xff\x0a\x0d\x0a" + _chunk(b"INFO", _info()), "A2R3 signature"),
        ("bad-first.a2r", _HEADER + _chunk(b"META", b"title\tExample\n") + _chunk(b"INFO", _info()), "begin with exactly one"),
        ("bad-rwcp.a2r", _HEADER + _chunk(b"INFO", _info()) + _chunk(b"RWCP", _rwcp(reserved=b"\x01" + b"\0" * 10)), "reserved header"),
        ("unterminated-rwcp.a2r", _HEADER + _chunk(b"INFO", _info()) + _chunk(b"RWCP", _rwcp(terminate=False)), "final X"),
        ("duplicate-slvd.a2r", _HEADER + _chunk(b"INFO", _info()) + _chunk(b"SLVD", _slvd(location=2)) + _chunk(b"SLVD", _slvd(location=2)), "repeats solved-track"),
        ("duplicate-meta.a2r", _HEADER + _chunk(b"INFO", _info()) + _chunk(b"META", b"title\tA\ntitle\tB\n"), "repeats key"),
        ("trailing.a2r", _canonical_a2r() + b"tail", "chunk header"),
    ],
)
def test_a2r3_rejects_noncanonical_structure(tmp_path: Path, name: str, payload: bytes, message: str) -> None:
    source = _write(tmp_path / name, payload)
    with pytest.raises(DiskForgeError, match=message):
        inspect_a2r(source)


def test_a2r3_requires_a2r_suffix(tmp_path: Path) -> None:
    source = _write(tmp_path / "wrong.img", _canonical_a2r())
    with pytest.raises(DiskForgeError, match=r"\.a2r"):
        inspect_a2r(source)


def test_a2r3_strict_cross_entrypoints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path / "canonical.a2r", _canonical_a2r())
    before = sha256_file(source)
    inspection = inspect_a2r(source)

    assert inspect_image(source).image_format == ImageFormat.A2R
    assert inspect_image(source).writable is False
    assert inventory_images(tmp_path).records[0].image_format == ImageFormat.A2R
    client = DiskForgeClient()
    assert client.inspect_a2r(source) == inspection
    with pytest.raises(DiskForgeError, match="A2R3 images"):
        client.convert(source, tmp_path / "invalid.img", image_format=ImageFormat.IMG)
    with pytest.raises(DiskForgeError, match="A2R3 images"):
        with client.filesystem(source):
            pass
    assert main(["--json", "a2r-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["drive_type"] == 1
    assert report["metadata_entries"] == 1
    assert report["captures"] == [{"location": 0, "type": 1, "index_signals": 1, "data_bytes": 3}]
    assert report["solved_tracks"] == [{"location": 1, "index_signals": 1, "data_bytes": 2, "mirror_outward": 0, "mirror_inward": 0}]
    with pytest.raises(DiskForgeError, match="A2R3 images"):
        convert_image(source, tmp_path / "flat.img", ImageFormat.RAW)
    assert sha256_file(source) == before


def test_main_window_routes_a2r_to_dedicated_inspector(qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui import main_window as main_window_module
    from diskforge.gui.main_window import MainWindow

    source = _write(tmp_path / "route.a2r", _canonical_a2r())
    settings = QSettings(str(tmp_path / "a2r.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    routed: list[Path] = []
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "Disk images"))
    monkeypatch.setattr(window, "inspect_a2r_image", lambda value=None: routed.append(value))

    window.open_image()
    assert routed == [source]
