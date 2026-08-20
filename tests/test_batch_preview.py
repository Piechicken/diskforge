from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.cli import main
from diskforge.core.batch import BatchRunner
from diskforge.core.storage import DiskForgeError


def _recipe(path: Path, operation: dict) -> Path:
    path.write_text(json.dumps({"schema": "diskforge.batch/v3", "operations": [operation]}), encoding="utf-8")
    return path


def test_batch_preview_validates_without_creating_destination(tmp_path: Path) -> None:
    destination = tmp_path / "out.img"
    recipe = _recipe(tmp_path / "recipe.json", {
        "kind": "convert", "source": "source.img", "destination": str(destination), "format": "img",
    })
    plan = BatchRunner().preview(recipe)
    assert plan[0]["kind"] == "convert"
    assert plan[0]["will_write"]
    assert not destination.exists()


def test_batch_preview_rejects_device_and_missing_fields(tmp_path: Path) -> None:
    device = _recipe(tmp_path / "device.json", {"kind": "write_device", "source": "x", "destination": "y"})
    with pytest.raises(DiskForgeError, match="Raw device"):
        BatchRunner().preview(device)
    invalid = _recipe(tmp_path / "invalid.json", {"kind": "resize", "source": "x"})
    with pytest.raises(DiskForgeError, match="missing"):
        BatchRunner().preview(invalid)


def test_cli_batch_dry_run_is_structured(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    recipe = _recipe(tmp_path / "recipe.json", {
        "kind": "compare", "source": "left.img", "destination": "right.img",
    })
    assert main(["--json", "batch", str(recipe), "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"]
    assert result["operations"][0]["kind"] == "compare"


def test_batch_v4_fat_metadata_previews_and_updates_explicit_paths(tmp_path: Path) -> None:
    from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
    from diskforge.core.models import FileSystemType

    image = create_fat_image(tmp_path / "metadata-batch.img", 8 * 1024 * 1024, FileSystemType.FAT16, "METABATCH")
    first = tmp_path / "FIRST.TXT"
    second = tmp_path / "SECOND.TXT"
    first.write_text("first", encoding="ascii")
    second.write_text("second", encoding="ascii")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([first, second])
    finally:
        filesystem.close()
    recipe = tmp_path / "metadata-batch.json"
    recipe.write_text(json.dumps({"schema": "diskforge.batch/v4", "operations": [{
        "kind": "fat_metadata", "source": str(image), "paths": ["/FIRST.TXT", "/SECOND.TXT"],
        "hidden": True, "modified": "2024-06-15T12:34:56",
    }]}), encoding="utf-8")

    runner = BatchRunner()
    plan = runner.preview(recipe)
    assert plan == [{
        "index": 0, "name": "fat_metadata", "kind": "fat_metadata", "source": str(image),
        "destination": None, "will_write": True,
    }]
    result = runner.run(recipe)
    assert result.succeeded == 1
    filesystem = FatImageFilesystem(image, read_only=True)
    try:
        entries = {entry.path: entry for entry in filesystem.list_entries("/")}
    finally:
        filesystem.close()
    assert entries["/FIRST.TXT"].attributes == "H"
    assert entries["/SECOND.TXT"].attributes == "H"

    invalid = _recipe(tmp_path / "invalid-metadata.json", {
        "kind": "fat_metadata", "source": str(image), "paths": ["/FIRST.TXT"],
    })
    with pytest.raises(DiskForgeError, match="at least one attribute"):
        runner.preview(invalid)
