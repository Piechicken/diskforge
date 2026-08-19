from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.eltorito import inspect_eltorito
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


@pytest.mark.parametrize(("rock_ridge", "udf"), [(False, False), (True, False), (False, True), (True, True)])
def test_single_boot_eltorito_iso_rebuild_preserves_content_profiles_and_catalog(tmp_path: Path, rock_ridge: bool, udf: bool) -> None:
    source_tree = _tree(tmp_path / "source")
    boot = source_tree / "boot.img"
    boot.write_bytes(b"BOOT" * 512)
    source_iso = create_iso_from_directory(
        source_tree, tmp_path / "bootable.iso", boot_image=boot, boot_platform_id=0xEF,
        boot_load_segment=0x7C0, rock_ridge=rock_ridge, udf=udf,
    )
    original_hash = sha256_file(source_iso)
    source_catalog = inspect_eltorito(source_iso)
    added = tmp_path / "ADDED.TXT"
    added.write_text("new payload", encoding="utf-8")

    rebuilt = tmp_path / "edited.iso"
    result = rebuild_iso_with_changes(source_iso, rebuilt, additions=[added], target_directory="/folder")

    assert sha256_file(source_iso) == original_hash == result.source_sha256
    assert len(result.files_added) == 1
    assert result.files_added[0].casefold() == "/folder/added.txt"
    rebuilt_catalog = inspect_eltorito(rebuilt)
    assert rebuilt_catalog.has_sections is False
    assert len(rebuilt_catalog.images) == 1
    assert rebuilt_catalog.images[0].__dict__ | {"lba": 0} == source_catalog.images[0].__dict__ | {"lba": 0}
    filesystem = IsoImageFilesystem(rebuilt)
    try:
        entries = {entry.path for entry in filesystem.list_entries("/folder")}
        extracted = filesystem.extract(["/boot.img", "/folder/ADDED.TXT"], tmp_path / "extract")
    finally:
        filesystem.close()
    assert "/folder/ADDED.TXT" in entries
    assert {item.name.casefold(): item.read_bytes() for item in extracted} == {
        "boot.img": b"BOOT" * 512,
        "added.txt": b"new payload",
    }


def test_bootable_iso_rebuild_rejects_boot_files_and_catalog_mutation(tmp_path: Path) -> None:
    source_tree = _tree(tmp_path / "source")
    boot = source_tree / "boot.img"
    boot.write_bytes(b"BOOT" * 512)
    source_iso = create_iso_from_directory(source_tree, tmp_path / "bootable.iso", boot_image=boot)
    added = tmp_path / "ADDED.TXT"
    added.write_text("new payload", encoding="utf-8")

    with pytest.raises(DiskForgeError, match="boot files and boot catalog"):
        rebuild_iso_with_changes(source_iso, tmp_path / "delete-boot.iso", delete_paths=["/BOOT.IMG"])
    with pytest.raises(DiskForgeError, match="boot files and boot catalog"):
        rebuild_iso_with_changes(source_iso, tmp_path / "delete-catalog.iso", delete_paths=["/BOOT.CAT"])
    catalog_named_addition = tmp_path / "BOOT.CAT"
    catalog_named_addition.write_text("not a catalog", encoding="utf-8")
    with pytest.raises(DiskForgeError, match="boot catalog is managed"):
        rebuild_iso_with_changes(source_iso, tmp_path / "add-catalog.iso", additions=[catalog_named_addition])


def test_bootable_iso_rebuild_rejects_sectioned_or_hybrid_system_area(tmp_path: Path) -> None:
    source_tree = _tree(tmp_path / "source")
    boot = source_tree / "boot.img"
    boot.write_bytes(b"BOOT" * 512)
    source_iso = create_iso_from_directory(source_tree, tmp_path / "bootable.iso", boot_image=boot)
    added = tmp_path / "ADDED.TXT"
    added.write_text("new payload", encoding="utf-8")
    catalog = inspect_eltorito(source_iso)

    sectioned = tmp_path / "sectioned.iso"
    sectioned.write_bytes(source_iso.read_bytes())
    with sectioned.open("r+b") as handle:
        handle.seek(catalog.catalog_lba * 2048 + 64)
        handle.write(b"\x91\xef" + b"\0" * 30)
    with pytest.raises(DiskForgeError, match="single initial"):
        rebuild_iso_with_changes(sectioned, tmp_path / "sectioned-output.iso", additions=[added])

    hybrid = tmp_path / "hybrid.iso"
    hybrid.write_bytes(source_iso.read_bytes())
    with hybrid.open("r+b") as handle:
        handle.seek(0)
        handle.write(b"\xfa")
    with pytest.raises(DiskForgeError, match="hybrid or nonstandard"):
        rebuild_iso_with_changes(hybrid, tmp_path / "hybrid-output.iso", additions=[added])
