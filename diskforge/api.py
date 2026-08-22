"""Stable, typed public API for embedding DiskForge image workflows.

The API intentionally exposes only file-image operations. Physical device writes
remain interactive desktop workflows and are not available for unattended hosts.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence

from .core.browse_session import materialize_browsable_image
from .core.compare import ComparisonResult, compare_streams
from .core.cpc_dsk import CpcDskInspection, export_cpc_dsk_to_raw, inspect_cpc_dsk
from .core.apridisk import ApriDiskInspection, export_apridisk_to_raw, inspect_apridisk
from .core.copyqm import CopyQmInspection, export_copyqm_to_raw, inspect_copyqm
from .core.sap import SapInspection, export_sap_to_raw, inspect_sap
from .core.msa import MsaInspection, export_msa_to_raw, inspect_msa
from .core.psi import PsiInspection, export_psi_to_raw, inspect_psi
from .core.pri import PriInspection, inspect_pri
from .core.eightysixf import EightySixFInspection, inspect_86f
from .core.fdi import FdiInspection, inspect_fdi
from .core.jv3 import Jv3Inspection, export_jv3_to_raw, inspect_jv3
from .core.dmk import DmkInspection, inspect_dmk
from .core.udi import UdiInspection, inspect_udi
from .core.scp import ScpInspection, inspect_scp
from .core.mfm import MfmInspection, inspect_mfm
from .core.pfi import PfiInspection, inspect_pfi
from .core.woz import WozInspection, inspect_woz
from .core.a2r import A2rInspection, inspect_a2r
from .core.d64 import D64Inspection, inspect_d64
from .core.d71 import D71Inspection, inspect_d71
from .core.d81 import D81Inspection, inspect_d81
from .core.g64 import G64Inspection, inspect_g64
from .core.g71 import G71Inspection, inspect_g71
from .core.p64 import P64Inspection, inspect_p64
from .core.d88 import D88Inspection, export_d88_to_raw, inspect_d88
from .core.dc42 import Dc42Inspection, export_dc42_data_to_raw, inspect_dc42
from .core.hfe import HfeInspection, inspect_hfe
from .core.fat_metadata import (FatMetadataResult, apply_fat_metadata,
                                metadata_update_from_values)
from .core.fat_recovery import DeletedFatFileCandidate
from .core.imd import ImdInspection, export_imd_to_raw, inspect_imd
from .core.inventory import (ImageInventory, ImageInventoryOptions, ReportFormat,
                             export_image_inventory, inventory_images)
from .core.td0 import Td0Inspection, export_td0_to_raw, inspect_td0
from .core.twoimg import TwoImgInspection, export_twoimg_to_raw, inspect_twoimg
from .core.filesystems import (D64ImageFilesystem, D71ImageFilesystem, D81ImageFilesystem, FatImageFilesystem, ImageFilesystem, IsoImageFilesystem,
                               create_fat_image, replace_iso_file_safely)
from .core.formats import Converter, convert_image, inspect_image, list_zip_image_payloads
from .core.models import (DiskPartition, ExtractionPolicy, FileSystemType, ImageFormat, ImageInfo,
                          ProgressCallback)
from .core.mounts import ImageMountCapability, ImageMountManager, ImageMountSession
from .core.partition_filesystems import open_partition_filesystem
from .core.partitions import list_partitions
from .core.readonly_fs import SleuthKitImageFilesystem
from .core.storage import CancellationToken, DiskForgeError, sha256_file

API_VERSION = "1.1"


@dataclass(frozen=True)
class ApiResult:
    """A small structured outcome suitable for logging across host applications."""

    operation: str
    source: Path | None
    destination: Path | None = None
    detail: str = ""


class DiskForgeClient:
    """A dependency-injectable facade for safe file-image operations."""

    def __init__(self, converter: Converter | None = None) -> None:
        self.converter = converter

    def inspect(self, image: Path | str) -> ImageInfo:
        return inspect_image(image, self.converter)

    def list_zip_image_payloads(self, image: Path | str) -> tuple[str, ...]:
        """List validated root-level browsable image entries in a regular ZIP without extracting one."""
        return list_zip_image_payloads(image)

    def sha256(self, image: Path | str) -> str:
        return sha256_file(image)

    def compare(self, source: Path | str, destination: Path | str, *,
                ignore_trailing_zero_sectors: bool = False,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> ComparisonResult:
        return compare_streams(
            source, destination, ignore_trailing_zero_sectors=ignore_trailing_zero_sectors,
            progress=progress, token=token,
        )

    def create_fat(self, destination: Path | str, *, size_bytes: int,
                   filesystem: FileSystemType, label: str = "DISKFORGE") -> ApiResult:
        target = create_fat_image(destination, size_bytes, filesystem, label)
        return ApiResult("create_fat", None, target, f"Created {filesystem.value} image")

    def convert(self, source: Path | str, destination: Path | str, *,
                image_format: ImageFormat, overwrite: bool = False,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> ApiResult:
        info = convert_image(source, destination, image_format, self.converter, progress, token, overwrite)
        return ApiResult("convert", Path(source), info.path, info.image_format.value)

    def inventory_images(self, root: Path | str, options: ImageInventoryOptions | None = None,
                         *, token: CancellationToken | None = None) -> ImageInventory:
        """Read only local image metadata and optional hashes into a filtered inventory."""
        return inventory_images(root, options, converter=self.converter, token=token)

    def export_image_inventory(self, inventory: ImageInventory, destination: Path | str,
                               report_format: ReportFormat, *,
                               token: CancellationToken | None = None) -> ApiResult:
        """Write a new JSON, CSV, or HTML inventory report without overwrite."""
        output = export_image_inventory(inventory, destination, report_format, token)
        return ApiResult("export_image_inventory", inventory.root, output, report_format)

    def partitions(self, image: Path | str) -> list[DiskPartition]:
        """Return validated MBR/GPT entries without selecting or mutating a partition."""
        return list_partitions(image)

    def inspect_imd(self, source: Path | str, *, token: CancellationToken | None = None) -> ImdInspection:
        """Inspect IMD track records without mutating or flattening the source."""
        return inspect_imd(source, token)

    def export_imd_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven normal-data rectangular IMD layout to a new RAW file."""
        output = export_imd_to_raw(source, destination, token)
        return ApiResult("export_imd_to_raw", Path(source), output, "Strict IMD-to-RAW export")

    def inspect_td0(self, source: Path | str, *, token: CancellationToken | None = None) -> Td0Inspection:
        """Inspect an ordinary TD0 sector container without mutating or flattening the source."""
        return inspect_td0(source, token)

    def export_td0_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven unflagged ordinary TD0 rectangular layout to a new RAW file."""
        output = export_td0_to_raw(source, destination, token)
        return ApiResult("export_td0_to_raw", Path(source), output, "Strict TD0-to-RAW export")

    def inspect_cpc_dsk(self, source: Path | str, *, token: CancellationToken | None = None) -> CpcDskInspection:
        """Inspect a signed CPC standard/extended DSK container without mutation."""
        return inspect_cpc_dsk(source, token)

    def export_cpc_dsk_to_raw(self, source: Path | str, destination: Path | str, *,
                              token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven normal rectangular CPC DSK layout to a new RAW file."""
        output = export_cpc_dsk_to_raw(source, destination, token)
        return ApiResult("export_cpc_dsk_to_raw", Path(source), output, "Strict CPC DSK-to-RAW export")

    def inspect_d88(self, source: Path | str, *, token: CancellationToken | None = None) -> D88Inspection:
        """Inspect one restricted D88 sector container without mutation."""
        return inspect_d88(source, token)

    def export_d88_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven normal rectangular D88 layout to a new RAW file."""
        output = export_d88_to_raw(source, destination, token)
        return ApiResult("export_d88_to_raw", Path(source), output, "Strict D88-to-RAW export")

    def inspect_hfe(self, source: Path | str, *, token: CancellationToken | None = None) -> HfeInspection:
        """Inspect an HFE bitstream container without decoding or mutation."""
        return inspect_hfe(source, token)

    def inspect_dc42(self, source: Path | str, *, token: CancellationToken | None = None) -> Dc42Inspection:
        """Validate a DC42 data and optional tag fork without mutating either."""
        return inspect_dc42(source, token)

    def export_dc42_data_to_raw(self, source: Path | str, destination: Path | str, *,
                                token: CancellationToken | None = None) -> ApiResult:
        """Export only a fully checksum-validated DC42 data fork to a new RAW file."""
        output = export_dc42_data_to_raw(source, destination, token)
        return ApiResult("export_dc42_data_to_raw", Path(source), output, "Verified DC42 data-fork RAW export")

    def inspect_apridisk(self, source: Path | str, *, token: CancellationToken | None = None) -> ApriDiskInspection:
        """Inspect APRIDISK sector records without mutation or sector flattening."""
        return inspect_apridisk(source, token)

    def export_apridisk_to_raw(self, source: Path | str, destination: Path | str, *,
                               token: CancellationToken | None = None) -> ApiResult:
        """Export only a proven normal rectangular APRIDISK sector layout to a new RAW file."""
        output = export_apridisk_to_raw(source, destination, token)
        return ApiResult("export_apridisk_to_raw", Path(source), output, "Strict APRIDISK-to-RAW export")

    def inspect_copyqm(self, source: Path | str, *, token: CancellationToken | None = None) -> CopyQmInspection:
        """Inspect a CopyQM container only when its fixed geometry and decoded data CRC validate."""
        return inspect_copyqm(source, token)

    def export_copyqm_to_raw(self, source: Path | str, destination: Path | str, *,
                             token: CancellationToken | None = None) -> ApiResult:
        """Export a checksum-verified CopyQM image to a separately created RAW output."""
        output = export_copyqm_to_raw(source, destination, token)
        return ApiResult("export_copyqm_to_raw", Path(source), output, "Checksum-verified CopyQM RAW export")

    def inspect_sap(self, source: Path | str, *, token: CancellationToken | None = None) -> SapInspection:
        """Inspect all SAP sectors, protection states, and Pukall CRCs without mutation."""
        return inspect_sap(source, token)

    def export_sap_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a fully regular, unprotected, CRC-valid SAP layout to new RAW output."""
        output = export_sap_to_raw(source, destination, token)
        return ApiResult("export_sap_to_raw", Path(source), output, "Strict CRC-validated SAP RAW export")

    def inspect_msa(self, source: Path | str, *, token: CancellationToken | None = None) -> MsaInspection:
        """Inspect and fully decode an MSA track stream without source mutation."""
        return inspect_msa(source, token)

    def export_msa_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a structurally complete and fully decoded MSA stream to a new RAW file."""
        output = export_msa_to_raw(source, destination, token)
        return ApiResult("export_msa_to_raw", Path(source), output, "Strict MSA track-validated RAW export")

    def inspect_psi(self, source: Path | str, *, token: CancellationToken | None = None) -> PsiInspection:
        """Inspect a fully checksummed PSI sector chunk stream without mutation."""
        return inspect_psi(source, token)

    def export_psi_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> ApiResult:
        """Export only a complete normal PSI sector layout to a separate RAW file."""
        output = export_psi_to_raw(source, destination, token)
        return ApiResult("export_psi_to_raw", Path(source), output, "Strict PSI block-validated RAW export")

    def inspect_pri(self, source: Path | str, *, token: CancellationToken | None = None) -> PriInspection:
        """Inspect a CRC-validated PRI bitstream container without decoding or mutating it."""
        return inspect_pri(source, token)

    def inspect_86f(self, source: Path | str, *, token: CancellationToken | None = None) -> EightySixFInspection:
        """Inspect a restricted 86F v2.12 bitstream layout without decoding or mutation."""
        return inspect_86f(source, token)

    def inspect_fdi(self, source: Path | str, *, token: CancellationToken | None = None) -> FdiInspection:
        """Inspect an FDI v2.0 multi-level container without decoding or mutation."""
        return inspect_fdi(source, token)

    def inspect_dmk(self, source: Path | str, *, token: CancellationToken | None = None) -> DmkInspection:
        """Inspect a native DMK bitstream layout without decoding, flattening, or mutation."""
        return inspect_dmk(source, token)

    def inspect_udi(self, source: Path | str, *, token: CancellationToken | None = None) -> UdiInspection:
        """Inspect a CRC-validated UDI v1.0 bitstream container without decoding or mutation."""
        return inspect_udi(source, token)

    def inspect_scp(self, source: Path | str, *, token: CancellationToken | None = None) -> ScpInspection:
        """Inspect a standard SCP floppy flux container without decoding or mutation."""
        return inspect_scp(source, token)

    def inspect_mfm(self, source: Path | str, *, token: CancellationToken | None = None) -> MfmInspection:
        """Inspect a strict HxC MFM bitstream container without decoding or mutation."""
        return inspect_mfm(source, token)

    def inspect_pfi(self, source: Path | str) -> PfiInspection:
        """Inspect a canonical PCE PFI v0 flux container without mutation or decoding."""
        return inspect_pfi(Path(source))

    def inspect_woz(self, source: Path | str, *, token: CancellationToken | None = None) -> WozInspection:
        """Inspect a canonical WOZ 2.0/2.1 bitstream container without mutation or decoding."""
        return inspect_woz(source, token)

    def inspect_a2r(self, source: Path | str) -> A2rInspection:
        """Inspect a canonical A2R 3.x flux container without mutation or decoding."""
        return inspect_a2r(Path(source))

    def inspect_d64(self, source: Path | str) -> D64Inspection:
        """Inspect a canonical 35-track D64 and its ordinary CBM DOS file chains without mutation."""
        return inspect_d64(source)

    def inspect_d71(self, source: Path | str) -> D71Inspection:
        """Inspect a canonical 70-track D71 and its ordinary CBM DOS file chains without mutation."""
        return inspect_d71(source)

    def inspect_d81(self, source: Path | str) -> D81Inspection:
        """Inspect a canonical 80-track D81 and its ordinary CBM DOS file chains without mutation."""
        return inspect_d81(source)

    def inspect_g64(self, source: Path | str, *, token: CancellationToken | None = None) -> G64Inspection:
        """Inspect a canonical G64 v0 GCR container without mutation or decoding."""
        return inspect_g64(source, token)

    def inspect_g71(self, source: Path | str, *, token: CancellationToken | None = None) -> G71Inspection:
        """Inspect a canonical G71 v0 double-sided GCR container without mutation or decoding."""
        return inspect_g71(source, token)

    def inspect_p64(self, source: Path | str, *, token: CancellationToken | None = None) -> P64Inspection:
        """Inspect a canonical P64 v0 NRZI pulse container without mutation or decoding."""
        return inspect_p64(source, token)

    def inspect_jv3(self, source: Path | str, *, token: CancellationToken | None = None) -> Jv3Inspection:
        """Inspect a JV3 sector container without mutation."""
        return inspect_jv3(source, token)

    def export_jv3_to_raw(self, source: Path | str, destination: Path | str, *,
                          token: CancellationToken | None = None) -> Path:
        """Export only a strictly proven normal JV3 rectangle to a new RAW file."""
        return export_jv3_to_raw(source, destination, token)

    def inspect_twoimg(self, source: Path | str, *, token: CancellationToken | None = None) -> TwoImgInspection:
        """Inspect a standard 2MG/2IMG container without mutating any of its blocks."""
        return inspect_twoimg(source, token)

    def export_twoimg_to_raw(self, source: Path | str, destination: Path | str, *,
                             token: CancellationToken | None = None) -> ApiResult:
        """Export only a validated DOS/ProDOS 2MG data block to a new RAW file."""
        output = export_twoimg_to_raw(source, destination, token)
        return ApiResult("export_twoimg_to_raw", Path(source), output, "Verified 2MG data-block RAW export")

    def replace_iso_file(self, source: Path | str, iso_path: str, replacement: Path | str,
                         destination: Path | str, *, overwrite: bool = False) -> ApiResult:
        """Write an equal-length ISO file replacement to a new verified image."""
        result = replace_iso_file_safely(source, iso_path, replacement, destination, overwrite=overwrite)
        return ApiResult("replace_iso_file", result.source, result.destination,
                         f"Replaced {result.iso_path} ({result.bytes_replaced} bytes) in a verified new ISO")

    def mount_capability(self) -> ImageMountCapability:
        """Report whether the local operating-system read-only mount backend is available."""
        return ImageMountManager().capability_report()

    def mount_read_only(self, image: Path | str) -> ImageMountSession:
        """Create a system-backed read-only mount session; callers must later unmount it."""
        return ImageMountManager().mount(image)

    def unmount(self, session: ImageMountSession) -> None:
        """Release a session produced by :meth:`mount_read_only`."""
        ImageMountManager().unmount(session)

    @contextmanager
    def filesystem(self, image: Path | str, *, writable: bool = False,
                   partition_index: int | None = None, zip_payload: str | None = None) -> Iterator[ImageFilesystem]:
        """Open a filesystem facade and always release the underlying resource."""
        source = Path(image)
        info = self.inspect(source)
        browse_session = None
        filesystem: ImageFilesystem | None = None
        try:
            if info.image_format == ImageFormat.TD0:
                raise DiskForgeError("TD0 images are read-only sector containers; inspect them or use strict TD0 RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.CPC_DSK:
                raise DiskForgeError("CPC DSK images are read-only sector containers; inspect them or use strict CPC DSK RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.D88:
                raise DiskForgeError("D88 images are read-only sector containers; inspect them or use strict D88 RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.HFE:
                raise DiskForgeError("HFE images are read-only bitstream containers; inspect structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.DC42:
                raise DiskForgeError("DC42 images are read-only containers; inspect them or use verified DC42 data-fork RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.TWOIMG:
                raise DiskForgeError("2MG/2IMG images are read-only containers; inspect them or use verified 2MG data-block RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.APRIDISK:
                raise DiskForgeError("APRIDISK images are read-only sector containers; inspect them or use strict APRIDISK RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.COPYQM:
                raise DiskForgeError("CopyQM images are read-only compressed containers; inspect them or use checksum-verified CopyQM RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.SAP:
                raise DiskForgeError("SAP images are read-only sector containers; inspect them or use strict CRC-validated SAP RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.MSA:
                raise DiskForgeError("MSA images are read-only compressed track containers; inspect them or use strict MSA track-validated RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.PSI:
                raise DiskForgeError("PSI images are read-only checksummed sector containers; inspect them or use strict PSI block-validated RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.PRI:
                raise DiskForgeError("PRI images are read-only bitstream containers; inspect their CRC-validated structure instead of filesystem access.")
            if info.image_format == ImageFormat.EIGHTYSIXF:
                raise DiskForgeError("86F images are read-only bitstream containers; inspect their validated v2.12 structure instead of filesystem access.")
            if info.image_format == ImageFormat.FDI:
                raise DiskForgeError("FDI images are read-only multi-level containers; inspect their validated v2.0 structure instead of filesystem access.")
            if info.image_format == ImageFormat.JV3:
                raise DiskForgeError("JV3 images are read-only sector containers; inspect them or use strict JV3 RAW export instead of filesystem access.")
            if info.image_format == ImageFormat.DMK:
                raise DiskForgeError("DMK images are read-only bitstream containers; inspect their native IDAM structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.UDI:
                raise DiskForgeError("UDI images are read-only bitstream containers; inspect their CRC-validated v1.0 structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.SCP:
                raise DiskForgeError("SCP images are read-only flux containers; inspect their validated standard track structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.MFM:
                raise DiskForgeError("HxC MFM images are read-only bitstream containers; inspect their validated track structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.WOZ:
                raise DiskForgeError("WOZ2 images are read-only Apple II bitstream containers; inspect their validated structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.A2R:
                raise DiskForgeError("A2R3 images are read-only flux containers; inspect their validated structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.G64:
                raise DiskForgeError("G64 images are read-only GCR bitstream containers; inspect their validated structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.G71:
                raise DiskForgeError("G71 images are read-only double-sided GCR bitstream containers; inspect their validated structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.P64:
                raise DiskForgeError("P64 images are read-only NRZI pulse containers; inspect their CRC-validated structure instead of opening a filesystem session.")
            if info.image_format == ImageFormat.ZIP:
                if writable:
                    raise DiskForgeError("ZIP image containers are read-only; writable filesystem access is unavailable.")
                browse_session = materialize_browsable_image(
                    source, converter=self.converter, zip_payload=zip_payload,
                )
                source = browse_session.image
                info = self.inspect(source)
            if partition_index is not None:
                filesystem = open_partition_filesystem(source, partition_index, writable=writable)
            elif info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
                filesystem = FatImageFilesystem(source, read_only=not writable)
            elif info.filesystem == FileSystemType.ISO9660:
                if writable:
                    raise DiskForgeError("ISO images are read-only; create a new ISO instead.")
                filesystem = IsoImageFilesystem(source)
            elif info.filesystem == FileSystemType.CBM_DOS:
                if writable:
                    raise DiskForgeError("Canonical D64/D71/D81 CBM DOS images are read-only; modification is unavailable.")
                if info.image_format == ImageFormat.D81:
                    filesystem = D81ImageFilesystem(source)
                elif info.image_format == ImageFormat.D71:
                    filesystem = D71ImageFilesystem(source)
                else:
                    filesystem = D64ImageFilesystem(source)
            elif info.filesystem in {FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS, FileSystemType.HFS_PLUS}:
                if writable:
                    raise DiskForgeError("NTFS, EXT, HFS and HFS+ image access is read-only.")
                filesystem = SleuthKitImageFilesystem(source, info.filesystem)
            else:
                raise DiskForgeError("No filesystem facade is available for this image.")
            yield filesystem
        finally:
            if filesystem is not None:
                filesystem.close()
            if browse_session is not None:
                browse_session.close()

    def extract(self, image: Path | str, paths: Sequence[str], destination: Path | str, *,
                policy: ExtractionPolicy | None = None, zip_payload: str | None = None,
                progress: ProgressCallback | None = None,
                token: CancellationToken | None = None) -> list[Path]:
        with self.filesystem(image, zip_payload=zip_payload) as filesystem:
            return filesystem.extract(paths, Path(destination), progress, token, policy)

    def inject(self, image: Path | str, sources: Sequence[Path | str], *,
               target_directory: str = "/", progress: ProgressCallback | None = None,
               token: CancellationToken | None = None) -> list[str]:
        with self.filesystem(image, writable=True) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images accept file injection.")
            return filesystem.inject(sources, target_directory, progress, token)


    def set_fat_metadata(self, image: Path | str, paths: Sequence[str], *,
                         read_only: bool | None = None, hidden: bool | None = None,
                         system: bool | None = None, archive: bool | None = None,
                         created: datetime | None = None, modified: datetime | None = None,
                         accessed: datetime | None = None, partition_index: int | None = None,
                         token: CancellationToken | None = None) -> tuple[FatMetadataResult, ...]:
        """Update standard DOS attributes and/or FAT times for explicit existing entry paths."""
        update = metadata_update_from_values(
            paths, read_only=read_only, hidden=hidden, system=system, archive=archive,
            created=created, modified=modified, accessed=accessed,
        )
        with self.filesystem(image, writable=True, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images support metadata updates.")
            return apply_fat_metadata(filesystem, update, token)

    def create_fat_directory(self, image: Path | str, directory_path: str, *,
                             partition_index: int | None = None,
                             token: CancellationToken | None = None) -> str:
        """Create one empty directory whose FAT parent already exists, without overwrite."""
        with self.filesystem(image, writable=True, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images support directory creation.")
            return filesystem.create_directory(directory_path, token)

    def copy_fat(self, image: Path | str, item_path: str, target_directory: str, *,
                 partition_index: int | None = None,
                 progress: ProgressCallback | None = None,
                 token: CancellationToken | None = None) -> str:
        """Copy one regular file or complete new directory tree into writable FAT without overwrite."""
        with self.filesystem(image, writable=True, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images support file or directory-tree copying.")
            return filesystem.copy(item_path, target_directory, progress, token)

    def move_fat(self, image: Path | str, item_path: str, target_directory: str, *,
                 partition_index: int | None = None,
                 progress: ProgressCallback | None = None,
                 token: CancellationToken | None = None) -> str:
        """Move one FAT file or directory tree; directories use controlled copy-then-delete."""
        with self.filesystem(image, writable=True, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images support file or directory-tree movement.")
            return filesystem.move(item_path, target_directory, progress, token)

    def rename_fat(self, image: Path | str, item_path: str, new_name: str, *,
                   partition_index: int | None = None) -> str:
        """Rename one FAT file or directory in place without replacing an existing entry."""
        with self.filesystem(image, writable=True, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images support entry renaming.")
            return filesystem.rename(item_path, new_name)

    def delete_fat(self, image: Path | str, item_path: str, *,
                   partition_index: int | None = None) -> str:
        """Delete one explicit non-root FAT file or directory tree from a writable image."""
        with self.filesystem(image, writable=True, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Only writable FAT images support entry deletion.")
            filesystem.delete([item_path])
        return item_path

    def list_deleted_fat(self, image: Path | str, *, partition_index: int | None = None) -> list[DeletedFatFileCandidate]:
        """List conservative FAT12/FAT16 deleted fixed-root-file candidates without mutating the image."""
        with self.filesystem(image, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Deleted-file candidates are available only for FAT images.")
            return filesystem.deleted_root_file_candidates()

    def recover_deleted_fat(self, image: Path | str, slot_index: int, destination: Path | str, *,
                            partition_index: int | None = None) -> Path:
        """Copy one revalidated single-cluster FAT deleted-file candidate to a new local output file."""
        with self.filesystem(image, partition_index=partition_index) as filesystem:
            if not isinstance(filesystem, FatImageFilesystem):
                raise DiskForgeError("Deleted-file recovery is available only for FAT images.")
            return filesystem.recover_deleted_root_file(slot_index, destination)
