"""Filesystem-level image operations for FAT and ISO9660 media.

The service exposes a uniform directory model to the GUI.  FAT is writable;
ISO9660 images are intentionally treated as immutable and are rebuilt into a
new image when files need to be injected.
"""
from __future__ import annotations

import os
import posixpath
import shutil
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

from .eltorito import ElToritoBootImage, inspect_eltorito
from .fat_recovery import (DeletedFatFileCandidate, list_deleted_root_files,
                           recover_deleted_root_file)
from .listing import export_directory_listing
from .formats import inspect_image
from .models import (ConflictPolicy, ExtractionLayout, ExtractionPolicy, FileSystemType,
                     ImageEntry, OperationKind, Progress, ProgressCallback, iter_parent_paths)
from .partitions import fat_partition_offset
from .storage import CancellationToken, DiskForgeError, sha256_file, stream_copy


@dataclass(frozen=True)
class IsoReplacementResult:
    """Verified result of a conservative file replacement in a copied ISO."""

    source: Path
    destination: Path
    iso_path: str
    bytes_replaced: int
    source_sha256: str
    output_sha256: str


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

    def __init__(self, image_path: Path | str, read_only: bool = False,
                 partition_index: int | None = None) -> None:
        self.path = Path(image_path)
        self.partition_index = partition_index
        self.offset = fat_partition_offset(self.path, partition_index=partition_index)
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

    def deleted_root_file_candidates(self, token: CancellationToken | None = None) -> list[DeletedFatFileCandidate]:
        """List conservative FAT12/FAT16 deleted root-file recovery candidates without mutation."""
        return list_deleted_root_files(self.path, offset=self.offset, token=token)

    def recover_deleted_root_file(self, slot_index: int, destination: Path | str,
                                  token: CancellationToken | None = None) -> Path:
        """Restore one revalidated single-cluster deleted-file candidate to a new local file."""
        return recover_deleted_root_file(self.path, slot_index, destination, offset=self.offset, token=token)

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

    def move(self, item_path: str, target_directory: str) -> str:
        """Move one FAT file or directory into an existing directory without overwrite."""
        if self.read_only:
            raise DiskForgeError("This FAT image is open read-only.")
        source = _normal(item_path)
        destination_directory = _normal(target_directory)
        if source == "/":
            raise DiskForgeError("The FAT root directory cannot be moved.")
        if not self.fs.exists(source):
            raise FileNotFoundError(source)
        if not self.fs.exists(destination_directory):
            raise DiskForgeError("The FAT move target directory does not exist.")
        source_info = self.fs.getinfo(source)
        target_info = self.fs.getinfo(destination_directory)
        if not target_info.is_dir:
            raise DiskForgeError("The FAT move target must be an existing directory.")
        if source_info.is_dir:
            raise DiskForgeError("FAT directory moves are not supported because they cannot be completed atomically.")
        destination = _normal(posixpath.join(destination_directory, posixpath.basename(source)))
        if destination == source:
            return source
        if self.fs.exists(destination):
            raise FileExistsError(destination)
        self.fs.move(source, destination)
        return destination

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
        """Export the same complete read-only report available to every facade."""
        return export_directory_listing(self, self.path, output, html=html)


def _iso9660_file_path(path: str) -> str:
    """Normalize one user-facing path to the ISO9660 file identifier form."""
    normalized = _normal(path)
    if normalized == "/":
        raise DiskForgeError("ISO replacement requires an existing regular file, not the root directory.")
    upper = normalized.upper()
    return upper if ";" in Path(upper).name else upper + ";1"


