from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.core.batch import BatchRunner
from diskforge.core.filesystems import create_iso_from_directory
from diskforge.core.storage import DiskForgeError, sha256_file


def _recipe(path: Path, operation: dict[str, object]) -> Path:
    path.write_text(json.dumps({"schema": "diskforge.batch/v4", "operations": [operation]}), encoding="utf-8")
    return path


def test_batch_exports_generic_iso_directory_report_without_changing_source(tmp_path: Path) -> None:
    source_tree = tmp_path / "source"
    source_tree.mkdir()
    (source_tree / "README.TXT").write_text("directory report", encoding="utf-8")
    image = create_iso_from_directory(source_tree, tmp_path / "source.iso")
    report = tmp_path / "report.html"
    recipe = _recipe(tmp_path / "report.json", {
        "kind": "export_listing", "source": str(image), "destination": str(report), "html": True,
    })
    before = sha256_file(image)
    runner = BatchRunner()

    preview = runner.preview(recipe)
    result = runner.run(recipe)

    assert preview == [{
        "index": 0, "name": "export_listing", "kind": "export_listing", "source": str(image),
        "destination": str(report), "will_write": True,
    }]
    assert result.items[0].success
    assert result.items[0].destination == report
    assert "README.TXT" in report.read_text(encoding="utf-8")
    assert sha256_file(image) == before


def test_batch_directory_report_rejects_nonpositive_partition_during_preview(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "invalid-report.json", {
        "kind": "export_listing", "source": "disk.img", "destination": "report.txt", "partition": 0,
    })

    with pytest.raises(DiskForgeError, match="positive integer"):
        BatchRunner().preview(recipe)



