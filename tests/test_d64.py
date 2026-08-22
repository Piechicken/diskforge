from __future__ import annotations

from pathlib import Path
import json
import zipfile

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.batch import BatchRunner
from diskforge.core.d64 import D64_SIZE_BYTES, D64_SECTOR_SIZE, inspect_d64, read_d64_file
from diskforge.core.filesystems import D64ImageFilesystem
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import ConflictPolicy, ExtractionPolicy, FileSystemType, ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _sectors(track: int) -> int:
    if track <= 17:
        return 21
    if track <= 24:
        return 19
    if track <= 30:
        return 18
    return 17


def _offset(track: int, sector: int) -> int:
    return (sum(_sectors(number) for number in range(1, track)) + sector) * D64_SECTOR_SIZE


def _sector(data: bytearray, track: int, sector: int) -> memoryview:
    offset = _offset(track, sector)
    return memoryview(data)[offset:offset + D64_SECTOR_SIZE]


def _canonical_d64(*, blocks: int = 1, file_type: int = 0x82, final_used: int = 8,
                   name: bytes = b"HELLO") -> bytearray:
    data = bytearray(D64_SIZE_BYTES)
    bam = _sector(data, 18, 0)
    bam[2] = 0x41
    bam[0x90:0xA0] = b"DISKFORGE".ljust(16, b"\xa0")
    bam[0xA2:0xA4] = b"DF"
    bam[0xA5:0xA7] = b"2A"
    for track in range(1, 36):
        bam[4 + (track - 1) * 4] = _sectors(track)

    directory = _sector(data, 18, 1)
    directory[0], directory[1] = 0, 0xFF
    directory[2] = file_type
    directory[3], directory[4] = (1, 0) if blocks else (0, 0)
    directory[5:21] = name.ljust(16, b"\xa0")
    directory[30:32] = blocks.to_bytes(2, "little")
    if blocks:
        payload = b"PAYLOAD"
        file_sector = _sector(data, 1, 0)
        file_sector[0], file_sector[1] = 0, final_used
        file_sector[2:2 + len(payload)] = payload
    return data


def _write(tmp_path: Path, data: bytes, name: str = "disk.d64") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_inspect_standard_d64_and_read_file(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d64())
    before = sha256_file(source)

    inspection = inspect_d64(source)

    assert inspection.size == D64_SIZE_BYTES
    assert inspection.disk_name == "DISKFORGE"
    assert inspection.disk_id == "DF"
    assert inspection.dos_type == "2A"
    assert inspection.directory_sectors == 1
    assert inspection.free_blocks == 683
    assert inspection.file_count == 1
    entry = inspection.files[0]
    assert entry.name == "HELLO"
    assert entry.path == "/001-HELLO"
    assert entry.file_type == "PRG"
    assert entry.closed is True
    assert entry.size == 7
    assert entry.attributes == "PRG"
    assert read_d64_file(source, entry) == b"PAYLOAD"
    assert sha256_file(source) == before


def test_d64_read_only_filesystem_lists_pages_and_extracts(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d64())
    before = sha256_file(source)
    filesystem = D64ImageFilesystem(source)

    entries = filesystem.list_entries()
    page = filesystem.list_entries_page(limit=1)
    assert [(entry.path, entry.name, entry.size, entry.attributes) for entry in entries] == [
        ("/001-HELLO", "HELLO", 7, "PRG"),
    ]
    assert page.total == 1
    assert page.entries == tuple(entries)
    with pytest.raises(FileNotFoundError):
        filesystem.list_entries("/not-a-directory")

    destination = tmp_path / "output"
    outputs = filesystem.extract([entries[0].path], destination)
    assert outputs == [destination / "HELLO"]
    assert outputs[0].read_bytes() == b"PAYLOAD"
    with pytest.raises(FileExistsError):
        filesystem.extract([entries[0].path], destination)
    renamed = filesystem.extract(
        [entries[0].path], destination,
        policy=ExtractionPolicy(conflict=ConflictPolicy.RENAME),
    )
    assert renamed == [destination / "HELLO-2"]
    assert renamed[0].read_bytes() == b"PAYLOAD"
    assert sha256_file(source) == before