def replace_iso_file_safely(source_iso: Path | str, iso_path: str, replacement: Path | str,
                            destination_iso: Path | str, *, overwrite: bool = False) -> IsoReplacementResult:
    """Replace one equal-length ISO9660 file in a verified *new* ISO image.

    ISO directory metadata is inherently fragile.  The service therefore uses
    pycdlib's focused in-place editor only on a byte-for-byte copy, accepts no
    directory or size changes, and validates the reopened result before making
    it available.  The original ISO and the local replacement source are never
    opened for writing.
    """
    source, candidate, destination = Path(source_iso), Path(replacement), Path(destination_iso)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    if source.resolve() == destination.resolve():
        raise DiskForgeError("The replacement destination must be different from the source ISO.")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    if not hasattr(pycdlib, "InPlaceEditor"):
        raise DiskForgeError("This pycdlib version does not provide the required safe ISO editor.")

    internal_path = _iso9660_file_path(iso_path)
    source_hash = sha256_file(source)
    replacement_hash = sha256_file(candidate)
    replacement_size = candidate.stat().st_size
    probe = pycdlib.PyCdlib()
    try:
        probe.open(str(source))
        if probe.has_rock_ridge() or probe.has_udf():
            raise DiskForgeError(
                "Safe replacement currently supports ISO9660/Joliet images only; Rock Ridge and UDF are refused."
            )
        try:
            record = probe.get_record(iso_path=internal_path)
        except Exception as exc:
            raise FileNotFoundError(internal_path) from exc
        if record.is_dir():
            raise DiskForgeError("ISO replacement requires an existing regular file, not a directory.")
        if int(record.data_length or 0) != replacement_size:
            raise DiskForgeError("The replacement file size must exactly match the existing ISO file size.")
    finally:
        probe.close()

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream_copy(source, destination, OperationKind.CONVERT, overwrite=overwrite)
        with candidate.open("rb") as payload:
            with pycdlib.InPlaceEditor(str(destination)) as editor:
                editor.modify_file(payload, replacement_size, internal_path)

        verifier = pycdlib.PyCdlib()
        extracted_path: Path | None = None
        try:
            verifier.open(str(destination))
            verified_record = verifier.get_record(iso_path=internal_path)
            if verified_record.is_dir() or int(verified_record.data_length or 0) != replacement_size:
                raise DiskForgeError("The replaced ISO entry did not retain its expected type and size.")
            descriptor, temporary_name = tempfile.mkstemp(prefix="diskforge-iso-verify-", suffix=".bin")
            os.close(descriptor)
            extracted_path = Path(temporary_name)
            verifier.get_file_from_iso(str(extracted_path), iso_path=internal_path)
            if sha256_file(extracted_path) != replacement_hash:
                raise DiskForgeError("The reopened ISO does not contain the requested replacement bytes.")
        finally:
            verifier.close()
            if extracted_path is not None:
                extracted_path.unlink(missing_ok=True)

        if sha256_file(source) != source_hash:
            raise DiskForgeError("The source ISO changed during the replacement operation.")
        if sha256_file(candidate) != replacement_hash:
            raise DiskForgeError("The replacement source changed during the replacement operation.")
        return IsoReplacementResult(source, destination, internal_path, replacement_size,
                                    source_hash, sha256_file(destination))
    except Exception:
        destination.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class IsoRebuildResult:
    """Verified result of ISO content editing into a separately rebuilt image."""

    source: Path
    destination: Path
    files_added: tuple[str, ...]
    paths_deleted: tuple[str, ...]
    directories_created: tuple[str, ...]
    source_sha256: str
    output_sha256: str


@dataclass(frozen=True)
class _ElToritoRebuildSpec:
    """The strictly reproducible part of one initial El Torito boot entry."""

    boot_path: str
    catalog_path: str
    platform_id: int
    bootable: bool
    media_name: str
    boot_load_size: int | None
    boot_load_segment: int
    expected_system_type: int
    expected_sector_count_512: int


def _iso_workspace_path(root: Path, path: str, *, allow_root: bool = False) -> tuple[str, Path]:
    """Map a caller ISO path to a traversal-safe location in an isolated workspace."""
    raw = str(path).replace("\\", "/")
    if any(part in {"", ".", ".."} for part in raw.split("/") if part):
        if ".." in raw.split("/"):
            raise DiskForgeError("ISO edit paths must not contain parent-directory components.")
    normalized = _normal(raw)
    if normalized == "/" and not allow_root:
        raise DiskForgeError("This ISO edit operation requires a path below the ISO root.")
    candidate = root if normalized == "/" else root / normalized.lstrip("/")
    resolved_root, resolved_candidate = root.resolve(), candidate.resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise DiskForgeError("ISO edit path escapes the isolated workspace.")
    return normalized, candidate


def _existing_iso_workspace_path(root: Path, path: str, *, allow_root: bool = False) -> tuple[str, Path]:
    """Resolve an existing ISO9660 workspace path without case-sensitive host assumptions."""
    normalized, _ = _iso_workspace_path(root, path, allow_root=allow_root)
    if normalized == "/":
        return normalized, root
    candidate = root
    for part in normalized.lstrip("/").split("/"):
        matches = [child for child in candidate.iterdir() if child.name.casefold() == part.casefold()]
        if len(matches) != 1:
            raise FileNotFoundError(normalized)
        candidate = matches[0]
    return normalized, candidate