def test_batch_moves_directory_tree_with_auditable_preview(tmp_path: Path) -> None:
    from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
    from diskforge.core.models import FileSystemType

    image = create_fat_image(tmp_path / "move-batch.img", 8 * 1024 * 1024, FileSystemType.FAT16, "BATCHMOVE")
    tree = tmp_path / "tree"
    nested = tree / "nested"
    nested.mkdir(parents=True)
    (tree / "payload.txt").write_text("batch move payload", encoding="utf-8")
    (nested / "child.txt").write_text("batch move child", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([tree])
        filesystem.fs.makedirs("/archive", recreate=True)
    finally:
        filesystem.close()
    recipe = _recipe(tmp_path / "move.json", {
        "kind": "move", "source": str(image), "item_path": "/tree", "target_directory": "/archive",
    })
    runner = BatchRunner()

    assert runner.preview(recipe) == [{
        "index": 0, "name": "move", "kind": "move", "source": str(image),
        "destination": "/archive", "will_write": True,
    }]
    result = runner.run(recipe)

    assert result.items[0].success
    assert result.items[0].destination == image
    filesystem = FatImageFilesystem(image, read_only=True)
    try:
        assert not filesystem.fs.exists("/tree")
        output = filesystem.extract(["/archive/tree/payload.txt", "/archive/tree/nested/child.txt"], tmp_path / "out")
    finally:
        filesystem.close()
    assert [item.read_text(encoding="utf-8") for item in output] == ["batch move payload", "batch move child"]


def test_batch_move_rejects_invalid_partition_during_preview(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "invalid-move.json", {
        "kind": "move", "source": "disk.img", "item_path": "/item.txt", "target_directory": "/archive", "partition": 0,
    })

    with pytest.raises(DiskForgeError, match="positive integer"):
        BatchRunner().preview(recipe)



def test_batch_reads_zip_image_container_and_rejects_write_recipe(tmp_path: Path) -> None:
    import zipfile

    from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
    from diskforge.core.models import FileSystemType

    image = create_fat_image(tmp_path / "inside.img", 8 * 1024 * 1024, FileSystemType.FAT16, "ZIPBATCH")
    payload = tmp_path / "payload.txt"
    payload.write_text("batch ZIP payload", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([payload])
        filesystem.fs.makedirs("/archive", recreate=True)
    finally:
        filesystem.close()
    archive = tmp_path / "inside.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as container:
        container.write(image, image.name)
    before = sha256_file(archive)

    output = tmp_path / "out"
    extract_recipe = _recipe(tmp_path / "zip-extract.json", {
        "kind": "extract", "source": str(archive), "destination": str(output), "paths": ["/payload.txt"],
    })
    runner = BatchRunner()
    assert runner.preview(extract_recipe)[0]["will_write"] is True
    extracted = runner.run(extract_recipe)
    assert extracted.items[0].success
    assert (output / "payload.txt").read_text(encoding="utf-8") == "batch ZIP payload"

    report = tmp_path / "zip-report.txt"
    report_recipe = _recipe(tmp_path / "zip-report.json", {
        "kind": "export_listing", "source": str(archive), "destination": str(report),
    })
    reported = runner.run(report_recipe)
    assert reported.items[0].success
    assert "/payload.txt" in report.read_text(encoding="utf-8")

    move_recipe = _recipe(tmp_path / "zip-move.json", {
        "kind": "move", "source": str(archive), "item_path": "/payload.txt", "target_directory": "/archive",
    })
    rejected = runner.run(move_recipe)
    assert rejected.items[0].success is False
    assert "read-only" in rejected.items[0].message
    assert sha256_file(archive) == before


def test_batch_creates_empty_fat_directory_with_auditable_preview(tmp_path: Path) -> None:
    from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
    from diskforge.core.models import FileSystemType

    image = create_fat_image(tmp_path / "mkdir-batch.img", 8 * 1024 * 1024, FileSystemType.FAT16, "BATCHDIR")
    recipe = _recipe(tmp_path / "mkdir.json", {
        "kind": "fat_mkdir", "source": str(image), "directory_path": "/DOCS",
    })
    runner = BatchRunner()

    assert runner.preview(recipe) == [{
        "index": 0, "name": "fat_mkdir", "kind": "fat_mkdir", "source": str(image),
        "destination": None, "will_write": True,
    }]
    result = runner.run(recipe)

    assert result.items[0].success and result.items[0].destination == image
    filesystem = FatImageFilesystem(image, read_only=True)
    try:
        assert filesystem.fs.getinfo("/DOCS").is_dir
    finally:
        filesystem.close()


@pytest.mark.parametrize("item, pattern", [
    ({"kind": "fat_mkdir", "source": "disk.img", "directory_path": ""}, "non-empty string"),
    ({"kind": "fat_mkdir", "source": "disk.img", "directory_path": "/DOCS", "partition": 0}, "positive integer"),
])
def test_batch_fat_mkdir_rejects_invalid_preview_values(tmp_path: Path, item: dict[str, object], pattern: str) -> None:
    recipe = _recipe(tmp_path / "invalid-mkdir.json", item)

    with pytest.raises(DiskForgeError, match=pattern):
        BatchRunner().preview(recipe)


def test_batch_copies_regular_fat_file_with_auditable_preview(tmp_path: Path) -> None:
    from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
    from diskforge.core.models import FileSystemType

    image = create_fat_image(tmp_path / "copy-batch.img", 8 * 1024 * 1024, FileSystemType.FAT16, "BATCHCOPY")
    tree = tmp_path / "tree"
    nested = tree / "nested"
    nested.mkdir(parents=True)
    (tree / "payload.txt").write_text("batch copy payload", encoding="utf-8")
    (nested / "child.txt").write_text("batch copy child", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([tree])
        filesystem.create_directory("/archive")
    finally:
        filesystem.close()
    recipe = _recipe(tmp_path / "copy.json", {
        "kind": "fat_copy", "source": str(image), "item_path": "/tree", "target_directory": "/archive",
    })
    runner = BatchRunner()

    assert runner.preview(recipe) == [{
        "index": 0, "name": "fat_copy", "kind": "fat_copy", "source": str(image),
        "destination": "/archive", "will_write": True,
    }]
    result = runner.run(recipe)

    assert result.items[0].success and result.items[0].destination == image
    filesystem = FatImageFilesystem(image, read_only=True)
    try:
        output = filesystem.extract(["/tree/payload.txt", "/tree/nested/child.txt", "/archive/tree/payload.txt", "/archive/tree/nested/child.txt"], tmp_path / "out")
    finally:
        filesystem.close()
    assert [path.read_text(encoding="utf-8") for path in output] == ["batch copy payload", "batch copy child", "batch copy payload", "batch copy child"]


def test_batch_fat_copy_rejects_invalid_partition_during_preview(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "invalid-copy.json", {
        "kind": "fat_copy", "source": "disk.img", "item_path": "/item.txt", "target_directory": "/archive", "partition": 0,
    })

    with pytest.raises(DiskForgeError, match="positive integer"):
        BatchRunner().preview(recipe)
