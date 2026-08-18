from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from diskforge.core.filesystems import FatImageFilesystem, IsoImageFilesystem, create_fat_image, create_iso_from_directory
from diskforge.core.formats import create_fixed_vhd, inspect_image
from diskforge.core.models import FileSystemType, ImageFormat
from diskforge.core.partitions import list_partitions
from diskforge.core.selfextract import create_self_extractor
from diskforge.core.storage import sha256_file, stream_copy, verify_equal


def test_fat_image_supports_inject_list_extract_and_listing(tmp_path: Path) -> None:
    image = tmp_path / "sample.img"
    source = tmp_path / "hello.txt"
    source.write_text("hello DiskForge", encoding="utf-8")
    create_fat_image(image, 4 * 1024 * 1024, FileSystemType.FAT12, "TEST")
    fs = FatImageFilesystem(image)
    try:
        inserted = fs.inject([source])
        assert inserted == ["/hello.txt"]
        entries = fs.list_entries("/")
        assert [entry.name for entry in entries] == ["hello.txt"]
        assert inspect_image(image).filesystem == FileSystemType.FAT12
        output = tmp_path / "out"
        extracted = fs.extract(["/hello.txt"], output)
        assert extracted[0].read_text(encoding="utf-8") == "hello DiskForge"
        plain = fs.export_listing(tmp_path / "listing.txt")
        assert "hello.txt" in plain.read_text(encoding="utf-8")
    finally:
        fs.close()


def test_iso_creation_can_be_browsed_and_extracted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "file.txt").write_text("iso payload", encoding="utf-8")
    image = tmp_path / "sample.iso"
    create_iso_from_directory(source, image)
    fs = IsoImageFilesystem(image)
    try:
        children = fs.list_entries("/")
        assert children and children[0].is_dir
        outputs = fs.extract(["/nested"], tmp_path / "extracted")
        assert outputs[0].read_text(encoding="utf-8") == "iso payload"
    finally:
        fs.close()


def test_fixed_vhd_conversion_keeps_payload(tmp_path: Path) -> None:
    source = tmp_path / "payload.img"
    source.write_bytes(b"\0" * 4096)
    vhd = tmp_path / "payload.vhd"
    info = create_fixed_vhd(source, vhd)
    assert info.image_format == ImageFormat.VHD
    assert info.virtual_size == 4096
    assert vhd.stat().st_size == 4096 + 512


def test_stream_copy_hash_and_verify(tmp_path: Path) -> None:
    source = tmp_path / "source.img"
    source.write_bytes(b"A" * 12000)
    destination = tmp_path / "destination.img"
    result = stream_copy(source, destination, operation=__import__("diskforge.core.models", fromlist=["OperationKind"]).OperationKind.CONVERT)
    assert result.bytes_copied == 12000
    assert verify_equal(source, destination)
    assert len(sha256_file(source)) == 64


def test_mbr_partition_parse(tmp_path: Path) -> None:
    image = tmp_path / "mbr.img"
    data = bytearray(4 * 1024 * 1024)
    data[446 + 4] = 0x06
    data[446 + 8:446 + 12] = (1).to_bytes(4, "little")
    data[446 + 12:446 + 16] = (100).to_bytes(4, "little")
    data[510:512] = b"\x55\xaa"
    image.write_bytes(data)
    parts = list_partitions(image)
    assert len(parts) == 1
    assert parts[0].start_lba == 1
    assert parts[0].filesystem == FileSystemType.FAT16


def test_self_extractor_verifies_payload(tmp_path: Path) -> None:
    image = tmp_path / "small.img"
    image.write_bytes(b"self extracting payload")
    package = create_self_extractor(image, tmp_path / "bundle.pyz")
    destination = tmp_path / "unpacked"
    completed = subprocess.run([sys.executable, str(package), str(destination)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert (destination / "small.img").read_bytes() == image.read_bytes()