def _iso_has_eltorito(source: Path) -> bool:
    try:
        inspect_eltorito(source)
    except DiskForgeError as exc:
        if str(exc) == "ISO image does not contain an El Torito boot record.":
            return False
        raise
    return True


def _eltorito_paths_at_lba(filesystem: "IsoImageFilesystem", entries: Sequence[ImageEntry], lba: int) -> list[ImageEntry]:
    """Return ordinary files backed by one contiguous extent starting at *lba*."""
    expected_offset = lba * 2048
    matches: list[ImageEntry] = []
    for entry in entries:
        if entry.is_dir:
            continue
        try:
            extents = filesystem.iso.get_file_byte_extents(**filesystem._lookup(entry.path))
        except Exception:
            continue
        if len(extents) == 1 and extents[0][0] == expected_offset:
            matches.append(entry)
    return matches


def _eltorito_media_parameters(image: ElToritoBootImage, boot_size: int) -> tuple[str, int | None]:
    """Translate only pycdlib-reproducible catalog fields to creator parameters."""
    if image.media_type == 0:
        if image.system_type != 0 or not 0 < image.sector_count_512 <= 0xFFFF:
            raise DiskForgeError("El Torito no-emulation metadata is unsupported for safe rebuilding.")
        if image.byte_count > boot_size:
            raise DiskForgeError("El Torito boot entry reads beyond its referenced file.")
        return "noemul", image.sector_count_512
    if image.media_type in {1, 2, 3}:
        expected_size = {1: 1200 * 1024, 2: 1440 * 1024, 3: 2880 * 1024}[image.media_type]
        if image.system_type != 0 or image.sector_count_512 != 1 or boot_size != expected_size:
            raise DiskForgeError("El Torito floppy-emulation metadata is unsupported for safe rebuilding.")
        return "floppy", None
    if image.media_type == 4:
        if image.sector_count_512 != 1 or boot_size < 512:
            raise DiskForgeError("El Torito hard-disk-emulation metadata is unsupported for safe rebuilding.")
        return "hdemul", None
    raise DiskForgeError("El Torito media type is unsupported for safe rebuilding.")


def _eltorito_rebuild_spec(source: Path, filesystem: "IsoImageFilesystem", entries: Sequence[ImageEntry]) -> _ElToritoRebuildSpec:
    """Inspect one reproducible boot entry and reject ambiguous/hybrid source images."""
    catalog = inspect_eltorito(source)
    if catalog.has_sections or len(catalog.images) != 1:
        raise DiskForgeError("ISO rebuilding supports only a single initial El Torito boot entry.")
    with source.open("rb") as handle:
        if any(handle.read(32768)):
            raise DiskForgeError("ISO rebuilding refuses hybrid or nonstandard system-area boot metadata.")
    image = catalog.images[0]
    boot_matches = _eltorito_paths_at_lba(filesystem, entries, image.lba)
    if len(boot_matches) != 1:
        raise DiskForgeError("El Torito boot image cannot be mapped uniquely to an ISO file.")
    # pycdlib exposes the catalog as a synthetic zero-inode directory record, so
    # it has no ordinary file extent (notably on UDF).  The raw catalog LBA was
    # already validated by inspect_eltorito(); constrain its visible companion to
    # the canonical root path created by add_eltorito instead of extracting it.
    catalog_matches = [entry for entry in entries if not entry.is_dir and entry.path.casefold() == "/boot.cat"]
    if len(catalog_matches) != 1:
        raise DiskForgeError("ISO rebuilding supports only the conventional root El Torito boot catalog name.")
    boot_entry, catalog_entry = boot_matches[0], catalog_matches[0]
    if boot_entry.path.casefold() == catalog_entry.path.casefold():
        raise DiskForgeError("El Torito boot image and boot catalog must be separate files.")
    media_name, boot_load_size = _eltorito_media_parameters(image, boot_entry.size)
    return _ElToritoRebuildSpec(
        boot_path=boot_entry.path,
        catalog_path=catalog_entry.path,
        platform_id=image.platform_id,
        bootable=image.bootable,
        media_name=media_name,
        boot_load_size=boot_load_size,
        boot_load_segment=image.load_segment,
        expected_system_type=image.system_type,
        expected_sector_count_512=image.sector_count_512,
    )


