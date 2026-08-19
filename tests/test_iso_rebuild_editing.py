from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.filesystems import (IsoImageFilesystem, create_iso_from_directory,
                                        rebuild_iso_with_changes)
from diskforge.core.storage import DiskForgeError, sha256_file


def _tree(root: Path) -> Path:
    (root / "folder").mkdir(parents=True)
    (root / "KEEP.TXT").write_text("keep", encoding="utf-8")
    (root / "folder" / "OLD.TXT").write_text("remove", encoding="utf-8")
    return root


def test_standard_iso_rebuild_adds_deletes_and_creates_directories_without_mutating_source(tmp_path: Path) -> None:
    source_tree = _tree(tmp_path / "source")
    source_iso = create_iso_from_directory(source_tree, tmp_path / "source.iso", volume_label="SOURCE")
    original_hash = sha256_file(source_iso)
    added = tmp_path / "ADDED.TXT"
    added.write_text("new payload", encoding="utf-8")
    destination = tmp_path / "edited.iso"

    result = rebuild_iso_with_changes(
        source_iso,
        destination,
        additions=[added],
        delete_paths=["/folder/OLD.TXT"],
        create_directories=["/empty"],
        target_directory="/folder",
    )

    assert sha256_file(source_iso) == original_hash == result.source_sha256
    assert destination.exists()
    assert result.files_added == ("/FOLDER/ADDED.TXT",)
    assert result.paths_deleted == ("/folder/OLD.TXT",)
    assert result.directories_created == ("/empty",)
    filesystem = IsoImageFilesystem(destination)
    try:
        assert {entry.path for entry in filesystem.list_entries("/")} == {"/EMPTY", "/FOLDER", "/KEEP.TXT"}
        assert {entry.path for entry in filesystem.list_entries("/folder")} == {"/folder/ADDED.TXT"}
        extracted = filesystem.extract(["/folder/ADDED.TXT", "/KEEP.TXT"], tmp_path / "extract")
    finally:
        filesystem.close()
    assert {item.name: item.read_text(encoding="utf-8") for item in extracted} == {
        "ADDED.TXT": "new payload", "KEEP.TXT": "keep",
    }


def test_standard_iso_rebuild_refuses_bootable_source(tmp_path: Path) -> None:
    source_tree = _tree(tmp_path / "source")
    boot = tmp_path / "boot.img"
    boot.write_bytes(b"\0" * 2048)
    source_iso = create_iso_from_directory(source_tree, tmp_path / "bootable.iso", boot_image=boot)
    added = tmp_path / "ADDED.TXT"
    added.write_text("new payload", encoding="utf-8")

    with pytest.raises(DiskForgeError, match="El Torito"):
        rebuild_iso_with_changes(source_iso, tmp_path / "edited.iso", additions=[added])
