"""Filesystem-level image operations for FAT and ISO9660 media.

The service exposes a uniform directory model to the GUI.  FAT is writable;
ISO9660 images are intentionally treated as immutable and are rebuilt into a
new image when files need to be injected.
"""
from __future__ import annotations

import os
import posixpath
import tempfile
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import pycdlib

# pyfatfs currently imports PyFilesystem2, whose namespace-package bootstrap still
# calls pkg_resources.  The three warnings below originate solely during that
# third-party import, are tracked upstream, and do not indicate a DiskForge API
# problem.  Keep the filter constrained to the import block so pytest -W error
# remains strict for all project code and every other warning source.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=r"pkg_resources is deprecated as an API.*",
                            category=Warning, module=r"(fs|pkg_resources)(\..*)?$")
    warnings.filterwarnings("ignore", message=r"Deprecated call to `pkg_resources\.declare_namespace.*",
                            category=DeprecationWarning, module=r"(fs|pkg_resources)(\..*)?$")
    from pyfatfs.EightDotThree import EightDotThree
    from pyfatfs.FATDirectoryEntry import FATDirectoryEntry
    from pyfatfs.PyFat import PyFat
    from pyfatfs.PyFatFS import PyFatFS

from .formats import inspect_image
from .models import (ConflictPolicy, ExtractionLayout, ExtractionPolicy, FileSystemType,
                     ImageEntry, OperationKind, Progress, ProgressCallback, iter_parent_paths)
from .partitions import fat_partition_offset
from .storage import CancellationToken, DiskForgeError


@dataclass(frozen=True)
class DirectoryPage:
    """A deterministic, bounded directory slice returned to desktop consumers."""

    entries: tuple[ImageEntry, ...]
    total: int
    offset: int
    limit: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.entries) < self.total


class ImageFilesystem:
    """Common image filesystem facade with cached, cancellable directory paging."""

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        raise NotImplementedError

    @staticmethod
    def _sort_entries(entries: Sequence[ImageEntry], sort_by: str, ascending: bool) -> tuple[ImageEntry, ...]:
        keys = {
            "name": lambda entry: (not entry.is_dir, entry.name.casefold()),
            "type": lambda entry: (not entry.is_dir, entry.name.rsplit(".", 1)[-1].casefold() if "." in entry.name else ""),
            "size": lambda entry: (not entry.is_dir, entry.size, entry.name.casefold()),
            "modified": lambda entry: (not entry.is_dir, entry.modified.timestamp() if entry.modified else float("-inf"), entry.name.casefold()),
        }
        if sort_by not in keys:
            raise DiskForgeError("Directory sort key is unsupported.")
        return tuple(sorted(entries, key=keys[sort_by], reverse=not ascending))

    def list_entries_page(self, path: str = "/", *, offset: int = 0, limit: int = 250,
                          sort_by: str = "name", ascending: bool = True,
                          token: CancellationToken | None = None) -> DirectoryPage:
        """Return a bounded directory page and retain a sorted cache for revisits."""
        if offset < 0 or limit <= 0:
            raise DiskForgeError("Directory page offset and limit must be positive.")
        if token:
            token.raise_if_cancelled()
        cache = getattr(self, "_directory_page_cache", None)
        if cache is None:
            cache = {}
            setattr(self, "_directory_page_cache", cache)
        normalized = _normal(path)
        key = (normalized, sort_by, ascending)
        entries = cache.get(key)
        if entries is None:
            source = self.list_entries(normalized)
            if token:
                token.raise_if_cancelled()
            entries = self._sort_entries(source, sort_by, ascending)
            cache[key] = entries
        if token:
            token.raise_if_cancelled()
        return DirectoryPage(entries[offset:offset + limit], len(entries), offset, limit)

    def clear_directory_cache(self) -> None:
        cache = getattr(self, "_directory_page_cache", None)
        if cache is not None:
            cache.clear()

    def walk_entries(self, path: str = "/", *, token: CancellationToken | None = None) -> Iterator[ImageEntry]:
        """Yield a complete subtree through the paged directory interface."""
        pending = [_normal(path)]
        while pending:
            directory = pending.pop()
            offset = 0
            while True:
                if token:
                    token.raise_if_cancelled()
                page = self.list_entries_page(directory, offset=offset, limit=250, token=token)
                for entry in page.entries:
                    if token:
                        token.raise_if_cancelled()
                    yield entry
                    if entry.is_dir:
                        pending.append(entry.path)
                offset += len(page.entries)
                if not page.has_more:
                    break

    def extract(self, paths: Sequence[str], destination: Path,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None,
                policy: ExtractionPolicy | None = None) -> list[Path]:
        raise NotImplementedError

    def close(self) -> None:
        self.clear_directory_cache()


