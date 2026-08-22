from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ImageFormat
from diskforge.core.pfi import _pfi_crc32, inspect_pfi
from diskforge.core.storage import DiskForgeError, sha256_file


def _chunk(chunk_id: bytes, payload: bytes) -> bytes:
    assert len(chunk_id) == 4
    header = chunk_id + struct.pack(">I", len(payload))
    return header + payload + struct.pack(">I", _pfi_crc32(header + payload))


def _canonical_pfi(*, include_comment: bool = True) -> bytes:
    chunks = [_chunk(b"PFI ", struct.pack(">I", 0))]
    if include_comment:
        chunks.append(_chunk(b"TEXT", b"canonical PFI\n"))
    chunks.extend([
        _chunk(b"TRAK", struct.pack(">III", 0, 0, 500_000)),
        _chunk(b"INDX", struct.pack(">II", 0, 250)),
        _chunk(b"DATA", b"\x08\x01\x00\x01\xFF"),
        _chunk(b"END ", b""),
    ])
    return b"".join(chunks)


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def test_pfi_strict_core_and_cross_entrypoints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path / "canonical.pfi", _canonical_pfi())
    before = sha256_file(source)

    inspection = inspect_pfi(source)
    assert inspection.source == source
    assert inspection.comments == 1
    assert inspection.chunks == 6
    assert len(inspection.tracks) == 1
    track = inspection.tracks[0]
    assert (track.cylinder, track.head, track.clock_rate) == (0, 0, 500_000)
    assert (track.index_count, track.data_chunks, track.data_bytes, track.pulse_count) == (2, 1, 5, 3)
    assert inspect_image(source).image_format == ImageFormat.PFI
    assert inspect_image(source).writable is False
    assert inventory_images(tmp_path).records[0].image_format == ImageFormat.PFI

    client = DiskForgeClient()
    assert client.inspect_pfi(source) == inspection
    with pytest.raises(DiskForgeError, match="flux containers"):
        client.convert(source, tmp_path / "invalid.img", image_format=ImageFormat.IMG)
    with pytest.raises(DiskForgeError):
        with client.filesystem(source):
            pass

    assert main(["--json", "pfi-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["comments"] == 1
    assert report["tracks"] == [{"cylinder": 0, "head": 0, "clock_rate": 500_000, "index_count": 2,
                                  "data_chunks": 1, "data_bytes": 5, "pulse_count": 3}]
    with pytest.raises(DiskForgeError, match="flux containers"):
        convert_image(source, tmp_path / "flat.img", ImageFormat.RAW)
    assert sha256_file(source) == before


@pytest.mark.parametrize(
    ("name", "payload", "message"),
    [
        ("bad-crc.pfi", _canonical_pfi()[:-4] + b"\0\0\0\0", "CRC"),
        ("duplicate-track.pfi", _canonical_pfi()[:-12] + _chunk(b"TRAK", struct.pack(">III", 0, 0, 400_000)) + _chunk(b"END ", b""), "repeats track"),
        ("bad-index.pfi", _chunk(b"PFI ", struct.pack(">I", 0)) + _chunk(b"TRAK", struct.pack(">III", 0, 0, 1)) + _chunk(b"INDX", b"\0\0\0") + _chunk(b"END ", b""), "multiple of four"),
        ("bad-pulse.pfi", _chunk(b"PFI ", struct.pack(">I", 0)) + _chunk(b"TRAK", struct.pack(">III", 0, 0, 1)) + _chunk(b"DATA", b"\x01\0") + _chunk(b"END ", b""), "variable-length pulse"),
        ("missing-end.pfi", _canonical_pfi()[:-12], "missing its final END"),
        ("trailing.pfi", _canonical_pfi() + b"tail", "trailing data"),
    ],
)
def test_pfi_rejects_crc_grammar_and_exact_eof_failures(tmp_path: Path, name: str, payload: bytes, message: str) -> None:
    source = _write(tmp_path / name, payload)
    with pytest.raises(DiskForgeError, match=message):
        inspect_pfi(source)


def test_main_window_routes_pfi_to_dedicated_inspector(qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui import main_window as main_window_module
    from diskforge.gui.main_window import MainWindow

    source = _write(tmp_path / "route.pfi", _canonical_pfi())
    settings = QSettings(str(tmp_path / "pfi.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    routed: list[Path] = []
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "Disk images"))
    monkeypatch.setattr(window, "inspect_pfi_image", lambda value=None: routed.append(value))

    window.open_image()
    assert routed == [source]
