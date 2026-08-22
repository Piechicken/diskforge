from __future__ import annotations

from pathlib import Path
import json

import pytest

from diskforge.api import DiskForgeClient
from diskforge.core.batch import BatchRunner
from diskforge.cli import main
from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.storage import CancellationToken, DiskForgeError


def _image(tmp_path: Path) -> Path:
    return create_fat_image(tmp_path / "directories.img", 2 * 1024 * 1024, FileSystemType.FAT12, "DIRS")


def test_fat_create_empty_directory_requires_existing_parent_and_persists(tmp_path: Path) -> None:
    image = _image(tmp_path)
    filesystem = FatImageFilesystem(image)
    try:
        assert filesystem.create_directory("/DOCS") == "/DOCS"
        assert filesystem.create_directory("/DOCS/LETTERS") == "/DOCS/LETTERS"
        assert filesystem.fs.getinfo("/DOCS").is_dir
        assert filesystem.fs.getinfo("/DOCS/LETTERS").is_dir
    finally:
        filesystem.close()

    reopened = FatImageFilesystem(image, read_only=True)
    try:
        assert {entry.path for entry in reopened.walk_entries()} >= {"/DOCS", "/DOCS/LETTERS"}
    finally:
        reopened.close()


def test_fat_create_empty_directory_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    image = _image(tmp_path)
    assert main(["--json", "mkdir-fat", str(image), "/CLI"]) == 0
    assert json.loads(capsys.readouterr().out) == {"directory": "/CLI"}
    client = DiskForgeClient()
    assert client.create_fat_directory(image, "/SDK") == "/SDK"
    reopened = FatImageFilesystem(image, read_only=True)
    try:
        assert {entry.path for entry in reopened.walk_entries()} >= {"/CLI", "/SDK"}
    finally:
        reopened.close()


def test_fat_create_empty_directory_rejects_conflicts_invalid_parent_root_read_only_and_cancel(tmp_path: Path) -> None:
    image = _image(tmp_path)
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.create_directory("/DOCS")
        with pytest.raises(FileExistsError):
            filesystem.create_directory("/DOCS")
        with pytest.raises(FileNotFoundError):
            filesystem.create_directory("/MISSING/CHILD")
        with pytest.raises(DiskForgeError, match="root directory"):
            filesystem.create_directory("/")
        payload = tmp_path / "parent.bin"
        payload.write_bytes(b"x")
        filesystem.inject([payload])
        with pytest.raises(DiskForgeError, match="parent"):
            filesystem.create_directory("/parent.bin/CHILD")
        token = CancellationToken(); token.cancel()
        with pytest.raises(DiskForgeError, match="cancelled"):
            filesystem.create_directory("/CANCELLED", token)
        assert not filesystem.fs.exists("/CANCELLED")
    finally:
        filesystem.close()

    read_only = FatImageFilesystem(image, read_only=True)
    try:
        with pytest.raises(DiskForgeError, match="read-only"):
            read_only.create_directory("/NOPE")
    finally:
        read_only.close()


