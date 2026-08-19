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