def _normal(path: str) -> str:
    path = "/" + path.replace("\\", "/").strip("/")
    return posixpath.normpath(path)


_DOS_ATTRIBUTE_FLAGS = {
    "read_only": FATDirectoryEntry.ATTR_READ_ONLY,
    "hidden": FATDirectoryEntry.ATTR_HIDDEN,
    "system": FATDirectoryEntry.ATTR_SYSTEM,
    "archive": FATDirectoryEntry.ATTR_ARCHIVE,
}


def _format_dos_attributes(value: int) -> str:
    """Render the editable DOS attribute bits in a stable user-facing order."""
    labels = (("R", FATDirectoryEntry.ATTR_READ_ONLY), ("H", FATDirectoryEntry.ATTR_HIDDEN),
              ("S", FATDirectoryEntry.ATTR_SYSTEM), ("A", FATDirectoryEntry.ATTR_ARCHIVE))
    return "".join(label for label, flag in labels if value & flag)


def _extraction_target(destination: Path, entry: ImageEntry, policy: ExtractionPolicy,
                       claimed: set[str]) -> Path | None:
    """Choose a safe output path according to explicit layout/conflict policy."""
    relative = entry.name if policy.layout == ExtractionLayout.FLATTEN else entry.path.lstrip("/")
    candidate = destination / relative
    root = destination.resolve()
    resolved = candidate.resolve()
    if root != resolved and root not in resolved.parents:
        raise DiskForgeError("Extraction path escapes the selected destination.")
    key = str(resolved).casefold()
    conflict = key in claimed or candidate.exists()
    if not conflict:
        claimed.add(key)
        return candidate
    if policy.conflict == ConflictPolicy.ERROR:
        raise FileExistsError(candidate)
    if policy.conflict == ConflictPolicy.SKIP:
        return None
    if policy.conflict == ConflictPolicy.OVERWRITE:
        if candidate.is_dir():
            raise IsADirectoryError(candidate)
        claimed.add(key)
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    index = 2
    while True:
        renamed = candidate.with_name(f"{stem}-{index}{suffix}")
        renamed_key = str(renamed.resolve()).casefold()
        if renamed_key not in claimed and not renamed.exists():
            claimed.add(renamed_key)
            return renamed
        index += 1


