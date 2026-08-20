from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.fat_recovery import (_layout, list_deleted_root_files,
                                         recover_deleted_root_file)
from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.storage import (CancellationToken, DiskForgeError,
                                    OperationCancelled, sha256_file)


def _mark_root_file_deleted(image: Path, filename: bytes = b"SHORT   TXT") -> int:
    """Create the conventional 0xE5 root-directory deletion record for this raw recovery test."""
    layout = _layout(image, 0)
    with image.open("r+b") as handle:
        for slot_index in range(layout.root_directory_entries):
            handle.seek(layout.root_directory_offset + slot_index * 32)
            entry = handle.read(32)
            if entry[:11] != filename:
                continue
            first_cluster = int.from_bytes(entry[26:28], "little")
            assert first_cluster >= 2
            handle.seek(layout.root_directory_offset + slot_index * 32)
            handle.write(b"\xe5")
            if layout.kind == "fat12":
                position = layout.first_fat_offset + first_cluster + first_cluster // 2
                handle.seek(position)
                packed = int.from_bytes(handle.read(2), "little")
                value = packed & 0xF000 if first_cluster % 2 == 0 else packed & 0x000F
                handle.seek(position)
                handle.write(value.to_bytes(2, "little"))
            else:
                handle.seek(layout.first_fat_offset + first_cluster * 2)
                handle.write(b"\x00\x00")
            return slot_index
    raise AssertionError("Expected injected short root file was not found")


@pytest.mark.parametrize("filesystem,size_bytes", [
    (FileSystemType.FAT12, 1440 * 1024),
    (FileSystemType.FAT16, 8 * 1024 * 1024),
])
def test_deleted_single_cluster_root_file_is_recovered_to_new_local_output(
    tmp_path: Path, filesystem: FileSystemType, size_bytes: int,
) -> None:
    image = create_fat_image(tmp_path / f"{filesystem.value}.img", size_bytes, filesystem, "RECOVER")
    original = b"recover this short FAT payload\n"
    payload = tmp_path / "SHORT.TXT"
    payload.write_bytes(original)
    fat = FatImageFilesystem(image)
    try:
        fat.inject([payload])
    finally:
        fat.close()
    _mark_root_file_deleted(image)
    before = sha256_file(image)

    candidates = list_deleted_root_files(image)
    candidate = next(item for item in candidates if item.display_name == "?HORT.TXT")
    assert candidate.recoverable
    assert candidate.bytes == len(original)
    assert candidate.cluster_bytes >= len(original)

    output = tmp_path / "recovered.bin"
    assert recover_deleted_root_file(image, candidate.slot_index, output) == output
    assert output.read_bytes() == original
    assert sha256_file(image) == before


def test_deleted_root_recovery_rejects_reallocated_cluster_and_existing_output(tmp_path: Path) -> None:
    image = create_fat_image(tmp_path / "reallocated.img", 8 * 1024 * 1024, FileSystemType.FAT16, "RECOVER")
    payload = tmp_path / "SHORT.TXT"
    payload.write_bytes(b"recovery payload")
    fat = FatImageFilesystem(image)
    try:
        fat.inject([payload])
    finally:
        fat.close()
    _mark_root_file_deleted(image)
    candidate = next(item for item in list_deleted_root_files(image) if item.display_name == "?HORT.TXT")
    layout = _layout(image, 0)
    with image.open("r+b") as handle:
        handle.seek(layout.first_fat_offset + candidate.first_cluster * 2)
        handle.write(b"\xff\xff")
    after_allocation = list_deleted_root_files(image)
    blocked = next(item for item in after_allocation if item.slot_index == candidate.slot_index)
    assert blocked.recoverable is False
    with pytest.raises(DiskForgeError, match="not recoverable"):
        recover_deleted_root_file(image, blocked.slot_index, tmp_path / "should-not-exist.bin")

    existing = tmp_path / "existing.bin"
    existing.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        recover_deleted_root_file(image, blocked.slot_index, existing)
    assert existing.read_bytes() == b"keep"


def test_deleted_root_recovery_rejects_fat32_and_honors_cancellation(tmp_path: Path) -> None:
    fat32 = create_fat_image(tmp_path / "fat32.img", 64 * 1024 * 1024, FileSystemType.FAT32, "RECOVER")
    with pytest.raises(DiskForgeError, match="FAT12/FAT16"):
        list_deleted_root_files(fat32)

    image = create_fat_image(tmp_path / "cancel.img", 8 * 1024 * 1024, FileSystemType.FAT16, "RECOVER")
    token = CancellationToken()
    token.cancel()
    with pytest.raises(OperationCancelled):
        list_deleted_root_files(image, token=token)
