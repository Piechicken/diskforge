"""Auditable temporary RAW materialization for browsing virtual disk images."""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .formats import Converter, extract_legacy_zip_image, extract_zip_image_payload, inspect_image
from .models import FileSystemType, ImageFormat, ImageInfo, OperationKind, ProgressCallback
from .storage import CancellationToken, DiskForgeError, stream_copy


@dataclass
class BrowsableImageSession:
    """A read-only browsing source that cleans converted bytes when closed."""

    source: Path
    image: Path
    source_info: ImageInfo
    temporary_directory: Path | None = None

    @property
    def temporary(self) -> bool:
        return self.temporary_directory is not None

    def close(self) -> None:
        if self.temporary_directory is not None:
            shutil.rmtree(self.temporary_directory, ignore_errors=True)
            self.temporary_directory = None

    def __enter__(self) -> "BrowsableImageSession":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:  # type: ignore[no-untyped-def]
        self.close()


def materialize_browsable_image(source: Path | str, *, converter: Converter | None = None,
                                 zip_payload: str | None = None,
                                 progress: ProgressCallback | None = None,
                                 token: CancellationToken | None = None) -> BrowsableImageSession:
    """Return an image path suitable for read-only filesystem probing.

    Native raw/FAT/ISO images are returned directly. A safe ZIP with one payload
    or an explicitly selected validated root-level payload, a legacy compressed image,
    or a fixed VHD is materialized to a private temporary
    file; VHDX, VMDK and QCOW2 require the explicitly configured converter. Every
    temporary directory is caller-owned through ``close`` and is always read-only.
    """
    original = Path(source)
    info = inspect_image(original, converter)
    if info.image_format not in {ImageFormat.VHD, ImageFormat.VHDX, ImageFormat.VMDK, ImageFormat.QCOW2,
                                 ImageFormat.IMZ, ImageFormat.WLZ, ImageFormat.ZIP}:
        return BrowsableImageSession(original, original, info)
    temporary = Path(tempfile.mkdtemp(prefix="diskforge-browse-"))
    raw = temporary / f"{original.stem}.img"
    try:
        if info.image_format in {ImageFormat.IMZ, ImageFormat.WLZ}:
            extract_legacy_zip_image(original, raw)
        elif info.image_format == ImageFormat.ZIP:
            payload = extract_zip_image_payload(
                original, raw, payload_name=zip_payload, progress=progress, token=token,
            )
            # The ZIP extractor has already validated the single root-level name.
            # Preserve its suffix only after extraction so extension-dependent,
            # shape-validated raw aliases are re-identified correctly.
            suffixed_raw = raw.with_suffix(Path(payload.payload_name).suffix.casefold())
            raw.replace(suffixed_raw)
            raw = suffixed_raw
        elif info.image_format == ImageFormat.VHD:
            if info.virtual_size is None:
                raise DiskForgeError("VHD browsing requires a valid fixed-VHD virtual size.")
            stream_copy(original, raw, operation=OperationKind.CONVERT, limit=info.virtual_size, progress=progress,
                        token=token, overwrite=True)
        elif converter is not None and converter.available:
            converter.convert(original, raw, ImageFormat.IMG, progress, token)
        else:
            raise DiskForgeError(
                f"Browsing {info.image_format.value} requires qemu-img. Configure it before opening this image."
            )
        if info.image_format == ImageFormat.ZIP:
            materialized_info = inspect_image(raw, converter)
            if materialized_info.filesystem not in {
                FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32,
                FileSystemType.ISO9660, FileSystemType.CBM_DOS, FileSystemType.NTFS, FileSystemType.EXT,
                FileSystemType.HFS, FileSystemType.HFS_PLUS,
            } and materialized_info.image_format != ImageFormat.ISO:
                raise DiskForgeError("ZIP image payload is not a supported browsable disk image.")
        return BrowsableImageSession(original, raw, info, temporary)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
