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
from diskforge.core.storage import DiskForgeError, sha256_file
from diskforge.core.woz import inspect_woz, is_woz2_header


def _chunk(chunk_id: bytes, payload: bytes) -> bytes:
    return chunk_id + struct.pack("<I", len(payload)) + payload


def _canonical_woz(*, version: int = 2, crc: bool = True, metadata: bytes | None = None) -> bytes:
    info = bytearray(60)
    info[:5] = bytes((version, 1, 1, 0, 1))
    info[5:37] = b"DiskForge".ljust(32, b" ")
    info[37:40] = bytes((1, 1, 32))
    struct.pack_into("<H", info, 44, 1)

    tmap = bytearray([0xFF]) * 160
    tmap[0] = 0
    tracks = bytearray(160 * 8 + 512)
    struct.pack_into("<HHI", tracks, 0, 3, 1, 8)
    tracks[160 * 8:160 * 8 + 1] = b"\x80"
    body = _chunk(b"INFO", bytes(info)) + _chunk(b"TMAP", bytes(tmap)) + _chunk(b"TRKS", bytes(tracks))
    if metadata is not None:
        body += _chunk(b"META", metadata)
    header = b"WOZ2\xff\x0a\x0d\x0a" + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF if crc else 0)
    return header + body


def _write(path: Path, blob: bytes) -> Path:
    path.write_bytes(blob)
    return path


def test_inspect_woz_validates_canonical_woz2_structure(tmp_path: Path) -> None:
    source = _write(tmp_path / "sample.woz", _canonical_woz(metadata=b"title\tExample\nlanguage\tEnglish\n"))

    inspected = inspect_woz(source)

    assert is_woz2_header(source.read_bytes()[:12])
    assert inspected.source == source
    assert inspected.crc_checked is True
    assert inspected.info_version == 2
    assert inspected.disk_type == 1
    assert inspected.disk_sides == 1
    assert inspected.write_protected is True
    assert inspected.creator == "DiskForge"
    assert inspected.metadata_entries == 2
    assert inspected.unknown_chunks == 0
    assert inspected.bit_tracks[0].index == 0
    assert inspected.bit_tracks[0].starting_block == 3
    assert inspected.bit_tracks[0].encoded_count == 8
    assert not inspected.flux_tracks


def test_inspect_woz_accepts_unset_crc_only(tmp_path: Path) -> None:
    source = _write(tmp_path / "unchecked.woz", _canonical_woz(crc=False))

    assert inspect_woz(source).crc_checked is False


def test_inspect_woz_rejects_crc_mismatch(tmp_path: Path) -> None:
    blob = _canonical_woz()
    source = _write(tmp_path / "crc.woz", blob[:-1] + bytes((blob[-1] ^ 1,)))
    with pytest.raises(DiskForgeError, match="CRC-32"):
        inspect_woz(source)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda blob: blob[:12] + _chunk(b"TMAP", bytes(160)) + blob[12:], "INFO must be the first"),
        (lambda blob: blob[:20] + b"\x01" + blob[21:], "INFO versions 2 and 3"),
        (lambda blob: blob[:88] + b"\x01" + blob[89:], "unused TRKS entry"),
        (lambda blob: blob + _chunk(b"META", b"bad-row"), "META must terminate"),
    ],
)
def test_inspect_woz_rejects_malformed_contracts(
    tmp_path: Path,
    mutate,
    match: str,
) -> None:  # type: ignore[no-untyped-def]
    source = _write(tmp_path / "broken.woz", mutate(_canonical_woz(crc=False)))
    with pytest.raises(DiskForgeError, match=match):
        inspect_woz(source)


def test_inspect_woz_rejects_non_woz_suffix(tmp_path: Path) -> None:
    source = _write(tmp_path / "wrong.img", _canonical_woz())
    with pytest.raises(DiskForgeError, match=r"\.woz"):
        inspect_woz(source)


def test_woz_strict_cross_entrypoints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path / "canonical.woz", _canonical_woz(metadata=b"title" + bytes((9,)) + b"Example" + bytes((10,))))
    before = sha256_file(source)
    inspection = inspect_woz(source)

    assert inspect_image(source).image_format == ImageFormat.WOZ
    assert inspect_image(source).writable is False
    assert inventory_images(tmp_path).records[0].image_format == ImageFormat.WOZ
    client = DiskForgeClient()
    assert client.inspect_woz(source) == inspection
    with pytest.raises(DiskForgeError, match="WOZ2 images"):
        client.convert(source, tmp_path / "invalid.img", image_format=ImageFormat.IMG)
    with pytest.raises(DiskForgeError, match="WOZ2 images"):
        with client.filesystem(source):
            pass
    assert main(["--json", "woz-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["info_version"] == 2
    assert report["metadata_entries"] == 1
    assert report["bit_tracks"] == [{"index": 0, "starting_block": 3, "block_count": 1, "bit_count": 8}]
    assert report["flux_tracks"] == []
    with pytest.raises(DiskForgeError, match="WOZ2 images"):
        convert_image(source, tmp_path / "flat.img", ImageFormat.RAW)
    assert sha256_file(source) == before


def test_main_window_routes_woz_to_dedicated_inspector(qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui import main_window as main_window_module
    from diskforge.gui.main_window import MainWindow

    source = _write(tmp_path / "route.woz", _canonical_woz())
    settings = QSettings(str(tmp_path / "woz.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)
    routed: list[Path] = []
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "Disk images"))
    monkeypatch.setattr(window, "inspect_woz_image", lambda value=None: routed.append(value))

    window.open_image()
    assert routed == [source]
