"""Command-line companion for DiskForge's GUI and automation workflows."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .core.batch import BatchRunner, write_example_batch
from .core.browse_session import materialize_browsable_image
from .core.bootsector import apply_boot_template, edit_fat_boot_properties, import_boot_sector_file, list_boot_templates
from .core.bundle import create_bundle, extract_bundle, inspect_bundle
from .core.compare import compare_streams
from .core.cpc_dsk import export_cpc_dsk_to_raw, inspect_cpc_dsk
from .core.apridisk import export_apridisk_to_raw, inspect_apridisk
from .core.copyqm import export_copyqm_to_raw, inspect_copyqm
from .core.sap import export_sap_to_raw, inspect_sap
from .core.msa import export_msa_to_raw, inspect_msa
from .core.psi import export_psi_to_raw, inspect_psi
from .core.pri import inspect_pri
from .core.eightysixf import inspect_86f
from .core.fdi import inspect_fdi
from .core.jv3 import export_jv3_to_raw, inspect_jv3
from .core.dmk import inspect_dmk
from .core.udi import inspect_udi
from .core.scp import inspect_scp
from .core.mfm import inspect_mfm
from .core.pfi import inspect_pfi
from .core.woz import inspect_woz
from .core.a2r import inspect_a2r
from .core.d64 import inspect_d64
from .core.d71 import inspect_d71
from .core.d81 import inspect_d81
from .core.g64 import inspect_g64
from .core.g71 import inspect_g71
from .core.p64 import inspect_p64
from .core.d88 import export_d88_to_raw, inspect_d88
from .core.dc42 import export_dc42_data_to_raw, inspect_dc42
from .core.hfe import inspect_hfe
from .core.deployment import prepare_fat_deployment
from .core.ext_inject import ExtFileInjector
from .core.fat_metadata import apply_fat_metadata, metadata_update_from_values
from .core.hfs_create import HfsImageCreator
from .core.hfs_inject import HfsFileInjector
from .core.imd import export_imd_to_raw, inspect_imd
from .core.inventory import ImageInventoryOptions, export_image_inventory, inventory_images
from .core.td0 import export_td0_to_raw, inspect_td0
from .core.twoimg import export_twoimg_to_raw, inspect_twoimg
from .core.device_queue import DeviceReadRequest, read_device_queue
from .core.devices import (backup_device_mbr, compare_image_with_device, format_removable_fat,
                           neutralize_device_mbr, restore_device_mbr)
from .core.eltorito import export_boot_image, inspect_eltorito
from .core.fat_layouts import FatImageLayout, create_fat_image_from_layout
from .core.floppy_format import FloppyControllerFormatter
from .core.filesystems import (D64ImageFilesystem, D71ImageFilesystem, D81ImageFilesystem, FatImageFilesystem, IsoImageFilesystem, create_fat_image,
                               create_iso_from_directory, defragment_fat_image, rebuild_iso_with_changes, replace_iso_file_safely)
from .core.formats import (Dmg2ImgConverter, QemuImgConverter, convert_image, create_dynamic_vhd_from_raw,
                           create_editable_fixed_vhd_copy, create_legacy_zip_image, extract_legacy_zip_image,
                           inspect_image, list_zip_image_payloads)
from .core.mbr import backup_mbr, reset_mbr_to_neutral, restore_mbr
from .core.legacy_floppy import (LEGACY_FLOPPY_PROFILES, LegacyFloppyGeometry,
                                  create_legacy_fat_floppy, create_legacy_fat_floppy_profile)
from .core.listing import export_directory_listing
from .core.media import create_dmf_image, trim_zero_tail, wrap_fat_image_in_mbr
from .core.mounts import ImageMountManager, ImageMountSession
from .core.ntfs_inject import NtfsFileInjector
from .core.metadata import load_image_metadata, save_image_comment
from .core.models import (ConflictPolicy, DeviceInfo, DeviceKind, ExtractionLayout, ExtractionPolicy,
                          FileSystemType, ImageFormat)
from .core.partition_filesystems import open_partition_filesystem
from .core.partitions import inspect_gpt, list_partitions
from .core.readonly_fs import SleuthKitImageFilesystem
from .core.resize import resize_image
from .core.selfextract import create_self_extractor
from .core.storage import DiskForgeError, sha256_file


def _progress(event) -> None:
    print(f"\r{event.operation.value}: {event.percent:3d}% {event.message:40}", end="", flush=True)


def _policy(args: argparse.Namespace) -> ExtractionPolicy:
    return ExtractionPolicy(ExtractionLayout(args.layout), ConflictPolicy(args.on_conflict))


def _parse_local_datetime(value: str | None, option: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DiskForgeError(f"{option} must be an ISO-8601 local date and time.") from exc
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        raise DiskForgeError(f"{option} must not include a timezone offset.")
    return parsed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="diskforge-cli", description="DiskForge image operations")
    root.add_argument("--json", action="store_true", help="Emit structured JSON where applicable")
    commands = root.add_subparsers(dest="command", required=True)

    read_queue = commands.add_parser("read-device-queue", help="Run an auditable read-only device acquisition queue")
    read_queue.add_argument("manifest", type=Path, help="JSON file containing a requests array")
    read_queue.add_argument("--continue-on-error", action="store_true")

    info = commands.add_parser("info", help="Inspect image metadata")
    info.add_argument("image", type=Path)
    zip_info = commands.add_parser("zip-info", help="List validated root-level browsable image payloads in a read-only ZIP")
    zip_info.add_argument("image", type=Path)
    imd_info = commands.add_parser("imd-info", help="Inspect IMD floppy-sector records without modifying the source")
    imd_info.add_argument("image", type=Path)
    convert_imd = commands.add_parser("convert-imd", help="Export only a strictly proven rectangular normal-data IMD layout to a new RAW image")
    convert_imd.add_argument("source", type=Path)
    convert_imd.add_argument("destination", type=Path)
    td0_info = commands.add_parser("td0-info", help="Inspect an ordinary TD0 floppy-sector container without modifying the source")
    td0_info.add_argument("image", type=Path)
    convert_td0 = commands.add_parser("convert-td0", help="Export only a strictly proven unflagged ordinary TD0 layout to a new RAW image")
    convert_td0.add_argument("source", type=Path)
    convert_td0.add_argument("destination", type=Path)
    cpc_dsk_info = commands.add_parser("cpc-dsk-info", help="Inspect a signed CPC standard or extended DSK container without modifying the source")
    cpc_dsk_info.add_argument("image", type=Path)
    convert_cpc_dsk = commands.add_parser("convert-cpc-dsk", help="Export only a strictly proven normal CPC DSK layout to a new RAW image")
    convert_cpc_dsk.add_argument("source", type=Path)
    convert_cpc_dsk.add_argument("destination", type=Path)
    d88_info = commands.add_parser("d88-info", help="Inspect a restricted D88 sector container without modifying the source")
    d88_info.add_argument("image", type=Path)
    convert_d88 = commands.add_parser("convert-d88", help="Export only a strictly proven normal D88 layout to a new RAW image")
    convert_d88.add_argument("source", type=Path)
    convert_d88.add_argument("destination", type=Path)
    hfe_info = commands.add_parser("hfe-info", help="Inspect an HFE bitstream container without decoding, converting, or modifying it")
    hfe_info.add_argument("image", type=Path)
    dc42_info = commands.add_parser("dc42-info", help="Inspect a checksum-validated DC42 container without modifying its source or tags")
    dc42_info.add_argument("image", type=Path)
    convert_dc42 = commands.add_parser("convert-dc42", help="Export only a fully checksum-validated DC42 data fork to a new RAW image")
    convert_dc42.add_argument("source", type=Path)
    convert_dc42.add_argument("destination", type=Path)
    twoimg_info = commands.add_parser("twoimg-info", help="Inspect a standard 2MG/2IMG container without modifying its data or optional blocks")
    twoimg_info.add_argument("image", type=Path)
    convert_twoimg = commands.add_parser("convert-twoimg", help="Export only a structurally validated DOS/ProDOS 2MG data block to a new RAW image")
    convert_twoimg.add_argument("source", type=Path)
    convert_twoimg.add_argument("destination", type=Path)
    apridisk_info = commands.add_parser("apridisk-info", help="Inspect APRIDISK sector records without modifying the source")
    apridisk_info.add_argument("image", type=Path)
    convert_apridisk = commands.add_parser("convert-apridisk", help="Export only a strictly proven rectangular APRIDISK layout to a new RAW image")
    convert_apridisk.add_argument("source", type=Path)
    convert_apridisk.add_argument("destination", type=Path)
    copyqm_info = commands.add_parser("copyqm-info", help="Inspect a checksum-validated CopyQM container without modifying the source")
    copyqm_info.add_argument("image", type=Path)
    convert_copyqm = commands.add_parser("convert-copyqm", help="Export only a checksum-verified CopyQM image to a new RAW file")
    convert_copyqm.add_argument("source", type=Path)
    convert_copyqm.add_argument("destination", type=Path)
    sap_info = commands.add_parser("sap-info", help="Inspect SAP sector records and CRCs without modifying the source")
    sap_info.add_argument("image", type=Path)
    convert_sap = commands.add_parser("convert-sap", help="Export only a fully validated regular SAP layout to a new RAW image")
    convert_sap.add_argument("source", type=Path)
    convert_sap.add_argument("destination", type=Path)
    msa_info = commands.add_parser("msa-info", help="Inspect and fully decode MSA tracks without modifying the source")
    msa_info.add_argument("image", type=Path)
    convert_msa = commands.add_parser("convert-msa", help="Export only a structurally validated MSA track stream to a new RAW image")
    convert_msa.add_argument("source", type=Path)
    convert_msa.add_argument("destination", type=Path)
    psi_info = commands.add_parser("psi-info", help="Inspect a checksummed PSI sector stream without modifying the source")
    psi_info.add_argument("image", type=Path)
    convert_psi = commands.add_parser("convert-psi", help="Export only a complete normal PSI layout to a new RAW image")
    convert_psi.add_argument("source", type=Path)
    convert_psi.add_argument("destination", type=Path)
    pri_info = commands.add_parser("pri-info", help="Inspect a CRC-validated PRI bitstream container without decoding or modifying it")
    pri_info.add_argument("image", type=Path)
    eightysixf_info = commands.add_parser("86f-info", help="Inspect a restricted 86F v2.12 bitstream layout without decoding or modifying it")
    eightysixf_info.add_argument("image", type=Path)
    fdi_info = commands.add_parser("fdi-info", help="Inspect an FDI v2.0 multi-level container without decoding or modifying it")
    fdi_info.add_argument("image", type=Path)
    dmk_info = commands.add_parser("dmk-info", help="Inspect a native DMK bitstream container without decoding or modifying it")
    dmk_info.add_argument("image", type=Path)
    udi_info = commands.add_parser("udi-info", help="Inspect a CRC-validated UDI v1.0 bitstream container without decoding or modifying it")
    udi_info.add_argument("image", type=Path)
    scp_info = commands.add_parser("scp-info", help="Inspect a standard SCP floppy flux container without decoding or modifying it")
    scp_info.add_argument("image", type=Path)
    mfm_info = commands.add_parser("mfm-info", help="Inspect a strict HxC MFM bitstream container without decoding or modifying it")
    mfm_info.add_argument("image", type=Path)
    pfi_info = commands.add_parser("pfi-info", help="Inspect a canonical PCE PFI flux container without decoding or modifying it")
    pfi_info.add_argument("image", type=Path)
    woz_info = commands.add_parser("woz-info", help="Inspect a canonical WOZ 2.0/2.1 Apple II container without decoding or modifying it")
    woz_info.add_argument("image", type=Path)
    a2r_info = commands.add_parser("a2r-info", help="Inspect a canonical A2R 3.x flux container without decoding or modifying it")
    a2r_info.add_argument("image", type=Path)
    d64_info = commands.add_parser("d64-info", help="Inspect a canonical 35-track D64 CBM DOS image and ordinary file chains without modifying it")
    d64_info.add_argument("image", type=Path)
    d71_info = commands.add_parser("d71-info", help="Inspect a canonical 70-track D71 CBM DOS image and ordinary file chains without modifying it")
    d71_info.add_argument("image", type=Path)
    d81_info = commands.add_parser("d81-info", help="Inspect a canonical 80-track D81 CBM DOS image and ordinary file chains without modifying it")
    d81_info.add_argument("image", type=Path)
    g64_info = commands.add_parser("g64-info", help="Inspect a canonical G64 v0 GCR container without decoding or modifying it")
    g64_info.add_argument("image", type=Path)
    g71_info = commands.add_parser("g71-info", help="Inspect a canonical G71 v0 double-sided GCR container without decoding or modifying it")
    g71_info.add_argument("image", type=Path)
    p64_info = commands.add_parser("p64-info", help="Inspect a canonical P64 v0 NRZI pulse container without decoding or modifying it")
    p64_info.add_argument("image", type=Path)
    jv3_info = commands.add_parser("jv3-info", help="Inspect a JV3 sector container without modifying it")
    jv3_info.add_argument("image", type=Path)
    convert_jv3 = commands.add_parser("convert-jv3", help="Export a strictly proven normal JV3 sector layout to a new RAW file")
    convert_jv3.add_argument("image", type=Path)
    convert_jv3.add_argument("destination", type=Path)
    inventory = commands.add_parser("inventory-images", help="Read-only inventory and filter report for local image files")
    inventory.add_argument("root", type=Path, help="Existing local directory to scan")
    inventory.add_argument("destination", type=Path, help="New report file outside the scanned directory")
    inventory.add_argument("--report-format", choices=["json", "csv", "html"], default="json")
    inventory.add_argument("--recursive", action="store_true")
    inventory.add_argument("--suffix", action="append", default=[], help="Allowed image suffix; repeatable")
    inventory.add_argument("--image-format", action="append", choices=[item.value for item in ImageFormat if item is not ImageFormat.UNKNOWN], default=[])
    inventory.add_argument("--filesystem", action="append", choices=[item.value for item in FileSystemType if item is not FileSystemType.UNKNOWN], default=[])
    inventory.add_argument("--min-bytes", type=int)
    inventory.add_argument("--max-bytes", type=int)
    inventory.add_argument("--sha256-prefix")
    inventory.add_argument("--include-sha256", action="store_true")
    inventory.add_argument("--include-partitions", action="store_true")

    listing = commands.add_parser("list", help="List files in a browsable image or explicit validated partition")
    listing.add_argument("image", type=Path)
    listing.add_argument("--path", default="/")
    listing.add_argument("--partition", type=int, help="Explicit MBR/GPT partition table index; NTFS/EXT/HFS/HFS+ stay read-only")
    listing.add_argument("--zip-payload", help="Explicit validated root-level image payload name for a multi-image ZIP; read-only")

    extract = commands.add_parser("extract", help="Extract files from a supported image filesystem")
    extract.add_argument("image", type=Path)
    extract.add_argument("destination", type=Path)
    extract.add_argument("paths", nargs="+", help="Image paths to extract")
    extract.add_argument("--layout", choices=[item.value for item in ExtractionLayout], default=ExtractionLayout.PRESERVE_PATHS.value)
    extract.add_argument("--on-conflict", choices=[item.value for item in ConflictPolicy], default=ConflictPolicy.ERROR.value)
    extract.add_argument("--partition", type=int, help="Explicit MBR/GPT partition table index; NTFS/EXT/HFS/HFS+ stay read-only")
    extract.add_argument("--zip-payload", help="Explicit validated root-level image payload name for a multi-image ZIP; read-only")

    inject = commands.add_parser("inject", help="Inject host files or directories into a writable FAT image")
    inject.add_argument("image", type=Path)
    inject.add_argument("sources", type=Path, nargs="+")
    inject.add_argument("--target-directory", default="/")
    inject.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    inject_ntfs = commands.add_parser("inject-ntfs", help="Copy regular local files into a new standalone NTFS image output")
    inject_ntfs.add_argument("source", type=Path)
    inject_ntfs.add_argument("destination", type=Path)
    inject_ntfs.add_argument("sources", type=Path, nargs="+")
    inject_ntfs.add_argument("--ntfscp", help="Optional explicit ntfscp executable")
    inject_ntfs.add_argument("--ntfsls", help="Optional explicit ntfsls executable")
    inject_ntfs.add_argument("--ntfscat", help="Optional explicit ntfscat executable")

    inject_ext = commands.add_parser("inject-ext", help="Copy regular local files into a new standalone EXT image output")
    inject_ext.add_argument("source", type=Path)
    inject_ext.add_argument("destination", type=Path)
    inject_ext.add_argument("sources", type=Path, nargs="+")
    inject_ext.add_argument("--debugfs", help="Optional explicit debugfs executable")
    inject_ext.add_argument("--e2fsck", help="Optional explicit e2fsck executable")

    inject_hfs = commands.add_parser("inject-hfs", help="Copy regular local files into a new standalone classic HFS image output")
    inject_hfs.add_argument("source", type=Path)
    inject_hfs.add_argument("destination", type=Path)
    inject_hfs.add_argument("sources", type=Path, nargs="+")
    inject_hfs.add_argument("--hmount", help="Optional explicit hmount executable")
    inject_hfs.add_argument("--hcopy", help="Optional explicit hcopy executable")
    inject_hfs.add_argument("--hls", help="Optional explicit hls executable")

    move_fat = commands.add_parser("move-fat", help="Move one regular file or directory tree into an existing directory of a writable FAT image")
    move_fat.add_argument("image", type=Path)
    move_fat.add_argument("source_path", help="Existing image file or directory path to move")
    move_fat.add_argument("target_directory", help="Existing image directory receiving a new same-name move target")
    move_fat.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    mkdir_fat = commands.add_parser("mkdir-fat", help="Create one empty directory under an existing directory of a writable FAT image")
    mkdir_fat.add_argument("image", type=Path)
    mkdir_fat.add_argument("directory_path", help="New image directory path; its parent must already exist")
    mkdir_fat.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    copy_fat = commands.add_parser("copy-fat", help="Copy one regular file or new directory tree into an existing directory of a writable FAT image")
    copy_fat.add_argument("image", type=Path)
    copy_fat.add_argument("source_path", help="Existing image file or directory path to copy")
    copy_fat.add_argument("target_directory", help="Existing image directory receiving a new same-name copy")
    copy_fat.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    delete_fat = commands.add_parser("delete-fat", help="Delete one explicit non-root file or directory tree from a writable FAT image")
    delete_fat.add_argument("image", type=Path)
    delete_fat.add_argument("item_path", help="Existing non-root image file or directory path to delete")
    delete_fat.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

    list_deleted = commands.add_parser("list-deleted-fat", help="List conservative deleted FAT12/FAT16 root-file recovery candidates")
    list_deleted.add_argument("image", type=Path)
    list_deleted.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")
    recover_deleted = commands.add_parser("recover-deleted-fat", help="Recover one conservative FAT deleted-file candidate to a new local file")
    recover_deleted.add_argument("image", type=Path)
    recover_deleted.add_argument("slot", type=int, help="Deleted root-directory slot index reported by list-deleted-fat")
    recover_deleted.add_argument("destination", type=Path, help="New local output file; it must not already exist")
    recover_deleted.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

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

    fat_metadata = commands.add_parser("set-fat-metadata", help="Set standard DOS attributes and/or FAT times on explicit image paths")
    fat_metadata.add_argument("image", type=Path)
    fat_metadata.add_argument("paths", nargs="+", help="One or more explicit FAT image entry paths")
    for name in ("read-only", "hidden", "system", "archive"):
        fat_metadata.add_argument(f"--{name}", action=argparse.BooleanOptionalAction, default=None)
    fat_metadata.add_argument("--created", help="ISO-8601 local creation date and time")
    fat_metadata.add_argument("--modified", help="ISO-8601 local modification date and time")
    fat_metadata.add_argument("--accessed", help="ISO-8601 local access date and time")
    fat_metadata.add_argument("--partition", type=int, help="Explicit MBR/GPT FAT partition table index")

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

    create_hfs = commands.add_parser("create-hfs", help="Create a verified standalone classic HFS image")
    create_hfs.add_argument("image", type=Path)
    create_hfs.add_argument("--size-kib", type=int, default=800, help="Image size in KiB; at least 800 and 512-byte aligned")
    create_hfs.add_argument("--label", default="DISKFORGE", help="Classic HFS volume label (1–27 safe ASCII characters)")
    create_hfs.add_argument("--hformat", help="Optional explicit hformat executable")

    dmf = commands.add_parser("create-dmf", help="Create an 80x2x21 FAT12 DMF-layout image file")
    dmf.add_argument("image", type=Path)
    dmf.add_argument("--label", default="DISKFORGE")

    legacy_floppy = commands.add_parser(
        "create-legacy-floppy", help="Create a verified FAT12 IMG/IMA legacy floppy with explicit geometry",
    )
    legacy_floppy.add_argument("image", type=Path)
    legacy_floppy.add_argument("--profile", choices=[profile.identifier for profile in LEGACY_FLOPPY_PROFILES])
    legacy_floppy.add_argument("--cylinders", type=int)
    legacy_floppy.add_argument("--heads", type=int)
    legacy_floppy.add_argument("--sectors-per-track", type=int)
    legacy_floppy.add_argument("--sector-size", type=int, default=512)
    legacy_floppy.add_argument("--format", choices=[ImageFormat.IMG.value, ImageFormat.IMA.value], default=ImageFormat.IMA.value)
    legacy_floppy.add_argument("--label", default="DISKFORGE")

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
    ntfs_status = commands.add_parser("ntfs-inject-status", help="Show optional controlled NTFS injection capability")
    ntfs_status.add_argument("--ntfscp", help="Optional explicit ntfscp executable")
    ntfs_status.add_argument("--ntfsls", help="Optional explicit ntfsls executable")
    ntfs_status.add_argument("--ntfscat", help="Optional explicit ntfscat executable")
    ext_status = commands.add_parser("ext-inject-status", help="Show optional controlled EXT injection capability")
    ext_status.add_argument("--debugfs", help="Optional explicit debugfs executable")
    ext_status.add_argument("--e2fsck", help="Optional explicit e2fsck executable")
    hfs_status = commands.add_parser("hfs-inject-status", help="Show optional controlled classic HFS injection capability")
    hfs_status.add_argument("--hmount", help="Optional explicit hmount executable")
    hfs_status.add_argument("--hcopy", help="Optional explicit hcopy executable")
    hfs_status.add_argument("--hls", help="Optional explicit hls executable")
    hfs_create_status = commands.add_parser("hfs-create-status", help="Show optional verified classic HFS creation capability")
    hfs_create_status.add_argument("--hformat", help="Optional explicit hformat executable")
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

    export_listing = commands.add_parser("export-listing", help="Export a browsable image directory listing as text or HTML")
    export_listing.add_argument("image", type=Path)
    export_listing.add_argument("output", type=Path)
    export_listing.add_argument("--html", action="store_true")
    export_listing.add_argument("--partition", type=int, help="Explicit MBR/GPT partition table index; FAT may be writable elsewhere, NTFS/EXT/HFS/HFS+ remain read-only")

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
    if writable and info.image_format == ImageFormat.ZIP:
        raise DiskForgeError("ZIP image containers are read-only; extract or open the payload through a read-only workflow.")
    if partition_index is not None:
        return open_partition_filesystem(image, partition_index, writable=writable)
    if info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
        return FatImageFilesystem(image, read_only=not writable)
    if info.filesystem == FileSystemType.ISO9660 or info.image_format == ImageFormat.ISO:
        return IsoImageFilesystem(image)
    if info.filesystem == FileSystemType.CBM_DOS:
        if writable:
            raise DiskForgeError("Canonical D64/D71/D81 CBM DOS images are read-only; modification is unavailable.")
        if info.image_format == ImageFormat.D81:
            return D81ImageFilesystem(image)
        if info.image_format == ImageFormat.D71:
            return D71ImageFilesystem(image)
        return D64ImageFilesystem(image)
    if info.filesystem in {FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS, FileSystemType.HFS_PLUS}:
        return SleuthKitImageFilesystem(image, info.filesystem)
    raise SystemExit("Image filesystem is not browsable. Supported: FAT, ISO, canonical D64/D71/D81 CBM DOS, NTFS, EXT, HFS and HFS+ with optional backend.")


@contextmanager
def _read_only_filesystem(image: Path, *, partition_index: int | None = None,
                          zip_payload: str | None = None):
    """Open a browsable image, materializing safe ZIP/container inputs temporarily."""
    session = materialize_browsable_image(image, converter=QemuImgConverter(), zip_payload=zip_payload)
    filesystem = None
    try:
        filesystem = _filesystem(session.image, partition_index=partition_index)
        yield filesystem
    finally:
        if filesystem is not None:
            filesystem.close()
        session.close()


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
        elif args.command == "zip-info":
            payloads = list_zip_image_payloads(args.image)
            _emit(args, {"source": str(args.image), "payloads": list(payloads), "count": len(payloads)}, "\n".join(payloads))
        elif args.command == "imd-info":
            inspection = inspect_imd(args.image)
            _emit(args, {
                "source": str(inspection.source), "description": inspection.description,
                "bytes": inspection.source_bytes, "tracks": len(inspection.tracks),
                "exportable": inspection.exportable, "export_reason": inspection.export_reason,
                "cylinders": inspection.cylinders, "heads": inspection.heads,
                "sectors_per_track": inspection.sectors_per_track,
                "bytes_per_sector": inspection.bytes_per_sector, "raw_bytes": inspection.raw_bytes,
                "track_records": [{
                    "mode": track.mode, "cylinder": track.cylinder, "head": track.head,
                    "sector_count": len(track.sectors), "optional_maps": track.has_optional_maps,
                    "sector_types": [sector.data_type for sector in track.sectors],
                } for track in inspection.tracks],
            }, inspection.export_reason)
        elif args.command == "convert-imd":
            destination = export_imd_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "td0-info":
            inspection = inspect_td0(args.image)
            _emit(args, {
                "source": str(inspection.source), "version": inspection.version,
                "data_rate_kbps": inspection.data_rate_kbps, "drive_type": inspection.drive_type,
                "sides": inspection.sides, "comment": inspection.comment, "bytes": inspection.source_bytes,
                "tracks": len(inspection.tracks), "exportable": inspection.exportable,
                "export_reason": inspection.export_reason, "cylinders": inspection.cylinders,
                "heads": inspection.heads, "sectors_per_track": inspection.sectors_per_track,
                "bytes_per_sector": inspection.bytes_per_sector, "raw_bytes": inspection.raw_bytes,
                "track_records": [{
                    "cylinder": track.cylinder, "head": track.head, "single_density": track.single_density,
                    "sector_count": len(track.sectors),
                    "sector_flags": [sector.flags for sector in track.sectors],
                    "sector_methods": [sector.method for sector in track.sectors],
                } for track in inspection.tracks],
            }, inspection.export_reason)
        elif args.command == "convert-td0":
            destination = export_td0_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "cpc-dsk-info":
            inspection = inspect_cpc_dsk(args.image)
            _emit(args, {
                "source": str(inspection.source), "kind": inspection.kind.value,
                "creator": inspection.creator, "bytes": inspection.source_bytes,
                "tracks": len(inspection.tracks), "exportable": inspection.exportable,
                "export_reason": inspection.export_reason, "cylinders": inspection.cylinders,
                "sides": inspection.sides, "sectors_per_track": inspection.sectors_per_track,
                "bytes_per_sector": inspection.bytes_per_sector, "raw_bytes": inspection.raw_bytes,
                "track_records": [{
                    "physical_track": track.physical_track, "physical_side": track.physical_side,
                    "header_track": track.header_track, "header_side": track.header_side,
                    "sector_count": track.sector_count,
                    "sector_ids": [sector.r for sector in track.sectors],
                    "status": [[sector.status1, sector.status2] for sector in track.sectors],
                } for track in inspection.tracks],
            }, inspection.export_reason)
        elif args.command == "convert-cpc-dsk":
            destination = export_cpc_dsk_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "d88-info":
            inspection = inspect_d88(args.image)
            _emit(args, {"source": str(inspection.source), "name": inspection.name,
                          "write_protected": inspection.write_protected, "media_type": inspection.media_type,
                          "bytes": inspection.source_bytes, "tracks": len(inspection.tracks),
                          "exportable": inspection.exportable, "export_reason": inspection.export_reason,
                          "cylinders": inspection.cylinders, "sides": inspection.sides,
                          "sectors_per_track": inspection.sectors_per_track,
                          "bytes_per_sector": inspection.bytes_per_sector, "raw_bytes": inspection.raw_bytes}, inspection.export_reason)
        elif args.command == "convert-d88":
            destination = export_d88_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "hfe-info":
            inspection = inspect_hfe(args.image)
            _emit(args, {"source": str(inspection.source), "version": inspection.version,
                          "revision": inspection.revision, "tracks": inspection.tracks,
                          "sides": inspection.sides, "track_encoding": inspection.track_encoding,
                          "bitrate_kbps": inspection.bitrate_kbps, "rpm": inspection.rpm,
                          "interface_mode": inspection.interface_mode,
                          "write_protected": inspection.write_protected,
                          "track_list_offset": inspection.track_list_offset_bytes,
                          "bytes": inspection.source_bytes,
                          "unreferenced_bytes": inspection.unreferenced_bytes,
                          "track_records": [{"index": item.index, "offset": item.offset_bytes,
                                             "declared_bytes": item.declared_bytes,
                                             "stored_bytes": item.stored_bytes,
                                             "sides": item.side_count} for item in inspection.track_records]},
                  "HFE structure inspected without bitstream decoding.")
        elif args.command == "dc42-info":
            inspection = inspect_dc42(args.image)
            _emit(args, {"source": str(inspection.source), "name": inspection.name,
                          "bytes": inspection.source_bytes, "data_bytes": inspection.data_bytes,
                          "tag_bytes": inspection.tag_bytes, "data_checksum": inspection.data_checksum,
                          "tag_checksum": inspection.tag_checksum, "encoding": inspection.encoding,
                          "format_byte": inspection.format_byte},
                  "DC42 data and tag checksums validated without modifying the source.")
        elif args.command == "convert-dc42":
            destination = export_dc42_data_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "twoimg-info":
            inspection = inspect_twoimg(args.image)
            _emit(args, {"source": str(inspection.source), "creator_id": inspection.creator_id,
                          "format": inspection.image_format, "format_name": inspection.format_name,
                          "write_protected": inspection.write_protected,
                          "volume_number": inspection.volume_number, "bytes": inspection.source_bytes,
                          "data_bytes": inspection.data_bytes, "prodos_blocks": inspection.prodos_blocks,
                          "comment": inspection.comment, "comment_bytes": inspection.comment_bytes,
                          "creator_data_bytes": inspection.creator_data_bytes,
                          "exportable": inspection.exportable, "export_reason": inspection.export_reason},
                  inspection.export_reason)
        elif args.command == "convert-twoimg":
            destination = export_twoimg_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "apridisk-info":
            inspection = inspect_apridisk(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "records": len(inspection.sectors), "deleted_records": inspection.deleted_records,
                          "comment": inspection.comment, "creator_data_bytes": inspection.creator_data_bytes,
                          "exportable": inspection.exportable, "export_reason": inspection.export_reason,
                          "cylinders": inspection.cylinders, "heads": inspection.heads,
                          "sectors_per_track": inspection.sectors_per_track,
                          "bytes_per_sector": inspection.bytes_per_sector, "raw_bytes": inspection.raw_bytes,
                          "sector_records": [{"cylinder": item.cylinder, "head": item.head,
                                              "sector": item.sector, "bytes": len(item.data),
                                              "compressed": item.compressed} for item in inspection.sectors]},
                  inspection.export_reason)
        elif args.command == "convert-apridisk":
            destination = export_apridisk_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "copyqm-info":
            inspection = inspect_copyqm(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "comment": inspection.comment, "media_description": inspection.media_description,
                          "volume_label": inspection.volume_label, "sector_size": inspection.sector_size,
                          "sectors_per_track": inspection.sectors_per_track, "heads": inspection.heads,
                          "tracks": inspection.tracks, "total_sectors": inspection.total_sectors,
                          "density": inspection.density, "data_crc": inspection.data_crc,
                          "calculated_crc": inspection.calculated_crc, "raw_bytes": inspection.raw_bytes},
                  f"CopyQM {inspection.tracks}×{inspection.heads}×{inspection.sectors_per_track} validated")
        elif args.command == "convert-copyqm":
            destination = export_copyqm_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "sap-info":
            inspection = inspect_sap(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "disk_type": inspection.disk_type, "tracks_per_side": inspection.tracks_per_side,
                          "heads": inspection.heads, "sector_records": len(inspection.sectors),
                          "crc_error_count": inspection.crc_error_count,
                          "protected_sector_count": inspection.protected_sector_count,
                          "exportable": inspection.exportable, "export_reason": inspection.export_reason,
                          "raw_bytes": inspection.raw_bytes,
                          "sectors": [{"cylinder": item.cylinder, "head": item.head,
                                       "sector": item.sector, "bytes": item.sector_size,
                                       "mode": item.mode, "protection": item.protection,
                                       "crc_valid": item.crc_valid} for item in inspection.sectors]},
                  inspection.export_reason)
        elif args.command == "convert-sap":
            destination = export_sap_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "msa-info":
            inspection = inspect_msa(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "sectors_per_track": inspection.sectors_per_track, "heads": inspection.heads,
                          "start_track": inspection.start_track, "end_track": inspection.end_track,
                          "track_count": len(inspection.tracks), "compressed_track_count": inspection.compressed_track_count,
                          "raw_bytes": inspection.raw_bytes,
                          "tracks": [{"cylinder": item.cylinder, "head": item.head,
                                      "stored_bytes": item.stored_bytes, "compressed": item.compressed,
                                      "decoded_bytes": len(item.data)} for item in inspection.tracks]},
                  f"MSA {inspection.start_track}-{inspection.end_track}, {inspection.heads} side(s), validated")
        elif args.command == "convert-msa":
            destination = export_msa_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "psi-info":
            inspection = inspect_psi(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "default_format": inspection.default_format, "comment_count": inspection.comment_count,
                          "metadata_chunk_count": inspection.metadata_chunk_count,
                          "sector_count": len(inspection.sectors),
                          "compressed_sector_count": inspection.compressed_sector_count,
                          "exportable": inspection.exportable, "export_reason": inspection.export_reason,
                          "raw_bytes": inspection.raw_bytes,
                          "sectors": [{"cylinder": item.cylinder, "head": item.head,
                                       "sector": item.sector, "bytes": item.data_bytes,
                                       "compressed": item.compressed} for item in inspection.sectors]},
                  inspection.export_reason)
        elif args.command == "convert-psi":
            destination = export_psi_to_raw(args.source, args.destination)
            _emit(args, {"source": str(args.source), "destination": str(destination)}, str(destination))
        elif args.command == "pri-info":
            inspection = inspect_pri(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "comment_count": inspection.comment_count, "unknown_chunk_count": inspection.unknown_chunk_count,
                          "track_count": len(inspection.tracks), "complete_data_track_count": inspection.complete_data_track_count,
                          "total_bits": inspection.total_bits, "clock_min_hz": inspection.clock_min_hz,
                          "clock_max_hz": inspection.clock_max_hz, "fuzz_event_count": inspection.fuzz_event_count,
                          "clock_event_count": inspection.clock_event_count, "weak_event_count": inspection.weak_event_count,
                          "tracks": [{"cylinder": item.cylinder, "head": item.head,
                                       "bits": item.bit_count, "clock_hz": item.clock_hz,
                                       "data_present": item.data_present, "fuzz_events": item.fuzz_events,
                                       "clock_events": item.clock_events, "weak_events": item.weak_events}
                                     for item in inspection.tracks]},
                  f"PRI structure validated: {len(inspection.tracks)} track(s), {inspection.total_bits} bit(s)")
        elif args.command == "jv3-info":
            inspection = inspect_jv3(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "write_protected": inspection.write_protected, "header_blocks": inspection.header_blocks,
                          "free_slots": inspection.free_slots, "exportable": inspection.exportable,
                          "export_reason": inspection.export_reason, "cylinders": inspection.cylinders,
                          "heads": inspection.heads, "sectors_per_track": inspection.sectors_per_track,
                          "raw_bytes": inspection.raw_bytes,
                          "sectors": [{"block": item.block, "slot": item.slot, "cylinder": item.cylinder,
                                       "head": item.head, "sector": item.sector, "flags": f"0x{item.flags:02X}",
                                       "data_bytes": len(item.data)} for item in inspection.sectors]},
                  f"JV3 structure validated: {len(inspection.sectors)} in-use sector(s), exportable={inspection.exportable}")
        elif args.command == "convert-jv3":
            destination = export_jv3_to_raw(args.image, args.destination)
            _emit(args, {"source": str(args.image), "destination": str(destination)},
                  f"Exported JV3 RAW image to {destination}")
        elif args.command == "dmk-info":
            inspection = inspect_dmk(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "tracks": inspection.tracks, "sides": inspection.sides,
                          "track_length": inspection.track_length, "write_protected": inspection.write_protected,
                          "single_density_size": inspection.single_density_size,
                          "ignore_density": inspection.ignore_density, "total_idams": inspection.total_idams,
                          "double_density_idams": inspection.double_density_idams,
                          "track_records": [{"logical_index": item.index, "cylinder": item.cylinder,
                                             "head": item.head, "offset": item.offset,
                                             "idam_count": item.idam_count,
                                             "double_density_idam_count": item.double_density_idam_count}
                                            for item in inspection.track_records]},
                  f"DMK native structure validated: {len(inspection.track_records)} track image(s), {inspection.total_idams} IDAM(s)")
        elif args.command == "udi-info":
            inspection = inspect_udi(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "cylinders": inspection.cylinders, "sides": inspection.sides,
                          "extended_header_bytes": inspection.extended_header_bytes,
                          "total_track_bytes": inspection.total_track_bytes,
                          "clock_mark_count": inspection.clock_mark_count,
                          "crc32": f"0x{inspection.crc32:08X}",
                          "tracks": [{"index": item.index, "cylinder": item.cylinder, "head": item.head,
                                      "data_bytes": item.data_bytes, "clock_mark_count": item.clock_mark_count}
                                     for item in inspection.tracks]},
                  f"UDI v1.0 structure validated: {len(inspection.tracks)} MFM track(s), {inspection.total_track_bytes} track byte(s)")
        elif args.command == "scp-info":
            inspection = inspect_scp(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "version": f"0x{inspection.version:02X}", "disk_type": f"0x{inspection.disk_type:02X}",
                          "start_track": inspection.start_track, "end_track": inspection.end_track,
                          "revolutions_per_track": inspection.revolutions_per_track, "heads": inspection.heads,
                          "resolution_ns": inspection.resolution_ns, "checksum": f"0x{inspection.checksum:08X}",
                          "total_flux_bytes": inspection.total_flux_bytes,
                          "tracks": [{"logical_index": item.logical_index, "cylinder": item.cylinder,
                                      "head": item.head, "offset": item.offset, "flux_bytes": item.flux_bytes,
                                      "revolutions": [{"duration_ticks": revolution.duration_ticks,
                                                        "flux_words": revolution.flux_words,
                                                        "flux_offset": revolution.flux_offset}
                                                       for revolution in item.revolutions]}
                                     for item in inspection.tracks]},
                  f"SCP standard structure validated: {len(inspection.tracks)} track(s), {inspection.total_flux_bytes} flux byte(s)")
        elif args.command == "mfm-info":
            inspection = inspect_mfm(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "tracks": inspection.tracks, "sides": inspection.sides,
                          "rpm": inspection.rpm, "bitrate_kbps": inspection.bitrate_kbps,
                          "interface_type": inspection.interface_type,
                          "track_table_offset": inspection.track_table_offset_bytes,
                          "padding_bytes": inspection.padding_bytes,
                          "track_records": [{"cylinder": item.cylinder, "side": item.side,
                                             "offset": item.offset_bytes, "bytes": item.bytes_stored}
                                            for item in inspection.track_records]},
                  f"HxC MFM structure validated: {len(inspection.track_records)} MFM track(s)")
        elif args.command == "pfi-info":
            inspection = inspect_pfi(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "chunks": inspection.chunks, "comments": inspection.comments,
                          "unknown_chunks": inspection.unknown_chunks,
                          "tracks": [{"cylinder": item.cylinder, "head": item.head,
                                      "clock_rate": item.clock_rate, "index_count": item.index_count,
                                      "data_chunks": item.data_chunks, "data_bytes": item.data_bytes,
                                      "pulse_count": item.pulse_count}
                                     for item in inspection.tracks]},
                  f"PFI v0 structure validated: {len(inspection.tracks)} flux track(s)")
        elif args.command == "woz-info":
            inspection = inspect_woz(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "crc_checked": inspection.crc_checked, "info_version": inspection.info_version,
                          "disk_type": inspection.disk_type, "disk_sides": inspection.disk_sides,
                          "write_protected": inspection.write_protected, "synchronized": inspection.synchronized,
                          "cleaned": inspection.cleaned, "creator": inspection.creator,
                          "optimal_bit_timing": inspection.optimal_bit_timing, "chunks": inspection.chunks,
                          "metadata_entries": inspection.metadata_entries,
                          "unknown_chunks": inspection.unknown_chunks,
                          "bit_tracks": [{"index": item.index, "starting_block": item.starting_block,
                                          "block_count": item.block_count, "bit_count": item.encoded_count}
                                         for item in inspection.bit_tracks],
                          "flux_tracks": [{"index": item.index, "starting_block": item.starting_block,
                                           "block_count": item.block_count, "byte_count": item.encoded_count}
                                          for item in inspection.flux_tracks]},
                  f"WOZ2 structure validated: {len(inspection.bit_tracks)} bit track(s), {len(inspection.flux_tracks)} flux track(s)")
        elif args.command == "a2r-info":
            inspection = inspect_a2r(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "chunks": inspection.chunks, "drive_type": inspection.drive_type,
                          "creator": inspection.creator, "write_protected": inspection.write_protected,
                          "synchronized": inspection.synchronized, "hard_sector_count": inspection.hard_sector_count,
                          "raw_capture_chunks": inspection.raw_capture_chunks,
                          "solved_flux_chunks": inspection.solved_flux_chunks,
                          "metadata_entries": inspection.metadata_entries,
                          "unknown_chunks": inspection.unknown_chunks,
                          "captures": [{"location": item.location, "type": item.capture_type,
                                        "index_signals": item.index_signals, "data_bytes": item.data_bytes}
                                       for item in inspection.captures],
                          "solved_tracks": [{"location": item.location, "index_signals": item.index_signals,
                                             "data_bytes": item.data_bytes,
                                             "mirror_outward": item.mirror_outward,
                                             "mirror_inward": item.mirror_inward}
                                            for item in inspection.solved_tracks]},
                  f"A2R3 structure validated: {len(inspection.captures)} capture(s), {len(inspection.solved_tracks)} solved flux track(s)")
        elif args.command == "d64-info":
            inspection = inspect_d64(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.size,
                          "disk_name": inspection.disk_name, "disk_id": inspection.disk_id,
                          "dos_type": inspection.dos_type, "directory_sectors": inspection.directory_sectors,
                          "free_blocks": inspection.free_blocks,
                          "files": [{"index": item.index, "path": item.path, "name": item.name,
                                     "type": item.file_type, "locked": item.locked, "closed": item.closed,
                                     "blocks": item.blocks, "bytes": item.size,
                                     "start_track": item.start_track, "start_sector": item.start_sector}
                                    for item in inspection.files]},
                  f"D64 structure validated: {len(inspection.files)} ordinary CBM DOS file(s)")
        elif args.command == "d71-info":
            inspection = inspect_d71(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.size,
                          "disk_name": inspection.disk_name, "disk_id": inspection.disk_id,
                          "dos_type": inspection.dos_type, "directory_sectors": inspection.directory_sectors,
                          "free_blocks": inspection.free_blocks,
                          "files": [{"index": item.index, "path": item.path, "name": item.name,
                                     "type": item.file_type, "locked": item.locked, "closed": item.closed,
                                     "blocks": item.blocks, "bytes": item.size,
                                     "start_track": item.start_track, "start_sector": item.start_sector}
                                    for item in inspection.files]},
                  f"D71 structure validated: {len(inspection.files)} ordinary double-sided CBM DOS file(s)")
        elif args.command == "d81-info":
            inspection = inspect_d81(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.size,
                          "disk_name": inspection.disk_name, "disk_id": inspection.disk_id,
                          "dos_type": inspection.dos_type, "directory_sectors": inspection.directory_sectors,
                          "free_blocks": inspection.free_blocks,
                          "files": [{"index": item.index, "path": item.path, "name": item.name,
                                     "type": item.file_type, "locked": item.locked, "closed": item.closed,
                                     "blocks": item.blocks, "bytes": item.size,
                                     "start_track": item.start_track, "start_sector": item.start_sector}
                                    for item in inspection.files]},
                  f"D81 structure validated: {len(inspection.files)} ordinary double-sided CBM DOS file(s)")
        elif args.command == "g64-info":
            inspection = inspect_g64(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "track_entries": inspection.track_entries,
                          "stored_track_bytes": inspection.stored_track_bytes,
                          "constant_speed_tracks": inspection.constant_speed_tracks,
                          "mapped_speed_tracks": inspection.mapped_speed_tracks,
                          "tracks": [{"entry_index": item.entry_index, "actual_bytes": item.actual_bytes,
                                      "speed_kind": item.speed_kind, "speed_zone": item.speed_zone}
                                     for item in inspection.tracks]},
                  f"G64 v0 structure validated: {len(inspection.tracks)} GCR track(s)")
        elif args.command == "g71-info":
            inspection = inspect_g71(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "track_entries": inspection.track_entries,
                          "stored_track_bytes": inspection.stored_track_bytes,
                          "constant_speed_tracks": inspection.constant_speed_tracks,
                          "mapped_speed_tracks": inspection.mapped_speed_tracks,
                          "tracks": [{"entry_index": item.entry_index, "actual_bytes": item.actual_bytes,
                                      "speed_kind": item.speed_kind, "speed_zone": item.speed_zone}
                                     for item in inspection.tracks]},
                  f"G71 v0 structure validated: {len(inspection.tracks)} opaque double-sided GCR track(s)")
        elif args.command == "p64-info":
            inspection = inspect_p64(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "flags": inspection.flags, "chunks": inspection.chunks,
                          "tracks": [{"half_track_index": item.half_track_index, "side": item.side,
                                      "pulses": item.pulses, "encoded_bytes": item.encoded_bytes}
                                     for item in inspection.tracks]},
                  f"P64 v0 structure validated: {len(inspection.tracks)} opaque NRZI half-track(s)")
        elif args.command == "fdi-info":
            inspection = inspect_fdi(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "header_bytes": inspection.header_bytes, "cylinders": inspection.cylinders,
                          "heads": inspection.heads, "media_type": inspection.media_type,
                          "rotation_rpm": inspection.rotation_rpm, "write_protected": inspection.write_protected,
                          "index_synchronized": inspection.index_synchronized, "disk_tpi": inspection.disk_tpi,
                          "head_tpi": inspection.head_tpi, "creator": inspection.creator, "comment": inspection.comment,
                          "blank_track_count": inspection.blank_track_count,
                          "declared_track_bytes": inspection.declared_track_bytes,
                          "tracks": [{"logical_index": item.logical_index, "cylinder": item.cylinder,
                                       "head": item.head, "type_code": f"0x{item.type_code:02X}",
                                       "category": item.category, "offset": item.offset_bytes,
                                       "declared_bytes": item.declared_bytes} for item in inspection.tracks]},
                  f"FDI v2.0 structure validated: {len(inspection.tracks)} track(s), {inspection.declared_track_bytes} declared byte(s)")
        elif args.command == "86f-info":
            inspection = inspect_86f(args.image)
            _emit(args, {"source": str(inspection.source), "bytes": inspection.source_bytes,
                          "disk_flags": f"0x{inspection.disk_flags:04X}", "sides": inspection.sides,
                          "has_surface_description": inspection.has_surface_description,
                          "table_entries": inspection.table_entries, "track_count": len(inspection.tracks),
                          "missing_track_count": inspection.missing_track_count, "total_bitcells": inspection.total_bitcells,
                          "total_encoded_bytes": inspection.total_encoded_bytes,
                          "tracks": [{"logical_index": item.logical_index, "cylinder": item.cylinder,
                                       "head": item.head, "offset": item.offset, "bitcells": item.bitcells,
                                       "index_hole": item.index_hole, "encoding": item.encoding,
                                       "bit_rate_kbps": item.bit_rate_kbps, "rpm": item.rpm,
                                       "data_bytes": item.data_bytes, "has_surface_description": item.has_surface_description}
                                     for item in inspection.tracks]},
                  f"86F v2.12 structure validated: {len(inspection.tracks)} track(s), {inspection.total_bitcells} bitcell(s)")
        elif args.command == "inventory-images":
            options = ImageInventoryOptions(
                recursive=args.recursive, suffixes=tuple(args.suffix),
                formats=tuple(ImageFormat(value) for value in args.image_format),
                filesystems=tuple(FileSystemType(value) for value in args.filesystem),
                min_bytes=args.min_bytes, max_bytes=args.max_bytes, sha256_prefix=args.sha256_prefix,
                include_sha256=args.include_sha256, include_partitions=args.include_partitions,
            )
            report = inventory_images(args.root, options, converter=QemuImgConverter())
            destination = export_image_inventory(report, args.destination, args.report_format)
            _emit(args, {"destination": str(destination), **report.as_mapping()}, str(destination))
        elif args.command == "list":
            with _read_only_filesystem(
                args.image, partition_index=args.partition, zip_payload=args.zip_payload,
            ) as fs:
                entries = fs.list_entries(args.path)
                _emit(args, [_entry_json(entry) for entry in entries], "\n".join(
                    f"{'d' if entry.is_dir else '-'} {entry.size:>12} {entry.attributes:>10} {entry.path}" for entry in entries
                ))
        elif args.command == "extract":
            with _read_only_filesystem(
                args.image, partition_index=args.partition, zip_payload=args.zip_payload,
            ) as fs:
                outputs = fs.extract(args.paths, args.destination, progress, policy=_policy(args))
                print() if outputs and not args.json else None
                _emit(args, {"outputs": [str(output) for output in outputs]}, "\n".join(str(output) for output in outputs))
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
        elif args.command == "inject-ntfs":
            result = NtfsFileInjector(args.ntfscp, args.ntfsls, args.ntfscat).inject(
                args.source, args.destination, args.sources, progress=progress,
            )
            _emit(args, {
                "source": str(result.source), "destination": str(result.destination),
                "source_sha256": result.source_sha256, "target_paths": list(result.target_paths),
                "payload_sha256": list(result.payload_sha256),
            }, str(result.destination))
        elif args.command == "inject-ext":
            result = ExtFileInjector(args.debugfs, args.e2fsck).inject(args.source, args.destination, args.sources, progress=progress)
            _emit(args, {
                "source": str(result.source), "destination": str(result.destination),
                "source_sha256": result.source_sha256, "target_paths": list(result.target_paths),
                "payload_sha256": list(result.payload_sha256),
            }, str(result.destination))
        elif args.command == "inject-hfs":
            result = HfsFileInjector(args.hmount, args.hcopy, args.hls).inject(
                args.source, args.destination, args.sources, progress=progress,
            )
            _emit(args, {
                "source": str(result.source), "destination": str(result.destination),
                "source_sha256": result.source_sha256, "target_paths": list(result.target_paths),
                "payload_sha256": list(result.payload_sha256),
            }, str(result.destination))
        elif args.command == "move-fat":
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images support file movement.")
                destination = fs.move(args.source_path, args.target_directory)
                _emit(args, {"source": args.source_path, "destination": destination}, destination)
            finally:
                fs.close()
        elif args.command == "mkdir-fat":
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images support directory creation.")
                directory = fs.create_directory(args.directory_path)
                _emit(args, {"directory": directory}, directory)
            finally:
                fs.close()
        elif args.command == "copy-fat":
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images support file copying.")
                destination = fs.copy(args.source_path, args.target_directory)
                _emit(args, {"source": args.source_path, "destination": destination}, destination)
            finally:
                fs.close()
        elif args.command == "delete-fat":
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("Only FAT images support entry deletion.")
                fs.delete([args.item_path])
                _emit(args, {"path": args.item_path}, args.item_path)
            finally:
                fs.close()
        elif args.command == "list-deleted-fat":
            fs = _filesystem(args.image, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise DiskForgeError("Deleted-file candidates are available only for FAT images.")
                candidates = fs.deleted_root_file_candidates()
                _emit(args, {"candidates": [candidate.__dict__ for candidate in candidates]}, "\n".join(
                    f"{candidate.slot_index}\t{candidate.display_name}\t{candidate.bytes}\t"
                    f"{'recoverable' if candidate.recoverable else 'unavailable'}\t{candidate.reason}"
                    for candidate in candidates
                ))
            finally:
                fs.close()
        elif args.command == "recover-deleted-fat":
            fs = _filesystem(args.image, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise DiskForgeError("Deleted-file recovery is available only for FAT images.")
                destination = fs.recover_deleted_root_file(args.slot, args.destination)
                _emit(args, {"image": str(args.image), "slot": args.slot, "destination": str(destination)}, str(destination))
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
        elif args.command == "set-fat-metadata":
            update = metadata_update_from_values(
                args.paths,
                read_only=args.read_only,
                hidden=args.hidden,
                system=args.system,
                archive=args.archive,
                created=_parse_local_datetime(args.created, "--created"),
                modified=_parse_local_datetime(args.modified, "--modified"),
                accessed=_parse_local_datetime(args.accessed, "--accessed"),
            )
            fs = _filesystem(args.image, writable=True, partition_index=args.partition)
            try:
                if not isinstance(fs, FatImageFilesystem):
                    raise SystemExit("FAT metadata updates are available only for writable FAT images.")
                results = apply_fat_metadata(fs, update)
                payload = {
                    "image": str(args.image),
                    "updated": [
                        {"path": result.path, "attributes": result.attributes, "fields": list(result.updated_fields)}
                        for result in results
                    ],
                }
                _emit(args, payload, "\n".join(result.path for result in results))
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
        elif args.command == "create-hfs":
            result = HfsImageCreator(args.hformat).create(
                args.image, args.size_kib * 1024, args.label, progress=progress,
            )
            _emit(args, {
                "path": str(result.destination), "label": result.label,
                "bytes": result.bytes_created, "sha256": result.sha256,
            }, str(result.destination))
        elif args.command == "create-dmf":
            created = create_dmf_image(args.image, args.label)
            _emit(args, {"path": str(created), "layout": "80x2x21", "bytes": created.stat().st_size}, str(created))
        elif args.command == "create-legacy-floppy":
            output_format = ImageFormat(args.format)
            if args.profile:
                if any(value is not None for value in (args.cylinders, args.heads, args.sectors_per_track)):
                    raise DiskForgeError("Choose either a legacy floppy profile or custom geometry, not both.")
                created = create_legacy_fat_floppy_profile(args.image, args.profile, image_format=output_format, label=args.label)
                geometry = next(profile.geometry for profile in LEGACY_FLOPPY_PROFILES if profile.identifier == args.profile)
                profile_id = args.profile
            else:
                values = (args.cylinders, args.heads, args.sectors_per_track)
                if any(value is None for value in values):
                    raise DiskForgeError("Custom legacy floppy creation requires --cylinders, --heads, and --sectors-per-track.")
                geometry = LegacyFloppyGeometry(args.cylinders, args.heads, args.sectors_per_track, args.sector_size)
                created = create_legacy_fat_floppy(args.image, geometry, image_format=output_format, label=args.label)
                profile_id = None
            _emit(args, {
                "path": str(created), "format": output_format.value, "profile": profile_id,
                "bytes": created.stat().st_size, "kib": created.stat().st_size // 1024,
                "geometry": {"cylinders": geometry.cylinders, "heads": geometry.heads,
                             "sectors_per_track": geometry.sectors_per_track, "sector_size": geometry.sector_size},
            }, str(created))
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
            payload = {"catalog_lba": catalog.catalog_lba, "has_sections": catalog.has_sections, "images": [
                {"index": image.index, "platform_id": image.platform_id, "bootable": image.bootable, "media_type": image.media_type,
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
        elif args.command == "ntfs-inject-status":
            _emit(args, NtfsFileInjector(args.ntfscp, args.ntfsls, args.ntfscat).capability_report().as_mapping())
        elif args.command == "ext-inject-status":
            _emit(args, ExtFileInjector(args.debugfs, args.e2fsck).capability_report().as_mapping())
        elif args.command == "hfs-inject-status":
            _emit(args, HfsFileInjector(args.hmount, args.hcopy, args.hls).capability_report().as_mapping())
        elif args.command == "hfs-create-status":
            _emit(args, HfsImageCreator(args.hformat).capability_report().as_mapping())
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
            with _read_only_filesystem(args.image, partition_index=args.partition) as filesystem:
                output = export_directory_listing(filesystem, args.image, args.output, html=args.html)
                _emit(args, {"path": str(output), "format": "html" if args.html else "text"}, str(output))
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
