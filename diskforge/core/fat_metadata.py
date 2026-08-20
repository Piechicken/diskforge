"""Explicit, auditable FAT metadata updates for existing writable image entries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .filesystems import FatImageFilesystem
from .storage import CancellationToken, DiskForgeError


_ATTRIBUTE_FIELDS = ("read_only", "hidden", "system", "archive")
_TIME_FIELDS = ("created", "modified", "accessed")


@dataclass(frozen=True)
class FatMetadataUpdate:
    """Requested standard DOS attributes and FAT timestamps for explicit entry paths."""

    paths: tuple[str, ...]
    read_only: bool | None = None
    hidden: bool | None = None
    system: bool | None = None
    archive: bool | None = None
    created: datetime | None = None
    modified: datetime | None = None
    accessed: datetime | None = None

    @property
    def attributes_requested(self) -> bool:
        return any(getattr(self, field) is not None for field in _ATTRIBUTE_FIELDS)

    @property
    def times_requested(self) -> bool:
        return any(getattr(self, field) is not None for field in _TIME_FIELDS)

    @property
    def requested_fields(self) -> tuple[str, ...]:
        return tuple(field for field in (*_ATTRIBUTE_FIELDS, *_TIME_FIELDS) if getattr(self, field) is not None)


@dataclass(frozen=True)
class FatMetadataResult:
    """Metadata observed immediately after one requested entry update."""

    path: str
    attributes: str | None
    updated_fields: tuple[str, ...]


def _validate_datetime(value: datetime, field: str) -> None:
    if value.tzinfo is not None and value.utcoffset() is not None:
        raise DiskForgeError(f"FAT {field} timestamps must not include a timezone offset.")
    if not 1980 <= value.year <= 2107:
        raise DiskForgeError(f"FAT {field} timestamp year must be between 1980 and 2107.")


def validate_fat_metadata_update(update: FatMetadataUpdate) -> None:
    """Reject ambiguous, empty, or non-FAT-representable requested updates before writes."""
    if not update.paths:
        raise DiskForgeError("FAT metadata update requires at least one explicit image path.")
    if any(not isinstance(path, str) or not path.strip() for path in update.paths):
        raise DiskForgeError("FAT metadata paths must be nonempty strings.")
    if len(set(update.paths)) != len(update.paths):
        raise DiskForgeError("FAT metadata paths must not contain duplicates.")
    if any(path.strip() == "/" for path in update.paths):
        raise DiskForgeError("FAT metadata updates cannot target the image root.")
    for field in _ATTRIBUTE_FIELDS:
        value = getattr(update, field)
        if value is not None and not isinstance(value, bool):
            raise DiskForgeError(f"FAT metadata {field} must be a boolean when provided.")
    for field in _TIME_FIELDS:
        value = getattr(update, field)
        if value is not None:
            if not isinstance(value, datetime):
                raise DiskForgeError(f"FAT metadata {field} must be a datetime when provided.")
            _validate_datetime(value, field)
    if not update.attributes_requested and not update.times_requested:
        raise DiskForgeError("FAT metadata update requires at least one attribute or timestamp field.")


def apply_fat_metadata(filesystem: FatImageFilesystem, update: FatMetadataUpdate,
                       token: CancellationToken | None = None) -> tuple[FatMetadataResult, ...]:
    """Apply one validated explicit update per FAT entry in caller order.

    The underlying FAT directory changes are intentionally not represented as a multi-entry transaction.
    Results therefore expose every completed entry before a later path can fail or cancellation is observed.
    """
    validate_fat_metadata_update(update)
    if filesystem.read_only:
        raise DiskForgeError("This FAT image is open read-only.")
    results: list[FatMetadataResult] = []
    for path in update.paths:
        if token:
            token.raise_if_cancelled()
        attributes = None
        if update.attributes_requested:
            attributes = filesystem.set_attributes(
                path,
                read_only=update.read_only,
                hidden=update.hidden,
                system=update.system,
                archive=update.archive,
            )
        if update.times_requested:
            filesystem.set_times(
                path,
                created=update.created,
                modified=update.modified,
                accessed=update.accessed,
            )
        results.append(FatMetadataResult(path, attributes, update.requested_fields))
    return tuple(results)


def metadata_update_from_values(paths: Iterable[str], *, read_only: bool | None = None,
                                hidden: bool | None = None, system: bool | None = None,
                                archive: bool | None = None, created: datetime | None = None,
                                modified: datetime | None = None,
                                accessed: datetime | None = None) -> FatMetadataUpdate:
    """Build and validate an update from public entrypoint values."""
    update = FatMetadataUpdate(tuple(paths), read_only, hidden, system, archive, created, modified, accessed)
    validate_fat_metadata_update(update)
    return update
