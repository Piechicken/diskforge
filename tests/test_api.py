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
    assert API_VERSION == "1.0"
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
