from __future__ import annotations

from pathlib import Path
import json
import struct
import zlib

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.p64 import inspect_p64, is_p64_header
from diskforge.core.storage import DiskForgeError, sha256_file


_SIGNATURE = b"P64-1541"


def _chunk(chunk_id: bytes, payload: bytes) -> bytes:
    return chunk_id + struct.pack("<II", len(payload), zlib.crc32(payload) & 0xFFFFFFFF) + payload


def _container(*chunks: bytes, flags: int = 0) -> bytes:
    stream = b"".join(chunks)
    return _SIGNATURE + struct.pack("<III", 0, flags, len(stream)) + struct.pack("<I", zlib.crc32(stream) & 0xFFFFFFFF) + stream


def _track(index_byte: int = 2, *, pulses: int = 4, encoded: bytes = b"\0\0\0\0") -> bytes:
    payload = struct.pack("<II", pulses, len(encoded)) + encoded
    return _chunk(b"HTP" + bytes([index_byte]), payload)


def _valid() -> bytes:
    return _container(_track(), _track(0x82), _chunk(b"DONE", b""), flags=1)


def _write(tmp_path: Path, payload: bytes, name: str = "capture.p64") -> Path:
    source = tmp_path / name
    source.write_bytes(payload)
    return source


def _reheader(blob: bytes, stream: bytes) -> bytes:
    return blob[:16] + struct.pack("<I", len(stream)) + struct.pack("<I", zlib.crc32(stream) & 0xFFFFFFFF) + stream


def test_p64_header_and_valid_structure(tmp_path: Path) -> None:
    source = _write(tmp_path, _valid())

    inspection = inspect_p64(source)

    assert is_p64_header(source.read_bytes()[:24])
    assert inspection.flags == 1
    assert inspection.chunks == 3
    assert [(track.half_track_index, track.side, track.pulses, track.encoded_bytes) for track in inspection.tracks] == [
        (2, 0, 4, 4),
        (2, 1, 4, 4),
    ]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda blob: b"NOT-P64!" + blob[8:], "P64-1541"),
        (lambda blob: blob[:8] + struct.pack("<I", 1) + blob[12:], "version-0"),
        (lambda blob: blob[:16] + struct.pack("<I", 4) + blob[20:], "chunk-stream size"),
        (lambda blob: blob[:12] + struct.pack("<I", 0x4) + blob[16:], "reserved"),
    ],
)
def test_p64_rejects_header_contract_violations(tmp_path: Path, mutate, message: str) -> None:
    with pytest.raises(DiskForgeError, match=message):
        inspect_p64(_write(tmp_path, mutate(_valid())))


def test_p64_rejects_bad_whole_stream_crc(tmp_path: Path) -> None:
    blob = bytearray(_valid())
    blob[20] ^= 0x80

    with pytest.raises(DiskForgeError, match="chunk-stream CRC"):
        inspect_p64(_write(tmp_path, bytes(blob)))


def test_p64_rejects_bad_chunk_crc_after_valid_global_crc(tmp_path: Path) -> None:
    blob = _valid()
    stream = bytearray(blob[24:])
    stream[8] ^= 0x01

    with pytest.raises(DiskForgeError, match="chunk .* CRC"):
        inspect_p64(_write(tmp_path, _reheader(blob, bytes(stream))))


def test_p64_rejects_duplicate_coordinate(tmp_path: Path) -> None:
    payload = _container(_track(2), _track(2), _chunk(b"DONE", b""))

    with pytest.raises(DiskForgeError, match="repeats"):
        inspect_p64(_write(tmp_path, payload))


def test_p64_rejects_invalid_range_stream_shape(tmp_path: Path) -> None:
    bad_payload = struct.pack("<II", 1, 3) + b"\0\0\0"
    payload = _container(_chunk(b"HTP\x02", bad_payload), _chunk(b"DONE", b""))

    with pytest.raises(DiskForgeError, match="too short"):
        inspect_p64(_write(tmp_path, payload))


def test_p64_rejects_range_size_mismatch(tmp_path: Path) -> None:
    bad_payload = struct.pack("<II", 1, 5) + b"\0\0\0\0"
    payload = _container(_chunk(b"HTP\x02", bad_payload), _chunk(b"DONE", b""))

    with pytest.raises(DiskForgeError, match="does not match"):
        inspect_p64(_write(tmp_path, payload))


def test_p64_rejects_unsupported_chunk_and_nonempty_done(tmp_path: Path) -> None:
    unknown = _container(_chunk(b"TEXT", b"x"), _chunk(b"DONE", b""))
    nonempty_done = _container(_track(), _chunk(b"DONE", b"x"))

    with pytest.raises(DiskForgeError, match="unsupported chunk"):
        inspect_p64(_write(tmp_path, unknown))
    with pytest.raises(DiskForgeError, match="DONE chunk"):
        inspect_p64(_write(tmp_path, nonempty_done, "done.p64"))


def test_p64_rejects_missing_done_and_trailing_data(tmp_path: Path) -> None:
    missing = _container(_track())
    trailing = _container(_track(), _chunk(b"DONE", b""), _chunk(b"HTP\x03", struct.pack("<II", 1, 4) + b"\0\0\0\0"))

    with pytest.raises(DiskForgeError, match="missing"):
        inspect_p64(_write(tmp_path, missing))
    with pytest.raises(DiskForgeError, match="trailing"):
        inspect_p64(_write(tmp_path, trailing, "trailing.p64"))


def test_p64_rejects_zero_pulse_count(tmp_path: Path) -> None:
    payload = _container(_track(pulses=0), _chunk(b"DONE", b""))

    with pytest.raises(DiskForgeError, match="pulse count"):
        inspect_p64(_write(tmp_path, payload))


def test_p64_strict_cross_entrypoints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path, _valid(), "canonical.p64")
    before = sha256_file(source)
    inspection = inspect_p64(source)

    assert inspect_image(source).image_format == ImageFormat.P64
    assert inspect_image(source).writable is False
    assert inventory_images(tmp_path).records[0].image_format == ImageFormat.P64
    client = DiskForgeClient()
    assert client.inspect_p64(source) == inspection
    with pytest.raises(DiskForgeError, match="P64 images"):
        client.convert(source, tmp_path / "invalid.img", image_format=ImageFormat.IMG)
    with pytest.raises(DiskForgeError, match="P64 images"):
        with client.filesystem(source):
            pass
    assert main(["--json", "p64-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["flags"] == 1
    assert report["chunks"] == 3
    assert report["tracks"] == [
        {"half_track_index": 2, "side": 0, "pulses": 4, "encoded_bytes": 4},
        {"half_track_index": 2, "side": 1, "pulses": 4, "encoded_bytes": 4},
    ]
    with pytest.raises(DiskForgeError, match="P64 images"):
        convert_image(source, tmp_path / "flat.img", ImageFormat.RAW)
    assert sha256_file(source) == before


def test_main_window_routes_p64_to_dedicated_inspector(qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui import main_window as main_window_module
    from diskforge.gui.main_window import MainWindow

    source = _write(tmp_path, _valid(), "route.p64")
    settings = QSettings(str(tmp_path / "p64.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    routed: list[Path] = []
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "Disk images"))
    monkeypatch.setattr(window, "inspect_p64_image", lambda value=None: routed.append(value))

    window.open_image()
    assert routed == [source]
