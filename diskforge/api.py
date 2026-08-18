"""Stable, typed public API for embedding DiskForge image workflows.

The API intentionally exposes only file-image operations. Physical device writes
remain interactive desktop workflows and are not available for unattended hosts.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from .core.compare import ComparisonResult, compare_streams
from .core.filesystems import FatImageFilesystem, ImageFilesystem, IsoImageFilesystem, create_fat_image
from .core.formats import Converter, convert_image, inspect_image
from .core.models import (ExtractionPolicy, FileSystemType, ImageFormat, ImageInfo,
                          ProgressCallback)
from .core.readonly_fs import SleuthKitImageFilesystem
from .core.storage import CancellationToken, DiskForgeError, sha256_file

API_VERSION = "1.0"


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

    @contextmanager
    def filesystem(self, image: Path | str, *, writable: bool = False) -> Iterator[ImageFilesystem]:
        """Open a filesystem facade and always release the underlying resource."""
        source = Path(image)
        info = self.inspect(source)
        if info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
            filesystem: ImageFilesystem = FatImageFilesystem(source, read_only=not writable)
        elif info.filesystem == FileSystemType.ISO9660:
            if writable:
                raise DiskForgeError("ISO images are read-only; create a new ISO instead.")
            filesystem = IsoImageFilesystem(source)
        elif info.filesystem in {FileSystemType.NTFS, FileSystemType.EXT}:
            if writable:
                raise DiskForgeError("NTFS and EXT image access is read-only.")
            filesystem = SleuthKitImageFilesystem(source, info.filesystem)
        else:
            raise DiskForgeError("No filesystem facade is available for this image.")
        try:
            yield filesystem
        finally:
            filesystem.close()

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