def test_fat_copy_regular_file_preserves_source_and_payload(tmp_path: Path) -> None:
    image = _image(tmp_path)
    payload = tmp_path / "payload.txt"
    payload.write_text("copy me", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([payload])
        filesystem.create_directory("/ARCHIVE")
        assert filesystem.copy("/payload.txt", "/ARCHIVE") == "/ARCHIVE/payload.txt"
        output = filesystem.extract(["/payload.txt", "/ARCHIVE/payload.txt"], tmp_path / "out")
    finally:
        filesystem.close()
    assert [value.read_text(encoding="utf-8") for value in output] == ["copy me", "copy me"]


def test_fat_copy_cli_and_sdk_contract(tmp_path: Path, capsys) -> None:
    image = _image(tmp_path)
    tree = tmp_path / "tree"
    nested = tree / "nested"
    nested.mkdir(parents=True)
    (tree / "payload.txt").write_text("copy me", encoding="utf-8")
    (nested / "child.txt").write_text("child", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([tree])
        filesystem.create_directory("/CLI")
        filesystem.create_directory("/SDK")
    finally:
        filesystem.close()
    assert main(["--json", "copy-fat", str(image), "/tree", "/CLI"]) == 0
    assert json.loads(capsys.readouterr().out) == {"source": "/tree", "destination": "/CLI/tree"}
    assert DiskForgeClient().copy_fat(image, "/tree", "/SDK") == "/SDK/tree"
    reopened = FatImageFilesystem(image, read_only=True)
    try:
        output = reopened.extract(["/tree/payload.txt", "/tree/nested/child.txt", "/CLI/tree/payload.txt", "/CLI/tree/nested/child.txt", "/SDK/tree/payload.txt", "/SDK/tree/nested/child.txt"], tmp_path / "out")
    finally:
        reopened.close()
    assert [value.read_text(encoding="utf-8") for value in output] == ["copy me", "child", "copy me", "child", "copy me", "child"]


def test_fat_copy_directory_tree_preserves_source_and_payload(tmp_path: Path) -> None:
    image = _image(tmp_path)
    tree = tmp_path / "tree"
    nested = tree / "nested"
    nested.mkdir(parents=True)
    (tree / "root.txt").write_text("root", encoding="utf-8")
    (nested / "child.txt").write_text("child", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([tree])
        filesystem.create_directory("/ARCHIVE")
        assert filesystem.copy("/tree", "/ARCHIVE") == "/ARCHIVE/tree"
        output = filesystem.extract(
            ["/tree/root.txt", "/tree/nested/child.txt", "/ARCHIVE/tree/root.txt", "/ARCHIVE/tree/nested/child.txt"],
            tmp_path / "out-tree",
        )
    finally:
        filesystem.close()
    assert [value.read_text(encoding="utf-8") for value in output] == ["root", "child", "root", "child"]


def test_fat_copy_rejects_collisions_source_tree_targets_invalid_target_read_only_and_cancel(tmp_path: Path) -> None:
    image = _image(tmp_path)
    payload = tmp_path / "payload.txt"
    payload.write_text("copy me", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([payload])
        filesystem.create_directory("/ARCHIVE")
        filesystem.copy("/payload.txt", "/ARCHIVE")
        with pytest.raises(FileExistsError):
            filesystem.copy("/payload.txt", "/ARCHIVE")
        with pytest.raises(DiskForgeError, match="inside the source"):
            filesystem.copy("/ARCHIVE", "/ARCHIVE")
        with pytest.raises(DiskForgeError, match="does not exist"):
            filesystem.copy("/payload.txt", "/MISSING")
        with pytest.raises(DiskForgeError, match="must be an existing directory"):
            filesystem.copy("/payload.txt", "/payload.txt")
        token = CancellationToken(); token.cancel()
        filesystem.create_directory("/CANCEL")
        with pytest.raises(DiskForgeError, match="cancelled"):
            filesystem.copy("/payload.txt", "/CANCEL", token=token)
        assert not filesystem.fs.exists("/CANCEL/payload.txt")
        filesystem.create_directory("/SOURCE")
        filesystem.create_directory("/SOURCE/NESTED")
        with pytest.raises(DiskForgeError, match="cancelled"):
            filesystem.copy("/SOURCE", "/CANCEL", token=token)
        assert not filesystem.fs.exists("/CANCEL/SOURCE")
    finally:
        filesystem.close()

    read_only = FatImageFilesystem(image, read_only=True)
    try:
        with pytest.raises(DiskForgeError, match="read-only"):
            read_only.copy("/payload.txt", "/")
    finally:
        read_only.close()


def test_fat_rename_core_sdk_and_batch_contract(tmp_path: Path) -> None:
    image = _image(tmp_path)
    first = tmp_path / "first.txt"
    first.write_text("rename payload", encoding="utf-8")
    second = tmp_path / "second.txt"
    second.write_text("occupied", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([first, second])
        assert filesystem.rename("/first.txt", "renamed.txt") == "/renamed.txt"
        assert filesystem.fs.exists("/renamed.txt")
        assert not filesystem.fs.exists("/first.txt")
        with pytest.raises(FileExistsError):
            filesystem.rename("/renamed.txt", "second.txt")
        with pytest.raises(DiskForgeError, match="single non-empty"):
            filesystem.rename("/renamed.txt", "nested/name.txt")
    finally:
        filesystem.close()

    assert DiskForgeClient().rename_fat(image, "/renamed.txt", "sdk.txt") == "/sdk.txt"
    recipe_path = tmp_path / "rename.json"
    recipe_path.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "fat_rename", "source": str(image), "item_path": "/sdk.txt", "new_name": "batch.txt"}],
    }), encoding="utf-8")
    runner = BatchRunner()
    preview = runner.preview(recipe_path)
    assert preview[0]["kind"] == "fat_rename"
    assert preview[0]["will_write"] is True
    result = runner.run(recipe_path)
    assert result.items[0].success
    reopened = FatImageFilesystem(image, read_only=True)
    try:
        assert reopened.fs.exists("/batch.txt")
        assert not reopened.fs.exists("/sdk.txt")
    finally:
        reopened.close()


