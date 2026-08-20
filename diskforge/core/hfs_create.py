"""Verified classic-HFS image creation through configured hfsutils.

The creator deliberately accepts only a new regular output file. It allocates a
private sibling temporary image, formats it with ``hformat`` in an isolated HOME,
checks the classic-HFS signature, calculates an audit SHA-256, and atomically
promotes the image only after success. It never targets a device, a pre-existing
file, a partition selector, or hformat's destructive ``-f`` mode.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .formats import ConverterCapabilityReport, inspect_image
from .models import FileSystemType, OperationKind, Progress, ProgressCallback
from .storage import CancellationToken, DiskForgeError, sha256_file, temporary_directory


MIN_CLASSIC_HFS_BYTES = 800 * 1024
_HFS_BLOCK_SIZE = 512
_SAFE_VOLUME_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,26}$")


@dataclass(frozen=True)
class HfsCreationResult:
    """Audit information for a verified newly created classic-HFS image."""

    destination: Path
    label: str
    bytes_created: int
    sha256: str


class HfsImageCreator:
    """Optional classic-HFS regular-file creator backed by hfsutils ``hformat``.

    The only supported scope is a newly created, standalone, offset-zero classic
    HFS image in a regular local file. The caller supplies a safe volume label
    and a 512-byte-aligned size of at least 800 KiB. HFS+, MFS, partition maps,
    existing images, device paths, preallocation through a source file, and
    physical-media formatting are intentionally outside this creator.
    """

    def __init__(self, hformat_executable: str | None = None) -> None:
        self.hformat = hformat_executable or shutil.which("hformat")

    @staticmethod
    def _available(executable: str | None) -> bool:
        return bool(executable and (Path(executable).is_file() or shutil.which(executable)))

    @property
    def available(self) -> bool:
        return self._available(self.hformat)

    def capability_report(self) -> ConverterCapabilityReport:
        formats = ("classic-hfs-regular-file-creation",)
        if not self.available:
            return ConverterCapabilityReport(
                "hfsutils", False, self.hformat, formats,
                "Optional classic HFS creation backend is unavailable; configure the hformat executable.",
            )
        return ConverterCapabilityReport(
            "hfsutils", True, self.hformat, formats,
            "Configured hfsutils backend can create a new standalone classic HFS regular-file image after explicit confirmation.",
        )

    def _require_available(self) -> None:
        if not self.available or not self.hformat:
            raise DiskForgeError("Classic HFS image creation requires an explicitly configured hformat executable.")

    @staticmethod
    def _looks_like_device(path: Path | str) -> bool:
        text = str(path)
        normalized = text.replace("\\", "/")
        return normalized.startswith("/dev/") or text.startswith("\\\\.\\")

    @staticmethod
    def _validate_label(label: str) -> str:
        if not _SAFE_VOLUME_LABEL.fullmatch(label):
            raise DiskForgeError(
                "Classic HFS volume label must be 1–27 ASCII characters and use only letters, digits, space, dot, underscore, or hyphen."
            )
        return label

    @staticmethod
    def _validate_size(size_bytes: int) -> int:
        try:
            value = int(size_bytes)
        except (TypeError, ValueError) as exc:
            raise DiskForgeError("Classic HFS image size must be an integer byte count.") from exc
        if value < MIN_CLASSIC_HFS_BYTES:
            raise DiskForgeError("Classic HFS image size must be at least 800 KiB.")
        if value % _HFS_BLOCK_SIZE:
            raise DiskForgeError("Classic HFS image size must be a multiple of 512 bytes.")
        return value

    @staticmethod
    def _run(
        executable: str,
        args: list[str],
        home: Path,
        token: CancellationToken | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if token:
            token.raise_if_cancelled()
        environment = {
            **os.environ,
            "HOME": str(home),
            "LC_ALL": "C",
            "LANG": "C",
        }
        process = subprocess.Popen(
            [executable, *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
        )
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    if token and token.cancelled:
                        process.terminate()
                        try:
                            process.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        token.raise_if_cancelled()
            return subprocess.CompletedProcess([executable, *args], process.returncode, stdout, stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    @staticmethod
    def _allocate(path: Path, size_bytes: int, token: CancellationToken | None = None) -> None:
        if token:
            token.raise_if_cancelled()
        with path.open("wb") as handle:
            handle.truncate(size_bytes)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        if path.stat().st_size != size_bytes:
            raise DiskForgeError("Classic HFS temporary image allocation produced an unexpected size.")

    def create(
        self,
        destination: Path | str,
        size_bytes: int,
        label: str = "DISKFORGE",
        *,
        progress: ProgressCallback | None = None,
        token: CancellationToken | None = None,
    ) -> HfsCreationResult:
        """Create and verify a new standalone classic-HFS regular-file image."""
        self._require_available()
        assert self.hformat
        destination_path = Path(destination)
        if self._looks_like_device(destination_path):
            raise DiskForgeError("Classic HFS creation accepts file outputs only, never physical devices.")
        if destination_path.exists():
            raise FileExistsError(f"Destination exists: {destination_path}")
        validated_size = self._validate_size(size_bytes)
        validated_label = self._validate_label(label)
        if token:
            token.raise_if_cancelled()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.hfs-create.", suffix=".partial", dir=destination_path.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            self._allocate(temporary, validated_size, token)
            if progress:
                progress(Progress(OperationKind.CREATE, 1, 3, "Allocating classic HFS image"))
            with temporary_directory("diskforge-hfs-create-") as workspace:
                home = workspace / "home"
                home.mkdir()
                formatted = self._run(self.hformat, ["-l", validated_label, str(temporary)], home, token)
            if formatted.returncode:
                raise DiskForgeError(formatted.stderr.strip() or "hformat could not create the classic HFS image.")
            if progress:
                progress(Progress(OperationKind.CREATE, 2, 3, "Formatting classic HFS image"))
            if inspect_image(temporary).filesystem != FileSystemType.HFS:
                raise DiskForgeError("Classic HFS creation output does not have a valid HFS signature.")
            digest = sha256_file(temporary, token=token)
            if progress:
                progress(Progress(OperationKind.CREATE, 3, 3, "Verifying classic HFS image"))
            os.replace(temporary, destination_path)
            return HfsCreationResult(destination_path, validated_label, validated_size, digest)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
