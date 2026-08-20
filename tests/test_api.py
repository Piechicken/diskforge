from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.api import API_VERSION, DiskForgeClient
from diskforge.core.models import FileSystemType
from diskforge.core.storage import DiskForgeError


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



def test_public_api_moves_regular_fat_file_and_rejects_directory_move(tmp_path: Path) -> None:
    client = DiskForgeClient()
    image = tmp_path / "move-api.img"
    client.create_fat(image, size_bytes=8 * 1024 * 1024, filesystem=FileSystemType.FAT16, label="MOVEAPI")
    payload = tmp_path / "payload.txt"
    payload.write_text("SDK move payload", encoding="utf-8")
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "placeholder.txt").write_text("directory anchor", encoding="utf-8")
    client.inject(image, [payload, archive])

    assert client.move_fat(image, "/payload.txt", "/archive") == "/archive/payload.txt"
    assert client.extract(image, ["/archive/payload.txt"], tmp_path / "out")[0].read_text(encoding="utf-8") == "SDK move payload"
    with pytest.raises(DiskForgeError, match="directory moves"):
        client.move_fat(image, "/archive", "/")



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
