"""Controlled classic-HFS file injection through configured hfsutils.

This deliberately narrow adapter writes only a private copy of a standalone
classic HFS image. It never mounts through the host OS, never targets a device
or partition, and never calls destructive HFS utilities such as ``hdel``.
``hfsutils`` has current-volume state in ``$HOME/.hcwd``; every operation
therefore receives a newly created private HOME directory.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .formats import ConverterCapabilityReport, inspect_image
from .models import FileSystemType, OperationKind, Progress, ProgressCallback
from .storage import CancellationToken, DiskForgeError, sha256_file, stream_copy, temporary_directory


_SAFE_HFS_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,30}$")
_MISSING_TARGET = "no such file or directory"


@dataclass(frozen=True)
class HfsInjectionResult:
    """Audit information for a verified copy-on-write classic-HFS injection."""

    source: Path
    destination: Path
    source_sha256: str
    target_paths: tuple[str, ...]
    payload_sha256: tuple[str, ...]


class HfsFileInjector:
    """Optional, copy-on-write classic-HFS root-file injector backed by hfsutils.

    The supported scope is intentionally limited to a standalone offset-zero
    classic HFS volume in a regular local image file. Each payload must be a
    local regular file and is added under its own safe ASCII basename at the HFS
    volume root. The adapter preserves only raw data forks. HFS+, MFS,
    partition offsets, image devices, existing targets, directories, links,
    nested paths, metadata edits, resource forks, rename/delete and source
    mutation are outside this adapter.
    """

    def __init__(
        self,
        hmount_executable: str | None = None,
        hcopy_executable: str | None = None,
        hls_executable: str | None = None,
    ) -> None:
        self.hmount = hmount_executable or shutil.which("hmount")
        self.hcopy = hcopy_executable or shutil.which("hcopy")
        self.hls = hls_executable or shutil.which("hls")

    @staticmethod
    def _available(executable: str | None) -> bool:
        return bool(executable and (Path(executable).is_file() or shutil.which(executable)))

    @property
    def available(self) -> bool:
        return all(self._available(executable) for executable in (self.hmount, self.hcopy, self.hls))

    def capability_report(self) -> ConverterCapabilityReport:
        formats = ("classic-hfs-regular-file-injection",)
        if not self.available:
            missing = [
                name for name, executable in (
                    ("hmount", self.hmount),
                    ("hcopy", self.hcopy),
                    ("hls", self.hls),
                ) if not self._available(executable)
            ]
            return ConverterCapabilityReport(
                "hfsutils", False, self.hmount, formats,
                "Optional classic HFS injection backend is unavailable; configure executable(s): "
                + ", ".join(missing) + ".",
            )
        return ConverterCapabilityReport(
            "hfsutils", True, self.hmount, formats,
            "Configured hfsutils backend can add regular local files to a new standalone classic HFS image output after explicit confirmation.",
        )

    def _require_available(self) -> None:
        if not self.available or not self.hmount or not self.hcopy or not self.hls:
            raise DiskForgeError(
                "Classic HFS file injection requires explicitly configured hmount, hcopy, and hls executables."
            )

    @staticmethod
    def _run(
        executable: str,
        args: list[str],
        home: Path,
        token: CancellationToken | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one HFS utility in a disposable state directory and C locale."""
        if token:
            token.raise_if_cancelled()
        environment = {
            **os.environ,
            "HOME": str(home),
            "LC_ALL": "C",
            "LANG": "C",
        }
        process = subprocess.Popen(
            [executable, *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
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
    def _target_name(name: str) -> str:
        """Validate a classic-HFS root basename independently of host rules."""
        if not _SAFE_HFS_NAME.fullmatch(name):
            raise DiskForgeError(
                "Classic HFS payload filename must be 1–31 ASCII characters and use only letters, digits, space, dot, underscore, or hyphen."
            )
        return ":" + name

    @classmethod
    def _target_path(cls, payload: Path) -> str:
        if not payload.is_file() or payload.is_symlink():
            raise DiskForgeError("Classic HFS injection accepts regular local files only.")
        return cls._target_name(payload.name)

    @staticmethod
    def _looks_like_device(path: Path | str) -> bool:
        text = str(path)
        return text.startswith("/dev/") or text.startswith("\\\\.\\")

    @classmethod
    def _validate_source(cls, source: Path) -> None:
        if cls._looks_like_device(source):
            raise DiskForgeError("Classic HFS injection accepts file images only, never physical devices.")
        if not source.is_file():
            raise FileNotFoundError(source)
        if inspect_image(source).filesystem != FileSystemType.HFS:
            raise DiskForgeError("Classic HFS injection requires a standalone classic HFS volume image at offset 0.")

    def _mount(self, image: Path, home: Path, token: CancellationToken | None) -> None:
        assert self.hmount
        mounted = self._run(self.hmount, [str(image)], home, token)
        if mounted.returncode:
            raise DiskForgeError(mounted.stderr.strip() or "hmount could not open classic HFS injection output.")

    def _target_absent(self, target_path: str, home: Path, token: CancellationToken | None) -> bool:
        """Use hls's diagnostic, not its unreliable success status, for absence."""
        assert self.hls
        result = self._run(self.hls, ["-1", "-N", target_path], home, token)
        diagnostic = result.stderr.casefold()
        if result.returncode == 0 and _MISSING_TARGET in diagnostic:
            return True
        if result.returncode == 0 and not result.stderr.strip():
            return False
        raise DiskForgeError(result.stderr.strip() or "hls could not verify the classic HFS target path.")

    def _verify_payload(
        self,
        target_path: str,
        expected_hash: str,
        workspace: Path,
        home: Path,
        index: int,
        token: CancellationToken | None,
    ) -> None:
        assert self.hcopy
        extracted = workspace / f"verified-{index}.bin"
        result = self._run(self.hcopy, ["-r", target_path, str(extracted)], home, token)
        if result.returncode or not extracted.is_file():
            raise DiskForgeError(result.stderr.strip() or f"hcopy could not read back {target_path}.")
        if sha256_file(extracted, token=token) != expected_hash:
            raise DiskForgeError("Classic HFS injected content does not match the local payload SHA-256.")

    def inject(
        self,
        source: Path | str,
        destination: Path | str,
        payloads: Iterable[Path | str],
        *,
        progress: ProgressCallback | None = None,
        token: CancellationToken | None = None,
    ) -> HfsInjectionResult:
        """Copy a classic HFS source image and add verified new root files."""
        self._require_available()
        assert self.hcopy
        source_path, destination_path = Path(source), Path(destination)
        self._validate_source(source_path)
        if destination_path.exists():
            raise FileExistsError(f"Destination exists: {destination_path}")
        input_paths = [Path(payload) for payload in payloads]
        if not input_paths:
            raise DiskForgeError("Classic HFS injection requires at least one local payload file.")
        target_paths = tuple(self._target_path(payload) for payload in input_paths)
        if len({target.casefold() for target in target_paths}) != len(target_paths):
            raise DiskForgeError("Classic HFS payload filenames must be unique without case distinctions.")
        if token:
            token.raise_if_cancelled()
        source_hash = sha256_file(source_path, token=token)
        expected_hashes = tuple(sha256_file(payload, token=token) for payload in input_paths)
        temporary = destination_path.with_name(f".{destination_path.name}.hfs-inject.partial")
        temporary.unlink(missing_ok=True)
        try:
            stream_copy(source_path, temporary, OperationKind.HFS_INJECT, progress=progress, token=token)
            with temporary_directory("diskforge-hfs-inject-") as workspace:
                home = workspace / "home"
                home.mkdir()
                self._mount(temporary, home, token)
                for index, (payload, target_path, expected_hash) in enumerate(
                    zip(input_paths, target_paths, expected_hashes), start=1
                ):
                    if token:
                        token.raise_if_cancelled()
                    if not self._target_absent(target_path, home, token):
                        raise DiskForgeError(
                            f"Classic HFS injection refuses to overwrite existing target: {target_path}"
                        )
                    write = self._run(self.hcopy, ["-r", str(payload), ":"], home, token)
                    if write.returncode:
                        raise DiskForgeError(write.stderr.strip() or f"hcopy write failed for {target_path}.")
                    self._verify_payload(target_path, expected_hash, workspace, home, index, token)
                    if progress:
                        progress(
                            Progress(
                                OperationKind.HFS_INJECT,
                                index,
                                len(target_paths),
                                f"Injecting {payload.name} into classic HFS",
                            )
                        )
            if inspect_image(temporary).filesystem != FileSystemType.HFS:
                raise DiskForgeError("Classic HFS injection output no longer has a valid HFS signature.")
            if sha256_file(source_path, token=token) != source_hash:
                raise DiskForgeError(
                    "Classic HFS source image changed during copy-on-write injection; output was discarded."
                )
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, destination_path)
            return HfsInjectionResult(source_path, destination_path, source_hash, target_paths, expected_hashes)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