def test_d64_strict_cross_entrypoints_and_zip_payload(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path, _canonical_d64(), "canonical.d64")
    before = sha256_file(source)
    inspection = inspect_d64(source)
    info = inspect_image(source)

    assert info.image_format == ImageFormat.D64
    assert info.filesystem == FileSystemType.CBM_DOS
    assert info.writable is False
    assert inventory_images(tmp_path).records[0].image_format == ImageFormat.D64
    client = DiskForgeClient()
    assert client.inspect_d64(source) == inspection
    with client.filesystem(source) as filesystem:
        assert isinstance(filesystem, D64ImageFilesystem)
        assert [entry.name for entry in filesystem.list_entries()] == ["HELLO"]
    with pytest.raises(DiskForgeError, match="read-only"):
        with client.filesystem(source, writable=True):
            pass
    with pytest.raises(DiskForgeError, match="D64 CBM DOS"):
        client.convert(source, tmp_path / "invalid.img", image_format=ImageFormat.IMG)
    with pytest.raises(DiskForgeError, match="D64 CBM DOS"):
        convert_image(source, tmp_path / "flat.img", ImageFormat.RAW)

    assert main(["--json", "d64-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["disk_name"] == "DISKFORGE"
    assert report["directory_sectors"] == 1
    assert report["free_blocks"] == 683
    assert report["files"] == [{
        "index": 1, "path": "/001-HELLO", "name": "HELLO", "type": "PRG",
        "locked": False, "closed": True, "blocks": 1, "bytes": 7,
        "start_track": 1, "start_sector": 0,
    }]

    runner = BatchRunner()
    with runner._read_only_filesystem(source) as filesystem:
        assert isinstance(filesystem, D64ImageFilesystem)
    with pytest.raises(DiskForgeError, match="read-only"):
        runner._filesystem(source, writable=True)

    archive = tmp_path / "images.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.write(source, arcname="payload.d64")
    with client.filesystem(archive) as filesystem:
        assert isinstance(filesystem, D64ImageFilesystem)
        assert filesystem.list_entries()[0].name == "HELLO"
    assert sha256_file(source) == before


def test_main_window_opens_d64_as_read_only_cbm_dos(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui.main_window import MainWindow

    source = _write(tmp_path, _canonical_d64(), "workspace.d64")
    settings = QSettings(str(tmp_path / "d64.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)

    window._open_path(source)

    assert isinstance(window.current_fs, D64ImageFilesystem)
    assert window.current_info is not None
    assert window.current_info.filesystem == FileSystemType.CBM_DOS
    assert window.table.rowCount() == 1
    assert window.action_inject.isEnabled() is False


def test_petscii_name_is_safe_and_locked_state_is_reported(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d64(file_type=0xC1, name=b"A/B\\C"))

    entry = inspect_d64(source).files[0]

    assert entry.name == "A∕B⧵C"
    assert entry.path == "/001-A∕B⧵C"
    assert entry.attributes == "SEQ, locked"


def test_zero_block_entry_is_readable_as_empty_file(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d64(blocks=0))

    entry = inspect_d64(source).files[0]

    assert entry.size == 0
    assert entry.chain == ()
    assert read_d64_file(source, entry) == b""


@pytest.mark.parametrize("name", ["disk.img", "disk.d64"])
def test_d64_requires_suffix_and_exact_standard_size(tmp_path: Path, name: str) -> None:
    source = _write(tmp_path, b"", name)

    with pytest.raises(DiskForgeError):
        inspect_d64(source)


def test_d64_rejects_directory_loop(tmp_path: Path) -> None:
    data = _canonical_d64()
    directory = _sector(data, 18, 1)
    directory[0], directory[1] = 18, 1

    with pytest.raises(DiskForgeError, match="directory chain contains a loop"):
        inspect_d64(_write(tmp_path, data))


def test_d64_rejects_rel_and_mismatched_file_block_count(tmp_path: Path) -> None:
    rel = _canonical_d64(file_type=0x84)
    with pytest.raises(DiskForgeError, match="REL"):
        inspect_d64(_write(tmp_path, rel, "rel.d64"))

    mismatch = _canonical_d64(blocks=2)
    with pytest.raises(DiskForgeError, match="block count"):
        inspect_d64(_write(tmp_path, mismatch, "mismatch.d64"))


def test_d64_rejects_invalid_final_length_and_bam_count(tmp_path: Path) -> None:
    invalid_final = _canonical_d64(final_used=0)
    with pytest.raises(DiskForgeError, match="used-byte count"):
        inspect_d64(_write(tmp_path, invalid_final, "final.d64"))

    invalid_bam = _canonical_d64()
    _sector(invalid_bam, 18, 0)[4] = 22
    with pytest.raises(DiskForgeError, match="free-sector count"):
        inspect_d64(_write(tmp_path, invalid_bam, "bam.d64"))
