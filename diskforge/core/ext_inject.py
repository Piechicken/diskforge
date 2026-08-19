"""Controlled EXT file injection through explicitly configured e2fsprogs.

``debugfs`` is a filesystem debugger, so DiskForge exposes only a deliberately
small copy-on-write adapter.  It never writes the source image, never uses
force/catastrophic/no-checksum modes, and requires a clean read-only ``e2fsck``
validation before promoting an output.
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


_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_NOT_FOUND = "File not found by ext2_lookup"


@dataclass(frozen=True)
class ExtInjectionResult:
    """Audit information for a verified copy-on-write EXT injection."""

    source: Path
    destination: Path
    source_sha256: str
    target_paths: tuple[str, ...]
    payload_sha256: tuple[str, ...]


class ExtFileInjector:
    """Optional no-mount EXT2/3/4 root-file injector backed by e2fsprogs."""

    def __init__(self, debugfs_executable: str | None = None, e2fsck_executable: str | None = None) -> None:
        self.debugfs = debugfs_executable or shutil.which("debugfs")
        self.e2fsck = e2fsck_executable or shutil.which("e2fsck")

    @staticmethod
    def _available(executable: str | None) -> bool:
        return bool(executable and (Path(executable).is_file() or shutil.which(executable)))

    @property
    def available(self) -> bool:
        return self._available(self.debugfs) and self._available(self.e2fsck)

    def capability_report(self) -> ConverterCapabilityReport:
        formats = ("ext2-ext3-ext4-regular-file-injection",)
        if not self.available:
            missing = [name for name, executable in (("debugfs", self.debugfs), ("e2fsck", self.e2fsck))
                       if not self._available(executable)]
            return ConverterCapabilityReport(
                "e2fsprogs", False, self.debugfs, formats,
                "Optional EXT injection backend is unavailable; configure executable(s): " + ", ".join(missing) + ".",
            )
        return ConverterCapabilityReport(
            "e2fsprogs", True, self.debugfs, formats,
            "Configured e2fsprogs backend can add regular local files to a new standalone EXT image output after explicit confirmation.",
        )

    def _require_available(self) -> None:
        if not self.available or not self.debugfs or not self.e2fsck:
            raise DiskForgeError("EXT file injection requires explicitly configured debugfs and e2fsck executables.")

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
    def _target_path(payload: Path) -> str:
        if not payload.is_file() or payload.is_symlink():
            raise DiskForgeError("EXT injection accepts regular local files only.")
        if not _SAFE_NAME.fullmatch(payload.name):
            raise DiskForgeError("EXT payload filename must use only ASCII letters, digits, dot, underscore, or hyphen.")
        return "/" + payload.name

    @staticmethod
    def _validate_source(source: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(source)
        if str(source).startswith("/dev/"):
            raise DiskForgeError("EXT injection accepts file images only, never physical devices.")
        if inspect_image(source).filesystem != FileSystemType.EXT:
            raise DiskForgeError("EXT injection requires a standalone EXT2, EXT3, or EXT4 volume image at offset 0.")

    def _target_absent(self, image: Path, target_path: str, token: CancellationToken | None) -> bool:
        assert self.debugfs
        result = self._run(self.debugfs, ["-R", f"stat {target_path}", str(image)], token)
        if result.returncode:
            raise DiskForgeError(result.stderr.strip() or "debugfs could not inspect EXT target path.")
        if _NOT_FOUND in result.stderr:
            return True
        if "Inode:" in result.stdout:
            return False
        raise DiskForgeError("debugfs returned an unrecognised target-path inspection result.")

    def _verify_payload(
        self, image: Path, target_path: str, expected_hash: str, workspace: Path, index: int,
        token: CancellationToken | None,
    ) -> None:
        assert self.debugfs
        extracted = workspace / f"verified-{index}.bin"
        result = self._run(self.debugfs, ["-R", f"dump -p {target_path} {extracted}", str(image)], token)
        if result.returncode or not extracted.is_file() or _NOT_FOUND in result.stderr:
            raise DiskForgeError(result.stderr.strip() or f"debugfs could not read back {target_path}.")
        if sha256_file(extracted, token=token) != expected_hash:
            raise DiskForgeError("EXT injected content does not match the local payload SHA-256.")

    def inject(
        self,
        source: Path | str,
        destination: Path | str,
        payloads: Iterable[Path | str],
        *,
        progress: ProgressCallback | None = None,
        token: CancellationToken | None = None,
    ) -> ExtInjectionResult:
        """Copy a standalone EXT image and add verified new root-directory files."""
        self._require_available()
        assert self.debugfs and self.e2fsck
        source_path, destination_path = Path(source), Path(destination)
        self._validate_source(source_path)
        if destination_path.exists():
            raise FileExistsError(f"Destination exists: {destination_path}")
        input_paths = [Path(payload) for payload in payloads]
        if not input_paths:
            raise DiskForgeError("EXT injection requires at least one local payload file.")
        target_paths = tuple(self._target_path(payload) for payload in input_paths)
        if len(set(target_paths)) != len(target_paths):
            raise DiskForgeError("EXT payload filenames must be unique within the root directory.")
        source_hash = sha256_file(source_path, token=token)
        expected_hashes = tuple(sha256_file(payload, token=token) for payload in input_paths)
        temporary = destination_path.with_name(f".{destination_path.name}.ext-inject.partial")
        temporary.unlink(missing_ok=True)
        try:
            stream_copy(source_path, temporary, OperationKind.INJECT, progress=progress, token=token)
            with temporary_directory("diskforge-ext-inject-") as workspace:
                commands = workspace / "commands.txt"
                undo = workspace / "changes.e2undo"
                command_lines: list[str] = []
                for index, (payload, target_path) in enumerate(zip(input_paths, target_paths), start=1):
                    if token:
                        token.raise_if_cancelled()
                    if not self._target_absent(temporary, target_path, token):
                        raise DiskForgeError(f"EXT injection refuses to overwrite existing target: {target_path}")
                    staged = workspace / f"payload-{index}.bin"
                    stream_copy(payload, staged, OperationKind.INJECT, token=token)
                    command_lines.append(f"write {staged} {target_path}")
                commands.write_text("\n".join(command_lines) + "\n", encoding="ascii")
                write = self._run(self.debugfs, ["-w", "-f", str(commands), "-z", str(undo), str(temporary)], token)
                if write.returncode:
                    raise DiskForgeError(write.stderr.strip() or "debugfs EXT injection failed.")
                if not undo.is_file() or undo.stat().st_size == 0:
                    raise DiskForgeError("debugfs completed without producing the required EXT undo log.")
                for index, (target_path, expected_hash) in enumerate(zip(target_paths, expected_hashes), start=1):
                    self._verify_payload(temporary, target_path, expected_hash, workspace, index, token)
                    if progress:
                        progress(Progress(OperationKind.INJECT, index, len(target_paths), f"Injecting {target_path} into EXT"))
            check = self._run(self.e2fsck, ["-fn", str(temporary)], token)
            if check.returncode != 0:
                raise DiskForgeError(check.stdout.strip() or check.stderr.strip() or "e2fsck rejected EXT injection output.")
            if inspect_image(temporary).filesystem != FileSystemType.EXT:
                raise DiskForgeError("EXT injection output no longer has a valid EXT signature.")
            if sha256_file(source_path, token=token) != source_hash:
                raise DiskForgeError("EXT source image changed during copy-on-write injection; output was discarded.")
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, destination_path)
            return ExtInjectionResult(source_path, destination_path, source_hash, target_paths, expected_hashes)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
