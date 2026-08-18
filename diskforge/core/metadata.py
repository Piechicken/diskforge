"""Non-invasive DiskForge metadata stored beside a source image."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .storage import DiskForgeError


@dataclass(frozen=True)
class ImageMetadata:
    image: Path
    comment: str = ""
    updated_at: datetime | None = None


def metadata_path(image: Path | str) -> Path:
    target = Path(image)
    return target.with_name(target.name + ".diskforge.json")


def load_image_metadata(image: Path | str) -> ImageMetadata:
    target, sidecar = Path(image), metadata_path(image)
    if not sidecar.exists():
        return ImageMetadata(target)
    try:
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiskForgeError("Image metadata sidecar is unreadable.") from exc
    if not isinstance(raw, dict) or raw.get("schema") != "diskforge.image-metadata/v1":
        raise DiskForgeError("Image metadata sidecar schema is not supported.")
    if raw.get("image_name") != target.name or not isinstance(raw.get("comment", ""), str):
        raise DiskForgeError("Image metadata sidecar does not match this image.")
    try:
        updated = datetime.fromisoformat(raw["updated_at"]) if raw.get("updated_at") else None
    except (TypeError, ValueError) as exc:
        raise DiskForgeError("Image metadata timestamp is invalid.") from exc
    return ImageMetadata(target, raw.get("comment", ""), updated)


def save_image_comment(image: Path | str, comment: str) -> ImageMetadata:
    """Atomically save a user comment without mutating image bytes."""
    target = Path(image)
    if not target.is_file():
        raise FileNotFoundError(target)
    if not isinstance(comment, str) or len(comment) > 16_384:
        raise DiskForgeError("Image comment must be text of at most 16,384 characters.")
    record = {
        "schema": "diskforge.image-metadata/v1",
        "image_name": target.name,
        "comment": comment,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    sidecar = metadata_path(target)
    temporary = sidecar.with_name(sidecar.name + ".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, sidecar)
    return load_image_metadata(target)
