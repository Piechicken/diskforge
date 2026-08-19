from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.core.batch import BatchRunner
from diskforge.core.eltorito import inspect_eltorito
from diskforge.core.filesystems import IsoImageFilesystem, create_iso_from_directory
from diskforge.core.storage import DiskForgeError


def _recipe(path: Path, operation: dict[str, object]) -> Path:
    path.write_text(json.dumps({"schema": "diskforge.batch/v4", "operations": [operation]}), encoding="utf-8")
    return path


def test_batch_v4_safely_rebuilds_single_boot_eltorito_iso(tmp_path: Path) -> None:
    source_tree = tmp_path / "source"
    (source_tree / "folder").mkdir(parents=True)
    (source_tree / "folder" / "OLD.TXT").write_text("old", encoding="utf-8")
    boot = source_tree / "boot.img"
    boot.write_bytes(b"BOOT" * 512)
    source = create_iso_from_directory(source_tree, tmp_path / "source.iso", boot_image=boot, boot_platform_id=0xEF)
    addition = tmp_path / "ADDED.TXT"
    addition.write_text("added", encoding="utf-8")
    destination = tmp_path / "edited.iso"
    recipe = _recipe(tmp_path / "edit.json", {
        "kind": "iso_edit", "source": str(source), "destination": str(destination),
        "additions": [str(addition)], "delete_paths": ["/folder/OLD.TXT"],
        "create_directories": ["/empty"], "target_directory": "/folder",
    })

    runner = BatchRunner()
    preview = runner.preview(recipe)
    assert preview == [{
        "index": 0, "name": "iso_edit", "kind": "iso_edit", "source": str(source),
        "destination": str(destination), "will_write": True,
    }]
    assert not destination.exists()
    result = runner.run(recipe)

    assert result.items[0].success is True
    catalog = inspect_eltorito(destination)
    assert catalog.has_sections is False
    assert len(catalog.images) == 1
    assert catalog.images[0].platform_id == 0xEF
    filesystem = IsoImageFilesystem(destination)
    try:
        assert {entry.path.casefold() for entry in filesystem.list_entries("/folder")} == {"/folder/added.txt"}
        assert {entry.path.casefold() for entry in filesystem.list_entries("/")} >= {"/empty", "/boot.cat", "/boot.img"}
    finally:
        filesystem.close()


@pytest.mark.parametrize("operation, message", [
    ({"kind": "iso_edit", "source": "source.iso", "destination": "out.iso"}, "requires additions"),
    ({"kind": "iso_edit", "source": "source.iso", "destination": "out.iso", "additions": "file.txt"}, "string lists"),
    ({"kind": "iso_edit", "source": "source.iso", "destination": "out.iso", "delete_paths": ["/file"], "target_directory": ["/"]}, "target_directory"),
])
def test_batch_v4_iso_edit_rejects_incomplete_or_invalid_parameters(tmp_path: Path, operation: dict[str, object], message: str) -> None:
    recipe = _recipe(tmp_path / "invalid.json", operation)
    with pytest.raises(DiskForgeError, match=message):
        BatchRunner().preview(recipe)
