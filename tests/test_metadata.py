from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.core.metadata import load_image_metadata, metadata_path, save_image_comment
from diskforge.core.storage import DiskForgeError


def test_image_comment_uses_non_invasive_sidecar(tmp_path: Path) -> None:
    image = tmp_path / "media.img"
    original = b"disk image bytes\0" * 128
    image.write_bytes(original)

    saved = save_image_comment(image, "Boot media for lab machines")

    assert saved.comment == "Boot media for lab machines"
    assert image.read_bytes() == original
    assert load_image_metadata(image).comment == saved.comment
    assert metadata_path(image).is_file()


def test_image_metadata_rejects_sidecar_for_different_image(tmp_path: Path) -> None:
    image = tmp_path / "media.img"
    image.write_bytes(b"bytes")
    sidecar = metadata_path(image)
    sidecar.write_text(json.dumps({
        "schema": "diskforge.image-metadata/v1",
        "image_name": "another.img",
        "comment": "wrong target",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }), encoding="utf-8")

    with pytest.raises(DiskForgeError, match="does not match"):
        load_image_metadata(image)