def _verify_eltorito_rebuild(destination: Path, spec: _ElToritoRebuildSpec) -> None:
    """Reopen a rebuilt bootable ISO and prove its boot catalog still targets the expected file."""
    catalog = inspect_eltorito(destination)
    if catalog.has_sections or len(catalog.images) != 1:
        raise DiskForgeError("Rebuilt ISO did not retain a single initial El Torito boot entry.")
    image = catalog.images[0]
    expected = (spec.platform_id, spec.bootable, spec.media_name, spec.boot_load_segment,
                spec.expected_system_type, spec.expected_sector_count_512)
    actual_media = {0: "noemul", 1: "floppy", 2: "floppy", 3: "floppy", 4: "hdemul"}.get(image.media_type)
    actual = (image.platform_id, image.bootable, actual_media, image.load_segment,
              image.system_type, image.sector_count_512)
    if actual != expected:
        raise DiskForgeError("Rebuilt ISO El Torito metadata does not match the verified source entry.")
    filesystem = IsoImageFilesystem(destination)
    try:
        entries = list(filesystem._walk("/"))
        boot_matches = _eltorito_paths_at_lba(filesystem, entries, image.lba)
        catalog_matches = [entry for entry in entries if not entry.is_dir and entry.path.casefold() == "/boot.cat"]
    finally:
        filesystem.close()
    if len(boot_matches) != 1 or boot_matches[0].path.casefold() != spec.boot_path.casefold():
        raise DiskForgeError("Rebuilt ISO El Torito boot entry no longer targets the expected file.")
    if len(catalog_matches) != 1 or catalog_matches[0].path.casefold() != spec.catalog_path.casefold():
        raise DiskForgeError("Rebuilt ISO El Torito boot catalog does not have the expected path.")


