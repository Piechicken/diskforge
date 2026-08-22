from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.api import API_VERSION, DiskForgeClient
from diskforge.core.models import FileSystemType
from diskforge.core.storage import DiskForgeError, sha256_file


def test_public_api_can_create_inject_extract_and_inspect(tmp_path: Path) -> None:
    client = DiskForgeClient()
    image = tmp_path / "api.img"
    created = client.create_fat(image, size_bytes=32 * 1024 * 1024, filesystem=FileSystemType.FAT16, label="API")
    source = tmp_path / "payload.txt"
    source.write_text("public API", encoding="utf-8")
    injected = client.inject(image, [source])
    extracted = client.extract(image, injected, tmp_path / "out")
    assert API_VERSION == "1.1"
    assert created.destination == image
    assert extracted[0].read_text(encoding="utf-8") == "public API"
    assert client.inspect(image).filesystem == FileSystemType.FAT16


def test_public_api_rejects_writable_iso_session(tmp_path: Path) -> None:
    client = DiskForgeClient()
    iso = tmp_path / "empty.iso"
    iso.write_bytes(b"not an iso")
    with pytest.raises(DiskForgeError, match="No filesystem facade"):
        with client.filesystem(iso, writable=True):
            pass


def test_public_api_v11_exposes_safe_iso_replacement_and_read_only_mount_capability(tmp_path: Path) -> None:
    from diskforge.core.filesystems import create_iso_from_directory

    client = DiskForgeClient()
    tree = tmp_path / "source"
    tree.mkdir()
    (tree / "payload.txt").write_bytes(b"original")
    source = tmp_path / "source.iso"
    create_iso_from_directory(tree, source)
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"updated!")
    destination = tmp_path / "replaced.iso"

    result = client.replace_iso_file(source, "/PAYLOAD.TXT", replacement, destination)

    assert API_VERSION == "1.1"
    assert result.operation == "replace_iso_file"
    assert result.destination == destination
    capability = client.mount_capability()
    assert capability.read_only is True
    assert isinstance(capability.available, bool)



def test_public_api_moves_fat_directory_tree_and_rejects_source_tree_target(tmp_path: Path) -> None:
    client = DiskForgeClient()
    image = tmp_path / "move-api.img"
    client.create_fat(image, size_bytes=8 * 1024 * 1024, filesystem=FileSystemType.FAT16, label="MOVEAPI")
    tree = tmp_path / "tree"
    nested = tree / "nested"
    nested.mkdir(parents=True)
    (tree / "payload.txt").write_text("SDK move payload", encoding="utf-8")
    (nested / "child.txt").write_text("SDK move child", encoding="utf-8")
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "placeholder.txt").write_text("directory anchor", encoding="utf-8")
    client.inject(image, [tree, archive])

    assert client.move_fat(image, "/tree", "/archive") == "/archive/tree"
    output = client.extract(image, ["/archive/tree/payload.txt", "/archive/tree/nested/child.txt"], tmp_path / "out")
    assert [item.read_text(encoding="utf-8") for item in output] == ["SDK move payload", "SDK move child"]
    with pytest.raises(DiskForgeError, match="inside the source"):
        client.move_fat(image, "/archive", "/archive/tree")



def test_public_api_reads_zip_image_container_and_rejects_writable_session(tmp_path: Path) -> None:
    import zipfile

    client = DiskForgeClient()
    image = tmp_path / "inside.img"
    client.create_fat(image, size_bytes=8 * 1024 * 1024, filesystem=FileSystemType.FAT16, label="ZIPAPI")
    payload = tmp_path / "payload.txt"
    payload.write_text("SDK ZIP payload", encoding="utf-8")
    client.inject(image, [payload])
    archive = tmp_path / "inside.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as container:
        container.write(image, image.name)

    with client.filesystem(archive) as filesystem:
        assert [entry.name for entry in filesystem.list_entries("/")] == ["payload.txt"]
    extracted = client.extract(archive, ["/payload.txt"], tmp_path / "out")
    assert extracted[0].read_text(encoding="utf-8") == "SDK ZIP payload"
    with pytest.raises(DiskForgeError, match="read-only"):
        with client.filesystem(archive, writable=True):
            pass
    with pytest.raises(DiskForgeError, match="read-only"):
        client.inject(archive, [payload])



def test_public_api_lists_and_recovers_conservative_deleted_fat_candidate(tmp_path: Path) -> None:
    from diskforge.core.fat_recovery import _layout
    from diskforge.core.storage import sha256_file

    client = DiskForgeClient()
    image = tmp_path / "deleted-api.img"
    client.create_fat(image, size_bytes=8 * 1024 * 1024, filesystem=FileSystemType.FAT16, label="RECOVER")
    payload = tmp_path / "SHORT.TXT"
    payload.write_bytes(b"SDK deleted-file recovery payload")
    client.inject(image, [payload])
    layout = _layout(image, 0)
    for slot in range(layout.root_directory_entries):
        with image.open("r+b") as handle:
            handle.seek(layout.root_directory_offset + slot * 32)
            entry = handle.read(32)
            if entry[:11] != b"SHORT   TXT":
                continue
            cluster = int.from_bytes(entry[26:28], "little")
            handle.seek(layout.root_directory_offset + slot * 32)
            handle.write(b"\xe5")
            copies = (layout.root_directory_offset - layout.first_fat_offset) // layout.fat_bytes
            for copy_index in range(copies):
                handle.seek(layout.first_fat_offset + copy_index * layout.fat_bytes + cluster * 2)
                handle.write(b"\x00\x00")
            break
    else:
        raise AssertionError("expected injected root entry")
    before = sha256_file(image)

    candidate = next(item for item in client.list_deleted_fat(image) if item.display_name == "?HORT.TXT")
    assert candidate.recoverable
    output = client.recover_deleted_fat(image, candidate.slot_index, tmp_path / "recovered-api.bin")
    assert output.read_bytes() == payload.read_bytes()
    assert sha256_file(image) == before



