"""Controlled NTFS file injection through explicitly configured ntfsprogs.

This module intentionally exposes a narrow, copy-on-write adapter instead of
turning the Sleuth Kit reader into a writer.  It never mounts an image, never
uses ``ntfscp --force``, and never changes the source image.  The optional
external executable is required at call time and is not bundled by DiskForge.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .formats import ConverterCapabilityReport, inspect_image
from .models import FileSystemType, OperationKind, Progress, ProgressCallback
from .storage import CancellationToken, DiskForgeError, sha256_file, stream_copy


_WINDOWS_FORBIDDEN = set('"*/:<>?\\|')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class NtfsInjectionResult:
    """Audit information for a verified copy-on-write NTFS injection."""

    source: Path
    destination: Path
    source_sha256: str
    target_paths: tuple[str, ...]
    payload_sha256: tuple[str, ...]


class NtfsFileInjector:
    """Optional, no-mount NTFS regular-file injector backed by ntfsprogs.

    The supported first scope is intentionally small: source must be a
    standalone offset-zero NTFS volume, every payload is a local regular file,
    and each file is added to the volume root under its own Windows-compatible
    filename.  Existing targets, directories, streams, links, metadata edits,
    partition offsets, mounted volumes, and physical devices are all outside
    this adapter.
    """

    def __init__(
        self,
        ntfscp_executable: str | None = None,
        ntfsls_executable: str | None = None,
        ntfscat_executable: str | None = None,
    ) -> None:
        self.ntfscp = ntfscp_executable or shutil.which("ntfscp")
        self.ntfsls = ntfsls_executable or shutil.which("ntfsls")
        self.ntfscat = ntfscat_executable or shutil.which("ntfscat")

    @staticmethod
    def _available(executable: str | None) -> bool:
        return bool(executable and (Path(executable).is_file() or shutil.which(executable)))

    @property
    def available(self) -> bool:
        return all(self._available(executable) for executable in (self.ntfscp, self.ntfsls, self.ntfscat))

    def capability_report(self) -> ConverterCapabilityReport:
        formats = ("ntfs-regular-file-injection",)
        if not self.available:
            missing = [name for name, executable in (
                ("ntfscp", self.ntfscp), ("ntfsls", self.ntfsls), ("ntfscat", self.ntfscat),
            ) if not self._available(executable)]
            return ConverterCapabilityReport(
                "ntfsprogs", False, self.ntfscp, formats,
                "Optional NTFS injection backend is unavailable; configure executable(s): " + ", ".join(missing) + ".",
            )
        return ConverterCapabilityReport(
            "ntfsprogs", True, self.ntfscp, formats,
            "Configured ntfsprogs backend can copy regular local files into a new standalone NTFS image output after explicit confirmation.",
        )

    def _require_available(self) -> None:
        if not self.available or not self.ntfscp or not self.ntfsls or not self.ntfscat:
            raise DiskForgeError(
                "NTFS file injection requires explicitly configured ntfscp, ntfsls, and ntfscat executables."
            )

    @staticmethod
    def _run(executable: str, args: list[str], token: CancellationToken | None = None) -> subprocess.CompletedProcess[str]:
        if token:
            token.raise_if_cancelled()
        process = subprocess.Popen([executable, *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    def _payload_hash_from_ntfs(
        executable: str, image: Path, target_path: str, token: CancellationToken | None,
    ) -> str:
        if token:
            token.raise_if_cancelled()
        process = subprocess.Popen([executable, str(image), target_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        digest = hashlib.sha256()
        try:
            while True:
                if token:
                    token.raise_if_cancelled()
                block = process.stdout.read(1024 * 1024) if process.stdout else b""
                if not block:
                    break
                digest.update(block)
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            if process.wait() != 0:
                raise DiskForgeError(stderr.strip() or f"ntfscat could not verify {target_path}.")
            return digest.hexdigest()
        finally:
            if process.poll() is None:
                process.kill()
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

    @staticmethod
    def _target_path(payload: Path) -> str:
        if not payload.is_file() or payload.is_symlink():
            raise DiskForgeError("NTFS injection accepts regular local files only.")
        name = payload.name
        stem = name.split(".", 1)[0].upper()
        if not name or name in {".", ".."} or name[-1:] in {" ", "."}:
            raise DiskForgeError("NTFS payload names cannot be empty or end in a space or dot.")
        if any(character in _WINDOWS_FORBIDDEN or ord(character) < 32 for character in name):
            raise DiskForgeError("NTFS payload name contains a Windows-reserved character.")
        if stem in _WINDOWS_RESERVED:
            raise DiskForgeError("NTFS payload name is reserved by Windows.")
        return "/" + name

    @staticmethod
    def _validate_source(source: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(source)
        if str(source).startswith("/dev/"):
            raise DiskForgeError("NTFS injection accepts file images only, never physical devices.")
        info = inspect_image(source)
        if info.filesystem != FileSystemType.NTFS:
            raise DiskForgeError("NTFS injection requires a standalone NTFS volume image at offset 0.")

    def inject(
        self,
        source: Path | str,
        destination: Path | str,
        payloads: Iterable[Path | str],
        *,
        progress: ProgressCallback | None = None,
        token: CancellationToken | None = None,
    ) -> NtfsInjectionResult:
        """Create a separate NTFS output and safely add root-directory files.

        The source hash is captured before copying and checked after all external
        operations.  A private output copy receives an `ntfscp -n` preflight
        and a real write only after each target is confirmed absent.  The copy
        is promoted atomically only after `ntfscat` reproduces every payload
        hash and the image signature still identifies as NTFS.
        """
        self._require_available()
        assert self.ntfscp and self.ntfsls and self.ntfscat
        source_path, destination_path = Path(source), Path(destination)
        self._validate_source(source_path)
        if destination_path.exists():
            raise FileExistsError(f"Destination exists: {destination_path}")
        input_paths = [Path(payload) for payload in payloads]
        if not input_paths:
            raise DiskForgeError("NTFS injection requires at least one local payload file.")
        target_paths = tuple(self._target_path(payload) for payload in input_paths)
        if len(set(target_paths)) != len(target_paths):
            raise DiskForgeError("NTFS payload filenames must be unique within the root directory.")
        if token:
            token.raise_if_cancelled()
        source_hash = sha256_file(source_path, token=token)
        temporary = destination_path.with_name(f".{destination_path.name}.ntfs-inject.partial")
        temporary.unlink(missing_ok=True)
        try:
            stream_copy(source_path, temporary, OperationKind.INJECT, progress=progress, token=token)
            for index, (payload, target_path) in enumerate(zip(input_paths, target_paths), start=1):
                if token:
                    token.raise_if_cancelled()
                existing = self._run(self.ntfsls, ["-l", "-p", target_path, str(temporary)], token)
                if existing.returncode == 0:
                    raise DiskForgeError(f"NTFS injection refuses to overwrite existing target: {target_path}")
                if existing.returncode != 3:
                    raise DiskForgeError(existing.stderr.strip() or "Unable to verify that NTFS target path is absent.")
                preflight = self._run(self.ntfscp, ["-n", str(temporary), str(payload), target_path], token)
                if preflight.returncode:
                    raise DiskForgeError(preflight.stderr.strip() or f"ntfscp preflight failed for {target_path}.")
                write = self._run(self.ntfscp, [str(temporary), str(payload), target_path], token)
                if write.returncode:
                    raise DiskForgeError(write.stderr.strip() or f"ntfscp write failed for {target_path}.")
                if progress:
                    progress(Progress(OperationKind.INJECT, index, len(input_paths), f"Injecting {payload.name} into NTFS"))
            payload_hashes = tuple(
                self._payload_hash_from_ntfs(self.ntfscat, temporary, target_path, token)
                for target_path in target_paths
            )
            expected_hashes = tuple(sha256_file(payload, token=token) for payload in input_paths)
            if payload_hashes != expected_hashes:
                raise DiskForgeError("NTFS injected content does not match the local payload SHA-256.")
            if inspect_image(temporary).filesystem != FileSystemType.NTFS:
                raise DiskForgeError("NTFS injection output no longer has a valid NTFS signature.")
            if sha256_file(source_path, token=token) != source_hash:
                raise DiskForgeError("NTFS source image changed during copy-on-write injection; output was discarded.")
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, destination_path)
            return NtfsInjectionResult(source_path, destination_path, source_hash, target_paths, payload_hashes)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
