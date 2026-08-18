"""Command-line companion for DiskForge's GUI and automation workflows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core.batch import BatchRunner, write_example_batch
from .core.bootsector import edit_fat_boot_properties
from .core.bundle import create_bundle, extract_bundle, inspect_bundle
from .core.compare import compare_streams
from .core.filesystems import FatImageFilesystem, IsoImageFilesystem, create_fat_image, create_iso_from_directory
from .core.formats import QemuImgConverter, convert_image, inspect_image
from .core.mbr import backup_mbr, reset_mbr_to_neutral, restore_mbr
from .core.metadata import load_image_metadata, save_image_comment
from .core.models import ConflictPolicy, ExtractionLayout, ExtractionPolicy, FileSystemType, ImageFormat
from .core.partitions import inspect_gpt, list_partitions
from .core.readonly_fs import SleuthKitImageFilesystem
from .core.resize import resize_image
from .core.selfextract import create_self_extractor
from .core.storage import sha256_file


def _progress(event) -> None:
    print(f"\r{event.operation.value}: {event.percent:3d}% {event.message:40}", end="", flush=True)


def _policy(args: argparse.Namespace) -> ExtractionPolicy:
    return ExtractionPolicy(ExtractionLayout(args.layout), ConflictPolicy(args.on_conflict))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="diskforge-cli", description="DiskForge image operations")
    root.add_argument("--json", action="store_true", help="Emit structured JSON where applicable")
    commands = root.add_subparsers(dest="command", required=True)

    info = commands.add_parser("info", help="Inspect image metadata")
    info.add_argument("image", type=Path)

    listing = commands.add_parser("list", help="List FAT, ISO, NTFS or EXT image files")
    listing.add_argument("image", type=Path)
    listing.add_argument("--path", default="/")

    extract = commands.add_parser("extract", help="Extract files from a supported image filesystem")
    extract.add_argument("image", type=Path)
    extract.add_argument("destination", type=Path)
    extract.add_argument("paths", nargs="+", help="Image paths to extract")
    extract.add_argument("--layout", choices=[item.value for item in ExtractionLayout], default=ExtractionLayout.PRESERVE_PATHS.value)
    extract.add_argument("--on-conflict", choices=[item.value for item in ConflictPolicy], default=ConflictPolicy.ERROR.value)

    inject = commands.add_parser("inject", help="Inject host files or directories into a writable FAT image")
    inject.add_argument("image", type=Path)
    inject.add_argument("sources", type=Path, nargs="+")
    inject.add_argument("--target-directory", default="/")

    rename = commands.add_parser("rename", help="Rename one FAT image entry")
    rename.add_argument("image", type=Path)
    rename.add_argument("path")
    rename.add_argument("new_name")

    attributes = commands.add_parser("set-attributes", help="Set standard DOS attributes on one FAT entry")
    attributes.add_argument("image", type=Path)
    attributes.add_argument("path")
    for name in ("read-only", "hidden", "system", "archive"):
        attributes.add_argument(f"--{name}", action=argparse.BooleanOptionalAction, default=None)

    label = commands.add_parser("set-label", help="Set a FAT volume label")
    label.add_argument("image", type=Path)
    label.add_argument("label")

    comment = commands.add_parser("comment", help="Read or write non-invasive image comment metadata")
    comment.add_argument("image", type=Path)
    comment.add_argument("text", nargs="?")

    create = commands.add_parser("create-fat", help="Create a formatted FAT image")
    create.add_argument("image", type=Path)
    create.add_argument("--size-mib", type=int, default=32)
    create.add_argument("--fat", choices=["12", "16", "32"], default="16")
    create.add_argument("--label", default="DISKFORGE")

    iso = commands.add_parser("create-iso", help="Create ISO9660/Joliet image from directory")
    iso.add_argument("directory", type=Path)
    iso.add_argument("image", type=Path)
    iso.add_argument("--label", default="DISKFORGE")

    convert = commands.add_parser("convert", help="Convert an image")
    convert.add_argument("source", type=Path)
    convert.add_argument("destination", type=Path)
    convert.add_argument("--format", choices=[item.value for item in ImageFormat if item not in {ImageFormat.UNKNOWN, ImageFormat.DMG}], required=True)
    convert.add_argument("--overwrite", action="store_true")

    resize = commands.add_parser("resize", help="Safely resize RAW or FAT image into a new file")
    resize.add_argument("source", type=Path)
    resize.add_argument("destination", type=Path)
    resize.add_argument("--size-bytes", type=int, required=True)
    resize.add_argument("--overwrite", action="store_true")

    compare = commands.add_parser("compare", help="Byte-compare two image files")
    compare.add_argument("source", type=Path)
    compare.add_argument("destination", type=Path)
    compare.add_argument("--bytes-to-compare", type=int)

    checksum = commands.add_parser("sha256", help="Calculate an image checksum")
    checksum.add_argument("image", type=Path)

    parts = commands.add_parser("partitions", help="Show validated MBR/GPT partition table")
    parts.add_argument("image", type=Path)

    boot = commands.add_parser("boot-properties", help="Edit structured FAT boot properties with backup")
    boot.add_argument("image", type=Path)
    boot.add_argument("--oem-name")
    boot.add_argument("--volume-label")
    boot.add_argument("--serial-number", type=lambda value: int(value, 0))

    mbr_backup = commands.add_parser("mbr-backup", help="Back up one MBR sector")
    mbr_backup.add_argument("image", type=Path)
    mbr_backup.add_argument("--output", type=Path)
    mbr_restore = commands.add_parser("mbr-restore", help="Restore an MBR backup after confirmation")
    mbr_restore.add_argument("image", type=Path)
    mbr_restore.add_argument("backup", type=Path)
    mbr_restore.add_argument("--confirm", required=True)
    mbr_reset = commands.add_parser("mbr-reset", help="Clear MBR bootstrap code while preserving partitions")
    mbr_reset.add_argument("image", type=Path)
    mbr_reset.add_argument("--confirm", required=True)

    bundle = commands.add_parser("bundle", help="Create a DiskForge multi-image bundle")
    bundle.add_argument("output", type=Path)
    bundle.add_argument("images", type=Path, nargs="+")
    bundle.add_argument("--comment", default="")
    bundle.add_argument("--description", default="")
    bundle.add_argument("--compression-level", type=int, choices=range(10), default=6)
    bundle.add_argument("--password-stdin", action="store_true", help="Read an encryption password from stdin")
    bundle.add_argument("--overwrite", action="store_true")

    unbundle = commands.add_parser("unbundle", help="Extract and verify a DiskForge bundle")
    unbundle.add_argument("bundle", type=Path)
    unbundle.add_argument("destination", type=Path)
    unbundle.add_argument("--name", action="append", dest="names")
    unbundle.add_argument("--password-stdin", action="store_true")
    unbundle.add_argument("--overwrite", action="store_true")

    sfx = commands.add_parser("self-extract", help="Create portable self-extracting .pyz bundle")
    sfx.add_argument("image", type=Path)
    sfx.add_argument("output", type=Path)
    sfx.add_argument("--description", default="")

    batch = commands.add_parser("batch", help="Run or generate batch recipe")
    batch.add_argument("recipe", type=Path, nargs="?")
    batch.add_argument("--example", type=Path)
    return root


def _filesystem(image: Path, *, writable: bool = False):
    info = inspect_image(image, QemuImgConverter())
    if info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        return FatImageFilesystem(image, read_only=not writable)
    if info.filesystem == FileSystemType.ISO9660 or info.image_format == ImageFormat.ISO:
        return IsoImageFilesystem(image)
    if info.filesystem in {FileSystemType.NTFS, FileSystemType.EXT}:
        return SleuthKitImageFilesystem(image, info.filesystem)
    raise SystemExit("Image filesystem is not browsable. Supported: FAT, ISO, NTFS and EXT with optional backend.")


def _entry_json(entry) -> dict[str, Any]:
    return {
        "path": entry.path, "name": entry.name, "directory": entry.is_dir, "bytes": entry.size,
        "modified": entry.modified.isoformat() if entry.modified else None,
        "created": entry.created.isoformat() if entry.created else None, "attributes": entry.attributes,
    }


def _emit(args: argparse.Namespace, value: Any, text: str | None = None) -> None:
    if args.json:
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
    elif text is not None:
        print(text)
    elif isinstance(value, (str, Path)):
        print(value)
    else:
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _password_from_stdin(enabled: bool) -> str | None:
    if not enabled:
        return None
    password = sys.stdin.readline().rstrip("\r\n")
    if not password:
        raise SystemExit("Password input was empty.")
    return password


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "info":
            info = inspect_image(args.image, QemuImgConverter())
            metadata = load_image_metadata(args.image)
            _emit(args, {
                "path": str(info.path), "format": info.image_format.value, "bytes": info.size,
                "virtual_bytes": info.virtual_size, "filesystem": info.filesystem.value,
                "writable": info.writable, "notes": list(info.notes), "comment": metadata.comment,
            })
        elif args.command == "list":
            fs = _filesystem(args.image)
            try:
                entries = fs.list_entries(args.path)
                _emit(args, [_entry_json(entry) for entry in entries], "\n".join(
                    f"{'d' if entry.is_dir else '-'} {entry.size:>12} {entry.attributes:>10} {entry.path}" for entry in entries
                ))
            finally:
                fs.close()
        elif args.command == "extract":
            fs = _filesystem(args.image)
            try:
                outputs = fs.extract(args.paths, args.destination, _progress, policy=_policy(args))
                print() if outputs and not args.json else None
                _emit(args, {"outputs": [str(output) for output in outputs]}, "\n".join(str(output) for output in outputs))
            finally:
                fs.close()
        elif args.command == "inject":
            fs = _filesystem(args.image, writable=True)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images are writable.")
                outputs = fs.inject(args.sources, args.target_directory, _progress)
                print() if outputs and not args.json else None
                _emit(args, {"paths": outputs}, "\n".join(outputs))
            finally:
                fs.close()
        elif args.command == "rename":
            fs = _filesystem(args.image, writable=True)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images support rename.")
                renamed = fs.rename(args.path, args.new_name)
                _emit(args, {"path": renamed}, renamed)
            finally:
                fs.close()
        elif args.command == "set-attributes":
            fs = _filesystem(args.image, writable=True)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images support DOS attributes.")
                value = fs.set_attributes(args.path, read_only=args.read_only, hidden=args.hidden,
                                          system=args.system, archive=args.archive)
                _emit(args, {"attributes": value}, value)
            finally:
                fs.close()
        elif args.command == "set-label":
            fs = _filesystem(args.image, writable=True)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images have a writable volume label.")
                value = fs.set_volume_label(args.label)
                _emit(args, {"label": value}, value)
            finally:
                fs.close()
        elif args.command == "comment":
            metadata = save_image_comment(args.image, args.text) if args.text is not None else load_image_metadata(args.image)
            _emit(args, {"comment": metadata.comment, "updated_at": metadata.updated_at}, metadata.comment)
        elif args.command == "create-fat":
            fat = FileSystemType(f"FAT{args.fat}")
            created = create_fat_image(args.image, args.size_mib * 1024 * 1024, fat, args.label)
            _emit(args, {"path": str(created)}, str(created))
        elif args.command == "create-iso":
            created = create_iso_from_directory(args.directory, args.image, args.label)
            _emit(args, {"path": str(created)}, str(created))
        elif args.command == "convert":
            result = convert_image(args.source, args.destination, ImageFormat(args.format), QemuImgConverter(),
                                   _progress, overwrite=args.overwrite)
            print() if not args.json else None
            _emit(args, {"path": str(result.path), "format": result.image_format.value}, str(result.path))
        elif args.command == "resize":
            result = resize_image(args.source, args.destination, args.size_bytes, progress=_progress,
                                  overwrite=args.overwrite)
            print() if not args.json else None
            _emit(args, result.__dict__, str(result.destination))
        elif args.command == "compare":
            result = compare_streams(args.source, args.destination, bytes_to_compare=args.bytes_to_compare,
                                     progress=_progress)
            print() if not args.json else None
            _emit(args, result.__dict__, f"{result.reason}; first difference: {result.first_difference}")
            return 0 if result.equal else 1
        elif args.command == "sha256":
            digest = sha256_file(args.image, progress=_progress)
            print() if not args.json else None
            _emit(args, {"sha256": digest}, digest)
        elif args.command == "partitions":
            partitions = list_partitions(args.image)
            gpt = inspect_gpt(args.image)
            payload = {
                "partitions": [part.__dict__ | {"filesystem": part.filesystem.value} for part in partitions],
                "gpt": (gpt.__dict__ | {"partitions": None}) if gpt else None,
            }
            _emit(args, payload, "\n".join(
                f"{part.index}\t{part.start_lba}\t{part.sectors}\t{part.filesystem.value}\t{part.name or part.type_code}" for part in partitions
            ))
        elif args.command == "boot-properties":
            info, backup = edit_fat_boot_properties(args.image, oem_name=args.oem_name,
                                                     volume_label=args.volume_label,
                                                     serial_number=args.serial_number)
            _emit(args, {"backup": str(backup), "oem": info.oem_name, "label": info.volume_label}, str(backup))
        elif args.command == "mbr-backup":
            backup = backup_mbr(args.image, args.output)
            _emit(args, {"backup": str(backup.backup), "sha256": backup.sha256}, str(backup.backup))
        elif args.command == "mbr-restore":
            backup = restore_mbr(args.image, args.backup, args.confirm)
            _emit(args, {"pre_restore_backup": str(backup.backup)}, str(backup.backup))
        elif args.command == "mbr-reset":
            backup = reset_mbr_to_neutral(args.image, args.confirm)
            _emit(args, {"backup": str(backup.backup)}, str(backup.backup))
        elif args.command == "bundle":
            info = create_bundle(args.images, args.output, password=_password_from_stdin(args.password_stdin),
                                 comment=args.comment, description=args.description,
                                 compression_level=args.compression_level, overwrite=args.overwrite)
            _emit(args, {"path": str(info.path), "encrypted": info.encrypted,
                         "items": [item.__dict__ for item in info.items]}, str(info.path))
        elif args.command == "unbundle":
            outputs = extract_bundle(args.bundle, args.destination, password=_password_from_stdin(args.password_stdin),
                                     names=args.names, overwrite=args.overwrite)
            _emit(args, {"outputs": [str(item) for item in outputs]}, "\n".join(str(item) for item in outputs))
        elif args.command == "self-extract":
            output = create_self_extractor(args.image, args.output, description=args.description)
            _emit(args, {"path": str(output)}, str(output))
        elif args.command == "batch":
            if args.example:
                output = write_example_batch(args.example)
                _emit(args, {"path": str(output)}, str(output))
            elif args.recipe:
                result = BatchRunner().run(args.recipe, print)
                payload = {"succeeded": result.succeeded, "failed": result.failed,
                           "items": [item.__dict__ | {"source": str(item.source), "destination": str(item.destination) if item.destination else None, "operation": item.operation.value} for item in result.items]}
                _emit(args, payload)
                return 0 if result.failed == 0 else 1
            else:
                raise SystemExit("Provide a recipe or --example output path.")
        return 0
    except Exception as exc:
        print(f"DiskForge error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