def test_public_api_inspects_and_exports_strict_imd_layout(tmp_path: Path) -> None:
    source = tmp_path / "api.imd"
    first = bytes(range(128))
    source.write_bytes(b"IMD API\x1a" + bytes((0, 0, 0, 2, 0)) + b"\x01\x02" + b"\x01" + first + b"\x02R")
    client = DiskForgeClient()
    inspection = client.inspect_imd(source)
    assert inspection.exportable
    result = client.export_imd_to_raw(source, tmp_path / "api.img")
    assert result.operation == "export_imd_to_raw"
    assert result.destination is not None
    assert result.destination.read_bytes() == first + b"R" * 128

    unsafe = tmp_path / "unsafe.imd"
    unsafe.write_bytes(b"IMD x\x1a" + bytes((0, 0, 0, 1, 0)) + b"\x01\x03" + bytes(128))
    with pytest.raises(DiskForgeError, match="cannot be safely exported"):
        client.export_imd_to_raw(unsafe, tmp_path / "blocked.img")



def test_public_api_inventories_images_without_mutating_sources(tmp_path: Path) -> None:
    from diskforge.core.inventory import ImageInventoryOptions

    root = tmp_path / "collection"
    root.mkdir()
    image = root / "api.img"
    image.write_bytes(bytes(4096))
    before = sha256_file(image)
    client = DiskForgeClient()
    inventory = client.inventory_images(root, ImageInventoryOptions(include_sha256=True))
    assert [record.relative_path for record in inventory.records] == ["api.img"]
    report = client.export_image_inventory(inventory, tmp_path / "api.csv", "csv")
    assert report.destination is not None and report.destination.exists()
    assert sha256_file(image) == before


def test_public_api_inspects_and_exports_strict_td0_layout(tmp_path: Path) -> None:
    from diskforge.core.td0 import _crc16

    header_prefix = b"TD" + bytes((0, 0, 0x21, 0, 1, 0, 0, 1))
    header = header_prefix + _crc16(header_prefix).to_bytes(2, "little")
    track_prefix = bytes((1, 0, 0))
    sector_prefix = bytes((0, 0, 1, 0, 0))
    payload = b"A" * 128
    data_header = (129).to_bytes(2, "little") + b"\x00"
    sector = sector_prefix + bytes((_crc16(sector_prefix + data_header + payload) & 0xFF,)) + data_header + payload
    source = tmp_path / "api.td0"
    source.write_bytes(header + track_prefix + bytes((_crc16(track_prefix) & 0xFF,)) + sector + b"\xff")
    before = sha256_file(source)
    client = DiskForgeClient()

    inspection = client.inspect_td0(source)
    assert inspection.exportable
    result = client.export_td0_to_raw(source, tmp_path / "api-td0.img")
    assert result.operation == "export_td0_to_raw"
    assert result.destination is not None and result.destination.read_bytes() == payload
    assert sha256_file(source) == before
    with pytest.raises(DiskForgeError, match="read-only sector containers"):
        with client.filesystem(source):
            pass


def test_public_api_updates_explicit_fat_metadata_paths(tmp_path: Path) -> None:
    from datetime import datetime

    client = DiskForgeClient()
    image = tmp_path / "metadata-api.img"
    client.create_fat(image, size_bytes=8 * 1024 * 1024, filesystem=FileSystemType.FAT16, label="METAAPI")
    first = tmp_path / "FIRST.TXT"
    second = tmp_path / "SECOND.TXT"
    first.write_text("first", encoding="ascii")
    second.write_text("second", encoding="ascii")
    client.inject(image, [first, second])

    results = client.set_fat_metadata(
        image, ["/FIRST.TXT", "/SECOND.TXT"], hidden=True,
        modified=datetime(2024, 6, 15, 12, 34, 56),
    )

    assert [result.path for result in results] == ["/FIRST.TXT", "/SECOND.TXT"]
    assert all(result.attributes == "H" for result in results)
    assert all(result.updated_fields == ("hidden", "modified") for result in results)
    with client.filesystem(image) as filesystem:
        entries = {entry.path: entry for entry in filesystem.list_entries("/")}
    assert all(entries[path].attributes == "H" for path in ("/FIRST.TXT", "/SECOND.TXT"))
    with pytest.raises(DiskForgeError, match="at least one attribute"):
        client.set_fat_metadata(image, ["/FIRST.TXT"])
