from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.core.batch import BatchRunner
from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.sequence import SequencePattern, planned_paths
from diskforge.core.storage import DiskForgeError


def _fat_image_with_file(path: Path, text: str) -> Path:
    image = create_fat_image(path, 2 * 1024 * 1024, FileSystemType.FAT12)
    source = path.with_suffix(".txt")
    source.write_text(text, encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([source])
    finally:
        filesystem.close()
    return image


def test_sequence_pattern_preview_and_path_validation(tmp_path: Path) -> None:
    pattern = SequencePattern(prefix="disk-", start=7, width=4, step=3, suffix="-files")
    assert pattern.preview(3) == ("disk-0007-files", "disk-0010-files", "disk-0013-files")
    assert planned_paths(tmp_path, pattern, 2) == (tmp_path / "disk-0007-files", tmp_path / "disk-0010-files")
    with pytest.raises(DiskForgeError, match="path separators"):
        SequencePattern(prefix="bad/name")


def test_batch_v3_extracts_images_to_sequenced_directories(tmp_path: Path) -> None:
    first = _fat_image_with_file(tmp_path / "first.img", "one")
    second = _fat_image_with_file(tmp_path / "second.img", "two")
    recipe = tmp_path / "batch.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v3",
        "operations": [{
            "kind": "extract", "sources": [str(first), str(second)], "paths": ["/"],
            "destination_root": str(tmp_path / "output"),
            "sequence": {"prefix": "disk-", "start": 1, "width": 2},
            "layout": "preserve_paths", "on_conflict": "error",
        }],
    }), encoding="utf-8")
    result = BatchRunner().run(recipe)
    assert result.succeeded == 1
    assert (tmp_path / "output" / "disk-01" / "first.txt").read_text(encoding="utf-8") == "one"
    assert (tmp_path / "output" / "disk-02" / "second.txt").read_text(encoding="utf-8") == "two"
