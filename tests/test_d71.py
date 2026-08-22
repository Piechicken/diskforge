from pathlib import Path
import json
import zipfile

import pytest

from diskforge.api import DiskForgeClient
from diskforge.cli import main
from diskforge.core.batch import BatchRunner
from diskforge.core.d71 import D71_SECTOR_SIZE, D71_SIZE_BYTES, inspect_d71, read_d71_file
from diskforge.core.filesystems import D71ImageFilesystem
from diskforge.core.formats import convert_image, inspect_image
from diskforge.core.inventory import inventory_images
from diskforge.core.models import FileSystemType, ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _sectors(track: int) -> int:
    side_track = (track - 1) % 35 + 1
    if side_track <= 17:
        return 21
    if side_track <= 24:
        return 19
    if side_track <= 30:
        return 18
    return 17


def _offset(track: int, sector: int) -> int:
    return (sum(_sectors(number) for number in range(1, track)) + sector) * D71_SECTOR_SIZE


def _sector(data: bytearray, track: int, sector: int) -> memoryview:
    offset = _offset(track, sector)
    return memoryview(data)[offset:offset + D71_SECTOR_SIZE]


def _canonical_d71(*, file_type: int = 0x82, reserve_bam_as_file: bool = False) -> bytearray:
    data = bytearray(D71_SIZE_BYTES)
    used = {(18, 0), (18, 1), (53, 0), (1, 0), (36, 0)}
    bam = _sector(data, 18, 0)
    side1_bam = _sector(data, 53, 0)
    bam[2], bam[3] = 0x41, 0x80
    bam[0x90:0xA0] = b"DISKFORGE".ljust(16, b"\xa0")
    bam[0xA2:0xA4], bam[0xA5:0xA7] = b"DF", b"2A"

    for track in range(1, 71):
        sector_count = _sectors(track)
        bitmap = bytearray(3)
        for sector in range(sector_count):
            if (track, sector) not in used:
                bitmap[sector // 8] |= 1 << (sector % 8)
        count = sum((bitmap[index // 8] >> (index % 8)) & 1 for index in range(sector_count))
        if track <= 35:
            entry = 4 + (track - 1) * 4
            bam[entry], bam[entry + 1:entry + 4] = count, bitmap
        else:
            bam[0xDD + (track - 36)] = count
            entry = (track - 36) * 3
            side1_bam[entry:entry + 3] = bitmap

    directory = _sector(data, 18, 1)
    directory[0], directory[1] = 0, 0xFF
    directory[2:5] = bytes((file_type, 36, 0))
    directory[5:21] = b"SIDEONE".ljust(16, b"\xa0")
    directory[30:32] = (1).to_bytes(2, "little")
    directory[34:37] = bytes((0x81, 1, 0))
    directory[37:53] = b"SIDETWO".ljust(16, b"\xa0")
    directory[62:64] = (1).to_bytes(2, "little")

    side_one = _sector(data, 36, 0)
    side_one[0], side_one[1], side_one[2:6] = 0, 5, b"SIDE"
    side_two = _sector(data, 1, 0)
    side_two[0], side_two[1], side_two[2:6] = 0, 5, b"ZERO"
    if reserve_bam_as_file:
        directory[2:5] = bytes((0x82, 18, 0))
        bam[0], bam[1] = 0, 1
    return data


def _write(tmp_path: Path, data: bytes, name: str = "disk.d71") -> Path:
    source = tmp_path / name
    source.write_bytes(data)
    return source


def test_inspect_d71_double_bam_and_side_one_file_chain(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d71())
    before = sha256_file(source)

    inspection = inspect_d71(source)

    assert inspection.size == D71_SIZE_BYTES
    assert inspection.disk_name == "DISKFORGE"
    assert inspection.disk_id == "DF"
    assert inspection.dos_type == "2A"
    assert inspection.directory_sectors == 1
    assert inspection.free_blocks == 1361
    assert [(item.name, item.start_track, item.file_type) for item in inspection.files] == [
        ("SIDEONE", 36, "PRG"),
        ("SIDETWO", 1, "SEQ"),
    ]
    assert read_d71_file(source, inspection.files[0]) == b"SIDE"
    assert read_d71_file(source, inspection.files[1]) == b"ZERO"
    assert sha256_file(source) == before


@pytest.mark.parametrize("mutator", [
    lambda data: _sector(data, 18, 0).__setitem__(3, 0),
    lambda data: _sector(data, 18, 0).__setitem__(0xDD, _sector(data, 18, 0)[0xDD] + 1),
    lambda data: _sector(data, 53, 0).__setitem__(0, _sector(data, 53, 0)[0] ^ 1),
])
def test_rejects_invalid_double_bam(mutator, tmp_path: Path) -> None:
    data = _canonical_d71()
    mutator(data)
    with pytest.raises(DiskForgeError):
        inspect_d71(_write(tmp_path, data))


def test_rejects_rel_and_system_bam_data_chain(tmp_path: Path) -> None:
    with pytest.raises(DiskForgeError):
        inspect_d71(_write(tmp_path, _canonical_d71(file_type=0x84)))
    with pytest.raises(DiskForgeError):
        inspect_d71(_write(tmp_path, _canonical_d71(reserve_bam_as_file=True)))


def test_rejects_wrong_profile_and_suffix(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d71()[:-1366])
    with pytest.raises(DiskForgeError):
        inspect_d71(source)
    wrong = _write(tmp_path, _canonical_d71(), "disk.img")
    with pytest.raises(DiskForgeError):
        inspect_d71(wrong)


def test_d71_read_only_filesystem_lists_and_extracts(tmp_path: Path) -> None:
    source = _write(tmp_path, _canonical_d71())
    filesystem = D71ImageFilesystem(source)

    entries = filesystem.list_entries()
    assert [(entry.name, entry.size, entry.attributes) for entry in entries] == [
        ("SIDEONE", 4, "PRG"), ("SIDETWO", 4, "SEQ"),
    ]
    destination = tmp_path / "output"
    outputs = filesystem.extract([item.path for item in entries], destination)
    assert [item.name for item in outputs] == ["SIDEONE", "SIDETWO"]
    assert [item.read_bytes() for item in outputs] == [b"SIDE", b"ZERO"]


def test_d71_strict_cross_entrypoints_and_zip_payload(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write(tmp_path, _canonical_d71(), "canonical.d71")
    before = sha256_file(source)
    inspection = inspect_d71(source)
    info = inspect_image(source)

    assert info.image_format == ImageFormat.D71
    assert info.filesystem == FileSystemType.CBM_DOS
    assert info.writable is False
    assert inventory_images(tmp_path).records[0].image_format == ImageFormat.D71
    client = DiskForgeClient()
    assert client.inspect_d71(source) == inspection
    with client.filesystem(source) as filesystem:
        assert isinstance(filesystem, D71ImageFilesystem)
        assert [entry.name for entry in filesystem.list_entries()] == ["SIDEONE", "SIDETWO"]
    with pytest.raises(DiskForgeError, match="read-only"):
        with client.filesystem(source, writable=True):
            pass
    with pytest.raises(DiskForgeError, match="D71 CBM DOS"):
        client.convert(source, tmp_path / "invalid.img", image_format=ImageFormat.IMG)
    with pytest.raises(DiskForgeError, match="D71 CBM DOS"):
        convert_image(source, tmp_path / "flat.img", ImageFormat.RAW)

    assert main(["--json", "d71-info", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["disk_name"] == "DISKFORGE"
    assert report["directory_sectors"] == 1
    assert report["free_blocks"] == 1361
    assert [(item["name"], item["start_track"], item["bytes"]) for item in report["files"]] == [
        ("SIDEONE", 36, 4), ("SIDETWO", 1, 4),
    ]

    runner = BatchRunner()
    with runner._read_only_filesystem(source) as filesystem:
        assert isinstance(filesystem, D71ImageFilesystem)
    with pytest.raises(DiskForgeError, match="read-only"):
        runner._filesystem(source, writable=True)

    archive = tmp_path / "images.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.write(source, arcname="payload.d71")
    with client.filesystem(archive) as filesystem:
        assert isinstance(filesystem, D71ImageFilesystem)
        assert [entry.name for entry in filesystem.list_entries()] == ["SIDEONE", "SIDETWO"]
    assert sha256_file(source) == before


def test_main_window_opens_d71_as_read_only_cbm_dos(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui.main_window import MainWindow

    source = _write(tmp_path, _canonical_d71(), "workspace.d71")
    settings = QSettings(str(tmp_path / "d71.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)

    window._open_path(source)

    assert isinstance(window.current_fs, D71ImageFilesystem)
    assert window.current_info is not None
    assert window.current_info.image_format == ImageFormat.D71
    assert window.current_info.filesystem == FileSystemType.CBM_DOS
    assert window.table.rowCount() == 2
    assert window.action_inject.isEnabled() is False
