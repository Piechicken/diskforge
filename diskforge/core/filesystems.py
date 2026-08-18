"""Filesystem-level image operations for FAT and ISO9660 media.

The service exposes a uniform directory model to the GUI.  FAT is writable;
ISO9660 images are intentionally treated as immutable and are rebuilt into a
new image when files need to be injected.
"""
from __future__ import annotations

import os
import posixpath
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import pycdlib
from pyfatfs.PyFat import PyFat
from pyfatfs.PyFatFS import PyFatFS

from .formats import inspect_image
from .models import FileSystemType, ImageEntry, OperationKind, Progress, ProgressCallback, iter_parent_paths
from .partitions import fat_partition_offset
from .storage import CancellationToken, DiskForgeError


class ImageFilesystem:
    """Common image filesystem facade."""

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        raise NotImplementedError

    def extract(self, paths: Sequence[str], destination: Path,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> list[Path]:
        raise NotImplementedError

    def close(self) -> None:
        return None


def _normal(path: str) -> str:
    path = "/" + path.replace("\\", "/").strip("/")
    return posixpath.normpath(path)


class FatImageFilesystem(ImageFilesystem):
    """Read/write FAT filesystem wrapper, including MBR/GPT partition offsets."""

    def __init__(self, image_path: Path | str, read_only: bool = False) -> None:
        self.path = Path(image_path)
        self.offset = fat_partition_offset(self.path)
        self.fs = PyFatFS(str(self.path), offset=self.offset, read_only=read_only, preserve_case=True)
        self.read_only = read_only

    def close(self) -> None:
        self.fs.close()

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        root = _normal(path)
        entries: list[ImageEntry] = []
        for name in self.fs.listdir(root):
            entry_path = _normal(posixpath.join(root, name))
            info = self.fs.getinfo(entry_path, namespaces=["details"])
            details = info.raw.get("details", {})
            entries.append(ImageEntry(
                path=entry_path,
                name=name,
                is_dir=bool(info.is_dir),
                size=int(details.get("size", 0) or 0),
                modified=_from_timestamp(details.get("modified")),
                created=_from_timestamp(details.get("created")),
            ))
        return sorted(entries, key=lambda item: (not item.is_dir, item.name.lower()))

    def _walk(self, path: str = "/") -> Iterator[ImageEntry]:
        for entry in self.list_entries(path):
            yield entry
            if entry.is_dir and entry.path != _normal(path):
                yield from self._walk(entry.path)

    def all_entries(self) -> list[ImageEntry]:
        return list(self._walk("/"))

    def extract(self, paths: Sequence[str], destination: Path,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> list[Path]:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        selected: list[ImageEntry] = []
        for item_path in paths:
            normalized = _normal(item_path)
            info = self.fs.getinfo(normalized, namespaces=["details"])
            selected.append(ImageEntry(normalized, Path(normalized).name, bool(info.is_dir),
                                      int(info.raw.get("details", {}).get("size", 0) or 0)))
        files = [entry for entry in selected if not entry.is_dir]
        total = sum(entry.size for entry in files) or len(files)
        done = 0
        extracted: list[Path] = []
        for entry in selected:
            if token:
                token.raise_if_cancelled()
            if entry.is_dir:
                for child in self._walk(entry.path):
                    if not child.is_dir:
                        self._extract_file(child, destination / child.path.lstrip("/"), token)
                        done += child.size or 1
                        if progress:
                            progress(Progress(OperationKind.EXTRACT, done, total, f"Extracting {child.name}"))
                        extracted.append(destination / child.path.lstrip("/"))
            else:
                output = destination / entry.path.lstrip("/")
                self._extract_file(entry, output, token)
                done += entry.size or 1
                if progress:
                    progress(Progress(OperationKind.EXTRACT, done, total, f"Extracting {entry.name}"))
                extracted.append(output)
        return extracted

    def _extract_file(self, entry: ImageEntry, output: Path, token: CancellationToken | None) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with self.fs.openbin(entry.path, "r") as src, output.open("wb") as dst:
            while block := src.read(1024 * 1024):
                if token:
                    token.raise_if_cancelled()
                dst.write(block)

    def inject(self, sources: Sequence[Path | str], target_directory: str = "/",
               progress: ProgressCallback | None = None,
               token: CancellationToken | None = None) -> list[str]:
        if self.read_only:
            raise DiskForgeError("This FAT image is open read-only.")
        destination = _normal(target_directory)
        if not self.fs.exists(destination):
            self.fs.makedirs(destination, recreate=True)
        source_files: list[tuple[Path, str]] = []
        for item in (Path(source) for source in sources):
            if not item.exists():
                raise FileNotFoundError(item)
            if item.is_dir():
                for file_path in item.rglob("*"):
                    if file_path.is_file():
                        relative = file_path.relative_to(item.parent).as_posix()
                        source_files.append((file_path, _normal(posixpath.join(destination, relative))))
            else:
                source_files.append((item, _normal(posixpath.join(destination, item.name))))
        total = sum(item.stat().st_size for item, _ in source_files) or len(source_files)
        done = 0
        injected: list[str] = []
        for source, target in source_files:
            if token:
                token.raise_if_cancelled()
            parent = posixpath.dirname(target)
            self.fs.makedirs(parent, recreate=True)
            with source.open("rb") as src, self.fs.openbin(target, "w") as dst:
                while block := src.read(1024 * 1024):
                    if token:
                        token.raise_if_cancelled()
                    dst.write(block)
                    done += len(block)
                    if progress:
                        progress(Progress(OperationKind.INJECT, done, total, f"Injecting {source.name}"))
            injected.append(target)
        return injected

    def delete(self, paths: Sequence[str]) -> None:
        if self.read_only:
            raise DiskForgeError("This FAT image is open read-only.")
        for item_path in sorted((_normal(value) for value in paths), key=len, reverse=True):
            info = self.fs.getinfo(item_path)
            if info.is_dir:
                self.fs.removetree(item_path)
            else:
                self.fs.remove(item_path)

    def set_modified(self, item_path: str, modified: datetime) -> None:
        if self.read_only:
            raise DiskForgeError("This FAT image is open read-only.")
        self.fs.setinfo(_normal(item_path), {"details": {"modified": modified.timestamp()}})

    def export_listing(self, output: Path, html: bool = False) -> Path:
        entries = self.all_entries()
        output.parent.mkdir(parents=True, exist_ok=True)
        if html:
            rows = "\n".join(
                f"<tr><td>{_escape(entry.path)}</td><td>{'Directory' if entry.is_dir else 'File'}</td>"
                f"<td>{entry.size}</td><td>{entry.modified.isoformat() if entry.modified else ''}</td></tr>"
                for entry in entries
            )
            output.write_text(
                "<!doctype html><meta charset='utf-8'><title>DiskForge image listing</title>"
                "<table><thead><tr><th>Path</th><th>Type</th><th>Bytes</th><th>Modified</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>", encoding="utf-8"
            )
        else:
            output.write_text("\n".join(
                f"{'D' if entry.is_dir else 'F'}\t{entry.size}\t{entry.modified.isoformat() if entry.modified else ''}\t{entry.path}"
                for entry in entries
            ) + "\n", encoding="utf-8")
        return output


class IsoImageFilesystem(ImageFilesystem):
    """Read-only ISO9660/Rock Ridge/Joliet browser and extractor."""

    def __init__(self, image_path: Path | str) -> None:
        self.path = Path(image_path)
        self.iso = pycdlib.PyCdlib()
        self.iso.open(str(self.path))

    def close(self) -> None:
        self.iso.close()

    @staticmethod
    def _iso_path(path: str) -> str:
        normalized = _normal(path)
        return "/" if normalized == "/" else normalized.upper() + ";1"

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        iso_path = "/" if _normal(path) == "/" else _normal(path).upper()
        entries: list[ImageEntry] = []
        for record in self.iso.list_children(iso_path=iso_path):
            raw = record.file_identifier()
            if raw in (b"\x00", b"\x01", b".", b".."):
                continue
            name = raw.decode("utf-8", errors="replace").rstrip(";1")
            is_dir = record.is_dir()
            entries.append(ImageEntry(
                path=_normal(posixpath.join(path, name)), name=name, is_dir=is_dir,
                size=int(record.data_length or 0),
            ))
        return sorted(entries, key=lambda item: (not item.is_dir, item.name.lower()))

    def _walk(self, path: str = "/") -> Iterator[ImageEntry]:
        for entry in self.list_entries(path):
            yield entry
            if entry.is_dir and entry.path != _normal(path):
                yield from self._walk(entry.path)

    def extract(self, paths: Sequence[str], destination: Path,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> list[Path]:
        destination.mkdir(parents=True, exist_ok=True)
        targets: list[ImageEntry] = []
        for selected in paths:
            normalized = _normal(selected)
            candidates = [entry for entry in self._walk("/") if entry.path.lower() == normalized.lower()]
            if not candidates:
                raise FileNotFoundError(selected)
            targets.extend(candidates)
        files = []
        for entry in targets:
            files.extend([entry] if not entry.is_dir else [child for child in self._walk(entry.path) if not child.is_dir])
        total = sum(entry.size for entry in files) or len(files)
        complete = 0
        outputs: list[Path] = []
        for entry in files:
            if token:
                token.raise_if_cancelled()
            output = destination / entry.path.lstrip("/")
            output.parent.mkdir(parents=True, exist_ok=True)
            self.iso.get_file_from_iso(str(output), iso_path=self._iso_path(entry.path))
            complete += entry.size or 1
            if progress:
                progress(Progress(OperationKind.EXTRACT, complete, total, f"Extracting {entry.name}"))
            outputs.append(output)
        return outputs


def create_fat_image(path: Path | str, size_bytes: int, filesystem: FileSystemType,
                     label: str = "DISKFORGE") -> Path:
    """Create a formatted FAT superfloppy image of a requested size."""
    fat_type = {
        FileSystemType.FAT12: PyFat.FAT_TYPE_FAT12,
        FileSystemType.FAT16: PyFat.FAT_TYPE_FAT16,
        FileSystemType.FAT32: PyFat.FAT_TYPE_FAT32,
    }.get(filesystem)
    if fat_type is None:
        raise DiskForgeError("Only FAT12, FAT16 and FAT32 can be formatted natively.")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # PyFat opens an existing writable file, so preallocate without loading it into memory.
    with target.open("wb") as handle:
        handle.truncate(size_bytes)
    pyfat = PyFat()
    completed = False
    try:
        pyfat.mkfs(str(target), fat_type=fat_type, size=size_bytes, label=label[:11])
        completed = True
    finally:
        if completed:
            pyfat.close()
    return target


def defragment_fat_image(source_image: Path | str, destination_image: Path | str,
                        progress: ProgressCallback | None = None,
                        token: CancellationToken | None = None) -> Path:
    """Rebuild a FAT superfloppy image with files written contiguously.

    FAT has no portable in-place defragmentation primitive. Rebuilding is safer:
    the source is opened read-only, every directory/file is copied into a fresh
    formatted image, and the original remains untouched until the user chooses
    to replace it. Partitioned images are intentionally excluded because this
    native formatter creates superfloppy images.
    """
    source, destination = Path(source_image), Path(destination_image)
    info = inspect_image(source)
    if info.filesystem not in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        raise DiskForgeError("Defragmentation is available for FAT images only.")
    if fat_partition_offset(source) != 0:
        raise DiskForgeError("Partitioned FAT images are not rebuilt in place; extract and re-create a new image instead.")
    import tempfile
    import shutil
    stage = Path(tempfile.mkdtemp(prefix="diskforge-defrag-"))
    source_fs = FatImageFilesystem(source, read_only=True)
    try:
        entries = source_fs.all_entries()
        actual_filesystem = {
            PyFat.FAT_TYPE_FAT12: FileSystemType.FAT12,
            PyFat.FAT_TYPE_FAT16: FileSystemType.FAT16,
            PyFat.FAT_TYPE_FAT32: FileSystemType.FAT32,
        }.get(source_fs.fs.fs.fat_type, info.filesystem)
        create_fat_image(destination, source.stat().st_size, actual_filesystem, "DISKFORGE")
        destination_fs = FatImageFilesystem(destination)
        try:
            files = [entry for entry in entries if not entry.is_dir]
            total = sum(entry.size for entry in files) or len(files)
            completed = 0
            for entry in sorted((item for item in entries if item.is_dir), key=lambda value: value.path.count("/")):
                if token:
                    token.raise_if_cancelled()
                destination_fs.fs.makedirs(entry.path, recreate=True)
            for entry in files:
                if token:
                    token.raise_if_cancelled()
                source_fs.extract([entry.path], stage)
                extracted = stage / entry.path.lstrip("/")
                destination_fs.inject([extracted], str(Path(entry.path).parent).replace("\\", "/"), token=token)
                completed += entry.size or 1
                if progress:
                    progress(Progress(OperationKind.DEFRAGMENT, completed, total, f"Rebuilding {entry.name}"))
        finally:
            destination_fs.close()
    finally:
        source_fs.close()
        shutil.rmtree(stage, ignore_errors=True)
    return destination


def create_iso_from_directory(source_directory: Path | str, destination: Path | str,
                              volume_label: str = "DISKFORGE"):
    """Build a portable ISO9660/Joliet image from a local directory tree."""
    source, target = Path(source_directory), Path(destination)
    if not source.is_dir():
        raise NotADirectoryError(source)
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, vol_ident=volume_label[:32])
    try:
        directories = [item for item in source.rglob("*") if item.is_dir()]
        for directory in directories:
            relative = directory.relative_to(source).as_posix()
            iso.add_directory(iso_path="/" + relative.upper(), joliet_path="/" + relative)
        for file_path in (item for item in source.rglob("*") if item.is_file()):
            relative = file_path.relative_to(source).as_posix()
            iso.add_file(str(file_path), iso_path="/" + relative.upper() + ";1", joliet_path="/" + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        iso.write(str(target))
    finally:
        iso.close()
    return target


def _from_timestamp(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value)) if value is not None else None
    except (TypeError, ValueError, OSError):
        return None


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
