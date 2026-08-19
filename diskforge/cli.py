"""Command-line companion for DiskForge's GUI and automation workflows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core.batch import BatchRunner, write_example_batch
from .core.bootsector import apply_boot_template, edit_fat_boot_properties, import_boot_sector_file, list_boot_templates
from .core.bundle import create_bundle, extract_bundle, inspect_bundle
from .core.compare import compare_streams
from .core.deployment import prepare_fat_deployment
from .core.device_queue import DeviceReadRequest, read_device_queue
from .core.devices import (backup_device_mbr, compare_image_with_device, format_removable_fat,
                           neutralize_device_mbr, restore_device_mbr)
from .core.eltorito import export_boot_image, inspect_eltorito
from .core.fat_layouts import FatImageLayout, create_fat_image_from_layout
from .core.floppy_format import FloppyControllerFormatter
from .core.filesystems import (FatImageFilesystem, IsoImageFilesystem, create_fat_image,
                               create_iso_from_directory, defragment_fat_image, rebuild_iso_with_changes, replace_iso_file_safely)
from .core.formats import (Dmg2ImgConverter, QemuImgConverter, convert_image, create_dynamic_vhd_from_raw,
                           create_editable_fixed_vhd_copy, create_legacy_zip_image, extract_legacy_zip_image,
                           inspect_image)
from .core.mbr import backup_mbr, reset_mbr_to_neutral, restore_mbr
from .core.media import create_dmf_image, trim_zero_tail, wrap_fat_image_in_mbr
from .core.mounts import ImageMountManager, ImageMountSession
from .core.metadata import load_image_metadata, save_image_comment
from .core.models import (ConflictPolicy, DeviceInfo, DeviceKind, ExtractionLayout, ExtractionPolicy,
                          FileSystemType, ImageFormat)
from .core.partitions import inspect_gpt, list_partitions
from .core.readonly_fs import SleuthKitImageFilesystem
from .core.resize import resize_image
from .core.selfextract import create_self_extractor
from .core.storage import DiskForgeError, sha256_file


def _progress(event) -> None:
    print(f"\r{event.operation.value}: {event.percent:3d}% {event.message:40}", end="", flush=True)


def _policy(args: argparse.Namespace) -> ExtractionPolicy:
    return ExtractionPolicy(ExtractionLayout(args.layout), ConflictPolicy(args.on_conflict))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="diskforge-cli", description="DiskForge image operations")
    root.add_argument("--json", action="store_true", help="Emit structured JSON where applicable")
    commands = root.add_subparsers(dest="command", required=True)

    read_queue = commands.add_parser("read-device-queue", help="Run an auditable read-only device acquisition queue")
    read_queue.add_argument("manifest", type=Path, help="JSON file containing a requests array")
    read_queue.add_argument("--continue-on-error", action="store_true")

    info = commands.add_parser("info", help="Inspect image metadata")
    info.add_argument("image", type=Path)

    listing = commands.add_parser("list", help="List FAT, ISO, NTFS or EXT image files")
    listing.add_argument("image", type=Path)
    listing.add_argument("--path", default="/")
    listing.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    extract = commands.add_parser("extract", help="Extract files from a supported image filesystem")
    extract.add_argument("image", type=Path)
    extract.add_argument("destination", type=Path)
    extract.add_argument("paths", nargs="+", help="Image paths to extract")
    extract.add_argument("--layout", choices=[item.value for item in ExtractionLayout], default=ExtractionLayout.PRESERVE_PATHS.value)
    extract.add_argument("--on-conflict", choices=[item.value for item in ConflictPolicy], default=ConflictPolicy.ERROR.value)
    extract.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    inject = commands.add_parser("inject", help="Inject host files or directories into a writable FAT image")
    inject.add_argument("image", type=Path)
    inject.add_argument("sources", type=Path, nargs="+")
    inject.add_argument("--target-directory", default="/")
    inject.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    rename = commands.add_parser("rename", help="Rename one FAT image entry")
    rename.add_argument("image", type=Path)
    rename.add_argument("path")
    rename.add_argument("new_name")
    rename.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    attributes = commands.add_parser("set-attributes", help="Set standard DOS attributes on one FAT entry")
    attributes.add_argument("image", type=Path)
    attributes.add_argument("path")
    for name in ("read-only", "hidden", "system", "archive"):
        attributes.add_argument(f"--{name}", action=argparse.BooleanOptionalAction, default=None)
    attributes.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    label = commands.add_parser("set-label", help="Set a FAT volume label")
    label.add_argument("image", type=Path)
    label.add_argument("label")
    label.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    comment = commands.add_parser("comment", help="Read or write non-invasive image comment metadata")
    comment.add_argument("image", type=Path)
    comment.add_argument("text", nargs="?")

    create = commands.add_parser("create-fat", help="Create a formatted FAT image")
    create.add_argument("image", type=Path)
    create.add_argument("--size-mib", type=int, default=32)
    create.add_argument("--fat", choices=["12", "16", "32"], default="16")
    create.add_argument("--label", default="DISKFORGE")

    dmf = commands.add_parser("create-dmf", help="Create an 80x2x21 FAT12 DMF-layout image file")
    dmf.add_argument("image", type=Path)
    dmf.add_argument("--label", default="DISKFORGE")

    layout = commands.add_parser("fat-layout", help="Inspect a reproducible FAT BPB layout")
    layout.add_argument("image", type=Path)
    create_from_layout = commands.add_parser("create-fat-from-layout", help="Create a FAT image from a validated template layout")
    create_from_layout.add_argument("template", type=Path)
    create_from_layout.add_argument("image", type=Path)
    create_from_layout.add_argument("--label", default="DISKFORGE")

    wrap_mbr = commands.add_parser("wrap-mbr", help="Wrap a FAT superfloppy image in a neutral single-partition MBR image")
    wrap_mbr.add_argument("source", type=Path)
    wrap_mbr.add_argument("destination", type=Path)
    wrap_mbr.add_argument("--bootable", action="store_true", help="Mark the single partition active; no boot code is added")
    wrap_mbr.add_argument("--overwrite", action="store_true")

    deployment = commands.add_parser("prepare-fat-deployment", help="Prepare a neutral-MBR FAT deployment image without writing a device")
    deployment.add_argument("source", type=Path)
    deployment.add_argument("prepared_image", type=Path)
    deployment.add_argument("--not-bootable", action="store_true", help="Leave the single MBR partition inactive")
    deployment.add_argument("--overwrite", action="store_true")

    trim = commands.add_parser("trim-zero-tail", help="Copy an image after removing only full trailing zero sectors")
    trim.add_argument("source", type=Path)
    trim.add_argument("destination", type=Path)
    trim.add_argument("--minimum-bytes", type=int, default=512)
    trim.add_argument("--overwrite", action="store_true")

    iso = commands.add_parser("create-iso", help="Create ISO9660/Joliet image from directory")
    iso.add_argument("directory", type=Path)
    iso.add_argument("image", type=Path)
    iso.add_argument("--label", default="DISKFORGE")
    iso.add_argument("--boot-image", type=Path, help="Optional local El Torito boot image; copied into the new ISO")
    iso.add_argument("--boot-platform", type=lambda value: int(value, 0), default=0, help="El Torito platform ID (default: 0/x86)")
    iso.add_argument("--boot-media", choices=["noemul", "floppy", "hdemul"], default="noemul")
    iso.add_argument("--boot-info-table", action="store_true", help="Write a boot info table into the ISO copy of the boot image")
    iso.add_argument("--boot-load-segment", type=lambda value: int(value, 0), default=0)
    iso.add_argument("--rock-ridge", action="store_true", help="Add Rock Ridge 1.09 names and metadata")
    iso.add_argument("--udf", action="store_true", help="Add a UDF 2.60 bridge filesystem")

    replace_iso = commands.add_parser("replace-iso-file", help="Safely replace one equal-size ISO9660 file into a new ISO")
    replace_iso.add_argument("source", type=Path)
    replace_iso.add_argument("iso_path", help="Existing ISO9660 path, for example /PAYLOAD.TXT")
    replace_iso.add_argument("replacement", type=Path)
    replace_iso.add_argument("destination", type=Path)
    replace_iso.add_argument("--overwrite", action="store_true")

    edit_iso = commands.add_parser("edit-iso", help="Rebuild a standard ISO9660/Joliet image after explicit content edits")
    edit_iso.add_argument("source", type=Path)
    edit_iso.add_argument("destination", type=Path)
    edit_iso.add_argument("--add", action="append", type=Path, default=[], help="Local file or directory to add; repeatable")
    edit_iso.add_argument("--delete", action="append", default=[], help="ISO file or directory path to delete; repeatable")
    edit_iso.add_argument("--mkdir", action="append", default=[], help="ISO directory path to create; repeatable")
    edit_iso.add_argument("--target-directory", default="/", help="Existing ISO directory receiving --add inputs")
    edit_iso.add_argument("--label", help="Optional volume label for the rebuilt ISO")
    edit_iso.add_argument("--overwrite", action="store_true")

    boot_info = commands.add_parser("iso-boot-info", help="Inspect an ISO El Torito boot catalog without modifying the ISO")
    boot_info.add_argument("image", type=Path)
    boot_export = commands.add_parser("export-boot-image", help="Export one ISO El Torito boot image")
    boot_export.add_argument("image", type=Path)
    boot_export.add_argument("output", type=Path)
    boot_export.add_argument("--index", type=int, default=0)
    boot_export.add_argument("--overwrite", action="store_true")

    converter_status = commands.add_parser("converter-status", help="Show optional virtual-disk converter capability")
    dmg_status = commands.add_parser("dmg-adapter-status", help="Show optional read-only DMG conversion adapter capability")
    mount_status = commands.add_parser("mount-status", help="Show controlled read-only image mount capability")
    mount_image = commands.add_parser("mount-image", help="Mount an image read-only and write a mount-session JSON file")
    mount_image.add_argument("image", type=Path)
    mount_image.add_argument("session", type=Path)
    mount_image.add_argument("--overwrite", action="store_true")
    unmount_image = commands.add_parser("unmount-image", help="Unmount a read-only image session recorded by mount-image")
    unmount_image.add_argument("session", type=Path)

    convert = commands.add_parser("convert", help="Convert an image")
    convert.add_argument("source", type=Path)
    convert.add_argument("destination", type=Path)
    convert.add_argument("--format", choices=[item.value for item in ImageFormat if item not in {ImageFormat.UNKNOWN, ImageFormat.DMG}], required=True)
    convert.add_argument("--overwrite", action="store_true")

    editable_vhd = commands.add_parser("create-editable-vhd-copy", help="Create an independently editable fixed-VHD FAT copy")
    editable_vhd.add_argument("source", type=Path)
    editable_vhd.add_argument("destination", type=Path)
    editable_vhd.add_argument("--overwrite", action="store_true")

    dynamic_vhd = commands.add_parser("create-dynamic-vhd", help="Export a FAT raw work image as a verified dynamic VHD using configured qemu-img")
    dynamic_vhd.add_argument("source", type=Path)
    dynamic_vhd.add_argument("destination", type=Path)
    dynamic_vhd.add_argument("--qemu-img", dest="qemu_img")
    dynamic_vhd.add_argument("--overwrite", action="store_true")

    legacy_pack = commands.add_parser("create-legacy-zip", help="Create a ZIP-compatible IMZ or WLZ single-image container")
    legacy_pack.add_argument("source", type=Path)
    legacy_pack.add_argument("destination", type=Path)
    legacy_pack.add_argument("--format", choices=[ImageFormat.IMZ.value, ImageFormat.WLZ.value], required=True)
    legacy_pack.add_argument("--overwrite", action="store_true")
    legacy_unpack = commands.add_parser("extract-legacy-zip", help="Safely extract the one raw payload from an IMZ or WLZ container")
    legacy_unpack.add_argument("source", type=Path)
    legacy_unpack.add_argument("destination", type=Path)

    resize = commands.add_parser("resize", help="Safely resize RAW or FAT image into a new file")
    resize.add_argument("source", type=Path)
    resize.add_argument("destination", type=Path)
    resize.add_argument("--size-bytes", type=int, required=True)
    resize.add_argument("--overwrite", action="store_true")

    compare = commands.add_parser("compare", help="Byte-compare two image files")
    compare.add_argument("source", type=Path)
    compare.add_argument("destination", type=Path)
    compare.add_argument("--bytes-to-compare", type=int)
    compare.add_argument("--ignore-trailing-zero-sectors", action="store_true", help="Report-only: ignore full trailing zero sectors when no byte limit is set")

    export_listing = commands.add_parser("export-listing", help="Export a FAT directory listing as text or HTML")
    export_listing.add_argument("image", type=Path)
    export_listing.add_argument("output", type=Path)
    export_listing.add_argument("--html", action="store_true")
    export_listing.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    defragment = commands.add_parser("defragment-fat", help="Rebuild a FAT superfloppy into a new defragmented image")
    defragment.add_argument("source", type=Path)
    defragment.add_argument("destination", type=Path)

    checksum = commands.add_parser("sha256", help="Calculate an image checksum")
    checksum.add_argument("image", type=Path)

    parts = commands.add_parser("partitions", help="Show validated MBR/GPT partition table")
    parts.add_argument("image", type=Path)

    boot = commands.add_parser("boot-properties", help="Edit structured FAT boot properties with backup")
    boot.add_argument("image", type=Path)
    boot.add_argument("--oem-name")
    boot.add_argument("--volume-label")
    boot.add_argument("--serial-number", type=lambda value: int(value, 0))

    import_boot = commands.add_parser("import-boot-sector", help="Safely import boot code while preserving a FAT BPB")
    import_boot.add_argument("image", type=Path)
    import_boot.add_argument("source", type=Path)
    import_boot.add_argument("--confirm", required=True, help="Must be IMPORT_BOOT_SECTOR")

    boot_templates = commands.add_parser("boot-templates", help="List original DiskForge FAT boot templates")
    boot_templates.add_argument("--verbose", action="store_true")
    apply_template = commands.add_parser("apply-boot-template", help="Apply an original FAT boot template after full-image backup")
    apply_template.add_argument("image", type=Path)
    apply_template.add_argument("template")
    apply_template.add_argument("--confirm", required=True, help="Must be APPLY_TEMPLATE")

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

    device_mbr_backup = commands.add_parser("device-mbr-backup", help="Back up the MBR of one safe device snapshot")
    device_mbr_backup.add_argument("manifest", type=Path, help="JSON device snapshot object")
    device_mbr_backup.add_argument("output", type=Path)
    device_mbr_restore = commands.add_parser("device-mbr-restore", help="Restore device MBR after fresh backup and readback verification")
    device_mbr_restore.add_argument("manifest", type=Path)
    device_mbr_restore.add_argument("backup", type=Path)
    device_mbr_restore.add_argument("pre_restore_backup", type=Path)
    device_mbr_restore.add_argument("--confirm", required=True)
    device_mbr_neutralize = commands.add_parser("device-mbr-neutralize", help="Clear device MBR bootstrap code while preserving its partition table")
    device_mbr_neutralize.add_argument("manifest", type=Path)
    device_mbr_neutralize.add_argument("backup", type=Path)
    device_mbr_neutralize.add_argument("--confirm", required=True)
    compare_device = commands.add_parser("compare-device", help="Read-only compare an image against one device snapshot")
    compare_device.add_argument("image", type=Path)
    compare_device.add_argument("manifest", type=Path)
    format_removable = commands.add_parser("format-removable-fat", help="Format a removable device as a fresh verified FAT volume")
    format_removable.add_argument("manifest", type=Path)
    format_removable.add_argument("--fat", choices=["12", "16", "32"], default="16")
    format_removable.add_argument("--label", default="DISKFORGE")
    format_removable.add_argument("--confirm", required=True, help="Must be FORMAT")
    floppy_status = commands.add_parser("floppy-format-status", help="Show controller-level floppy format capability")
    usb_floppy_status = commands.add_parser("usb-floppy-format-status", help="Show guarded UFI USB floppy format capability")
    usb_floppy_discover = commands.add_parser("discover-ufi-floppy", help="Discover UFI USB floppy capacities from a generic-SCSI device snapshot")
    usb_floppy_discover.add_argument("manifest", type=Path)
    floppy_format = commands.add_parser("format-floppy-controller", help="Low-level format one standard controller floppy from a device snapshot")
    floppy_format.add_argument("manifest", type=Path)
    floppy_format.add_argument("--confirm", required=True, help="Must be FORMAT_FLOPPY")
    usb_floppy_format = commands.add_parser("format-ufi-floppy", help="Low-level format a discovered UFI USB floppy with explicit capacity")
    usb_floppy_format.add_argument("manifest", type=Path)
    usb_floppy_format.add_argument("--capacity", type=int, required=True, help="One capacity reported by discover-ufi-floppy")
    usb_floppy_format.add_argument("--confirm", required=True, help="Must be FORMAT_FLOPPY")

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
    sfx.add_argument("image", type=Path, help="Primary image payload")
    sfx.add_argument("output", type=Path)
    sfx.add_argument("--add", action="append", type=Path, default=[], help="Additional image payload; repeatable")
    sfx.add_argument("--description", default="")
    sfx.add_argument("--overwrite", action="store_true")

    batch = commands.add_parser("batch", help="Run or generate batch recipe")
    batch.add_argument("recipe", type=Path, nargs="?")
    batch.add_argument("--example", type=Path)
    batch.add_argument("--dry-run", action="store_true", help="Validate and print the batch plan without performing operations")
    return root


def _device_from_manifest(path: Path) -> DeviceInfo:
    """Load an explicit device snapshot so destructive CLI commands never infer a target."""
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise DiskForgeError("Device manifest must be a JSON object.")
    return DeviceInfo(
        str(record["identifier"]), str(record.get("display_name") or record["identifier"]),
        int(record["size"]), DeviceKind(str(record.get("kind", DeviceKind.DISK.value))),
        removable=bool(record.get("removable", False)), mounted=bool(record.get("mounted", False)),
        mountpoints=tuple(str(value) for value in record.get("mountpoints", [])),
        model=str(record.get("model", "")), system_disk=bool(record.get("system_disk", False)),
    )


def _filesystem(image: Path, *, writable: bool = False, partition_index: int | None = None):
    info = inspect_image(image, QemuImgConverter())
    if partition_index is not None:
        return FatImageFilesystem(image, read_only=not writable, partition_index=partition_index)
    if info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        return FatImageFilesystem(image, read_only=not writable)
    if info.filesystem == FileSystemType.ISO9660 or info.image_format == ImageFormat.ISO:
        return IsoImageFilesystem(image)
    if info.filesystem in {FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS, FileSystemType.HFS_PLUS}:
        return SleuthKitImageFilesystem(image, info.filesystem)
    raise SystemExit("Image filesystem is not browsable. Supported: FAT, ISO, NTFS, EXT, HFS and HFS+ with optional backend.")


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
    progress = None if args.json else _progress
    try:
        if args.command == "read-device-queue":
            payload = json.loads(args.manifest.read_text(encoding="utf-8"))
            records = payload.get("requests") if isinstance(payload, dict) else None
            if not isinstance(records, list):
                raise DiskForgeError("Read-queue manifest must contain a requests array.")
            requests: list[DeviceReadRequest] = []
            for record in records:
                if not isinstance(record, dict):
                    raise DiskForgeError("Each read-queue request must be an object.")
                device = DeviceInfo(
                    str(record["identifier"]), str(record.get("display_name") or record["identifier"]),
                    int(record["size"]), DeviceKind(str(record.get("kind", DeviceKind.DISK.value))),
                    removable=bool(record.get("removable", False)), mounted=bool(record.get("mounted", False)),
                    mountpoints=tuple(str(value) for value in record.get("mountpoints", [])),
                    model=str(record.get("model", "")), system_disk=bool(record.get("system_disk", False)),
                )
                requests.append(DeviceReadRequest(device, Path(str(record["destination"])), bool(record.get("overwrite", False))))
            report = read_device_queue(requests, continue_on_error=args.continue_on_error, progress=progress)
            _emit(args, report.as_mapping())
        elif args.command == "info":
            info = inspect_image(args.image, QemuImgConverter())
            metadata = load_image_metadata(args.image)
            _emit(args, {
                "path": str(info.path), "format": info.image_format.value, "bytes": info.size,
                "virtual_bytes": info.virtual_size, "filesystem": info.filesystem.value,
                "writable": info.writable, "notes": list(info.notes), "comment": metadata.comment,
            })
        elif args.command == "list":
            fs = _filesystem(args.image, partition_index=args.partition)
            try:
                entries = fs.list_entries(args.path)
                _emit(args, [_entry_json(entry) for entry in entries], "\n".join(
                    f"{'d' if entry.is_dir else '-'} {entry.size:>12} {entry.attributes:>10} {entry.path}" for entry in entries
                ))
            finally:
                fs.close()
        elif args.command == "extract":
            fs = _filesystem(args.image, partition_index=args.partition)
            try:
                outputs = fs.extract(args.paths, args.destination, progress, policy=_policy(args))
                print() if outputs and not args.json else None
                _emit(args, {"outputs": [str(output) for output in outputs]}, "\n".join(str(output) for output in outputs))
            finally:
                fs.close()
        elif args.command == "inject":
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images are writable.")
                outputs = fs.inject(args.sources, args.target_directory, progress)
                print() if outputs and not args.json else None
                _emit(args, {"paths": outputs}, "\n".join(outputs))
            finally:
                fs.close()
        elif args.command == "rename":
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images support rename.")
                renamed = fs.rename(args.path, args.new_name)
                _emit(args, {"path": renamed}, renamed)
            finally:
                fs.close()
        elif args.command == "set-attributes":
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images support DOS attributes.")
                value = fs.set_attributes(args.path, read_only=args.read_only, hidden=args.hidden,
                                          system=args.system, archive=args.archive)
                _emit(args, {"attributes": value}, value)
            finally:
                fs.close()
        elif args.command == "set-label":
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
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
        elif args.command == "create-dmf":
            created = create_dmf_image(args.image, args.label)
            _emit(args, {"path": str(created), "layout": "80x2x21", "bytes": created.stat().st_size}, str(created))
        elif args.command == "fat-layout":
            layout = FatImageLayout.from_image(args.image)
            _emit(args, layout.as_mapping())
        elif args.command == "create-fat-from-layout":
            layout = FatImageLayout.from_image(args.template)
            created = create_fat_image_from_layout(args.image, layout, label=args.label)
            _emit(args, {"path": str(created), "layout": layout.as_mapping()}, str(created))
        elif args.command == "wrap-mbr":
            result = wrap_fat_image_in_mbr(args.source, args.destination, bootable=args.bootable, overwrite=args.overwrite, progress=progress)
            print() if not args.json else None
            _emit(args, {"path": str(result.path), "source": str(result.source), "start_lba": result.partition_start_lba,
                         "sectors": result.partition_sectors, "partition_type": f"0x{result.partition_type:02X}"}, str(result.path))
        elif args.command == "prepare-fat-deployment":
            plan = prepare_fat_deployment(args.source, args.prepared_image, bootable=not args.not_bootable,
                                          overwrite=args.overwrite, progress=progress)
            print() if not args.json else None
            _emit(args, {"source": str(plan.source), "prepared_image": str(plan.prepared_image),
                         "start_lba": plan.partition_start_lba, "sectors": plan.partition_sectors,
                         "partition_type": f"0x{plan.partition_type:02X}", "bootable": plan.bootable,
                         "requires_confirmation": plan.requires_confirmation}, str(plan.prepared_image))
        elif args.command == "trim-zero-tail":
            result = trim_zero_tail(args.source, args.destination, minimum_size=args.minimum_bytes, overwrite=args.overwrite, progress=progress)
            print() if not args.json else None
            _emit(args, {"path": str(result.destination), "original_bytes": result.original_size,
                         "trimmed_bytes": result.trimmed_size, "bytes_removed": result.bytes_removed}, str(result.destination))
        elif args.command == "create-iso":
            created = create_iso_from_directory(
                args.directory, args.image, args.label, boot_image=args.boot_image,
                boot_platform_id=args.boot_platform, boot_media=args.boot_media,
                boot_info_table=args.boot_info_table, boot_load_segment=args.boot_load_segment,
                rock_ridge=args.rock_ridge, udf=args.udf,
            )
            _emit(args, {"path": str(created), "boot_image": str(args.boot_image) if args.boot_image else None,
                         "boot_platform": args.boot_platform if args.boot_image else None,
                         "boot_media": args.boot_media if args.boot_image else None,
                         "rock_ridge": args.rock_ridge, "udf": args.udf}, str(created))
        elif args.command == "replace-iso-file":
            result = replace_iso_file_safely(args.source, args.iso_path, args.replacement, args.destination,
                                             overwrite=args.overwrite)
            _emit(args, {"source": str(result.source), "destination": str(result.destination),
                         "iso_path": result.iso_path, "bytes_replaced": result.bytes_replaced,
                         "source_sha256": result.source_sha256, "output_sha256": result.output_sha256},
                  str(result.destination))
        elif args.command == "edit-iso":
            result = rebuild_iso_with_changes(
                args.source, args.destination, additions=args.add, delete_paths=args.delete,
                create_directories=args.mkdir, target_directory=args.target_directory,
                volume_label=args.label, overwrite=args.overwrite, progress=progress,
            )
            _emit(args, {"source": str(result.source), "destination": str(result.destination),
                         "files_added": list(result.files_added), "paths_deleted": list(result.paths_deleted),
                         "directories_created": list(result.directories_created),
                         "source_sha256": result.source_sha256, "output_sha256": result.output_sha256},
                  str(result.destination))
        elif args.command == "iso-boot-info":
            catalog = inspect_eltorito(args.image)
            payload = {"catalog_lba": catalog.catalog_lba, "images": [
                {"index": image.index, "bootable": image.bootable, "media_type": image.media_type,
                 "load_segment": image.load_segment, "system_type": image.system_type,
                 "sectors_512": image.sector_count_512, "lba": image.lba, "bytes": image.byte_count}
                for image in catalog.images
            ]}
            _emit(args, payload, "\n".join(f"{image.index}\tLBA {image.lba}\t{image.byte_count} bytes\t{'bootable' if image.bootable else 'not bootable'}" for image in catalog.images))
        elif args.command == "export-boot-image":
            output = export_boot_image(args.image, args.output, index=args.index, overwrite=args.overwrite, progress=progress)
            print() if not args.json else None
            _emit(args, {"path": str(output), "index": args.index, "bytes": output.stat().st_size}, str(output))
        elif args.command == "converter-status":
            _emit(args, QemuImgConverter().capability_report().as_mapping())
        elif args.command == "dmg-adapter-status":
            _emit(args, Dmg2ImgConverter().capability_report().as_mapping())
        elif args.command == "mount-status":
            _emit(args, ImageMountManager().capability_report().as_mapping())
        elif args.command == "mount-image":
            if args.session.exists() and not args.overwrite:
                raise FileExistsError(args.session)
            session = ImageMountManager().mount(args.image)
            args.session.parent.mkdir(parents=True, exist_ok=True)
            args.session.write_text(json.dumps({
                "image": str(session.image), "platform": session.platform, "device": session.device,
                "mount_point": str(session.mount_point) if session.mount_point else None, "read_only": session.read_only,
            }, indent=2), encoding="utf-8")
            _emit(args, {"session": str(args.session), "mount_point": str(session.mount_point) if session.mount_point else None,
                         "device": session.device, "read_only": True}, str(args.session))
        elif args.command == "unmount-image":
            record = json.loads(args.session.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise DiskForgeError("Mount session file must contain a JSON object.")
            session = ImageMountSession(Path(str(record["image"])), str(record["platform"]),
                                        str(record["device"]) if record.get("device") else None,
                                        Path(str(record["mount_point"])) if record.get("mount_point") else None,
                                        bool(record.get("read_only", False)))
            ImageMountManager().unmount(session)
            args.session.unlink(missing_ok=True)
            _emit(args, {"unmounted": str(session.image), "session_removed": str(args.session)})
        elif args.command == "convert":
            result = convert_image(args.source, args.destination, ImageFormat(args.format), QemuImgConverter(),
                                   progress, overwrite=args.overwrite)
            print() if not args.json else None
            _emit(args, {"path": str(result.path), "format": result.image_format.value}, str(result.path))
        elif args.command == "create-editable-vhd-copy":
            result = create_editable_fixed_vhd_copy(args.source, args.destination, overwrite=args.overwrite,
                                                    progress=progress)
            print() if not args.json else None
            _emit(args, {"source": str(result.source), "destination": str(result.destination),
                         "virtual_bytes": result.virtual_size}, str(result.destination))
        elif args.command == "create-dynamic-vhd":
            result = create_dynamic_vhd_from_raw(args.source, args.destination, QemuImgConverter(args.qemu_img),
                                                 overwrite=args.overwrite)
            print() if not args.json else None
            _emit(args, {"source": str(result.source), "destination": str(result.destination),
                         "virtual_bytes": result.virtual_size, "disk_type": "dynamic"}, str(result.destination))
        elif args.command == "create-legacy-zip":
            result = create_legacy_zip_image(args.source, args.destination, ImageFormat(args.format),
                                             overwrite=args.overwrite)
            _emit(args, {"source": str(result.source), "destination": str(result.destination),
                         "payload": result.payload_name, "payload_bytes": result.payload_size}, str(result.destination))
        elif args.command == "extract-legacy-zip":
            result = extract_legacy_zip_image(args.source, args.destination)
            _emit(args, {"source": str(result.source), "destination": str(result.destination),
                         "payload": result.payload_name, "payload_bytes": result.payload_size}, str(result.destination))
        elif args.command == "resize":
            result = resize_image(args.source, args.destination, args.size_bytes, progress=progress,
                                  overwrite=args.overwrite)
            print() if not args.json else None
            _emit(args, result.__dict__, str(result.destination))
        elif args.command == "compare":
            result = compare_streams(
                args.source, args.destination, bytes_to_compare=args.bytes_to_compare,
                ignore_trailing_zero_sectors=args.ignore_trailing_zero_sectors, progress=progress,
            )
            print() if not args.json else None
            _emit(args, result.__dict__, f"{result.reason}; first difference: {result.first_difference}")
            return 0 if result.equal else 1
        elif args.command == "export-listing":
            filesystem = _filesystem(args.image, partition_index=args.partition)
            try:
                if not isinstance(filesystem, FatImageFilesystem):
                    raise DiskForgeError("Directory listing export is currently available for FAT images only.")
                output = filesystem.export_listing(args.output, html=args.html)
                _emit(args, {"path": str(output), "format": "html" if args.html else "text"}, str(output))
            finally:
                filesystem.close()
        elif args.command == "defragment-fat":
            output = defragment_fat_image(args.source, args.destination, progress=progress)
            print() if not args.json else None
            _emit(args, {"source": str(args.source), "destination": str(output)}, str(output))
        elif args.command == "sha256":
            digest = sha256_file(args.image, progress=progress)
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
        elif args.command == "import-boot-sector":
            if args.confirm != "IMPORT_BOOT_SECTOR":
                raise DiskForgeError("Boot-sector import requires the exact confirmation phrase IMPORT_BOOT_SECTOR.")
            info, backup = import_boot_sector_file(args.image, args.source)
            _emit(args, {"backup": str(backup), "oem": info.oem_name, "label": info.volume_label,
                         "filesystem": info.filesystem_label}, str(backup))
        elif args.command == "boot-templates":
            templates = list_boot_templates()
            payload = [{"id": item.identifier, "name": item.name, "description": item.description,
                        "license": item.license_notice} for item in templates]
            text = "\n".join(f"{item.identifier}\t{item.name}\t{item.description}" for item in templates)
            _emit(args, payload, text)
        elif args.command == "apply-boot-template":
            if args.confirm != "APPLY_TEMPLATE":
                raise DiskForgeError("Refusing to apply boot template without --confirm APPLY_TEMPLATE.")
            info, backup = apply_boot_template(args.image, args.template)
            _emit(args, {"backup": str(backup), "template": args.template, "oem": info.oem_name,
                         "label": info.volume_label}, str(backup))
        elif args.command == "mbr-backup":
            backup = backup_mbr(args.image, args.output)
            _emit(args, {"backup": str(backup.backup), "sha256": backup.sha256}, str(backup.backup))
        elif args.command == "mbr-restore":
            backup = restore_mbr(args.image, args.backup, args.confirm)
            _emit(args, {"pre_restore_backup": str(backup.backup)}, str(backup.backup))
        elif args.command == "mbr-reset":
            backup = reset_mbr_to_neutral(args.image, args.confirm)
            _emit(args, {"backup": str(backup.backup)}, str(backup.backup))
        elif args.command == "device-mbr-backup":
            audit = backup_device_mbr(_device_from_manifest(args.manifest), args.output)
            _emit(args, audit.__dict__, str(audit.backup))
        elif args.command == "device-mbr-restore":
            audit = restore_device_mbr(_device_from_manifest(args.manifest), args.backup,
                                       args.pre_restore_backup, args.confirm)
            _emit(args, audit.__dict__, str(audit.backup))
        elif args.command == "device-mbr-neutralize":
            audit = neutralize_device_mbr(_device_from_manifest(args.manifest), args.backup, args.confirm)
            _emit(args, audit.__dict__, str(audit.backup))
        elif args.command == "compare-device":
            result = compare_image_with_device(args.image, _device_from_manifest(args.manifest), progress=progress)
            print() if not args.json else None
            _emit(args, result.__dict__, f"{result.reason}; first difference: {result.first_difference}")
            return 0 if result.equal else 1
        elif args.command == "format-removable-fat":
            result = format_removable_fat(_device_from_manifest(args.manifest), FileSystemType(f"FAT{args.fat}"),
                                          args.label, args.confirm)
            _emit(args, result.__dict__)
        elif args.command == "floppy-format-status":
            _emit(args, FloppyControllerFormatter().capability_report().as_mapping())
        elif args.command == "usb-floppy-format-status":
            _emit(args, FloppyControllerFormatter().usb_capability_report().as_mapping())
        elif args.command == "discover-ufi-floppy":
            discovery = FloppyControllerFormatter().discover_usb(_device_from_manifest(args.manifest))
            _emit(args, {"identifier": discovery.identifier, "supported_capacities": list(discovery.supported_capacities)})
        elif args.command == "format-floppy-controller":
            result = FloppyControllerFormatter().format(_device_from_manifest(args.manifest), args.confirm)
            _emit(args, result.__dict__)
        elif args.command == "format-ufi-floppy":
            result = FloppyControllerFormatter().format_usb(_device_from_manifest(args.manifest), args.capacity, args.confirm)
            _emit(args, result.__dict__)
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
            output = create_self_extractor([args.image, *args.add], args.output, description=args.description, overwrite=args.overwrite)
            _emit(args, {"path": str(output), "items": [str(path) for path in [args.image, *args.add]]}, str(output))
        elif args.command == "batch":
            if args.example:
                output = write_example_batch(args.example)
                _emit(args, {"path": str(output)}, str(output))
            elif args.recipe:
                runner = BatchRunner()
                if args.dry_run:
                    plan = runner.preview(args.recipe)
                    _emit(args, {"dry_run": True, "operations": plan})
                else:
                    result = runner.run(args.recipe, print)
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