def rebuild_iso_with_changes(source_iso: Path | str, destination_iso: Path | str, *,
                             additions: Iterable[Path | str] = (), delete_paths: Iterable[str] = (),
                             create_directories: Iterable[str] = (), target_directory: str = "/",
                             volume_label: str | None = None, overwrite: bool = False,
                             progress: ProgressCallback | None = None,
                             token: CancellationToken | None = None) -> IsoRebuildResult:
    """Safely rebuild a standard ISO9660/Joliet image after explicit content edits.

    The source is always opened read-only and expanded inside a private temporary
    workspace.  Changes are applied only in that workspace, then a separate ISO
    is authored and reopened for a complete file-by-file SHA-256 verification.
    Rock Ridge and UDF profiles are recreated from their user-visible directory
    context. A single, initial El Torito entry is also recreated only after a
    strict catalog, system-area, file-range, and output verification; multi-entry,
    sectioned, hybrid, and otherwise ambiguous boot layouts are refused.
    """
    source, destination = Path(source_iso), Path(destination_iso)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == destination.resolve():
        raise DiskForgeError("The rebuilt ISO destination must be different from the source ISO.")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    additions = tuple(Path(item) for item in additions)
    deletions = tuple(delete_paths)
    directories = tuple(create_directories)
    if not additions and not deletions and not directories:
        raise DiskForgeError("ISO rebuilding requires at least one add, delete, or directory operation.")
    for item in additions:
        if not item.exists():
            raise FileNotFoundError(item)
    source_hash = sha256_file(source)
    probe = pycdlib.PyCdlib()
    try:
        probe.open(str(source))
        rock_ridge = probe.has_rock_ridge()
        udf = probe.has_udf()
        has_eltorito = _iso_has_eltorito(source)
        label_value = (volume_label or probe.pvd.volume_identifier.decode("ascii", errors="ignore").strip() or "DISKFORGE")[:32]
    finally:
        probe.close()
    stage_root = Path(tempfile.mkdtemp(prefix="diskforge-iso-edit-"))
    workspace, verification = stage_root / "content", stage_root / "verify"
    changed_additions: list[str] = []
    changed_deletions: list[str] = []
    created_directories: list[str] = []
    eltorito_spec: _ElToritoRebuildSpec | None = None
    try:
        source_fs = IsoImageFilesystem(source)
        try:
            source_entries = list(source_fs._walk("/"))
            if has_eltorito:
                eltorito_spec = _eltorito_rebuild_spec(source, source_fs, source_entries)
            file_entries = [
                entry for entry in source_entries
                if not entry.is_dir and (not eltorito_spec or entry.path.casefold() != eltorito_spec.catalog_path.casefold())
            ]
            for directory in sorted((entry for entry in source_entries if entry.is_dir), key=lambda entry: entry.path.count("/")):
                _, target = _iso_workspace_path(workspace, directory.path)
                target.mkdir(parents=True, exist_ok=True)
            for index, entry in enumerate(file_entries, start=1):
                if token:
                    token.raise_if_cancelled()
                _, target = _iso_workspace_path(workspace, entry.path)
                target.parent.mkdir(parents=True, exist_ok=True)
                source_fs.extract([entry.path], workspace, token=token)
                if progress:
                    progress(Progress(OperationKind.ISO_EDIT, index, len(file_entries) or 1, f"Staging {entry.name}"))
        finally:
            source_fs.close()
        for value in deletions:
            requested = _normal(value)
            if eltorito_spec and requested.casefold() in {eltorito_spec.boot_path.casefold(), eltorito_spec.catalog_path.casefold()}:
                raise DiskForgeError("El Torito boot files and boot catalog cannot be deleted during safe rebuilding.")
            normalized, target = _existing_iso_workspace_path(workspace, value)
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            changed_deletions.append(normalized)
        for value in directories:
            normalized, target = _iso_workspace_path(workspace, value)
            if target.exists() and not target.is_dir():
                raise FileExistsError(normalized)
            target.mkdir(parents=True, exist_ok=True)
            created_directories.append(normalized)
        _, target_root = _existing_iso_workspace_path(workspace, target_directory, allow_root=True)
        if not target_root.is_dir():
            raise FileNotFoundError(f"ISO target directory does not exist: {_normal(target_directory)}")
        for item in additions:
            if token:
                token.raise_if_cancelled()
            targets: list[tuple[Path, Path]] = []
            if item.is_dir():
                for candidate in item.rglob("*"):
                    if candidate.is_file():
                        targets.append((candidate, target_root / item.name / candidate.relative_to(item)))
                if not targets:
                    (target_root / item.name).mkdir(parents=True, exist_ok=True)
            else:
                targets.append((item, target_root / item.name))
            for candidate, target in targets:
                candidate_path = "/" + target.relative_to(workspace).as_posix()
                if eltorito_spec and candidate_path.casefold() == eltorito_spec.catalog_path.casefold():
                    raise DiskForgeError("El Torito boot catalog is managed automatically during safe rebuilding.")
                if target.exists():
                    raise FileExistsError(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, target)
                changed_additions.append("/" + target.relative_to(workspace).as_posix())
        if token:
            token.raise_if_cancelled()
        destination.parent.mkdir(parents=True, exist_ok=True)
        creator_options: dict[str, object] = {"rock_ridge": rock_ridge, "udf": udf}
        if eltorito_spec:
            _, boot_file = _existing_iso_workspace_path(workspace, eltorito_spec.boot_path)
            creator_options.update({
                "boot_image": boot_file,
                "boot_platform_id": eltorito_spec.platform_id,
                "boot_media": eltorito_spec.media_name,
                "boot_load_size": eltorito_spec.boot_load_size,
                "boot_load_segment": eltorito_spec.boot_load_segment,
                "bootable": eltorito_spec.bootable,
            })
        create_iso_from_directory(workspace, destination, label_value, **creator_options)
        verifier = IsoImageFilesystem(destination)
        try:
            expected_files = sorted(item for item in workspace.rglob("*") if item.is_file())
            for index, expected in enumerate(expected_files, start=1):
                if token:
                    token.raise_if_cancelled()
                relative = "/" + expected.relative_to(workspace).as_posix()
                verifier.extract([relative], verification, token=token)
                extracted = verification / relative.lstrip("/")
                if sha256_file(extracted) != sha256_file(expected):
                    raise DiskForgeError(f"Rebuilt ISO verification failed for {relative}.")
                if progress:
                    progress(Progress(OperationKind.ISO_EDIT, index, len(expected_files) or 1, f"Verifying {expected.name}"))
        finally:
            verifier.close()
        if eltorito_spec:
            _verify_eltorito_rebuild(destination, eltorito_spec)
        if sha256_file(source) != source_hash:
            raise DiskForgeError("The source ISO changed during rebuilding.")
        return IsoRebuildResult(source, destination, tuple(sorted(changed_additions)), tuple(sorted(changed_deletions)),
                                tuple(sorted(set(created_directories))), source_hash, sha256_file(destination))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


