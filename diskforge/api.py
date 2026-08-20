"""Stable, typed public API for embedding DiskForge image workflows.

The API intentionally exposes only file-image operations. Physical device writes
remain interactive desktop workflows and are not available for unattended hosts.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence

from .core.browse_session import materialize_browsable_image
from .core.compare import ComparisonResult, compare_streams
from .core.cpc_dsk import CpcDskInspection, export_cpc_dsk_to_raw, inspect_cpc_dsk
from .core.d88 import D88Inspection, export_d88_to_raw, inspect_d88
from .core.fat_metadata import (FatMetadataResult, apply_fat_metadata,
                                metadata_update_from_values)
from .core.fat_recovery import DeletedFatFileCandidate
from .core.imd import ImdInspection, export_imd_to_raw, inspect_imd
from .core.inventory import (ImageInventory, ImageInventoryOptions, ReportFormat,
                             export_image_inventory, inventory_images)
from .core.td0 import Td0Inspection, export_td0_to_raw, inspect_td0
from .core.filesystems import (FatImageFilesystem, ImageFilesystem, IsoImageFilesystem,
                               create_fat_image, replace_iso_file_safely)
from .core.formats import Converter, convert_image, inspect_image
from .core.models import (DiskPartition, ExtractionPolicy, FileSystemType, ImageFormat, ImageInfo,
                          ProgressCallback)
from .core.mounts import ImageMountCapability, ImageMountManager, ImageMountSession
from .core.partition_filesystems import open_partition_filesystem
from .core.partitions import list_partitions
from .core.readonly_fs import SleuthKitImageFilesystem
from .core.storage import CancellationToken, DiskForgeError, sha256_file

API_VERSION = "1.1"


@dataclass(frozen=True)
class ApiResult:
    """A small structured outcome suitable for logging across host applications."""

    operation: str
    source: Path | None
    destination: Path | None = None
    detail: str = ""


class DiskForgeClient:
    """A dependency-injectable facade for safe file-image operations."""

    def __init__(self, converter: Converter | None = None) -> None:
        self.converter = converter

    def inspect(self, image: Path | str) -> ImageInfo:
        return inspect_image(image, self.converter)

    def sha256(self, image: Path | str) -> str:
        return sha256_file(image)

    def compare(self, source: Path | str, destination: Path | str, *,
                ignore_trailing_zero_sectors: bool = False,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> ComparisonResult:
        return compare_streams(
            source, destination, ignore_trailing_zero_sectors=ignore_trailing_zero_sectors,
            progress=progress, token=token,
        )

    def create_fat(self, destination: Path | str, *, size_bytes: int,
                   filesystem: FileSystemType, label: str = "DISKFORGE") -> ApiResult:
        target = create_fat_image(destination, size_bytes, filesystem, label)
        return ApiResult("create_fat", None, target, f"Created {filesystem.value} image")

    def convert(self, source: Path | str, destination: Path | str, *,
                image_format: ImageFormat, overwrite: bool = False,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> ApiResult:
        info = convert_image(source, destination, image_format, self.converter, progress, token, overwrite)
        return ApiResult("convert", Path(source), info.path, info.image_format.value)

    def inventory_images(self, root: Path | str, options: ImageInventoryOptions | None = None,
                         *, token: CancellationToken | None = None) -> ImageInventory:
        """Read only local image metadata and optional hashes into a filtered inventory."""
        return inventory_images(root, options, converter=self.converter, token=token)

    def export_image_inventory(self, inventory: ImageInventory, destination: Path | str,
                               report_format: ReportFormat, *,
                               token: CancellationToken | None = None) -> ApiResult:
        """Write a new JSON, CSV, or HTML inventory report without overwrite."""
        output = export_image_inventory(inventory, destination, report_format, token)
        return ApiResult("export_image_inventory", inventory.root, output, report_format)

    def partitions(self, image: Path | str) -> list[DiskPartition]:
        """Return validated MBR/GPT entries without selecting or mutating a partition."""
        return list_partitions(image)

    def inspect_imd(self, source: Path | str, *, token: CancellationToken | None = None) -> ImdInspection:
        """Inspect IMD track records without mutating or flattening the source."""
        return inspect_imd(source, token)

    def export_imd_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven normal-data rectangular IMD layout to a new RAW file."""
        output = export_imd_to_raw(source, destination, token)
        return ApiResult("export_imd_to_raw", Path(source), output, "Strict IMD-to-RAW export")

    def inspect_td0(self, source: Path | str, *, token: CancellationToken | None = None) -> Td0Inspection:
        """Inspect an ordinary TD0 sector container without mutating or flattening the source."""
        return inspect_td0(source, token)

    def export_td0_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven unflagged ordinary TD0 rectangular layout to a new RAW file."""
        output = export_td0_to_raw(source, destination, token)
        return ApiResult("export_td0_to_raw", Path(source), output, "Strict TD0-to-RAW export")

    def inspect_cpc_dsk(self, source: Path | str, *, token: CancellationToken | None = None) -> CpcDskInspection:
        """Inspect a signed CPC standard/extended DSK container without mutation."""
        return inspect_cpc_dsk(source, token)

    def export_cpc_dsk_to_raw(self, source: Path | str, destination: Path | str, *,
                              token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven normal rectangular CPC DSK layout to a new RAW file."""
        output = export_cpc_dsk_to_raw(source, destination, token)
        return ApiResult("export_cpc_dsk_to_raw", Path(source), output, "Strict CPC DSK-to-RAW export")

    def inspect_d88(self, source: Path | str, *, token: CancellationToken | None = None) -> D88Inspection:
        """Inspect one restricted D88 sector container without mutation."""
        return inspect_d88(source, token)

    def export_d88_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven normal rectangular D88 layout to a new RAW file."""
        output = export_d88_to_raw(source, destination, token)
        return ApiResult("export_d88_to_raw", Path(source), output, "Strict D88-to-RAW export")

    def replace_iso_file(self, source: Path | str, iso_path: str, replacement: Path | str,
                         destination: Path | str, *, overwrite: bool = False) -> ApiResult:
        """Write an equal-length ISO file replacement to a new verified image."""
        result = replace_iso_file_safely(source, iso_path, replacement, destination, overwrite=overwrite)
        return ApiResult("replace_iso_file", result.source, result.destination,
                         f"Replaced {result.iso_path} ({result.bytes_replaced} bytes) in a verified new ISO")

    def mount_capability(self) -> ImageMountCapability:
        """Report whether the local operating-system read-only mount backend is available."""
        return ImageMountManager().capability_report()

    def mount_read_only(self, image: Path | str) -> ImageMountSession:
        """Create a system-backed read-only mount session; callers must later unmount it."""
        return ImageMountManager().mount(image)

    def unmount(self, session: ImageMountSession) -> None:
        """Release a session produced by :meth:`mount_read_only`."""
        ImageMountManager().unmount(session)

    @contextmanager
    def filesystem(self, image: Path | str, *, writable: bool = False,
                   partition_index: int | None = None) -> Iterator[ImageFilesystem]:
        """Open a filesystem facade and always release the underlying resource."""
        source = Path(image)
        info = self.inspect(source)
        browse_session = None
        filesystem: ImageFilesystem | None = None
        try:
            if info.image_format == ImageFormat.TD0:
                raise DiskForgeError("TD0 images are read-only sector containers; inspect them or use strict TD0 RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.CPC_DSK:
                raise DiskForgeError("CPC DSK images are read-only sector containers; inspect them or use strict CPC DSK RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.D88:
                raise DiskForgeError("D88 images are read-only sector containers; inspect them or use strict D88 RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.ZIP:
                if writable:
                    raise DiskForgeError("ZIP image containers are read-only; writable filesystem access is unavailable.")
                browse_session = materialize_browsable_image(source, converter=self.converter)
                source = browse_session.image
                info = self.inspect(source)
            if partition_index is not None:
                filesystem = open_partition_filesystem(source, partition_index, writable=writable)
            elif info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
                filesystem = FatImageFilesystem(source, read_only=not writable)
            elif info.filesystem == FileSystemType.ISO9660:
                if writable:
                    raise DiskForgeError("ISO images are read-only; create a new ISO instead.")
                filesystem = IsoImageFilesystem(source)
            elif info.filesystem in {FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS, FileSystemType.HFS_PLUS}:
                if writable:
                    raise DiskForgeError("NTFS, EXT, HFS and HFS+ image access is read-only.")
                filesystem = SleuthKitImageFilesystem(source, info.filesystem)
            else:
                raise DiskForgeError("No filesystem facade is available for this image.")
            yield filesystem
        finally:
            if filesystem is not None:
                filesystem.close()
            if browse_session is not None:
                browse_session.close()

    def extract(self, image: Path | str, paths: Sequence[str], destination: Path | str, *,
                policy: ExtractionPolicy | None = None,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> list[Path]:
        with self.filesystem(image) as filesystem:
            return filesystem.extract(paths, Path(destination), progress, token, policy)

    def inject(self, image: Path | str, sources: Sequence[Path | str], *,
               target_directory: str = "/", progress: ProgressCallback | None = None,
               token: CancellationToken | None = None) -> list[str]:
        with self.filesystem(image, writable=True) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images accept file injection.")
            return filesystem.inject(sources, target_directory, progress, token)


    def set_fat_metadata(self, image: Path | str, paths: Sequence[str], *,
                         read_only: bool | None = None, hidden: bool | None = None,
                         system: bool | None = None, archive: bool | None = None,
                         created: datetime | None = None, modified: datetime | None = None,
                         accessed: datetime | None = None, partition_index: int | None = None,
                         token: CancellationToken | None = None) -> tuple[FatMetadataResult, ...]:
        """Update standard DOS attributes and/or FAT times for explicit existing entry paths."""
        update = metadata_update_from_values(
            paths, read_only=read_only, hidden=hidden, system=system, archive=archive,
            created=created, modified=modified, accessed=accessed,
        )
        with self.filesystem(image, writable=True, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images support metadata updates.")
            return apply_fat_metadata(filesystem, update, token)

    def move_fat(self, image: Path | str, item_path: str, target_directory: str) -> str:
        """Move one regular file into an existing directory of a writable FAT image."""
        with self.filesystem(image, writable=True) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images support file movement.")
            return filesystem.move(item_path, target_directory)

    def list_deleted_fat(self, image: Path | str, *, partition_index: int | None = None) -> list[DeletedFatFileCandidate]:
        """List conservative FAT12/FAT16 deleted fixed-root-file candidates without mutating the image."""
        with self.filesystem(image, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Deleted-file candidates are available only for FAT images.")
            return filesystem.deleted_root_file_candidates()

    def recover_deleted_fat(self, image: Path | str, slot_index: int, destination: Path | str, *,
                            partition_index: int | None = None) -> Path:
        """Copy one revalidated single-cluster FAT deleted-file candidate to a new local output file."""
        with self.filesystem(image, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Deleted-file recovery is available only for FAT images.")
            return filesystem.recover_deleted_root_file(slot_index, destination)
