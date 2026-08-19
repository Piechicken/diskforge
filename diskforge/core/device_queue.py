"""Auditable, read-only queues for copying selected physical media to image files."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .devices import read_device_to_image
from .models import DeviceInfo, ProgressCallback
from .storage import CancellationToken, DiskForgeError, sha256_file


@dataclass(frozen=True)
class DeviceReadRequest:
    """One explicitly selected source device and independent destination image."""

    device: DeviceInfo
    destination: Path
    overwrite: bool = False


@dataclass(frozen=True)
class DeviceReadItem:
    device: str
    destination: Path
    bytes_copied: int
    sha256: str | None
    error: str | None = None


@dataclass(frozen=True)
class DeviceReadReport:
    """An auditable result of a sequential read-only acquisition queue."""

    items: tuple[DeviceReadItem, ...]

    @property
    def succeeded(self) -> int:
        return sum(item.error is None for item in self.items)

    @property
    def failed(self) -> int:
        return sum(item.error is not None for item in self.items)

    def as_mapping(self) -> dict[str, object]:
        return {
            "succeeded": self.succeeded,
            "failed": self.failed,
            "items": [
                {**asdict(item), "destination": str(item.destination)}
                for item in self.items
            ],
        }


def read_device_queue(requests: Sequence[DeviceReadRequest], *, continue_on_error: bool = False,
                      progress: ProgressCallback | None = None,
                      token: CancellationToken | None = None) -> DeviceReadReport:
    """Sequentially acquire selected devices without any device-write capability.

    Destinations must be unique.  A SHA-256 is calculated after each successful
    copy, so callers can persist one compact audit report alongside their images.
    ``continue_on_error`` is explicit; otherwise the first failed acquisition
    ends the queue while preserving prior completed results.
    """
    if not requests:
        raise DiskForgeError("The read queue has no selected devices.")
    destinations = [request.destination.resolve() for request in requests]
    if len(set(destinations)) != len(destinations):
        raise DiskForgeError("Every queued device read requires a different destination file.")
    results: list[DeviceReadItem] = []
    for request in requests:
        if token:
            token.raise_if_cancelled()
        try:
            output = read_device_to_image(request.device, request.destination, progress, token, request.overwrite)
            digest = sha256_file(output, token=token)
            results.append(DeviceReadItem(request.device.identifier, output, output.stat().st_size, digest))
        except Exception as exc:
            results.append(DeviceReadItem(request.device.identifier, request.destination, 0, None, str(exc)))
            if not continue_on_error:
                break
    return DeviceReadReport(tuple(results))