def test_fat_rename_rejects_read_only_and_invalid_batch_partition(tmp_path: Path) -> None:
    image = _image(tmp_path)
    payload = tmp_path / "payload.txt"
    payload.write_text("payload", encoding="utf-8")
    writable = FatImageFilesystem(image)
    try:
        writable.inject([payload])
    finally:
        writable.close()
    read_only = FatImageFilesystem(image, read_only=True)
    try:
        with pytest.raises(DiskForgeError, match="read-only"):
            read_only.rename("/payload.txt", "blocked.txt")
    finally:
        read_only.close()
    recipe_path = tmp_path / "invalid-rename.json"
    recipe_path.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "fat_rename", "source": str(image), "item_path": "/payload.txt", "new_name": "new.txt", "partition": 0}],
    }), encoding="utf-8")
    with pytest.raises(DiskForgeError, match="positive integer"):
        BatchRunner().preview(recipe_path)


def test_fat_delete_core_cli_sdk_and_batch_contract(tmp_path: Path, capsys) -> None:
    image = _image(tmp_path)
    tree = tmp_path / "tree"
    nested = tree / "nested"
    nested.mkdir(parents=True)
    (tree / "root.txt").write_text("root", encoding="utf-8")
    (nested / "child.txt").write_text("child", encoding="utf-8")
    sdk_payload = tmp_path / "sdk.txt"
    sdk_payload.write_text("sdk", encoding="utf-8")
    batch_payload = tmp_path / "batch.txt"
    batch_payload.write_text("batch", encoding="utf-8")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([tree, sdk_payload, batch_payload])
        filesystem.delete(["/tree"])
        assert not filesystem.fs.exists("/tree")
        with pytest.raises(DiskForgeError, match="root directory"):
            filesystem.delete(["/"])
        with pytest.raises(DiskForgeError, match="at least one"):
            filesystem.delete([])
        with pytest.raises(DiskForgeError, match="unique"):
            filesystem.delete(["/sdk.txt", "/sdk.txt"])
    finally:
        filesystem.close()

    assert main(["--json", "delete-fat", str(image), "/sdk.txt"]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": "/sdk.txt"}
    assert DiskForgeClient().delete_fat(image, "/batch.txt") == "/batch.txt"

    recipe_path = tmp_path / "delete.json"
    recipe_path.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "fat_delete", "source": str(image), "item_path": "/missing.txt"}],
    }), encoding="utf-8")
    runner = BatchRunner()
    preview = runner.preview(recipe_path)
    assert preview[0]["kind"] == "fat_delete"
    assert preview[0]["will_write"] is True
    result = runner.run(recipe_path)
    assert not result.items[0].success


def test_fat_delete_batch_executes_and_rejects_read_only_or_invalid_partition(tmp_path: Path) -> None:
    image = _image(tmp_path)
    payload = tmp_path / "payload.txt"
    payload.write_text("payload", encoding="utf-8")
    writable = FatImageFilesystem(image)
    try:
        writable.inject([payload])
    finally:
        writable.close()
    recipe_path = tmp_path / "delete.json"
    recipe_path.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "fat_delete", "source": str(image), "item_path": "/payload.txt"}],
    }), encoding="utf-8")
    result = BatchRunner().run(recipe_path)
    assert result.items[0].success
    reopened = FatImageFilesystem(image, read_only=True)
    try:
        assert not reopened.fs.exists("/payload.txt")
        with pytest.raises(DiskForgeError, match="read-only"):
            reopened.delete(["/anything.txt"])
    finally:
        reopened.close()
    invalid = tmp_path / "invalid-delete.json"
    invalid.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "fat_delete", "source": str(image), "item_path": "/x", "partition": 0}],
    }), encoding="utf-8")
    with pytest.raises(DiskForgeError, match="positive integer"):
        BatchRunner().preview(invalid)
