"""Explicit, safe filesystem routing for validated image partitions.

Partition parsing remains separate from filesystem access.  This module accepts a
stable one-based table index only after :func:`select_partition` validates the
MBR/GPT structure.  FAT is the sole writable partition workflow.  NTFS, EXT,
classic HFS, and HFS+ can use the existing Sleuth Kit adapter at the exact
partition byte offset, but are always read-only.
"""
from __future__ import annotations

from pathlib import Path

from .filesystems import FatImageFilesystem, ImageFilesystem
from .models import FileSystemType
from .partitions import select_partition
from .readonly_fs import SleuthKitImageFilesystem
from .storage import DiskForgeError


_FAT_FILESYSTEMS = frozenset({
    FileSystemType.FAT12,
    FileSystemType.FAT16,
    FileSystemType.FAT32,
})
_READONLY_FILESYSTEMS = frozenset({
    FileSystemType.NTFS,
    FileSystemType.EXT,
    FileSystemType.HFS,
    FileSystemType.HFS_PLUS,
})


def open_partition_filesystem(
    image: Path | str,
    partition_index: int,
    *,
    writable: bool = False,
    fls_executable: str | None = None,
    icat_executable: str | None = None,
) -> ImageFilesystem:
    """Open exactly one validated image partition under the narrowest contract.

    ``partition_index`` is never inferred.  FAT retains the established
    caller-controlled writable mode.  Every other supported filesystem is
    routed through ``fls``/``icat`` with its validated byte offset and refuses
    writable access before an external process is started.
    """
    target = Path(image)
    partition = select_partition(target, partition_index)
    if partition.filesystem in _FAT_FILESYSTEMS:
        return FatImageFilesystem(target, read_only=not writable, partition_index=partition_index)
    if partition.filesystem in _READONLY_FILESYSTEMS:
        if writable:
            raise DiskForgeError(
                f"Partition {partition_index} is {partition.filesystem.value} and is available for read-only browsing only."
            )
        return SleuthKitImageFilesystem(
            target,
            partition.filesystem,
            offset=partition.offset,
            fls_executable=fls_executable,
            icat_executable=icat_executable,
        )
    raise DiskForgeError(
        f"Partition {partition_index} is not a supported FAT, NTFS, EXT, HFS, or HFS+ filesystem."
    )
