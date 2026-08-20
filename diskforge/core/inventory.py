"""Read-only inventory, filtering, and reporting for local image collections."""
from __future__ import annotations

import csv
import html
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .formats import Converter, inspect_image
from .models import FileSystemType, ImageFormat
from .partitions import list_partitions
from .storage import CancellationToken, DiskForgeError, sha256_file


_MAX_CANDIDATES = 10_000
_MAX_FILE_BYTES = 16 * 1024 * 1024 * 1024
_IMAGE_SUFFIXES = frozenset({".img", ".ima", ".bin", ".dd", ".dmf", ".iso", ".hfs", ".vhd", ".vhdx", ".vmdk", ".qcow2", ".dmg", ".imz", ".wlz", ".zip", ".imd", ".td0", ".dsk", ".d88", ".1dd", ".2dd"})
ReportFormat = Literal["json", "csv", "html"]


@dataclass(frozen=True)
class ImageInventoryOptions:
    recursive: bool = False
    suffixes: tuple[str, ...] = ()
    formats: tuple[ImageFormat, ...] = ()
    filesystems: tuple[FileSystemType, ...] = ()
    min_bytes: int | None = None
    max_bytes: int | None = None
    sha256_prefix: str | None = None
    include_sha256: bool = False
    include_partitions: bool = False


@dataclass(frozen=True)
class ImageInventoryRecord:
    relative_path: str
    size: int
    suffix: str
    image_format: ImageFormat | None = None
    filesystem: FileSystemType | None = None
    virtual_bytes: int | None = None
    sha256: str | None = None
    partitions: tuple[dict[str, object], ...] = ()
    error: str | None = None

    def as_mapping(self) -> dict[str, object]:
        return {
            "path": self.relative_path, "bytes": self.size, "suffix": self.suffix,
            "format": self.image_format.value if self.image_format else None,
            "filesystem": self.filesystem.value if self.filesystem else None,
            "virtual_bytes": self.virtual_bytes, "sha256": self.sha256,
            "partitions": list(self.partitions), "error": self.error,
        }


@dataclass(frozen=True)
class ImageInventory:
    root: Path
    options: ImageInventoryOptions
    records: tuple[ImageInventoryRecord, ...]
    candidates_seen: int

    @property
    def recognized(self) -> int:
        return sum(item.image_format is not None and item.error is None for item in self.records)

    @property
    def errors(self) -> int:
        return sum(item.error is not None for item in self.records)

    def as_mapping(self) -> dict[str, object]:
        return {
            "root": str(self.root), "candidates_seen": self.candidates_seen,
            "records": [record.as_mapping() for record in self.records],
            "summary": {"reported": len(self.records), "recognized": self.recognized, "errors": self.errors},
        }


def _normalize_suffixes(suffixes: tuple[str, ...]) -> frozenset[str]:
    normalized: set[str] = set()
    for value in suffixes:
        if not isinstance(value, str) or not value.strip():
            raise DiskForgeError("Inventory suffix filters must be nonempty strings.")
        normalized.add("." + value.strip().casefold().lstrip("."))
    return frozenset(normalized)


def _validate(options: ImageInventoryOptions) -> tuple[frozenset[str], str | None]:
    suffixes = _normalize_suffixes(options.suffixes)
    if options.min_bytes is not None and options.min_bytes < 0:
        raise DiskForgeError("The inventory minimum byte filter cannot be negative.")
    if options.max_bytes is not None and options.max_bytes < 0:
        raise DiskForgeError("The inventory maximum byte filter cannot be negative.")
    if options.min_bytes is not None and options.max_bytes is not None and options.min_bytes > options.max_bytes:
        raise DiskForgeError("The inventory minimum byte filter cannot exceed the maximum.")
    prefix = options.sha256_prefix.casefold() if options.sha256_prefix else None
    if prefix is not None and (not prefix or len(prefix) > 64 or any(value not in "0123456789abcdef" for value in prefix)):
        raise DiskForgeError("The inventory SHA-256 prefix must contain one to 64 hexadecimal characters.")
    return suffixes, prefix


def _candidate_paths(root: Path, recursive: bool, token: CancellationToken | None) -> list[Path]:
    try:
        root_stat = root.lstat()
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise DiskForgeError("The inventory root must be an existing non-symlink local directory.")
    pending = [root]
    discovered: list[Path] = []
    while pending:
        if token:
            token.raise_if_cancelled()
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if token:
                    token.raise_if_cancelled()
                if entry.is_symlink():
                    continue
                try:
                    entry_stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISREG(entry_stat.st_mode):
                    discovered.append(Path(entry.path))
                    if len(discovered) > _MAX_CANDIDATES:
                        raise DiskForgeError("The inventory exceeds the 10000-candidate safety limit.")
                elif recursive and stat.S_ISDIR(entry_stat.st_mode):
                    pending.append(Path(entry.path))
    return sorted(discovered, key=lambda value: value.relative_to(root).as_posix().casefold())


