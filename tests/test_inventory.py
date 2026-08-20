from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.core.filesystems import create_fat_image
from diskforge.core.inventory import (ImageInventoryOptions, export_image_inventory,
                                      inventory_images)
from diskforge.core.models import FileSystemType, ImageFormat
from diskforge.core.storage import DiskForgeError, sha256_file


def _inventory_tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "images"
    root.mkdir()
    first = create_fat_image(root / "first.ima", 1_474_560, FileSystemType.FAT12, "FIRST")
    nested = root / "nested"
    nested.mkdir()
    second = create_fat_image(nested / "second.img", 1_474_560, FileSystemType.FAT12, "SECOND")
    (root / "notes.txt").write_text("not an image", encoding="utf-8")
    (root / "broken.iso").write_bytes(b"not an ISO")
    return root, first


def test_inventory_filters_stably_and_preserves_sources(tmp_path: Path) -> None:
    root, first = _inventory_tree(tmp_path)
    before = sha256_file(first)
    options = ImageInventoryOptions(
        recursive=True, formats=(ImageFormat.IMA, ImageFormat.IMG),
        filesystems=(FileSystemType.FAT12,), include_sha256=True,
    )
    inventory = inventory_images(root, options)
    assert [record.relative_path for record in inventory.records] == ["first.ima", "nested/second.img"]
    assert all(record.sha256 for record in inventory.records)
    assert inventory.recognized == 2
    assert inventory.errors == 0
    assert sha256_file(first) == before


def test_inventory_retains_suffix_recognition_as_an_auditable_record(tmp_path: Path) -> None:
    root, _ = _inventory_tree(tmp_path)
    inventory = inventory_images(root, ImageInventoryOptions())
    broken = next(record for record in inventory.records if record.relative_path == "broken.iso")
    assert broken.error is None
    assert broken.image_format is ImageFormat.ISO
    assert broken.filesystem is FileSystemType.UNKNOWN
    assert all(record.relative_path != "notes.txt" for record in inventory.records)


def test_inventory_sha_prefix_and_report_output_boundaries(tmp_path: Path) -> None:
    root, first = _inventory_tree(tmp_path)
    prefix = sha256_file(first)[:12]
    inventory = inventory_images(root, ImageInventoryOptions(sha256_prefix=prefix))
    assert [record.relative_path for record in inventory.records] == ["first.ima"]
    assert inventory.records[0].sha256 is not None

    destination = tmp_path / "report.json"
    assert export_image_inventory(inventory, destination, "json") == destination
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["summary"]["reported"] == 1
    with pytest.raises(FileExistsError):
        export_image_inventory(inventory, destination, "json")
    with pytest.raises(DiskForgeError, match="inside the scanned root"):
        export_image_inventory(inventory, root / "unsafe.html", "html")


@pytest.mark.parametrize("options", [
    ImageInventoryOptions(min_bytes=-1),
    ImageInventoryOptions(min_bytes=10, max_bytes=1),
    ImageInventoryOptions(sha256_prefix="not-hex"),
])
def test_inventory_rejects_invalid_filter_contract(tmp_path: Path, options: ImageInventoryOptions) -> None:
    root, _ = _inventory_tree(tmp_path)
    with pytest.raises(DiskForgeError):
        inventory_images(root, options)
