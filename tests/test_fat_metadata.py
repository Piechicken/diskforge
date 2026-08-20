from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from diskforge.core.fat_metadata import (apply_fat_metadata, metadata_update_from_values,
                                         validate_fat_metadata_update)
from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.storage import CancellationToken, DiskForgeError, OperationCancelled


def _image_with_entries(tmp_path: Path) -> Path:
    image = create_fat_image(tmp_path / "metadata.img", 8 * 1024 * 1024, FileSystemType.FAT16, "METADATA")
    first = tmp_path / "FIRST.TXT"
    second = tmp_path / "SECOND.TXT"
    first.write_text("first", encoding="ascii")
    second.write_text("second", encoding="ascii")
    filesystem = FatImageFilesystem(image)
    try:
        filesystem.inject([first, second])
    finally:
        filesystem.close()
    return image


def test_apply_fat_metadata_updates_explicit_paths_in_order(tmp_path: Path) -> None:
    image = _image_with_entries(tmp_path)
    update = metadata_update_from_values(
        ["/FIRST.TXT", "/SECOND.TXT"], read_only=True, hidden=True,
        modified=datetime(2024, 6, 15, 12, 34, 56),
    )

    filesystem = FatImageFilesystem(image)
    try:
        results = apply_fat_metadata(filesystem, update)
        entries = {entry.path: entry for entry in filesystem.list_entries("/")}
    finally:
        filesystem.close()

    assert [result.path for result in results] == ["/FIRST.TXT", "/SECOND.TXT"]
    assert all(result.attributes == "RH" for result in results)
    assert all(result.updated_fields == ("read_only", "hidden", "modified") for result in results)
    assert all(entries[path].attributes == "RH" for path in ("/FIRST.TXT", "/SECOND.TXT"))
    assert all(entries[path].modified is not None and entries[path].modified.year == 2024 for path in entries)


@pytest.mark.parametrize("paths, kwargs, message", [
    ([], {"hidden": True}, "at least one"),
    (["/FIRST.TXT", "/FIRST.TXT"], {"hidden": True}, "duplicates"),
    (["/"], {"hidden": True}, "image root"),
    (["/FIRST.TXT"], {}, "at least one attribute"),
    (["/FIRST.TXT"], {"modified": datetime(2024, 1, 1, tzinfo=timezone.utc)}, "timezone offset"),
    (["/FIRST.TXT"], {"modified": datetime(1979, 12, 31)}, "between 1980 and 2107"),
])
def test_fat_metadata_rejects_ambiguous_or_unrepresentable_requests(
    paths: list[str], kwargs: dict[str, object], message: str,
) -> None:
    with pytest.raises(DiskForgeError, match=message):
        metadata_update_from_values(paths, **kwargs)  # type: ignore[arg-type]


def test_fat_metadata_rejects_read_only_session(tmp_path: Path) -> None:
    image = _image_with_entries(tmp_path)
    update = metadata_update_from_values(["/FIRST.TXT"], archive=False)
    filesystem = FatImageFilesystem(image, read_only=True)
    try:
        with pytest.raises(DiskForgeError, match="read-only"):
            apply_fat_metadata(filesystem, update)
    finally:
        filesystem.close()


def test_fat_metadata_observes_cancellation_before_later_explicit_path(tmp_path: Path) -> None:
    image = _image_with_entries(tmp_path)
    token = CancellationToken()
    token.cancel()
    update = metadata_update_from_values(["/FIRST.TXT", "/SECOND.TXT"], system=True)
    filesystem = FatImageFilesystem(image)
    try:
        before = {entry.path: entry.attributes for entry in filesystem.list_entries("/")}
        with pytest.raises(OperationCancelled):
            apply_fat_metadata(filesystem, update, token)
        after = {entry.path: entry.attributes for entry in filesystem.list_entries("/")}
    finally:
        filesystem.close()
    assert after == before


def test_validate_fat_metadata_update_accepts_partial_timestamp_fields() -> None:
    update = metadata_update_from_values(["/ENTRY"], created=datetime(2024, 1, 2, 3, 4, 5))
    validate_fat_metadata_update(update)
    assert update.requested_fields == ("created",)
