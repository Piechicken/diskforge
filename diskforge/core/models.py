"""Core public data models used by DiskForge.

The application deliberately keeps destructive operations explicit.  Every image
or device write travels through an OperationPlan and a SafetyGate before bytes
are changed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Optional


SECTOR_SIZE = 512


class ImageFormat(str, Enum):
    """Formats handled natively or through an optional conversion provider."""

    RAW = "raw"
    IMG = "img"
    ISO = "iso"
    VHD = "vhd"
    VHDX = "vhdx"
    VMDK = "vmdk"
    QCOW2 = "qcow2"
    DMG = "dmg"
    IMZ = "imz"
    WLZ = "wlz"
    UNKNOWN = "unknown"

    @classmethod
    def from_path(cls, path: Path | str) -> "ImageFormat":
        suffix = Path(path).suffix.lower().lstrip(".")
        aliases = {"ima": cls.IMG, "bin": cls.RAW, "dd": cls.RAW}
        alias = aliases.get(suffix)
        if alias is not None:
            return alias
        try:
            return cls(suffix)
        except ValueError:
            return cls.UNKNOWN


class FileSystemType(str, Enum):
    FAT12 = "FAT12"
    FAT16 = "FAT16"
    FAT32 = "FAT32"
    ISO9660 = "ISO9660"
    NTFS = "NTFS"
    EXT = "EXT"
    HFS = "HFS"
    HFS_PLUS = "HFS+"
    UNKNOWN = "Unknown"


class ExtractionLayout(str, Enum):
    """How files selected from an image are mapped to a local directory."""

    PRESERVE_PATHS = "preserve_paths"
    FLATTEN = "flatten"
    IGNORE_SUBDIRECTORIES = "ignore_subdirectories"


class ConflictPolicy(str, Enum):
    """Conflict behavior deliberately chosen by a caller before extraction."""

    ERROR = "error"
    OVERWRITE = "overwrite"
    SKIP = "skip"
    RENAME = "rename"


@dataclass(frozen=True)
class ExtractionPolicy:
    layout: ExtractionLayout = ExtractionLayout.PRESERVE_PATHS
    conflict: ConflictPolicy = ConflictPolicy.ERROR


class DeviceKind(str, Enum):
    DISK = "disk"
    PARTITION = "partition"
    REMOVABLE = "removable"
    OPTICAL = "optical"


class OperationKind(str, Enum):
    CREATE = "create"
    OPEN = "open"
    EXTRACT = "extract"
    INJECT = "inject"
    CONVERT = "convert"
    READ_DEVICE = "read_device"
    WRITE_DEVICE = "write_device"
    FORMAT_DEVICE = "format_device"
    VERIFY = "verify"
    DEFRAGMENT = "defragment"
    EDIT_BOOT_SECTOR = "edit_boot_sector"
    RESIZE = "resize"
    COMPARE = "compare"
    BUNDLE = "bundle"
    UNBUNDLE = "unbundle"
    LEGACY_COMPRESS = "legacy_compress"
    LEGACY_EXTRACT = "legacy_extract"


@dataclass(frozen=True)
class ImageInfo:
    path: Path
    image_format: ImageFormat
    size: int
    filesystem: FileSystemType = FileSystemType.UNKNOWN
    sector_size: int = SECTOR_SIZE
    writable: bool = False
    virtual_size: Optional[int] = None
    checksum_sha256: Optional[str] = None
    created_at: Optional[datetime] = None
    notes: tuple[str, ...] = ()

    @property
    def display_size(self) -> str:
        return human_bytes(self.virtual_size or self.size)


@dataclass(frozen=True)
class DiskPartition:
    index: int
    start_lba: int
    sectors: int
    type_code: str
    name: str = ""
    filesystem: FileSystemType = FileSystemType.UNKNOWN

    @property
    def offset(self) -> int:
        return self.start_lba * SECTOR_SIZE

    @property
    def size(self) -> int:
        return self.sectors * SECTOR_SIZE


@dataclass(frozen=True)
class DeviceInfo:
    identifier: str
    display_name: str
    size: int
    kind: DeviceKind
    removable: bool = False
    mounted: bool = False
    mountpoints: tuple[str, ...] = ()
    model: str = ""
    system_disk: bool = False


@dataclass(frozen=True)
class ImageEntry:
    path: str
    name: str
    is_dir: bool
    size: int = 0
    modified: Optional[datetime] = None
    created: Optional[datetime] = None
    attributes: str = ""


@dataclass
class Progress:
    operation: OperationKind
    completed: int
    total: int
    message: str = ""

    @property
    def percent(self) -> int:
        return 0 if self.total <= 0 else min(100, int(self.completed * 100 / self.total))


ProgressCallback = Callable[[Progress], None]


@dataclass(frozen=True)
class OperationPlan:
    kind: OperationKind
    source: Path | str
    destination: Path | str | None = None
    bytes_expected: int = 0
    require_confirmation_phrase: bool = False
    confirmation_phrase: str = ""
    notes: tuple[str, ...] = ()


@dataclass
class BatchItemResult:
    source: Path
    destination: Optional[Path]
    operation: OperationKind
    success: bool
    message: str
    name: str = ""


@dataclass
class BatchResult:
    started: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed: Optional[datetime] = None
    items: list[BatchItemResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(item.success for item in self.items)

    @property
    def failed(self) -> int:
        return sum(not item.success for item in self.items)


def human_bytes(value: int) -> str:
    """Format bytes without pulling an additional presentation dependency."""
    value = max(0, int(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} PiB"


def iter_parent_paths(path: str) -> Iterable[str]:
    """Yield normalized POSIX parents from shallow to deep."""
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    current: list[str] = []
    for part in parts[:-1]:
        current.append(part)
        yield "/" + "/".join(current)
