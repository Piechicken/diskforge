"""Command-line companion for DiskForge's GUI and automation workflows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core.batch import BatchRunner, write_example_batch
from .core.filesystems import FatImageFilesystem, IsoImageFilesystem, create_fat_image, create_iso_from_directory
from .core.formats import QemuImgConverter, convert_image, inspect_image
from .core.models import FileSystemType, ImageFormat
from .core.partitions import list_partitions
from .core.selfextract import create_self_extractor
from .core.storage import sha256_file


def _progress(event) -> None:
    print(f"\r{event.operation.value}: {event.percent:3d}% {event.message:40}", end="", flush=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="diskforge-cli", description="DiskForge image operations")
    commands = root.add_subparsers(dest="command", required=True)

    info = commands.add_parser("info", help="Inspect image metadata")
    info.add_argument("image", type=Path)

    listing = commands.add_parser("list", help="List FAT or ISO image files")
    listing.add_argument("image", type=Path)
    listing.add_argument("--path", default="/")

    extract = commands.add_parser("extract", help="Extract files from a FAT or ISO image")
    extract.add_argument("image", type=Path)
    extract.add_argument("destination", type=Path)
    extract.add_argument("paths", nargs="+", help="Image paths to extract")

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

    checksum = commands.add_parser("sha256", help="Calculate an image checksum")
    checksum.add_argument("image", type=Path)

    parts = commands.add_parser("partitions", help="Show MBR/GPT partition table")
    parts.add_argument("image", type=Path)

    sfx = commands.add_parser("self-extract", help="Create portable self-extracting .pyz bundle")
    sfx.add_argument("image", type=Path)
    sfx.add_argument("output", type=Path)
    sfx.add_argument("--description", default="")

    batch = commands.add_parser("batch", help="Run or generate batch recipe")
    batch.add_argument("recipe", type=Path, nargs="?")
    batch.add_argument("--example", type=Path)
    return root


def _filesystem(image: Path):
    info = inspect_image(image, QemuImgConverter())
    if info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        return FatImageFilesystem(image)
    if info.filesystem == FileSystemType.ISO9660 or info.image_format == ImageFormat.ISO:
        return IsoImageFilesystem(image)
    raise SystemExit("Image filesystem is not currently browsable. FAT and ISO9660 are supported natively.")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "info":
            info = inspect_image(args.image, QemuImgConverter())
            print(json.dumps({
                "path": str(info.path), "format": info.image_format.value, "bytes": info.size,
                "virtual_bytes": info.virtual_size, "filesystem": info.filesystem.value,
                "writable": info.writable, "notes": list(info.notes),
            }, indent=2))
        elif args.command == "list":
            fs = _filesystem(args.image)
            try:
                for entry in fs.list_entries(args.path):
                    print(f"{'d' if entry.is_dir else '-'} {entry.size:>12} {entry.path}")
            finally:
                fs.close()
        elif args.command == "extract":
            fs = _filesystem(args.image)
            try:
                outputs = fs.extract(args.paths, args.destination, _progress)
                print()
                for output in outputs:
                    print(output)
            finally:
                fs.close()
        elif args.command == "create-fat":
            fat = FileSystemType(f"FAT{args.fat}")
            create_fat_image(args.image, args.size_mib * 1024 * 1024, fat, args.label)
            print(args.image)
        elif args.command == "create-iso":
            create_iso_from_directory(args.directory, args.image, args.label)
            print(args.image)
        elif args.command == "convert":
            result = convert_image(args.source, args.destination, ImageFormat(args.format), QemuImgConverter(),
                                   _progress, overwrite=args.overwrite)
            print(f"\n{result.path}")
        elif args.command == "sha256":
            print(sha256_file(args.image, progress=_progress))
        elif args.command == "partitions":
            for part in list_partitions(args.image):
                print(f"{part.index}\t{part.start_lba}\t{part.sectors}\t{part.filesystem.value}\t{part.name or part.type_code}")
        elif args.command == "self-extract":
            print(create_self_extractor(args.image, args.output, description=args.description))
        elif args.command == "batch":
            if args.example:
                print(write_example_batch(args.example))
            elif args.recipe:
                result = BatchRunner().run(args.recipe, print)
                print(json.dumps({"succeeded": result.succeeded, "failed": result.failed,
                                  "items": [item.__dict__ | {"source": str(item.source), "destination": str(item.destination) if item.destination else None, "operation": item.operation.value} for item in result.items]}, indent=2))
            else:
                raise SystemExit("Provide a recipe or --example output path.")
        return 0
    except Exception as exc:
        print(f"DiskForge error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
