"""Safe FAT deployment planning and execution for removable media."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .devices import write_image_to_device
from .media import MbrWrappedImage, wrap_fat_image_in_mbr
from .models import DeviceInfo, ProgressCallback
from .storage import CancellationToken, DiskForgeError


@dataclass(frozen=True)
class FatDeploymentPlan:
    """A non-destructive plan that can be reviewed before any device write."""

    source: Path
    prepared_image: Path
    device: DeviceInfo | None
    partition_start_lba: int
    partition_sectors: int
    partition_type: int
    bootable: bool
    requires_confirmation: bool = True


def prepare_fat_deployment(source: Path | str, prepared_image: Path | str, *,
                           device: DeviceInfo | None = None, bootable: bool = True,
                           overwrite: bool = False,
                           progress: ProgressCallback | None = None,
                           token: CancellationToken | None = None) -> FatDeploymentPlan:
    """Wrap a FAT superfloppy in a fresh neutral MBR image without touching a device."""
    result: MbrWrappedImage = wrap_fat_image_in_mbr(
        source, prepared_image, bootable=bootable, overwrite=overwrite, progress=progress, token=token,
    )
    prepared = result.path
    if device is not None and device.size and prepared.stat().st_size > device.size:
        raise DiskForgeError("Prepared MBR image is larger than the selected device.")
    return FatDeploymentPlan(
        Path(source), prepared, device, result.partition_start_lba, result.partition_sectors,
        result.partition_type, bootable,
    )


def execute_fat_deployment(plan: FatDeploymentPlan, confirmation_phrase: str, *,
                           verify_after_write: bool = True,
                           progress: ProgressCallback | None = None,
                           token: CancellationToken | None = None) -> bool:
    """Execute a reviewed plan only through the central protected write path."""
    if plan.device is None:
        raise DiskForgeError("Select a removable destination device before deployment.")
    if confirmation_phrase != "ERASE":
        raise DiskForgeError("Deployment requires the exact confirmation phrase ERASE.")
    return write_image_to_device(
        plan.prepared_image, plan.device, confirmation_phrase, progress=progress, token=token,
        verify_after_write=verify_after_write,
    )
