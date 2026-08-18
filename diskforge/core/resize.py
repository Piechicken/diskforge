"""Safe, new-file image resizing for RAW and FAT superfloppy images."""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .filesystems import FatImageFilesystem, create_fat_image
from .formats import inspect_image
from .models import FileSystemType, OperationKind, Progress, ProgressCallback
from .partitions import fat_partition_offset
from .storage import CancellationToken, DiskForgeError


_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ResizeResult:
    source: Path
    destination: Path
    previous_size: int
    new_size: int
    filesystem: FileSystemType


def boot_sector_size(path: Path | str) -> int | None:
    """Return the total FAT volume size advertised by a sector-zero BPB."""
    target = Path(path)
    with target.open("rb") as handle:
        sector = handle.read(512)
    if len(sector) != 512:
        return None
    bytes_per_sector = int.from_bytes(sector[11:13], "little")
    total_sectors = int.from_bytes(sector[19:21], "little") or int.from_bytes(sector[32:36], "little")
    if bytes_per_sector not in {512, 1024, 2048, 4096} or total_sectors <= 0:
        return None
    return bytes_per_sector * total_sectors


def _tail_is_zero(source: Path, start: int, token: CancellationToken | None = None) -> bool:
    with source.open("rb") as handle:
        handle.seek(start)
        while block := handle.read(_CHUNK_SIZE):
            if token:
                token.raise_if_cancelled()
            if any(block):
                return False
    return True


def _copy_resized_raw(source: Path, destination: Path, new_size: int,
                      progress: ProgressCallback | None, token: CancellationToken | None) -> None:
    copy_size = min(source.stat().st_size, new_size)
    with source.open("rb") as reader, destination.open("wb") as writer:
        completed = 0
        while completed < copy_size:
            if token:
                token.raise_if_cancelled()
            block = reader.read(min(_CHUNK_SIZE, copy_size - completed))
            if not block:
                raise DiskForgeError("Source image ended during resize.")
            writer.write(block)
            completed += len(block)
            if progress:
                progress(Progress(OperationKind.RESIZE, completed, new_size, "Copying image data"))
        writer.truncate(new_size)
        writer.flush()
        os.fsync(writer.fileno())


def _fat_type(filesystem: FatImageFilesystem, fallback: FileSystemType) -> FileSystemType:
    mapping = {
        12: FileSystemType.FAT12,
        16: FileSystemType.FAT16,
        32: FileSystemType.FAT32,
    }
    # pyfatfs defines stable integer constants (12/16/32); accepting fallback
    # keeps the service resilient to future library changes.
    return mapping.get(int(filesystem.fs.fs.fat_type), fallback)


def _copy_resized_fat(source: Path, destination: Path, new_size: int,
                      filesystem: FileSystemType, progress: ProgressCallback | None,
                      token: CancellationToken | None) -> None:
    if fat_partition_offset(source) != 0:
        raise DiskForgeError("Resizing a partitioned FAT image is not yet supported; export the partition first.")
    stage = Path(tempfile.mkdtemp(prefix="diskforge-resize-", dir=destination.parent))
    source_fs = FatImageFilesystem(source, read_only=True)
    destination_fs: FatImageFilesystem | None = None
    try:
        entries = source_fs.all_entries()
        files = [entry for entry in entries if not entry.is_dir]
        # The fresh FAT allocation has filesystem overhead, so the definitive
        # capacity check happens during injection.  This check produces a clear
        # early error for obviously impossible requests.
        if sum(entry.size for entry in files) > new_size:
            raise DiskForgeError("The requested size is smaller than the stored file data.")
        create_fat_image(destination, new_size, _fat_type(source_fs, filesystem), source_fs.volume_label() or "DISKFORGE")
        destination_fs = FatImageFilesystem(destination)
        total, completed = sum(entry.size for entry in files) or len(files), 0
        for entry in sorted((item for item in entries if item.is_dir), key=lambda item: item.path.count("/")):
            if token:
                token.raise_if_cancelled()
            destination_fs.fs.makedirs(entry.path, recreate=True)
        for entry in files:
            if token:
                token.raise_if_cancelled()
            source_fs.extract([entry.path], stage, token=token)
            extracted = stage / entry.path.lstrip("/")
            destination_fs.inject([extracted], str(Path(entry.path).parent).replace("\\", "/"), token=token)
            destination_fs.set_times(entry.path, created=entry.created, modified=entry.modified)
            if entry.attributes:
                destination_fs.set_attributes(
                    entry.path, read_only="R" in entry.attributes, hidden="H" in entry.attributes,
                    system="S" in entry.attributes, archive="A" in entry.attributes,
                )
            completed += entry.size or 1
            if progress:
                progress(Progress(OperationKind.RESIZE, completed, total, f"Rebuilding {entry.name}"))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if destination_fs:
            destination_fs.close()
        source_fs.close()
        shutil.rmtree(stage, ignore_errors=True)


def resize_image(source: Path | str, destination: Path | str, new_size: int, *,
                 progress: ProgressCallback | None = None, token: CancellationToken | None = None,
                 overwrite: bool = False) -> ResizeResult:
    """Resize an image to a new output file without silently discarding data."""
    input_path, output_path = Path(source), Path(destination)
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if new_size <= 0 or new_size % 512:
        raise DiskForgeError("Image size must be a positive multiple of 512 bytes.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(output_path)
    if input_path.resolve() == output_path.resolve():
        raise DiskForgeError("Resize output must be a new image file.")
    info = inspect_image(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    previous_size = input_path.stat().st_size
    if info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        _copy_resized_fat(input_path, output_path, new_size, info.filesystem, progress, token)
    else:
        if new_size < previous_size and not _tail_is_zero(input_path, new_size, token):
            raise DiskForgeError("Refusing to shrink a raw image that contains non-zero data beyond the requested size.")
        _copy_resized_raw(input_path, output_path, new_size, progress, token)
    return ResizeResult(input_path, output_path, previous_size, new_size, info.filesystem)