class IsoImageFilesystem(ImageFilesystem):
    """Read-only ISO9660/Rock Ridge/Joliet browser and extractor."""

    def __init__(self, image_path: Path | str) -> None:
        self.path = Path(image_path)
        self.iso = pycdlib.PyCdlib()
        self.iso.open(str(self.path))
        self._name_context = "rr" if self.iso.has_rock_ridge() else "udf" if self.iso.has_udf() else "iso"

    def close(self) -> None:
        self.iso.close()

    @staticmethod
    def _iso_path(path: str) -> str:
        normalized = _normal(path)
        return "/" if normalized == "/" else normalized.upper() + ";1"

    def _lookup(self, path: str, *, directory: bool = False) -> dict[str, str]:
        normalized = _normal(path)
        if self._name_context == "rr":
            return {"rr_path": normalized}
        if self._name_context == "udf":
            return {"udf_path": normalized}
        return {"iso_path": "/" if normalized == "/" else normalized.upper() if directory else self._iso_path(normalized)}

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        entries: list[ImageEntry] = []
        for record in self.iso.list_children(**self._lookup(path, directory=True)):
            if record is None:
                continue
            raw = record.file_identifier()
            if raw in (b"\x00", b"\x01", b".", b".."):
                continue
            if self._name_context == "rr":
                full_path = self.iso.full_path_from_dirrecord(record, rockridge=True)
                name = Path(full_path).name
            elif self._name_context == "udf":
                full_path = self.iso.full_path_from_dirrecord(record)
                name = raw.decode("utf-8", errors="replace")
            else:
                name = raw.decode("utf-8", errors="replace").rstrip(";1")
                full_path = _normal(posixpath.join(path, name))
            if full_path in {"/.", "/.."}:
                continue
            is_dir = record.is_dir()
            size = int(record.get_data_length()) if hasattr(record, "get_data_length") else int(record.data_length or 0)
            entries.append(ImageEntry(
                path=_normal(full_path), name=name, is_dir=is_dir,
                size=size,
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
            self.iso.get_file_from_iso(str(output), **self._lookup(entry.path))
            complete += entry.size or 1
            if progress:
                progress(Progress(OperationKind.EXTRACT, complete, total, f"Extracting {entry.name}"))
            outputs.append(output)
        return outputs


def create_fat_image(path: Path | str, size_bytes: int, filesystem: FileSystemType,
                     label: str = "DISKFORGE", *, media_type: int = 0xF8,
                     sectors_per_track: int = 0, heads: int = 0, sector_size: int = 512,
                     fat_count: int = 2) -> Path:
    """Create a formatted FAT superfloppy image of a requested size.

    ``media_type`` and optional BIOS geometry are deliberately explicit because
    they are presentation/firmware metadata rather than an instruction to write
    a physical device.  A zero geometry preserves the formatter default.  Sector
    size and FAT count are constrained to values that the native formatter can
    generate portably; callers importing a layout must validate it first.
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
        if sector_size not in {512, 1024, 2048, 4096}:
            raise DiskForgeError("FAT sector size must be a supported power of two from 512 to 4096 bytes.")
        if size_bytes < sector_size or size_bytes % sector_size:
            raise DiskForgeError("FAT image size must be sector-aligned.")
        if fat_count not in {1, 2}:
            raise DiskForgeError("FAT images must contain one or two allocation tables.")
        if not 0 <= sectors_per_track <= 0xFFFF or not 0 <= heads <= 0xFFFF:
            raise DiskForgeError("FAT geometry values must fit in 16-bit BPB fields.")
        pyfat.mkfs(str(target), fat_type=fat_type, size=size_bytes, label=label[:11], media_type=media_type,
                   sector_size=sector_size, number_of_fats=fat_count)
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


def _iso9660_component(name: str, *, is_file: bool) -> str:
    """Return a valid ISO9660 level-3 component without silently colliding names."""
    normalized = name.upper()
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
    if is_file and "." in normalized:
        stem, extension = normalized.rsplit(".", 1)
        stem = "".join(char if char in allowed else "_" for char in stem).strip("_") or "FILE"
        extension = "".join(char if char in allowed else "_" for char in extension).strip("_")
        return stem if not extension else f"{stem}.{extension}"
    return "".join(char if char in allowed else "_" for char in normalized).strip("_") or "DIR"


def _iso9660_path(relative: Path, *, is_file: bool) -> str:
    components = [_iso9660_component(component, is_file=is_file and index == len(relative.parts) - 1)
                  for index, component in enumerate(relative.parts)]
    return "/" + "/".join(components) + (";1" if is_file else "")


def create_iso_from_directory(source_directory: Path | str, destination: Path | str,
                              volume_label: str = "DISKFORGE", *,
                              boot_image: Path | str | None = None,
                              boot_platform_id: int = 0,
                              boot_media: str = "noemul",
                              boot_info_table: bool = False,
                              boot_load_size: int | None = None,
                              boot_load_segment: int = 0,
                              bootable: bool = True,
                              rock_ridge: bool = False,
                              udf: bool = False) -> Path:
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
    if boot_load_size is not None and not 0 < boot_load_size <= 0xFFFF:
        raise DiskForgeError("El Torito load sector count must fit in an unsigned 16-bit field.")
    if not 0 <= boot_load_segment <= 0xFFFF:
        raise DiskForgeError("El Torito load segment must fit in 16 bits.")
    selected_boot = Path(boot_image).resolve() if boot_image is not None else None
    if selected_boot is not None and not selected_boot.is_file():
        raise FileNotFoundError(selected_boot)
    iso = pycdlib.PyCdlib()
    profile: dict[str, str | int] = {"interchange_level": 3, "joliet": 3, "vol_ident": volume_label[:32]}
    if rock_ridge:
        profile["rock_ridge"] = "1.09"
    if udf:
        profile["udf"] = "2.60"
    iso.new(**profile)
    try:
        directories = [item for item in source.rglob("*") if item.is_dir()]
        files = [item for item in source.rglob("*") if item.is_file()]
        normalized_paths: dict[str, str] = {}
        for item in [*directories, *files]:
            relative_path = item.relative_to(source)
            iso_name = _iso9660_path(relative_path, is_file=item.is_file()).casefold()
            original = relative_path.as_posix()
            if iso_name in normalized_paths:
                raise DiskForgeError(f"Local paths {normalized_paths[iso_name]!r} and {original!r} collide after ISO9660 name normalization.")
            normalized_paths[iso_name] = original
        for directory in directories:
            relative = directory.relative_to(source).as_posix()
            directory_kwargs: dict[str, object] = {"iso_path": _iso9660_path(directory.relative_to(source), is_file=False), "joliet_path": "/" + relative}
            if rock_ridge:
                directory_kwargs["rr_name"] = directory.name
            if udf:
                directory_kwargs["udf_path"] = "/" + relative
            iso.add_directory(**directory_kwargs)
        boot_iso_path: str | None = None
        for file_path in files:
            relative = file_path.relative_to(source).as_posix()
            iso_path = _iso9660_path(file_path.relative_to(source), is_file=True)
            file_kwargs: dict[str, object] = {"iso_path": iso_path, "joliet_path": "/" + relative}
            if rock_ridge:
                file_kwargs["rr_name"] = file_path.name
            if udf:
                file_kwargs["udf_path"] = "/" + relative
            iso.add_file(str(file_path), **file_kwargs)
            if selected_boot is not None and file_path.resolve() == selected_boot:
                boot_iso_path = iso_path
        if selected_boot is not None and boot_iso_path is None:
            boot_iso_path = "/BOOT.IMG;1"
            boot_kwargs: dict[str, object] = {"iso_path": boot_iso_path, "joliet_path": "/boot.img"}
            if rock_ridge:
                boot_kwargs["rr_name"] = "boot.img"
            if udf:
                boot_kwargs["udf_path"] = "/boot.img"
            iso.add_file(str(selected_boot), **boot_kwargs)
        if boot_iso_path is not None:
            eltorito_kwargs: dict[str, object] = {
                "platform_id": boot_platform_id, "media_name": boot_media,
                "boot_info_table": boot_info_table, "boot_load_size": boot_load_size,
                "boot_load_seg": boot_load_segment, "bootable": bootable,
                "joliet_bootcatfile": "/boot.cat",
            }
            if rock_ridge:
                eltorito_kwargs["rr_bootcatname"] = "boot.cat"
            if udf:
                eltorito_kwargs["udf_bootcatfile"] = "/boot.cat"
            iso.add_eltorito(boot_iso_path, **eltorito_kwargs)
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
