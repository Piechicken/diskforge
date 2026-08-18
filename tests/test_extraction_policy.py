from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.models import ConflictPolicy, ExtractionLayout, ExtractionPolicy, FileSystemType


def test_fat_extraction_policy_controls_layout_and_conflicts(tmp_path: Path) -> None:
    image = tmp_path / "source.img"
    source_a = tmp_path / "a"
    source_b = tmp_path / "b"
    source_a.mkdir()
    source_b.mkdir()
    (source_a / "same.txt").write_text("A", encoding="utf-8")
    (source_b / "same.txt").write_text("B", encoding="utf-8")
    create_fat_image(image, 8 * 1024 * 1024, FileSystemType.FAT16)

    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([source_a, source_b])
        output = tmp_path / "flat"
        extracted = filesystem.extract(
            ["/a", "/b"], output,
            policy=ExtractionPolicy(ExtractionLayout.FLATTEN, ConflictPolicy.RENAME),
        )
        assert [path.name for path in extracted] == ["same.txt", "same-2.txt"]
        assert (output / "same.txt").read_text(encoding="utf-8") == "A"
        assert (output / "same-2.txt").read_text(encoding="utf-8") == "B"

        preserved = tmp_path / "preserved"
        first = filesystem.extract(["/a/same.txt"], preserved)
        assert first == [preserved / "a" / "same.txt"]
        with pytest.raises(FileExistsError):
            filesystem.extract(["/a/same.txt"], preserved)
        overwritten = filesystem.extract(
            ["/a/same.txt"], preserved,
            policy=ExtractionPolicy(ExtractionLayout.PRESERVE_PATHS, ConflictPolicy.OVERWRITE),
        )
        assert overwritten == first
        assert filesystem.extract(
            ["/a"], tmp_path / "ignored",
            policy=ExtractionPolicy(ExtractionLayout.IGNORE_SUBDIRECTORIES, ConflictPolicy.ERROR),
        ) == []
    finally:
        filesystem.close()
