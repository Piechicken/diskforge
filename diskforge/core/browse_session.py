"""Auditable temporary RAW materialization for browsing virtual disk images."""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .formats import Converter, inspect_image
from .models import ImageFormat, ImageInfo, OperationKind, ProgressCallback
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
                                 progress: ProgressCallback | None = None,
                                 token: CancellationToken | None = None) -> BrowsableImageSession:
    """Return an image path suitable for read-only filesystem probing.

    Native raw/FAT/ISO images are returned directly.  A fixed VHD is copied only
    up to its validated virtual size, excluding the footer.  VHDX, VMDK and QCOW2
    require the explicitly configured converter and are converted to a temporary
    RAW image.  Every temporary directory is caller-owned through ``close``.
    """
    original = Path(source)
    info = inspect_image(original, converter)
    if info.image_format not in {ImageFormat.VHD, ImageFormat.VHDX, ImageFormat.VMDK, ImageFormat.QCOW2}:
        return BrowsableImageSession(original, original, info)
    temporary = Path(tempfile.mkdtemp(prefix="diskforge-browse-"))
    raw = temporary / f"{original.stem}.img"
    try:
        if info.image_format == ImageFormat.VHD:
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
        return BrowsableImageSession(original, raw, info, temporary)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
