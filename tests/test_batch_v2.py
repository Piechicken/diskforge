from __future__ import annotations

import json
from pathlib import Path

from diskforge.core.batch import BatchRunner
from diskforge.core.filesystems import create_fat_image
from diskforge.core.models import FileSystemType


def test_batch_v2_runs_safe_image_operations(tmp_path: Path) -> None:
    image = tmp_path / "media.img"
    host_file = tmp_path / "payload.txt"
    host_file.write_text("batch data", encoding="utf-8")
    create_fat_image(image, 8 * 1024 * 1024, FileSystemType.FAT16)
    bundle = tmp_path / "media.dfb"
    extract_dir = tmp_path / "extract"
    recipe = tmp_path / "safe-batch.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v2",
        "operations": [
            {"kind": "inject", "destination": str(image), "sources": [str(host_file)]},
            {"kind": "extract", "source": str(image), "destination": str(extract_dir), "paths": ["/payload.txt"]},
            {"kind": "compare", "source": str(host_file), "destination": str(extract_dir / "payload.txt")},
            {"kind": "bundle", "sources": [str(image)], "destination": str(bundle), "comment": "batch"},
            {"kind": "unbundle", "source": str(bundle), "destination": str(tmp_path / "unbundle")},
        ],
    }), encoding="utf-8")

    result = BatchRunner().run(recipe)

    assert result.succeeded == 5
    assert result.failed == 0
    assert (extract_dir / "payload.txt").read_text(encoding="utf-8") == "batch data"
    assert (tmp_path / "unbundle" / "media.img").is_file()


def test_batch_v1_remains_accepted_and_password_bundle_is_rejected(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps({
        "schema": "diskforge.batch/v1",
        "operations": [{
            "kind": "bundle", "sources": [str(tmp_path / "missing.img")],
            "destination": str(tmp_path / "x.dfb"), "password_env": "SECRET",
        }],
    }), encoding="utf-8")

    result = BatchRunner().run(unsafe)

    assert result.failed == 1
    assert "interactively" in result.items[0].message
