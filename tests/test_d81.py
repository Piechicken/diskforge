import json
import zipfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.batch import BatchRunner
from diskforge.core.d81 import (D81_SECTOR_SIZE, D81_SIZE_BYTES, inspect_d81,
                                read_d81_file)
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import ImageInventoryOptions, inventory_images
from diskforge.core.models import FileSystemType, ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file
from diskforge.gui.main_window import MainWindow


def _offset(track: int, sector: int) -> int:
    return ((track - 1) * 40 + sector) * D81_SECTOR_SIZE


def _sector(data: bytearray, track: int, sector: int) -> memoryview:
    offset = _offset(track, sector)
    return memoryview(data)[offset:offset + D81_SECTOR_SIZE]


def _set_used(data: bytearray, track: int, sector: int) -> None:
    bam = _sector(data, 40, 1 if track <= 40 else 2)
    entry = 0x10 + ((track - 1) % 40) * 6
    bit = 1 << (sector % 8)
    bitmap_offset = entry + 1 + sector // 8
    if bam[bitmap_offset] & bit:
        bam[bitmap_offset] &= ~bit
        bam[entry] -= 1


def _canonical_d81() -> bytearray:
    data = bytearray(D81_SIZE_BYTES)
    header = _sector(data, 40, 0)
    header[0:4] = bytes((40, 3, 0x44, 0))
    header[4:20] = b"DISKFORGE".ljust(16, b"\xa0")
    header[0x16:0x18] = b"ID"
    header[0x18:0x1B] = bytes((0xA0, ord("3"), ord("D")))

    for bam_sector, link in ((1, (40, 2)), (2, (0, 0xFF))):
        bam = _sector(data, 40, bam_sector)
        bam[0:4] = bytes((*link, 0x44, 0xBB))
        bam[4:6] = b"ID"
        for local_track in range(40):
            entry = 0x10 + local_track * 6
            bam[entry] = 40
            bam[entry + 1:entry + 6] = b"\xff" * 5

    directory = _sector(data, 40, 3)
    directory[0:5] = bytes((0, 0xFF, 0x82, 41, 0))
    directory[5:21] = b"SIDEONE".ljust(16, b"\xa0")
    directory[30:32] = (1).to_bytes(2, "little")
    file_sector = _sector(data, 41, 0)
    file_sector[0:6] = bytes((0, 5)) + b"ZERO"

    for location in ((40, 0), (40, 1), (40, 2), (40, 3), (41, 0)):
        _set_used(data, *location)
    return data


def _write(tmp_path: Path, data: bytes, name: str = "canonical.d81") -> Path:
    source = tmp_path / name
    source.write_bytes(data)
    return source


def test_d81_strictly_reads_double_sided_bam_and_ordinary_file(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d81())
    before = sha256_file(source)

    inspection = inspect_d81(source)

    assert inspection.size == D81_SIZE_BYTES
    assert inspection.disk_name == "DISKFORGE"
    assert inspection.disk_id == "ID"
    assert inspection.dos_type == "3D"
    assert inspection.directory_sectors == 1
    assert inspection.free_blocks == 3195
    assert [(item.name, item.file_type, item.start_track, item.size) for item in inspection.files] == [
        ("SIDEONE", "PRG", 41, 4),
    ]
    assert read_d81_file(source, inspection.files[0]) == b"ZERO"
    assert sha256_file(source) == before


@pytest.mark.parametrize("name", ["disk.img", "short.d81"])
def test_d81_requires_suffix_and_exact_size(tmp_path: Path, name: str) -> None:
    with pytest.raises(DiskForgeError):
        inspect_d81(_write(tmp_path, b"", name))


def test_d81_rejects_bam_count_and_required_free_sector(tmp_path: Path) -> None:
    count = _canonical_d81()
    _sector(count, 40, 1)[0x10] -= 1
    with pytest.raises(DiskForgeError, match="count"):
        inspect_d81(_write(tmp_path, count, "count.d81"))

    free_system = _canonical_d81()
    bam = _sector(free_system, 40, 1)
    bam[0x10 + (40 - 1) * 6] += 1
    bam[0x10 + (40 - 1) * 6 + 1] |= 1
    with pytest.raises(DiskForgeError, match="required"):
        inspect_d81(_write(tmp_path, free_system, "system.d81"))


def test_d81_rejects_noncanonical_directory_and_rel(tmp_path: Path) -> None:
    extended = _canonical_d81()
    _sector(extended, 40, 3)[0:2] = bytes((39, 0))
    with pytest.raises(DiskForgeError, match="canonical linear"):
        inspect_d81(_write(tmp_path, extended, "extended.d81"))

    rel = _canonical_d81()
    _sector(rel, 40, 3)[2] = 0x84
    with pytest.raises(DiskForgeError, match="REL"):
        inspect_d81(_write(tmp_path, rel, "rel.d81"))


def test_d81_cross_entry_read_only_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path, _canonical_d81())
    before = sha256_file(source)

    info = inspect_image(source)
    assert info.image_format == ImageFormat.D81
    assert info.filesystem == FileSystemType.CBM_DOS
    assert info.writable is False

    inventory = inventory_images(tmp_path, ImageInventoryOptions(include_sha256=True))
    record = next(item for item in inventory.records if item.relative_path == source.name)
    assert record.image_format == ImageFormat.D81
    assert record.filesystem == FileSystemType.CBM_DOS
    assert record.sha256 == before

    client = DiskForgeClient()
    sdk = client.inspect_d81(source)
    assert sdk.files == inspect_d81(source).files
    with client.filesystem(source) as filesystem:
        entries = filesystem.list_entries("/")
        assert [(entry.name, entry.size) for entry in entries] == [("SIDEONE", 4)]
        output = filesystem.extract([entries[0].path], tmp_path / "sdk-out")
    assert output[0].read_bytes() == b"ZERO"
    with pytest.raises(DiskForgeError, match="read-only"):
        with client.filesystem(source, writable=True):
            pass

    assert main(["--json", "d81-info", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bytes"] == D81_SIZE_BYTES
    assert payload["free_blocks"] == 3195
    assert payload["files"] == [{"index": 1, "path": "/001-SIDEONE", "name": "SIDEONE",
                                  "type": "PRG", "locked": False, "closed": True, "blocks": 1,
                                  "bytes": 4, "start_track": 41, "start_sector": 0}]

    batch_filesystem = BatchRunner._filesystem(source)
    try:
        assert [entry.name for entry in batch_filesystem.list_entries("/")] == ["SIDEONE"]
    finally:
        batch_filesystem.close()

    with pytest.raises(DiskForgeError, match="read-only"):
        convert_image(source, tmp_path / "converted.img", ImageFormat.IMG)

    archive = tmp_path / "canonical.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as handle:
        handle.write(source, arcname="payload.d81")
    with client.filesystem(archive) as filesystem:
        assert [entry.name for entry in filesystem.list_entries("/")] == ["SIDEONE"]
    assert sha256_file(source) == before


def test_d81_gui_direct_open_is_read_only(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d81())
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window._open_path(source)
        assert window.current_info is not None
        assert window.current_info.image_format == ImageFormat.D81
        assert window.current_fs is not None and window.current_fs.read_only
        assert [entry.name for entry in window.current_fs.list_entries("/")] == ["SIDEONE"]
    finally:
        window.close()
        app.processEvents()
