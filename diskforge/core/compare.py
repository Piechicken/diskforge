"""Read-only, cancellable byte-level comparison for images and devices."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .models import OperationKind, Progress, ProgressCallback
from .storage import CancellationToken


_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ComparisonResult:
    """A deterministic comparison summary suitable for GUI and JSON output."""

    source: Path
    destination: Path
    source_size: int
    destination_size: int
    bytes_compared: int
    equal: bool
    first_difference: int | None
    source_sha256: str
    destination_sha256: str
    reason: str = ""


def compare_streams(source: Path | str, destination: Path | str, *, bytes_to_compare: int | None = None,
                    progress: ProgressCallback | None = None,
                    token: CancellationToken | None = None) -> ComparisonResult:
    """Compare two readable byte streams without modifying either endpoint.

    If `bytes_to_compare` is omitted, all common bytes are read; differing sizes
    are reported after the shared region has been verified.  Explicit limits are
    useful for validating the written image portion of a larger physical device.
    """
    left, right = Path(source), Path(destination)
    source_size, destination_size = left.stat().st_size, right.stat().st_size
    if bytes_to_compare is not None:
        if bytes_to_compare < 0:
            raise ValueError("bytes_to_compare must be non-negative.")
        limit = min(bytes_to_compare, source_size, destination_size)
        size_reason = "" if source_size >= bytes_to_compare and destination_size >= bytes_to_compare else "comparison limit exceeds an endpoint"
    else:
        limit = min(source_size, destination_size)
        size_reason = "" if source_size == destination_size else "endpoint sizes differ"
    left_hash, right_hash = hashlib.sha256(), hashlib.sha256()
    completed, difference = 0, None
    with left.open("rb") as source_handle, right.open("rb") as destination_handle:
        while completed < limit:
            if token:
                token.raise_if_cancelled()
            take = min(_CHUNK_SIZE, limit - completed)
            first, second = source_handle.read(take), destination_handle.read(take)
            if len(first) != take or len(second) != take:
                size_reason = "endpoint ended during comparison"
                break
            left_hash.update(first)
            right_hash.update(second)
            if first != second:
                mismatch = next(index for index, pair in enumerate(zip(first, second)) if pair[0] != pair[1])
                difference = completed + mismatch
                completed += take
                if progress:
                    progress(Progress(OperationKind.COMPARE, completed, limit, "Difference found"))
                break
            completed += take
            if progress:
                progress(Progress(OperationKind.COMPARE, completed, limit, "Comparing sectors"))
    equal = difference is None and not size_reason and completed == limit
    if difference is not None:
        reason = "bytes differ"
    elif size_reason:
        reason = size_reason
    else:
        reason = "identical"
    return ComparisonResult(left, right, source_size, destination_size, completed, equal, difference,
                            left_hash.hexdigest(), right_hash.hexdigest(), reason)
