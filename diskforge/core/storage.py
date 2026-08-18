"""Streaming storage primitives and destructive-operation safeguards."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import BinaryIO, Iterator, Optional

from .models import OperationKind, Progress, ProgressCallback, SECTOR_SIZE


DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024


class DiskForgeError(RuntimeError):
    """Base exception exposed to the desktop layer."""


class OperationCancelled(DiskForgeError):
    """Raised when a user cancelled a long-running operation."""


class SafetyError(DiskForgeError):
    """Raised before an unsafe device-changing operation starts."""


@dataclass(frozen=True)
class CopyResult:
    source: Path | str
    destination: Path | str
    bytes_copied: int
    source_sha256: str
    destination_sha256: Optional[str] = None


class CancellationToken:
    """Thread-safe cancellation flag passed from GUI workers to core services."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OperationCancelled("The operation was cancelled.")


def _size_of(stream_or_path: Path | str | BinaryIO) -> int:
    if isinstance(stream_or_path, (str, Path)):
        return Path(stream_or_path).stat().st_size
    current = stream_or_path.tell()
    stream_or_path.seek(0, os.SEEK_END)
    size = stream_or_path.tell()
    stream_or_path.seek(current)
    return size


def sha256_file(path: Path | str, chunk_size: int = DEFAULT_CHUNK_SIZE,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> str:
    """Calculate SHA-256 progressively without loading a whole image in memory."""
    target = Path(path)
    total = target.stat().st_size
    digest = hashlib.sha256()
    completed = 0
    with target.open("rb") as handle:
        while block := handle.read(chunk_size):
            if token:
                token.raise_if_cancelled()
            digest.update(block)
            completed += len(block)
            if progress:
                progress(Progress(OperationKind.VERIFY, completed, total, "Hashing image"))
    return digest.hexdigest()


def stream_copy(
    source: Path | str,
    destination: Path | str,
    operation: OperationKind,
    *,
    limit: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress: ProgressCallback | None = None,
    token: CancellationToken | None = None,
    overwrite: bool = False,
    source_offset: int = 0,
    destination_offset: int = 0,
) -> CopyResult:
    """Copy bytes transactionally to a file or explicitly to a block device.

    File destinations are written to a sibling temporary path and atomically
    replaced only after a successful copy.  A device destination is never
    inferred here: callers must invoke ``validate_device_write`` first.
    """
    source_path = Path(source)
    destination_text = str(destination)
    destination_path = Path(destination)
    source_size = source_path.stat().st_size
    expected = min(limit if limit is not None else source_size - source_offset,
                   source_size - source_offset)
    if expected < 0:
        raise DiskForgeError("Source offset is beyond the end of the file.")
    if destination_path.exists() and destination_path.is_file() and not overwrite:
        raise FileExistsError(f"Destination exists: {destination_path}")

    write_to_device = _looks_like_device(destination_text)
    temp_path: Path | None = None
    actual_destination: Path | str = destination
    if not write_to_device:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.", suffix=".partial", dir=destination_path.parent
        )
        os.close(descriptor)
        temp_path = Path(temporary_name)
        actual_destination = temp_path

    digest = hashlib.sha256()
    copied = 0
    try:
        with source_path.open("rb") as src, open(actual_destination, "r+b" if write_to_device else "wb") as dst:
            src.seek(source_offset)
            dst.seek(destination_offset)
            remaining = expected
            while remaining:
                if token:
                    token.raise_if_cancelled()
                block = src.read(min(chunk_size, remaining))
                if not block:
                    raise DiskForgeError("Source ended before the expected byte count.")
                dst.write(block)
                digest.update(block)
                copied += len(block)
                remaining -= len(block)
                if progress:
                    progress(Progress(operation, copied, expected, "Copying sectors"))
            dst.flush()
            try:
                os.fsync(dst.fileno())
            except OSError:
                pass
        if temp_path:
            os.replace(temp_path, destination_path)
    except Exception:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        raise
    return CopyResult(source, destination, copied, digest.hexdigest())


def verify_equal(source: Path | str, destination: Path | str,
                 bytes_to_compare: int | None = None,
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 progress: ProgressCallback | None = None,
                 token: CancellationToken | None = None) -> bool:
    """Compare two streams incrementally and return false at the first mismatch."""
    source_path, destination_path = Path(source), Path(destination)
    source_size, destination_size = source_path.stat().st_size, destination_path.stat().st_size
    expected = bytes_to_compare if bytes_to_compare is not None else source_size
    if source_size < expected or destination_size < expected:
        return False
    compared = 0
    with source_path.open("rb") as src, destination_path.open("rb") as dst:
        while compared < expected:
            if token:
                token.raise_if_cancelled()
            take = min(chunk_size, expected - compared)
            if src.read(take) != dst.read(take):
                return False
            compared += take
            if progress:
                progress(Progress(OperationKind.VERIFY, compared, expected, "Verifying sectors"))
    return True


def _looks_like_device(path: str) -> bool:
    if os.name == "nt":
        return path.startswith("\\\\.\\")
    return path.startswith("/dev/")


def validate_device_write(
    device_path: str,
    image_size: int,
    device_size: int,
    confirmation_phrase: str,
    *,
    expected_phrase: str = "ERASE",
    is_system_disk: bool = False,
    mounted: bool = False,
) -> None:
    """Enforce application-level safety rules before any physical device write."""
    if not _looks_like_device(device_path):
        raise SafetyError("Target is not a recognized raw device path.")
    if is_system_disk:
        raise SafetyError("Refusing to overwrite the operating-system disk.")
    if mounted:
        raise SafetyError("Refusing to overwrite a mounted device. Unmount it first.")
    if image_size > device_size:
        raise SafetyError("The image is larger than the target device.")
    if confirmation_phrase.strip().upper() != expected_phrase:
        raise SafetyError(f"Type {expected_phrase} exactly to authorize this destructive operation.")


@contextmanager
def temporary_directory(prefix: str = "diskforge-") -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def read_sector(path: Path | str, sector: int, sector_size: int = SECTOR_SIZE) -> bytes:
    if sector < 0:
        raise ValueError("Sector index must be non-negative.")
    with Path(path).open("rb") as handle:
        handle.seek(sector * sector_size)
        data = handle.read(sector_size)
    if len(data) != sector_size:
        raise DiskForgeError("Requested sector is outside the image.")
    return data


def write_sector(path: Path | str, sector: int, data: bytes, sector_size: int = SECTOR_SIZE) -> None:
    if len(data) != sector_size:
        raise ValueError(f"A sector must contain exactly {sector_size} bytes.")
    with Path(path).open("r+b") as handle:
        handle.seek(sector * sector_size)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