class FatImageFilesystem(ImageFilesystem):
    """Read/write FAT filesystem wrapper, including MBR/GPT partition offsets."""

    def __init__(self, image_path: Path | str, read_only: bool = False) -> None:
        self.path = Path(image_path)
        self.offset = fat_partition_offset(self.path)
        # Historical FAT volumes may retain the DOS dirty-volume bit even when
        # their directory and allocation data are fully readable.  pyfatfs emits
        # this advisory at open time; it cannot help the user recover data and
        # would otherwise leak as an application warning.  Scope the filter to
        # this one dependency message so all other warnings remain fatal.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"Filesystem was not cleanly unmounted on last access.*",
                category=UserWarning,
                module=r"pyfatfs\.PyFat",
            )
            self.fs = PyFatFS(str(self.path), offset=self.offset, read_only=read_only, preserve_case=True)
        self.read_only = read_only

    def close(self) -> None:
        self.clear_directory_cache()
        self.fs.close()

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        root = _normal(path)
        entries: list[ImageEntry] = []
        for name in self.fs.listdir(root):
            entry_path = _normal(posixpath.join(root, name))
            info = self.fs.getinfo(entry_path, namespaces=["details"])
            details = info.raw.get("details", {})
            dentry = self.fs._get_dir_entry(entry_path)
            entries.append(ImageEntry(
                path=entry_path,
                name=name,
                is_dir=bool(info.is_dir),
                size=int(details.get("size", 0) or 0),
                modified=_from_timestamp(details.get("modified")),
                created=_from_timestamp(details.get("created")),
                attributes=_format_dos_attributes(dentry.attr),
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
                token: CancellationToken | None = None,
                policy: ExtractionPolicy | None = None) -> list[Path]:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        active_policy = policy or ExtractionPolicy()
        selected: list[ImageEntry] = []
        for item_path in paths:
            normalized = _normal(item_path)
            info = self.fs.getinfo(normalized, namespaces=["details"])
            selected.append(ImageEntry(normalized, Path(normalized).name, bool(info.is_dir),
                                      int(info.raw.get("details", {}).get("size", 0) or 0)))
        files: list[ImageEntry] = []
        for entry in selected:
            if not entry.is_dir:
                files.append(entry)
            elif active_policy.layout != ExtractionLayout.IGNORE_SUBDIRECTORIES:
                files.extend(child for child in self._walk(entry.path) if not child.is_dir)
        deduplicated = {entry.path: entry for entry in files}
        files = list(deduplicated.values())
        total = sum(entry.size for entry in files) or len(files)
        done = 0
        extracted: list[Path] = []
        claimed: set[str] = set()
        for entry in files:
            if token:
                token.raise_if_cancelled()
            output = _extraction_target(destination, entry, active_policy, claimed)
            if output is None:
                continue
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

    def rename(self, item_path: str, new_name: str) -> str:
        """Rename a FAT file or directory within its current parent directory."""
        if self.read_only:
            raise DiskForgeError("This FAT image is open read-only.")
        source = _normal(item_path)
        candidate = new_name.strip()
        if not candidate or candidate in {".", ".."} or "/" in candidate or "\\" in candidate:
            raise DiskForgeError("A new name must be a single non-empty filename.")
        destination = _normal(posixpath.join(posixpath.dirname(source), candidate))
        if destination == source:
            return source
        if self.fs.exists(destination):
            raise FileExistsError(destination)
        self.fs.move(source, destination)
        return destination

    def set_attributes(self, item_path: str, *, read_only: bool | None = None,
                       hidden: bool | None = None, system: bool | None = None,
                       archive: bool | None = None) -> str:
        """Update the standard editable DOS attribute bits of one FAT entry."""
        if self.read_only:
            raise DiskForgeError("This FAT image is open read-only.")
        entry = self.fs._get_dir_entry(_normal(item_path))
        requested = {
            "read_only": read_only,
            "hidden": hidden,
            "system": system,
            "archive": archive,
        }
        value = entry.attr
        for name, enabled in requested.items():
            if enabled is None:
                continue
            flag = _DOS_ATTRIBUTE_FLAGS[name]
            value = value | flag if enabled else value & ~flag
        entry.attr = value
        self.fs.fs.update_directory_entry(entry.get_parent_dir())
        return _format_dos_attributes(value)

    def set_times(self, item_path: str, *, created: datetime | None = None,
                  modified: datetime | None = None, accessed: datetime | None = None) -> None:
        """Update FAT timestamps without changing omitted fields."""
        if self.read_only:
            raise DiskForgeError("This FAT image is open read-only.")
        details = {
            name: value.timestamp()
            for name, value in (("created", created), ("modified", modified), ("accessed", accessed))
            if value is not None
        }
        if not details:
            return
        self.fs.setinfo(_normal(item_path), {"details": details})

    def set_modified(self, item_path: str, modified: datetime) -> None:
        """Backward-compatible shorthand for timestamp editing."""
        self.set_times(item_path, modified=modified)

    def volume_label(self) -> str:
        """Return the FAT BPB volume label (without trailing padding)."""
        header = self.fs.fs.bpb_header
        label = header.get("BS_VolLab", b"")
        if isinstance(label, str):
            return label.rstrip()
        return bytes(label).decode("ascii", errors="replace").rstrip()

    def set_volume_label(self, label: str) -> str:
        """Update both the BPB label and the root-directory volume-ID entry."""
        if self.read_only:
            raise DiskForgeError("This FAT image is open read-only.")
        normalized = label.strip().upper()
        if not normalized or len(normalized) > 11 or any(ord(character) < 32 or ord(character) > 126 for character in normalized):
            raise DiskForgeError("A FAT volume label must contain 1–11 printable ASCII characters.")
        fat = self.fs.fs
        fat.bpb_header["BS_VolLab"] = normalized.ljust(11).encode("ascii")
        fat._write_bpb_header()
        _, _, specials = fat.root_dir.get_entries()
        volume_entry = next((entry for entry in specials if entry.is_volume_id()), None)
        if volume_entry is None:
            label_name = EightDotThree(encoding=fat.encoding)
            label_name.set_str_name(EightDotThree.make_8dot3_name(normalized, fat.root_dir))
            volume_entry = FATDirectoryEntry.new(name=label_name, tz=datetime.now().astimezone().tzinfo,
                                                 encoding=fat.encoding,
                                                 attr=FATDirectoryEntry.ATTR_VOLUME_ID)
            fat.root_dir.add_subdirectory(volume_entry)
        else:
            label_name = EightDotThree(encoding=fat.encoding)
            label_name.set_str_name(EightDotThree.make_8dot3_name(normalized, fat.root_dir))
            volume_entry.name = label_name
        fat.update_directory_entry(fat.root_dir)
        return normalized

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
                token: CancellationToken | None = None,
                policy: ExtractionPolicy | None = None) -> list[Path]:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        active_policy = policy or ExtractionPolicy()
        targets: list[ImageEntry] = []
        for selected in paths:
            normalized = _normal(selected)
            candidates = [entry for entry in self._walk("/") if entry.path.lower() == normalized.lower()]
            if not candidates:
                raise FileNotFoundError(selected)
            targets.extend(candidates)
        files: list[ImageEntry] = []
        for entry in targets:
            if not entry.is_dir:
                files.append(entry)
            elif active_policy.layout != ExtractionLayout.IGNORE_SUBDIRECTORIES:
                files.extend(child for child in self._walk(entry.path) if not child.is_dir)
        files = list({entry.path: entry for entry in files}.values())
        total = sum(entry.size for entry in files) or len(files)
        complete = 0
        outputs: list[Path] = []
        claimed: set[str] = set()
        for entry in files:
            if token:
                token.raise_if_cancelled()
            output = _extraction_target(destination, entry, active_policy, claimed)
            if output is None:
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            self.iso.get_file_from_iso(str(output), iso_path=self._iso_path(entry.path))
            complete += entry.size or 1
            if progress:
                progress(Progress(OperationKind.EXTRACT, complete, total, f"Extracting {entry.name}"))
            outputs.append(output)
        return outputs


