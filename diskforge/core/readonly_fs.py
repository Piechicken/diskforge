"""Optional, read-only NTFS and EXT image access through Sleuth Kit.

The adapter deliberately uses only ``fls`` and ``icat`` read operations.  It
never asks the host operating system to mount a volume and exposes no mutation
methods.  The executables are optional and must be explicitly available on the
user's PATH or supplied by preference in a later GUI layer.
"""
from __future__ import annotations

import os
import posixpath
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .filesystems import ImageFilesystem, _extraction_target, _normal
from .models import ExtractionLayout, ExtractionPolicy, FileSystemType, ImageEntry, OperationKind, Progress, ProgressCallback
from .storage import CancellationToken, DiskForgeError


_LINE = re.compile(r"^(?P<kind>[a-zA-Z])/[a-zA-Z*]+\s+(?P<inode>\d+)(?:-[\d-]+)?:\s*$")


class SleuthKitImageFilesystem(ImageFilesystem):
    """Read-only filesystem facade backed by local Sleuth Kit executables."""

    def __init__(self, image_path: Path | str, filesystem: FileSystemType, *, offset: int = 0,
                 fls_executable: str | None = None, icat_executable: str | None = None) -> None:
        self.path = Path(image_path)
        if filesystem not in {FileSystemType.NTFS, FileSystemType.EXT}:
            raise DiskForgeError("Sleuth Kit browsing is available only for NTFS and EXT filesystems.")
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        if offset < 0 or offset % 512:
            raise DiskForgeError("Filesystem offset must be a non-negative multiple of 512 bytes.")
        self.filesystem = filesystem
        self.offset = offset
        self.fls = fls_executable or shutil.which("fls")
        self.icat = icat_executable or shutil.which("icat")
        if not self.fls or not self.icat:
            raise DiskForgeError("NTFS/EXT browsing requires the optional Sleuth Kit fls and icat executables.")
        self._entries: list[ImageEntry] | None = None
        self._inode_by_path: dict[str, str] = {}

    @property
    def _fs_name(self) -> str:
        return "ntfs" if self.filesystem == FileSystemType.NTFS else "ext"

    @property
    def _base_args(self) -> list[str]:
        args = ["-f", self._fs_name]
        if self.offset:
            args += ["-o", str(self.offset // 512)]
        return args

    def _run(self, executable: str, args: list[str]) -> str:
        completed = subprocess.run([executable, *args], text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, check=False)
        if completed.returncode:
            raise DiskForgeError(completed.stderr.strip() or "Sleuth Kit command failed.")
        return completed.stdout

    @staticmethod
    def _time(value: str) -> datetime | None:
        value = value.replace(" (UTC)", "").strip()
        if value.startswith("0000-00-00"):
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _load_entries(self) -> list[ImageEntry]:
        if self._entries is not None:
            return self._entries
        text = self._run(self.fls, [*self._base_args, "-p", "-r", "-l", str(self.path)])
        entries: list[ImageEntry] = []
        for line in text.splitlines():
            columns = line.split("\t")
            if len(columns) < 2:
                continue
            match = _LINE.match(columns[0])
            if not match or match.group("kind").upper() == "V":
                continue
            raw_path = columns[1].strip().replace("\\", "/")
            if not raw_path or raw_path in {".", ".."} or raw_path.startswith("$"):
                continue
            path = _normal(raw_path)
            if path in self._inode_by_path:
                continue
            is_dir = match.group("kind").lower() == "d"
            modified = self._time(columns[3]) if len(columns) > 3 else None
            try:
                size = int(columns[6]) if len(columns) > 6 else 0
            except ValueError:
                size = 0
            entry = ImageEntry(path, posixpath.basename(path), is_dir, size, modified=modified,
                               attributes=f"inode:{match.group('inode')}")
            entries.append(entry)
            self._inode_by_path[path] = match.group("inode")
        self._entries = sorted(entries, key=lambda item: (not item.is_dir, item.path.casefold()))
        return self._entries

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        root = _normal(path)
        return [entry for entry in self._load_entries() if posixpath.dirname(entry.path) == root]

    def _walk(self, path: str) -> list[ImageEntry]:
        root = _normal(path)
        prefix = root.rstrip("/") + "/"
        return [entry for entry in self._load_entries() if entry.path.startswith(prefix)]

    def _extract_inode(self, inode: str, output: Path, token: CancellationToken | None) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen([self.icat, *self._base_args, str(self.path), inode], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        try:
            with output.open("wb") as destination:
                while True:
                    if token and token.cancelled:
                        process.kill()
                        token.raise_if_cancelled()
                    block = process.stdout.read(1024 * 1024) if process.stdout else b""
                    if not block:
                        break
                    destination.write(block)
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            if process.wait() != 0:
                output.unlink(missing_ok=True)
                raise DiskForgeError(stderr.strip() or "Sleuth Kit file extraction failed.")
        finally:
            if process.poll() is None:
                process.kill()
            process.stdout and process.stdout.close()
            process.stderr and process.stderr.close()

    def extract(self, paths: Sequence[str], destination: Path,
                progress: ProgressCallback | None = None, token: CancellationToken | None = None,
                policy: ExtractionPolicy | None = None) -> list[Path]:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        active_policy = policy or ExtractionPolicy()
        entries_by_path = {entry.path: entry for entry in self._load_entries()}
        files: list[ImageEntry] = []
        for selected in paths:
            entry = entries_by_path.get(_normal(selected))
            if entry is None:
                raise FileNotFoundError(selected)
            if entry.is_dir:
                if active_policy.layout != ExtractionLayout.IGNORE_SUBDIRECTORIES:
                    files.extend(child for child in self._walk(entry.path) if not child.is_dir)
            else:
                files.append(entry)
        files = list({entry.path: entry for entry in files}.values())
        total, completed = sum(entry.size for entry in files) or len(files), 0
        claimed: set[str] = set()
        outputs: list[Path] = []
        for entry in files:
            if token:
                token.raise_if_cancelled()
            output = _extraction_target(destination, entry, active_policy, claimed)
            if output is None:
                continue
            inode = self._inode_by_path.get(entry.path)
            if inode is None:
                raise DiskForgeError("Filesystem entry does not have an inode mapping.")
            self._extract_inode(inode, output, token)
            if entry.size and output.stat().st_size != entry.size:
                output.unlink(missing_ok=True)
                raise DiskForgeError("Extracted file length differs from filesystem metadata.")
            completed += entry.size or 1
            if progress:
                progress(Progress(OperationKind.EXTRACT, completed, total, f"Extracting {entry.name}"))
            outputs.append(output)
        return outputs

    def close(self) -> None:
        self._entries = None
        self._inode_by_path.clear()