def _partition_summary(path: Path) -> tuple[dict[str, object], ...]:
    return tuple({
        "index": part.index, "scheme": part.scheme, "type": part.type_code,
        "offset_bytes": part.offset_bytes, "size_bytes": part.size_bytes,
    } for part in list_partitions(path))


def inventory_images(root: Path | str, options: ImageInventoryOptions | None = None, *,
                     converter: Converter | None = None,
                     token: CancellationToken | None = None) -> ImageInventory:
    """Collect filtered image metadata without opening writable filesystem sessions."""
    root_path = Path(root)
    options = options or ImageInventoryOptions()
    suffix_filter, sha_prefix = _validate(options)
    records: list[ImageInventoryRecord] = []
    candidates = _candidate_paths(root_path, options.recursive, token)
    for path in candidates:
        if token:
            token.raise_if_cancelled()
        relative = path.relative_to(root_path).as_posix()
        try:
            size = path.stat().st_size
        except OSError as exc:
            records.append(ImageInventoryRecord(relative, 0, path.suffix.casefold(), error=str(exc)))
            continue
        suffix = path.suffix.casefold()
        if suffix not in _IMAGE_SUFFIXES or (suffix_filter and suffix not in suffix_filter):
            continue
        if size > _MAX_FILE_BYTES or (options.min_bytes is not None and size < options.min_bytes) or (
            options.max_bytes is not None and size > options.max_bytes
        ):
            continue
        try:
            info = inspect_image(path, converter)
            if options.formats and info.image_format not in options.formats:
                continue
            if options.filesystems and info.filesystem not in options.filesystems:
                continue
            digest = sha256_file(path, token=token) if (options.include_sha256 or sha_prefix) else None
            if sha_prefix and (digest is None or not digest.startswith(sha_prefix)):
                continue
            partitions: tuple[dict[str, object], ...] = ()
            partition_error = None
            if options.include_partitions:
                try:
                    partitions = _partition_summary(path)
                except Exception as exc:  # Normal for superfloppy and malformed candidates; preserve the observation.
                    partition_error = str(exc)
            records.append(ImageInventoryRecord(
                relative, size, suffix, info.image_format, info.filesystem, info.virtual_size,
                digest, partitions, partition_error,
            ))
        except Exception as exc:
            records.append(ImageInventoryRecord(relative, size, suffix, error=str(exc)))
    return ImageInventory(root_path, options, tuple(records), len(candidates))


def _render_csv(inventory: ImageInventory) -> str:
    import io

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["path", "bytes", "suffix", "format", "filesystem", "virtual_bytes", "sha256", "partitions", "error"])
    writer.writeheader()
    for record in inventory.records:
        mapping = record.as_mapping()
        mapping["partitions"] = json.dumps(mapping["partitions"], ensure_ascii=False, separators=(",", ":"))
        writer.writerow(mapping)
    return stream.getvalue()


def _render_html(inventory: ImageInventory) -> str:
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value) if value is not None else '')}</td>" for value in (
            record.relative_path, record.size, record.suffix,
            record.image_format.value if record.image_format else "",
            record.filesystem.value if record.filesystem else "", record.virtual_bytes or "", record.sha256 or "", record.error or "",
        )) + "</tr>"
        for record in inventory.records
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>DiskForge image inventory</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccd;padding:.45rem;text-align:left;vertical-align:top}th{background:#eef}</style></head><body>"
        f"<h1>DiskForge image inventory</h1><p>Root: {html.escape(str(inventory.root))}; reported: {len(inventory.records)}; "
        f"recognized: {inventory.recognized}; errors: {inventory.errors}</p><table><thead><tr>"
        "<th>Path</th><th>Bytes</th><th>Suffix</th><th>Format</th><th>Filesystem</th><th>Virtual bytes</th><th>SHA-256</th><th>Error</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></body></html>"
    )


def export_image_inventory(inventory: ImageInventory, destination: Path | str, report_format: ReportFormat,
                           token: CancellationToken | None = None) -> Path:
    """Atomically write a new local JSON/CSV/HTML inventory report without overwrite."""
    target = Path(destination)
    if report_format not in {"json", "csv", "html"}:
        raise DiskForgeError("Inventory reports support json, csv, or html only.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir():
        raise DiskForgeError("The inventory report destination directory does not exist.")
    try:
        target.resolve().relative_to(inventory.root.resolve())
    except ValueError:
        pass
    else:
        raise DiskForgeError("The inventory report destination cannot be inside the scanned root directory.")
    content = json.dumps(inventory.as_mapping(), indent=2, ensure_ascii=False) if report_format == "json" else (
        _render_csv(inventory) if report_format == "csv" else _render_html(inventory)
    )
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.diskforge-inventory-", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            for index in range(0, len(content), 65536):
                if token:
                    token.raise_if_cancelled()
                handle.write(content[index:index + 65536])
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