def create_fat_image(path: Path | str, size_bytes: int, filesystem: FileSystemType,
                     label: str = "DISKFORGE", *, media_type: int = 0xF8,
                     sectors_per_track: int = 0, heads: int = 0) -> Path:
    """Create a formatted FAT superfloppy image of a requested size.

    ``media_type`` and optional BIOS geometry are deliberately explicit because
    they are presentation/firmware metadata rather than an instruction to write
    a physical device.  A zero geometry preserves the formatter default.
    """
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
        if not 0 <= media_type <= 0xFF:
            raise DiskForgeError("FAT media type must be a single unsigned byte.")
        if not 0 <= sectors_per_track <= 0xFFFF or not 0 <= heads <= 0xFFFF:
            raise DiskForgeError("FAT geometry values must fit in 16-bit BPB fields.")
        pyfat.mkfs(str(target), fat_type=fat_type, size=size_bytes, label=label[:11], media_type=media_type)
        completed = True
    finally:
        if completed:
            pyfat.close()
    # pyfatfs writes its final BPB while closing.  Patch optional geometry only
    # after that flush so its close operation cannot overwrite these fields.
    if sectors_per_track or heads:
        with target.open("r+b") as handle:
            handle.seek(24)
            handle.write(int(sectors_per_track).to_bytes(2, "little"))
            handle.write(int(heads).to_bytes(2, "little"))
            handle.flush()
            os.fsync(handle.fileno())
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
                              volume_label: str = "DISKFORGE", *,
                              boot_image: Path | str | None = None,
                              boot_platform_id: int = 0,
                              boot_media: str = "noemul",
                              boot_info_table: bool = False,
                              boot_load_segment: int = 0) -> Path:
    """Build an ISO9660/Joliet image, optionally with a validated El Torito entry.

    A boot image may either be a file inside ``source_directory`` or an external
    local file.  An external image is copied into the *new* ISO as ``BOOT.IMG``;
    its source bytes are never changed.  Only standard El Torito media modes are
    accepted, and the resulting catalog can be inspected with ``inspect_eltorito``.
    """
    source, target = Path(source_directory), Path(destination)
    if not source.is_dir():
        raise NotADirectoryError(source)
    if boot_media not in {"noemul", "floppy", "hdemul"}:
        raise DiskForgeError("El Torito boot media must be noemul, floppy, or hdemul.")
    if not 0 <= boot_platform_id <= 0xFF:
        raise DiskForgeError("El Torito platform ID must be an unsigned byte.")
    if not 0 <= boot_load_segment <= 0xFFFF:
        raise DiskForgeError("El Torito load segment must fit in 16 bits.")
    selected_boot = Path(boot_image).resolve() if boot_image is not None else None
    if selected_boot is not None and not selected_boot.is_file():
        raise FileNotFoundError(selected_boot)
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, vol_ident=volume_label[:32])
    try:
        directories = [item for item in source.rglob("*") if item.is_dir()]
        for directory in directories:
            relative = directory.relative_to(source).as_posix()
            iso.add_directory(iso_path="/" + relative.upper(), joliet_path="/" + relative)
        boot_iso_path: str | None = None
        for file_path in (item for item in source.rglob("*") if item.is_file()):
            relative = file_path.relative_to(source).as_posix()
            iso_path = "/" + relative.upper() + ";1"
            iso.add_file(str(file_path), iso_path=iso_path, joliet_path="/" + relative)
            if selected_boot is not None and file_path.resolve() == selected_boot:
                boot_iso_path = iso_path
        if selected_boot is not None and boot_iso_path is None:
            boot_iso_path = "/BOOT.IMG;1"
            iso.add_file(str(selected_boot), iso_path=boot_iso_path, joliet_path="/boot.img")
        if boot_iso_path is not None:
            iso.add_eltorito(
                boot_iso_path, platform_id=boot_platform_id, media_name=boot_media,
                boot_info_table=boot_info_table, boot_load_seg=boot_load_segment,
            )
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
