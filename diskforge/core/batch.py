"""Declarative and auditable batch-operation support."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .formats import QemuImgConverter, convert_image
from .models import BatchItemResult, BatchResult, ImageFormat, OperationKind
from .storage import DiskForgeError, sha256_file


class BatchRunner:
    """Execute a narrowly scoped JSON batch specification.

    Batch files deliberately reject raw-device writes.  Disk writes require the
    interactive GUI confirmation flow, preventing an imported recipe from
    silently erasing a drive.
    """

    def __init__(self, converter: QemuImgConverter | None = None) -> None:
        self.converter = converter or QemuImgConverter()

    def load(self, path: Path | str) -> dict[str, Any]:
        target = Path(path)
        data = json.loads(target.read_text(encoding="utf-8"))
        if data.get("schema") != "diskforge.batch/v1":
            raise DiskForgeError("Unsupported batch schema.")
        if not isinstance(data.get("operations"), list):
            raise DiskForgeError("Batch operations must be a list.")
        return data

    def run(self, path: Path | str, on_item: Callable[[str], None] | None = None) -> BatchResult:
        spec = self.load(path)
        result = BatchResult()
        for item in spec["operations"]:
            label = str(item.get("name") or item.get("kind") or "operation")
            if on_item:
                on_item(label)
            try:
                output = self._run_item(item)
                result.items.append(BatchItemResult(
                    Path(item.get("source", "")), Path(output) if output else None,
                    OperationKind(item["kind"]), True, "Completed"
                ))
            except Exception as exc:  # An individual batch error must not hide later results.
                result.items.append(BatchItemResult(
                    Path(item.get("source", "")), Path(item["destination"]) if item.get("destination") else None,
                    OperationKind(item.get("kind", "verify")), False, str(exc)
                ))
                if not item.get("continue_on_error", False):
                    break
        result.completed = datetime.now(timezone.utc)
        return result

    def _run_item(self, item: dict[str, Any]) -> str | None:
        kind = OperationKind(item["kind"])
        if kind == OperationKind.CONVERT:
            target_format = ImageFormat(item["format"])
            info = convert_image(item["source"], item["destination"], target_format,
                                 converter=self.converter, overwrite=bool(item.get("overwrite", False)))
            return str(info.path)
        if kind == OperationKind.VERIFY:
            expected = str(item["sha256"]).lower()
            actual = sha256_file(item["source"])
            if actual.lower() != expected:
                raise DiskForgeError(f"SHA-256 mismatch for {item['source']}")
            return None
        if kind in {OperationKind.READ_DEVICE, OperationKind.WRITE_DEVICE}:
            raise DiskForgeError("Raw device actions are not permitted in unattended batch files.")
        raise DiskForgeError(f"Batch operation is not implemented: {kind.value}")


def example_batch() -> dict[str, Any]:
    return {
        "schema": "diskforge.batch/v1",
        "operations": [
            {
                "name": "Convert archival IMG to fixed VHD",
                "kind": "convert",
                "source": "archive.img",
                "destination": "archive.vhd",
                "format": "vhd",
                "overwrite": False,
            },
            {
                "name": "Verify the converted image",
                "kind": "verify",
                "source": "archive.vhd",
                "sha256": "replace-with-sha256",
            },
        ],
    }


def write_example_batch(path: Path | str) -> Path:
    target = Path(path)
    target.write_text(json.dumps(example_batch(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
