"""Declarative and auditable batch-operation support.

Batch files are intentionally restricted to image files and local directories.
They cannot write, format or repartition physical devices because those actions
must always go through an interactive, foreground confirmation flow.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .bundle import create_bundle, extract_bundle
from .compare import compare_streams
from .filesystems import FatImageFilesystem, IsoImageFilesystem, replace_iso_file_safely
from .formats import (QemuImgConverter, convert_image, create_legacy_zip_image,
                      extract_legacy_zip_image, inspect_image)
from .models import (BatchItemResult, BatchResult, ConflictPolicy, ExtractionLayout,
                     ExtractionPolicy, FileSystemType, ImageFormat, OperationKind)
from .readonly_fs import SleuthKitImageFilesystem
from .resize import resize_image
from .sequence import SequencePattern, planned_paths
from .storage import DiskForgeError, sha256_file


class BatchRunner:
    """Execute a deliberately safe JSON batch specification."""

    _SCHEMAS = {"diskforge.batch/v1", "diskforge.batch/v2", "diskforge.batch/v3", "diskforge.batch/v4"}

    def __init__(self, converter: QemuImgConverter | None = None) -> None:
        self.converter = converter or QemuImgConverter()

    def load(self, path: Path | str) -> dict[str, Any]:
        target = Path(path)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DiskForgeError("Batch file is unreadable or invalid JSON.") from exc
        if not isinstance(data, dict) or data.get("schema") not in self._SCHEMAS:
            raise DiskForgeError("Unsupported batch schema.")
        if not isinstance(data.get("operations"), list):
            raise DiskForgeError("Batch operations must be a list.")
        return data

    @staticmethod
    def _operation_kind(item: dict[str, Any]) -> OperationKind:
        try:
            return OperationKind(str(item["kind"]))
        except (KeyError, ValueError) as exc:
            raise DiskForgeError("Batch operation kind is missing or unsupported.") from exc

    def preview(self, path: Path | str) -> list[dict[str, Any]]:
        """Validate a recipe without reading images, creating files, or writing devices."""
        spec = self.load(path)
        preview: list[dict[str, Any]] = []
        required: dict[OperationKind, tuple[str, ...]] = {
            OperationKind.CONVERT: ("source", "destination", "format"),
            OperationKind.VERIFY: ("source", "sha256"),
            OperationKind.COMPARE: ("source", "destination"),
            OperationKind.RESIZE: ("source", "destination", "size_bytes"),
            OperationKind.EXTRACT: (),
            OperationKind.INJECT: ("destination", "sources"),
            OperationKind.BUNDLE: ("sources", "destination"),
            OperationKind.UNBUNDLE: ("source", "destination"),
            OperationKind.LEGACY_COMPRESS: ("source", "destination", "format"),
            OperationKind.LEGACY_EXTRACT: ("source", "destination"),
            OperationKind.ISO_REPLACE: ("source", "destination", "iso_path", "replacement"),
        }
        for position, raw in enumerate(spec["operations"]):
            item = raw if isinstance(raw, dict) else {}
            kind = self._operation_kind(item)
            if kind in {OperationKind.READ_DEVICE, OperationKind.WRITE_DEVICE}:
                raise DiskForgeError("Raw device actions are not permitted in unattended batch files.")
            if kind not in required:
                raise DiskForgeError(f"Batch operation is not implemented: {kind.value}")
            if kind == OperationKind.EXTRACT:
                has_single = "source" in item and "destination" in item
                has_sequence = "sources" in item and "destination_root" in item and "sequence" in item
                if not (has_single or has_sequence):
                    raise DiskForgeError("Extraction requires source/destination or sources/destination_root/sequence.")
            else:
                absent = [key for key in required[kind] if key not in item]
                if absent:
                    raise DiskForgeError(f"Batch {kind.value} operation is missing: {', '.join(absent)}.")
            if kind == OperationKind.CONVERT:
                try:
                    ImageFormat(str(item["format"]))
                except ValueError as exc:
                    raise DiskForgeError("Batch conversion format is unsupported.") from exc
            if kind == OperationKind.LEGACY_COMPRESS and str(item["format"]) not in {ImageFormat.IMZ.value, ImageFormat.WLZ.value}:
                raise DiskForgeError("Legacy compression format must be imz or wlz.")
            preview.append({
                "index": position,
                "name": str(item.get("name") or kind.value),
                "kind": kind.value,
                "source": item.get("source"),
                "destination": item.get("destination") or item.get("destination_root"),
                "will_write": kind in {OperationKind.CONVERT, OperationKind.RESIZE, OperationKind.INJECT,
                                         OperationKind.BUNDLE, OperationKind.UNBUNDLE, OperationKind.EXTRACT,
                                         OperationKind.LEGACY_COMPRESS, OperationKind.LEGACY_EXTRACT,
                                         OperationKind.ISO_REPLACE},
            })
        return preview

    def run(self, path: Path | str, on_item: Callable[[str], None] | None = None) -> BatchResult:
        spec = self.load(path)
        result = BatchResult()
        for raw in spec["operations"]:
            item = raw if isinstance(raw, dict) else {}
            label = str(item.get("name") or item.get("kind") or "operation")
            if on_item:
                on_item(label)
            try:
                kind = self._operation_kind(item)
                output = self._run_item(item, kind)
                source_value = item.get("source") or (item.get("sources") or [""])[0]
                result.items.append(BatchItemResult(
                    Path(source_value), Path(output) if output else None,
                    kind, True, "Completed", label
                ))
            except Exception as exc:  # An individual error must remain auditable.
                try:
                    kind = self._operation_kind(item)
                except DiskForgeError:
                    kind = OperationKind.VERIFY
                source_value = item.get("source") or (item.get("sources") or [""])[0]
                result.items.append(BatchItemResult(
                    Path(source_value), Path(item["destination"]) if item.get("destination") else None,
                    kind, False, str(exc), label
                ))
                if not item.get("continue_on_error", False):
                    break
        result.completed = datetime.now(timezone.utc)
        return result

    @staticmethod
    def _policy(item: dict[str, Any]) -> ExtractionPolicy:
        try:
            return ExtractionPolicy(
                ExtractionLayout(str(item.get("layout", ExtractionLayout.PRESERVE_PATHS.value))),
                ConflictPolicy(str(item.get("on_conflict", ConflictPolicy.ERROR.value))),
            )
        except ValueError as exc:
            raise DiskForgeError("Extraction layout or conflict policy is invalid.") from exc

    @staticmethod
    def _filesystem(source: Path):
        info = inspect_image(source)
        if info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
            return FatImageFilesystem(source, read_only=False)
        if info.filesystem == FileSystemType.ISO9660:
            return IsoImageFilesystem(source)
        if info.filesystem in {FileSystemType.NTFS, FileSystemType.EXT}:
            return SleuthKitImageFilesystem(source, info.filesystem)
        raise DiskForgeError("Batch filesystem actions require FAT, ISO, NTFS or EXT image content.")

    def _run_item(self, item: dict[str, Any], kind: OperationKind) -> str | None:
        if kind == OperationKind.CONVERT:
            target_format = ImageFormat(str(item["format"]))
            info = convert_image(item["source"], item["destination"], target_format,
                                 converter=self.converter, overwrite=bool(item.get("overwrite", False)))
            return str(info.path)
        if kind == OperationKind.VERIFY:
            expected = str(item["sha256"]).lower()
            actual = sha256_file(item["source"])
            if actual.lower() != expected:
                raise DiskForgeError(f"SHA-256 mismatch for {item['source']}")
            return None
        if kind == OperationKind.COMPARE:
            comparison = compare_streams(item["source"], item["destination"],
                                         bytes_to_compare=item.get("bytes_to_compare"))
            if not comparison.equal:
                location = comparison.first_difference if comparison.first_difference is not None else "size"
                raise DiskForgeError(f"Byte comparison failed at {location}: {comparison.reason}")
            return None
        if kind == OperationKind.ISO_REPLACE:
            result = replace_iso_file_safely(item["source"], str(item["iso_path"]), item["replacement"],
                                             item["destination"], overwrite=bool(item.get("overwrite", False)))
            return str(result.destination)
        if kind == OperationKind.LEGACY_COMPRESS:
            result = create_legacy_zip_image(item["source"], item["destination"], ImageFormat(str(item["format"])),
                                             overwrite=bool(item.get("overwrite", False)))
            return str(result.destination)
        if kind == OperationKind.LEGACY_EXTRACT:
            result = extract_legacy_zip_image(item["source"], item["destination"])
            return str(result.destination)
        if kind == OperationKind.RESIZE:
            resized = resize_image(item["source"], item["destination"], int(item["size_bytes"]),
                                   overwrite=bool(item.get("overwrite", False)))
            return str(resized.destination)
        if kind == OperationKind.EXTRACT:
            paths = item.get("paths", ["/"])
            if not isinstance(paths, list) or not all(isinstance(value, str) for value in paths):
                raise DiskForgeError("Batch extraction paths must be a string list.")
            source_values = item.get("sources")
            if source_values is None:
                source_paths = [Path(item["source"])]
                destinations = [Path(item["destination"])]
            else:
                if not isinstance(source_values, list) or not source_values or not all(isinstance(value, str) for value in source_values):
                    raise DiskForgeError("Batch extraction sources must be a non-empty string list.")
                if "destination_root" not in item or "sequence" not in item:
                    raise DiskForgeError("Multi-image extraction requires destination_root and sequence.")
                source_paths = [Path(value) for value in source_values]
                destinations = list(planned_paths(item["destination_root"], SequencePattern.from_mapping(item["sequence"]), len(source_paths)))
            for source, destination in zip(source_paths, destinations):
                filesystem = self._filesystem(source)
                try:
                    filesystem.extract(paths, destination, policy=self._policy(item))
                finally:
                    filesystem.close()
            return str(destinations[-1])
        if kind == OperationKind.INJECT:
            source = Path(item["destination"])
            sources = item.get("sources")
            if not isinstance(sources, list) or not all(isinstance(value, str) for value in sources):
                raise DiskForgeError("Batch injection sources must be a string list.")
            filesystem = self._filesystem(source)
            try:
                if not isinstance(filesystem, FatImageFilesystem):
                    raise DiskForgeError("Batch injection is available only for writable FAT images.")
                filesystem.inject(sources, str(item.get("target_directory", "/")))
            finally:
                filesystem.close()
            return str(source)
        if kind == OperationKind.BUNDLE:
            sources = item.get("sources")
            if not isinstance(sources, list) or not all(isinstance(value, str) for value in sources):
                raise DiskForgeError("Bundle sources must be a string list.")
            if item.get("password") or item.get("password_env"):
                raise DiskForgeError("Password-protected bundles must be created interactively, not from batch files.")
            bundle = create_bundle(sources, item["destination"], comment=str(item.get("comment", "")),
                                   description=str(item.get("description", "")),
                                   compression_level=int(item.get("compression_level", 6)),
                                   overwrite=bool(item.get("overwrite", False)))
            return str(bundle.path)
        if kind == OperationKind.UNBUNDLE:
            if item.get("password") or item.get("password_env"):
                raise DiskForgeError("Password-protected bundles must be opened interactively, not from batch files.")
            extracted = extract_bundle(item["source"], item["destination"],
                                       names=item.get("names"), overwrite=bool(item.get("overwrite", False)))
            return str(extracted[0]) if extracted else str(item["destination"])
        if kind in {OperationKind.READ_DEVICE, OperationKind.WRITE_DEVICE}:
            raise DiskForgeError("Raw device actions are not permitted in unattended batch files.")
        raise DiskForgeError(f"Batch operation is not implemented: {kind.value}")


def example_batch() -> dict[str, Any]:
    return {
        "schema": "diskforge.batch/v3",
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
