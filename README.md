<p align="center">
  <img src="assets/diskforge-workspace.png" alt="DiskForge workspace showing an opened FAT image" width="900">
</p>

<h1 align="center">DiskForge</h1>

<p align="center"><strong>Cross-platform disk image studio for safe creation, exploration, conversion, and recovery workflows.</strong></p>

<p align="center">
  <a href="https://github.com/Piechicken/diskforge/actions/workflows/ci.yml"><img src="https://github.com/Piechicken/diskforge/actions/workflows/ci.yml/badge.svg?branch=main" alt="Build status"></a>
  <a href="https://github.com/Piechicken/diskforge/releases"><img src="https://img.shields.io/github/v/release/Piechicken/diskforge?display_name=tag&color=7C3AED" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0EA5E9.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-2563EB.svg" alt="Python 3.10 or newer">
  <img src="https://img.shields.io/badge/GUI-Qt-16A34A.svg" alt="Qt GUI">
  <img src="https://img.shields.io/badge/UI-7%20languages-9333EA.svg" alt="Seven interface languages">
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **DiskForge gives disk images a real desktop workspace.** Create, inspect, browse, extract, inject, convert, verify, and safely restore images without treating a physical drive as an afterthought.

## Release downloads

The v0.10.0 formal release provides four native desktop builds. Download the package matching your operating system from the [Releases page](https://github.com/Piechicken/diskforge/releases): **Windows x64**, **Linux x64**, **macOS Intel**, or **macOS Apple Silicon**. Each package is built and validated in GitHub Actions on its target runner.

| Platform | Package | Launch |
|---|---|---|
| Windows x64 | `DiskForge-v0.10.0-windows-x64.zip` | Extract, then run `DiskForge.exe`. |
| Linux x64 | `DiskForge-v0.10.0-linux-x64.zip` | Extract, then run `./DiskForge`. |
| macOS Intel | `DiskForge-v0.10.0-macos-intel-x64.zip` | Extract, then move `DiskForge.app` to Applications. |
| macOS Apple Silicon | `DiskForge-v0.10.0-macos-arm64.zip` | Extract, then move `DiskForge.app` to Applications. |

## Interface languages

DiskForge v0.10.0 localizes the document workspace and the FAT-template, safe boot-code import, editable fixed-VHD, partition-selection, safe ISO replacement, legacy ZIP-container, read-only mount, device MBR, removable-media, controller-floppy, and guarded UFI USB floppy paths at runtime. Select **Tools → Language** to switch immediately between the six United Nations working languages—**Arabic, Chinese, English, French, Russian, and Spanish**—plus **Japanese**. The preference is retained for the next launch. Selecting Arabic switches the complete Qt layout to right-to-left while preserving technical values such as device paths, checksums, file extensions, and the physical-write confirmation phrase `ERASE`. UFI UI coverage does not imply completed real-hardware formatting acceptance.

Read [LOCALIZATION.md](docs/LOCALIZATION.md) for the language matrix, RTL behavior, safety boundaries, and translation-maintenance workflow.

<p align="center">
  <img src="assets/diskforge-arabic-rtl.png" alt="DiskForge interface in Arabic with right-to-left layout" width="700">
</p>

## What it does

DiskForge brings the most useful image-management workflows into one original, auditable application. The main window combines an image explorer, directory table, image metadata panel, activity log, and cancellable progress area. Destructive actions are visually isolated from ordinary browsing and require explicit confirmation.

| Workflow | Native capability | Notes |
|---|---|---|
| Create images | RAW/IMG/IMA, FAT12, FAT16, FAT32, verified legacy FAT12 floppy profiles, DMF-layout FAT12, FAT templates, ISO9660/Joliet/Rock Ridge/UDF, optional classic HFS | Create editable FAT images from standard presets, a validated FAT BPB template, or explicit IMG/IMA legacy floppy profiles. The legacy directory covers conventional PC-compatible 160 KiB through 2.88 MiB layouts and custom supported CHS geometry. ISO media can be created from a local directory with optional El Torito boot media. With explicitly available `hformat`, DiskForge can create a new standalone classic HFS regular-file image from 800 KiB upward; HFS+ remains read-only. |
| Browse and extract | FAT12/16/32—including validated unlabeled legacy DOS floppy media and conventional-size `.vfd`/`.flp`/capacity-suffixed raw aliases—conservative FAT12/FAT16 deleted root-file candidates; read-only IMD, TD0, CPC DSK, D88, APRIDISK, CopyQM, SAP, MSA, PSI, DC42, 2MG/2IMG, HFE, PRI, restricted 86F, FDI, JV3, DMK, UDI v1.0, standard SCP, canonical HxC MFM, canonical PCE PFI v0 flux-container inspection, canonical WOZ 2.0/2.1 Apple II container inspection, canonical A2R 3.x flux-container inspection, verified canonical 35-track D64 and 70-track double-sided D71 CBM DOS directory browsing and ordinary-file extraction, canonical G64 v0 1541 GCR-container inspection, canonical G71 v0 double-sided 1571 GCR-container inspection, and canonical P64 v0 1541 NRZI pulse-container inspection; ISO9660/Joliet, safe explicitly selected multi-image ZIP containers, fixed VHD data views, and optional NTFS/EXT2/EXT3/classic-HFS/HFS+ read-only backend | A regular ZIP with one to 64 safe root-level image payloads is materialized only into an auto-cleaned private read-only session. A sole payload opens directly; a multi-image ZIP requires an explicit selected payload in the desktop, CLI, or SDK. It never becomes writable or convertible. Legacy raw aliases are classified only when their suffix and exact byte size match a conventional 512-byte PC floppy shape; variable-sector, XDF, GCR, hard-sectored, and flux media are not guessed. Deterministic paged trees and sortable tables avoid unbounded directory rendering. Validated MBR/GPT partitions are always selected by explicit table index: FAT retains its existing edit path, while NTFS/EXT/classic HFS/HFS+ are opened only at their exact validated offset through the read-only backend. Double-click opens a non-executing document workspace for text, images, common archives, legacy setup packages, executables, and binary data. Text documents can be found, saved as a copy, and—only for writable FAT entries—edited and saved back. Fixed VHD normally opens through a temporary read-only RAW data view; a validated independent fixed-VHD copy may be reopened as a writable FAT session. |
| Inventory image directories | Read-only local image metadata scanning with JSON, CSV, or HTML reports | Scan one local directory, optionally recursively, and filter known image candidates by suffix, recognized format, filesystem, byte range, or SHA-256 prefix. Per-record SHA-256 and partition summaries are optional. Every report is a new file outside the scanned root; no candidate image is modified. |
| Change image contents | FAT injection, explicit empty-directory creation, recursive folders, deletion, rename, cross-directory file and directory-tree copying plus controlled movement, timestamps, DOS attributes, and volume labels; safe rebuild-based ISO edits; optional controlled NTFS/EXT/classic-HFS injection | Valid FAT payloads inside IMG and IMA share the same editable path. An empty directory can be explicitly created only at a new path whose parent already exists; this never overwrites or creates implicit parents. A regular file or complete directory tree can be copied to an existing directory without overwrite; copying preserves its source, requires a new same-name target, and rejects a directory target inside the source tree. A file or directory tree may also move to such a target: a directory first completes a cancellable copy, then removes its source. Cancellation before deletion or a deletion failure retains both complete trees for manual resolution, so directory movement is not claimed to be atomic. Missing/non-directory targets, root movement, collisions, read-only sessions, and source-tree targets are rejected before mutation. Same-directory rename remains a separate action. Explicit FAT deletion is available for one non-root file or directory tree at a time after path validation; it is irreversible and is not claimed to be transactional. ISO changes always write a separate rebuilt image and verify staged content. Rock Ridge/UDF profiles are preserved; only a verified single-entry El Torito catalog is rebuilt, while multi-boot, hybrid, and ambiguous boot layouts are rejected. With explicitly available `ntfsprogs`, `e2fsprogs`, or `hfsutils`, NTFS/EXT/classic HFS can receive new root-directory regular files only in a separately verified output image; no source, partition-offset, metadata, rename, delete, or overwrite write is allowed. Classic HFS injection transfers raw data forks only; HFS+ remains read-only. |
| Convert formats | RAW/IMG/IMA and fixed VHD natively | IMG and IMA preserve their explicitly selected raw-image extension during conversion. VHDX, VMDK, and QCOW2 use an explicitly configured `qemu-img` adapter with visible capability reporting and cancellation. A separately configured `dmg2img` adapter can only create a new raw output from DMG; DiskForge does not mount or write DMG files. |
| Compact FAT images | Rebuild-based defragmentation | Writes a new image, preserving the original image as the recovery point. |
| Inspect and repair structures | 512-byte hex viewer/editor, validated FAT boot properties, original neutral/message templates, neutral MBR wrapping and deployment planning for FAT superfloppy images, trailing-zero-sector copy trimming, MBR backup/restore/neutral reset, and GPT CRC diagnostics | Full image or MBR backups are created before protected structural changes. Templates preserve BPB fields and use no imported boot program; wrapping, deployment preparation, and trimming always write a new file. |
| Verify and automate | SHA-256, byte-for-byte compare, graphical batch recipe studio, preflight plans, per-item result review, versioned JSON recipes, and directory reports | Schema v4 adds declarative `iso_edit`, `ntfs_inject`, `ext_inject`, `hfs_inject`, `hfs_create`, `export_listing`, FAT `move`, `fat_mkdir`, `fat_copy`, `fat_rename`, `fat_delete`, and explicit-path FAT `fat_metadata`; all recipe writes can be previewed before execution and raw-device writes remain rejected. `export_listing` only creates a local text/HTML report and can target an explicitly selected read-only partition. Text/HTML directory reports use one stable full traversal for every browsable filesystem and explicit read-only partition. The visual designer covers conversion—including IMA target selection—validation, comparison, resize, injection, classic-HFS creation, extraction, and container recipes. Comparisons can optionally report only full trailing zero sectors as ignored. |
| Annotate and resize | Non-invasive image comments and safe new-file RAW/FAT resize | Raw images refuse shrinking if non-zero tail bytes would be discarded. |
| Build redistributable bundles | Authenticated multi-image `.dfb` containers and SHA-256-verified multi-image self-extracting `.pyz` archives | `.dfb` supports optional scrypt-derived AES-256-GCM encryption, compression, comments, and per-file verification. Each native platform package also includes a separate `DiskForgeExtractor` that verifies and extracts `.pyz` payloads without requiring the recipient to pre-install Python. |
| Read and write physical media | Streamed device imaging and restoration | Rejects system disks, mounted targets, and capacity mismatches; typed confirmation is required. Detected optical media are read-only and export to ISO by default. |
| Low-level floppy formatting | Linux controller floppy and detected UFI USB floppy backends | `fdformat` is limited to standard controller nodes. A UFI USB candidate must be sysfs-associated with removable media, prove itself through `ufiformat -i`, use an explicitly reported capacity and the `FORMAT_FLOPPY` phrase, and is always verified with `-V`. FAT creation remains a separate, newly confirmed operation; real hardware acceptance is still required for each drive model. |

FDI v2.0, DMK, canonical HxC MFM, canonical PCE PFI v0, canonical WOZ 2.0/2.1, canonical A2R 3.x, canonical G64 v0, canonical G71 v0, and canonical P64 v0 are structure-only, read-only container inspectors: none decodes tracks, bitstreams, or flux, opens a filesystem, converts, repairs, writes, nor reconstructs RAW data. JV3 is likewise read-only; it produces a separate RAW output only after normal sectors prove one complete rectangular, fixed-geometry layout. Every other historical-container variant remains preserved for inspection only or is rejected instead of being guessed or flattened. A canonical 35-track D64 is a narrow **read-only CBM DOS filesystem** workflow: DiskForge accepts exactly 174,848-byte, 256-byte-sector `.d64` sources without an error map, validates BAM counts, the directory chain, ordinary SEQ/PRG/USR chains, and final-sector byte counts, then lists or extracts those verified files. 40-track/error-map variants, REL and GEOS layouts, GCR decoding, repair, conversion, creation, and writes remain unavailable. A canonical 70-track D71 likewise requires exactly 349,696 bytes without an error map and validates the double-sided flag plus both BAM bitmap/count regions before listing or extracting ordinary SEQ/PRG/USR files. It rejects 40-track/error-map variants, REL/GEOS, GCR decoding, repair, generic conversion, creation, editing, writes, and device routes.

## Safety first

> A disk-image utility should make dangerous operations **hard to trigger accidentally**.

DiskForge never mounts an image or writes a physical device automatically. FAT deployment first produces a reviewable neutral-MBR image; it does not bypass the protected physical-write operation. Before a physical write, it checks capacity, mounted state, and system-disk status, then requires the exact phrase `ERASE`. The write path can verify bytes after completion. Boot-sector changes also create a full-image backup first. Always work with disposable test images before operating on irreplaceable media.

## Portable configuration

Use `diskforge --portable` to write preferences, language choice, recent images, view mode, theme, font, and external-tool path to `DiskForgeData/diskforge.ini` in the current directory. Use `--portable=DIR`, `--portable-directory DIR`, or `DISKFORGE_PORTABLE_DIR` to select an explicit location. This mode uses an ordinary portable INI file and does not require a system registry entry.

## Start in minutes

### Run from source

```bash
python -m pip install -e '.[dev]'
diskforge
```

### Use the command line

```bash
diskforge-cli create-fat demo.img --size-mib 32 --fat 16
diskforge-cli info demo.img
diskforge-cli list demo.img
diskforge-cli list partitioned.img --partition 2
diskforge-cli export-listing partitioned.img partition-report.html --html --partition 2
diskforge-cli mkdir-fat demo.img /DOCS  # one new empty directory; parent must already exist
diskforge-cli copy-fat demo.img /README.TXT /DOCS  # preserves source; a file or complete directory tree; no overwrite
diskforge-cli move-fat demo.img /README.TXT /DOCS  # /DOCS must exist; a directory uses cancellable copy-then-delete
diskforge-cli delete-fat demo.img /DOCS/OLD.TXT  # one explicit non-root file or directory tree; irreversible
diskforge-cli set-fat-metadata demo.img /README.TXT /DOCS/NOTES.TXT --hidden --modified 2024-06-15T12:34:56  # explicit writable FAT paths only
diskforge-cli list archived-image.zip  # one safe root-level image payload; read-only
diskforge-cli list-deleted-fat demo.img  # FAT12/FAT16 fixed-root 8.3 candidates only
diskforge-cli recover-deleted-fat demo.img 17 recovered.bin  # a new local output; never writes demo.img
diskforge-cli imd-info legacy.imd  # read-only track/sector audit
diskforge-cli convert-imd legacy.imd exported.img  # only a proven rectangular normal-data layout
diskforge-cli td0-info legacy.td0  # read-only ordinary TD0 track/sector audit
diskforge-cli convert-td0 legacy.td0 exported.img  # only a proven unflagged ordinary rectangular layout
diskforge-cli dc42-info disk.dc42  # verifies header, forks, and checksums
diskforge-cli convert-dc42 disk.dc42 exported.img  # verified data fork only
diskforge-cli twoimg-info apple.2mg  # validates standard 2MG/2IMG structure
diskforge-cli convert-twoimg apple.2mg exported.img  # DOS/ProDOS data block only
diskforge-cli apridisk-info legacy.dsk  # signature-based APRIDISK audit
diskforge-cli copyqm-info archive.qm  # checksummed CopyQM audit
diskforge-cli sap-info thomson.sap  # CRC-validated SAP audit
diskforge-cli msa-info atari.msa  # fully decodes and validates MSA tracks
diskforge-cli psi-info media.psi  # checksummed PSI sector stream
diskforge-cli pri-info capture.pri  # CRC-validated PRI bitstream structure
diskforge-cli 86f-info capture.86f  # restricted 86F v2.12 bitstream structure
diskforge-cli fdi-info capture.fdi  # FDI v2.0 multi-level container structure
diskforge-cli jv3-info disk.jv3  # JV3 sector-container inspection
diskforge-cli convert-jv3 disk.jv3 exported.img  # only a proven normal rectangular layout
diskforge-cli dmk-info capture.dmk  # native DMK header and IDAM-directory structure
diskforge-cli udi-info capture.udi  # CRC32-validated uppercase UDI v1.0 MFM track structure only
diskforge-cli scp-info capture.scp  # standard read-only SCP flux-track structure only
diskforge-cli mfm-info capture.mfm  # canonical HxC MFM bitstream structure only
diskforge-cli pfi-info capture.pfi  # canonical PCE PFI v0 CRC-validated flux structure only
diskforge-cli woz-info disk.woz  # canonical WOZ 2.0/2.1 structure only
diskforge-cli a2r-info capture.a2r  # canonical A2R 3.x flux-container structure only
diskforge-cli d64-info disk.d64  # verified canonical 35-track D64 CBM DOS structure and ordinary file chains
diskforge-cli list disk.d64  # read-only CBM DOS directory listing
diskforge-cli d71-info disk.d71  # verified canonical 70-track double-sided D71 CBM DOS structure and ordinary file chains
diskforge-cli list disk.d71  # read-only double-sided CBM DOS directory listing
diskforge-cli d81-info disk.d81  # verified canonical 80-track D81 double-sided CBM DOS structure and ordinary file chains
diskforge-cli list disk.d81  # read-only D81 CBM DOS directory listing
diskforge-cli g64-info disk.g64  # canonical G64 v0 1541 GCR-container structure only
diskforge-cli g71-info disk.g71  # canonical G71 v0 double-sided 1571 GCR-container structure only
diskforge-cli p64-info capture.p64  # canonical P64 v0 CRC-validated NRZI pulse-container structure only
diskforge-cli inventory-images ./image-library image-library-report.json --recursive --include-sha256  # read-only; report must be outside the scan root
diskforge-cli bundle demo.dfb demo.img --comment "lab media"
diskforge-cli compare demo.img restored.img
diskforge-cli create-dmf demo.dmf
diskforge-cli create-legacy-floppy win16-disk --profile pc525_dsdd_360 --format ima
diskforge-cli create-legacy-floppy custom-disk --format img --cylinders 80 --heads 2 --sectors-per-track 9
diskforge-cli create-iso folder bootable.iso --boot-image boot.img --boot-media noemul
diskforge-cli edit-iso bootable.iso revised.iso --add README.TXT --mkdir /DOCS
diskforge-cli iso-boot-info bootable.iso
diskforge-cli export-boot-image bootable.iso boot.img
diskforge-cli inject-ntfs standalone.ntfs revised.ntfs PAYLOAD.TXT
diskforge-cli inject-ext standalone.ext4 revised.ext4 PAYLOAD.TXT
diskforge-cli inject-hfs standalone.hfs revised.hfs PAYLOAD.TXT
diskforge-cli create-hfs created.hfs --size-kib 800 --label DISKFORGE
diskforge-cli ntfs-inject-status
diskforge-cli ext-inject-status
diskforge-cli hfs-inject-status
diskforge-cli hfs-create-status
diskforge-cli boot-templates
diskforge-cli prepare-fat-deployment demo.img demo-deploy.img
diskforge-cli batch recipe.json --dry-run
diskforge-cli --help
```

### Build a native package

```bash
python scripts/build.py
```

Build on each target operating system to create that platform’s native application. The repository workflow performs these builds automatically for the four release targets.

## Format coverage

| Format or filesystem | Inspect | Browse / modify | Create / convert |
|---|---:|---:|---:|
| RAW / IMG / IMA / BIN | Yes | Valid FAT payloads in IMG/IMA are editable, previewable, extractable, and hashable | Native RAW/IMG/IMA copy conversion; explicit IMG/IMA legacy FAT12 profiles and supported custom CHS creation |
| IMD | Read-only track/sector inspection | No direct filesystem editing. Strict export creates a new RAW file only after proving a complete rectangular CHS layout with normal data. | No IMD creation or in-place conversion. |
| TD0 | Read-only ordinary uncompressed track/sector inspection with documented CRC checks | No direct filesystem editing. Strict export creates a new RAW file only after proving an exact-EOF, unflagged complete rectangular CHS layout with matching logical/physical coordinates and reconstructed ordinary data. | No TD0 creation, advanced-compression support, in-place conversion, repair, or write path. |
| CPC DSK / D88 / APRIDISK / CopyQM / SAP / MSA / PSI | Read-only format-specific structural inspection | A new RAW output is available only after the relevant parser proves its documented clean complete rectangular sector/track layout, exact input termination, and applicable checksum/CRC conditions. | No source writes, generic conversion, filesystem session, repair, device output, overwrite, or irregular/weak/protected-media claim. |
| DC42 / 2MG / 2IMG | Read-only fork/container inspection | DC42 can export a fully verified data fork; 2MG/2IMG can export a validated DOS/ProDOS data block, each to a separate new RAW file. | No container write; DC42 tags and 2MG NIB/irregular layouts are not flattened. |
| HFE / PRI / 86F | Read-only bitstream structural inspection | HFE validates header/LUT track ranges; PRI validates chunk CRCs, tracks, clocks, and events; 86F validates a restricted v2.12 fixed-RPM total-bitcell layout. | No bitstream decoding, RAW export, filesystem session, editing, repair, or device route. |
| PCE PFI v0 | Read-only flux-container structural inspection | Validates published big-endian chunk framing, zero-initialized CRC-32, track contexts, index-list alignment, pulse-token syntax, zero-length END, and exact EOF. | No flux or sector decoding, RAW export, filesystem session, conversion, editing, repair, or device route. |
| WOZ 2.0/2.1 | Read-only Apple II container structural inspection | Validates the signed WOZ2 header, optional CRC-32, INFO v2/v3, canonical INFO/TMAP/TRKS order, opaque mapped track ranges, optional FLUX-map consistency, bounded UTF-8 META grammar, and exact EOF. | No WOZ1, bitstream/flux/sector decoding, RAW export, filesystem session, conversion, editing, repair, or device route. |
| A2R 3.x | Read-only flux-container structural inspection | Validates the fixed A2R3 signature, first INFO v1 block, bounded little-endian chunk grammar, RWCP capture entries, SLVD solved-track entries, UTF-8 META grammar, and exact EOF. | No A2R1/A2R2, flux/bitstream/sector decoding, RAW export, filesystem session, conversion, editing, repair, or device route. |
| D64 (canonical 35-track) | Read-only CBM DOS filesystem inspection | Requires exactly 174,848 bytes of 256-byte sectors; validates BAM version/counts, the directory chain, ordinary SEQ/PRG/USR file chains, and final-sector byte counts. Verified files can be listed or extracted directly or after safe ZIP materialization. | No 40-track/error-map variants, REL/GEOS layouts, GCR decoding, repair, generic conversion, creation, editing, write, or device route. |
| D71 (canonical 70-track) | Read-only double-sided CBM DOS filesystem inspection | Requires exactly 349,696 bytes of 256-byte sectors; validates the double-sided flag, side-0 BAM entries, side-1 BAM bitmap/count region, directory chain, ordinary SEQ/PRG/USR file chains, final-sector byte counts, and no directory/file/system-sector overlap. Verified files can be listed or extracted directly or after safe ZIP materialization. | No 40-track/error-map variants, REL/GEOS layouts, GCR decoding, repair, generic conversion, creation, editing, write, or device route. |
| D81 (canonical 80-track) | Read-only double-sided CBM DOS filesystem inspection | Requires exactly 819,200 bytes of 256-byte sectors; validates the 1581 header, both 40-entry BAM sectors, matching disk IDs, every 40-bit allocation bitmap/count, canonical linear track-40 directory, ordinary SEQ/PRG/USR file chains, final-sector byte counts, and no directory/file/system-sector overlap. Verified files can be listed or extracted directly or after safe ZIP materialization. | No error-map variants, extended directories, REL/GEOS/CBM partitions, GCR decoding, repair, generic conversion, creation, editing, write, or device route. |
| G64 v0 | Read-only 1541 GCR-container structural inspection | Validates the fixed `GCR-1541` version-0 signature, bounded little-endian track and speed tables, opaque stored track allocations, constant or mapped speed zones, non-overlap, and exact EOF. | No `GCR-1571`, GCR/sector decoding, RAW export, filesystem session, conversion, editing, repair, or device route. |
| G71 v0 | Read-only double-sided 1571 GCR-container structural inspection | Validates the fixed `GCR-1571` version-0 signature, exactly 168 half-track entries, bounded little-endian track and speed tables, opaque stored-track allocations, constant or mapped speed zones, non-overlap, and exact EOF. | GCR bytes stay opaque: no GCR/sector decoding, RAW export, browsing, filesystem session, conversion, editing, repair, writing, or device route. |
| P64 v0 | Read-only 1541 NRZI pulse-container structural inspection | Validates the fixed `P64-1541` version-0 signature, defined flags, whole-stream and per-chunk CRC-32, bounded HTPx framing, unique half-track/side coordinates, range-stream byte counts, final empty DONE, and exact EOF. | Range-coded NRZI data stays opaque: no pulse/GCR/sector decoding, RAW export, filesystem session, conversion, editing, repair, or device route. |
| FAT12 / FAT16 / FAT32 | Yes | FAT remains editable. FAT12/FAT16 additionally expose conservative fixed-root deleted 8.3 candidates; recovery only copies one currently free single cluster to a new local file. | Yes |
| ISO9660 / Joliet / Rock Ridge / UDF | Yes | Read/extract; safely rebuild into a separate edited image | Create from folder; Rock Ridge/UDF profile creation |
| Fixed VHD | Yes | Temporary read-only data view and conversion | Yes |
| VHDX / VMDK / QCOW2 | With adapter | Temporary read-only RAW view after configured conversion | With adapter |
| NTFS / EXT2 / EXT3 / EXT4 | Signature or partition hint | Read/list/extract with the optional Sleuth Kit backend at offset 0 or an explicitly selected validated MBR/GPT partition; text/HTML directory reports are available. Optional controlled new-output root-file injection remains standalone offset-0 only with configured `ntfsprogs` / `e2fsprogs` | Browsing is read-only. Injection is external-backend only: standalone offset-0 volumes, new regular root files, no overwrite; source SHA-256, read-back SHA-256, and filesystem validation are required. |
| HFS / HFS+ | Signature or partition hint | Read/list/data-fork extract with the optional Sleuth Kit backend at offset 0 or an explicitly selected validated MBR/GPT partition; text/HTML directory reports are available. Classic HFS additionally supports optional controlled new-output root-file injection and verified new regular-file creation through configured `hfsutils` | Partition browsing is read-only. Classic HFS creation only: new regular file, at least 800 KiB in 512-byte units, safe 1–27-character ASCII label, no device, partition map, existing output, or `-f`; output HFS signature and SHA-256 are verified before atomic promotion. Injection remains standalone offset-0, new safe regular root files, raw data forks only, no overwrite; source and every read-back payload require SHA-256. HFS+ remains read-only; no journaled HFS+ write, resource-fork reconstruction, or filesystem repair. |
| ZIP image container (`.zip`) | ZIP structure and one to 64 validated candidate payloads | Read/list/extract/report only after auto-cleaned temporary materialization; a multi-image archive requires an explicit selected name | No create, conversion, filesystem editing, or archive write. Every root-level unencrypted Stored/Deflated `.img`, `.ima`, `.bin`, `.dd`, `.dmf`, `.vfd`, `.flp`, capacity aliases, `.d64`, `.d71`, `.d81`, `.iso` or `.hfs` payload up to 2 GiB must validate; any unsafe member rejects the container. |
| DiskForge bundle (`.dfb`) | Header and authenticated manifest | Extract and verify; optional AES-256-GCM password protection | Create from one or more local images. |
| El Torito boot catalog | Inspect | Export boot image; safely preserve one verified initial entry during ISO rebuild | Create new bootable ISO media from a directory and optional local boot image. Multi-section/multi-boot, hybrid-system-area, or ambiguous mappings are rejected during rebuild. |
| DMG | Signature hint | Not natively modified | Use a compatible external workflow. |

DiskForge exposes unsupported editing paths honestly instead of attempting unsafe writes. The historical-container inspectors are deliberately format-specific read-only contracts: HFE, PRI, restricted 86F, canonical PCE PFI, and canonical P64 do not decode bitstreams, pulses, or produce RAW; DC42 and 2MG/2IMG export only independently verified data areas; APRIDISK, CopyQM, SAP, MSA, and PSI export a new RAW only after their individual parsers prove normal complete rectangular data. Every such container rejects source writes, generic conversion, filesystem sessions, existing output targets, devices, repair, and unsupported variants.  Batch inventory is a local read-only report workflow, not a forensic scanner or unattended mutation: it accepts one existing non-symlink directory, ignores links, recognizes known image suffixes only, finds at most 10,000 regular files, excludes files above 16 GiB, and writes only a new JSON/CSV/HTML report outside the scan root. It does not mount images, inspect physical devices, overwrite reports, or enter batch schema v4. IMD is inspected as a floppy-sector container and is not automatically treated as a raw or writable filesystem. A new RAW file can be exported only from a complete rectangular CHS layout with fixed sector count/size, consecutive `1..N` identifiers, no optional maps, and normal (including normal compressed-fill) sector data. TD0 is likewise a sector container, not a raw or writable filesystem: only ordinary uncompressed `TD` records are inspected, with header/comment/track/sector CRC validation. New RAW export additionally requires exact EOF, unflagged sectors, matching physical and logical CHS, fixed geometry, and exact reconstruction of ordinary raw/repeated-pattern/RLE data. Advanced-compressed `td`, multi-volume records, CRC failures, flags or missing data, mixed density, irregular geometry, output overwrite, TD0 writing, editing, repair, devices, and bitstream/flux claims are rejected. Irregular geometry, missing/deleted/bad sectors, variable layouts, duplicate records, maps, trailing bytes, device targets, overwrites, IMD writing, and any bitstream/flux claim are rejected. FAT deleted-file recovery is a narrow **candidate-copy** workflow, not generic forensic recovery: it accepts only FAT12/FAT16 fixed-root ordinary 8.3 slots with a positive payload no larger than one cluster and a currently free start cluster. The deleted first filename character is unavailable; candidate bytes can be stale or overwritten, so no original-name or integrity claim is made. FAT32, subdirectories, long names, zero-length and multi-cluster chains, occupied clusters, source writes, existing-output overwrite, device recovery, and batch recovery are rejected. A regular ZIP is a narrow **read-only image container**, not a general filesystem or conversion source: it may contain one to 64 safe root-level unencrypted Stored/Deflated payloads with approved direct image extensions, each no larger than 2 GiB. A sole payload opens directly; multiple payloads require an explicit exact root-level name in the desktop, CLI, or SDK. Folders, unsafe names, encryption, unsupported compression, empty/oversized/unknown payloads, more than 64 entries, recursive containers, virtual-disk chains, conversion, and every ZIP write are rejected; temporary bytes are removed on normal close, error, and cancellation. FAT movement accepts one regular file or complete directory tree and one existing target directory: it never overwrites or merges entries. Directory trees use cancellable copy-then-delete, so cancellation before deletion or deletion failure retains both complete trees and is not claimed to be atomic. FAT metadata batches are limited to explicitly listed existing entries in a writable FAT image or explicitly selected FAT partition. They may set or clear only the standard read-only, hidden, system, and archive bits and apply caller-supplied timezone-free FAT creation, modification, or access times. Empty requests, root or duplicate paths, wildcards, recursion, implicit current times, non-FAT filesystems, devices, ACL/ADS/ownership changes, and automatic selection are rejected. Batch preview identifies the write, but multiple FAT directory updates are not claimed to have all-or-nothing rollback.  Legacy profile creation is intentionally limited to flat, FAT-compatible sectors of 512, 1024, 2048, or 4096 bytes; 128/256-byte-sector media, GCR or variable-sector encodings, hard-sectored disks, non-FAT filesystems, copy-protected tracks, and flux/bitcell captures remain raw preservation/inspection workflows. Configure `qemu-img` through **Tools → Preferences** when virtual-disk conversion is needed. NTFS/EXT/HFS/HFS+ read-only browsing requires locally installed Sleuth Kit `fls` and `icat`; optional controlled injection requires explicitly configured `ntfscp`/`ntfsls`/`ntfscat`, `debugfs`/`e2fsck`, or, for classic HFS only, `hmount`/`hcopy`/`hls` for injection or `hformat` for verified creation. DiskForge never downloads, mounts, or runs an external converter silently. Read [FILESYSTEM_INJECTION.md](docs/FILESYSTEM_INJECTION.md) for the exact copy-on-write contract and unsupported paths.

## Engineering quality

The project includes automated coverage for FAT creation, safe file and directory-tree movement, safe explicitly selected ZIP image-payload materialization and cleanup, conservative FAT deleted-candidate recovery, read-only IMD inspection and strict RAW export, read-only TD0 inspection and strict CRC-validated RAW export, explicit multi-path FAT metadata updates across CLI/SDK/batch/desktop, read-only batch image inventory filtering and JSON/CSV/HTML reporting, and advanced metadata editing, bootable ISO creation and El Torito inspection, original boot template BPB preservation, fixed VHD temporary browsing and cleanup, deployment planning, conservative zero-tail reports, native drag-and-drop contracts, complete graphical batch-recipe editing and no-side-effect preflight, document preview/find/save-back behavior, paged directory traversal, seven-language coverage for the complete workspace, public API sessions, portable settings, task-center history, persistent directory views and font preferences, theme selection, cross-platform optical-device classification, checksums, authenticated image bundles, safe resizing, GPT CRC diagnostics, MBR lifecycle protection, read-only EXT integration, self-extractors, device-write safety, directory export, and rebuild-based FAT compaction. pytest uses strict configuration, strict marker checks, and warning-as-error behavior; the GUI is also validated in an off-screen environment. Continuous integration runs the same quality gate on Windows, Linux, macOS Intel, and macOS Apple Silicon, then packages each native target. Version tags are validated against project metadata and a pre-existing release causes publication to fail rather than overwrite its assets.

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
QT_QPA_PLATFORM=offscreen python scripts/gui_i18n_smoke.py
```

Read [BUILDING.md](docs/BUILDING.md) for build and release details, [API.md](docs/API.md) for the stable Python integration facade, [VALIDATION.md](docs/VALIDATION.md) for optional real-filesystem and UFI hardware acceptance, [FILESYSTEM_INJECTION.md](docs/FILESYSTEM_INJECTION.md) for optional NTFS/EXT/classic-HFS write constraints, and [COMPLETION_ACCEPTANCE.md](docs/COMPLETION_ACCEPTANCE.md) for the auditable convergence boundary. The visual smoke-test note is available in [gui_validation.md](artifacts/gui_validation.md).

## Contributing

Issues and pull requests are welcome. Keep changes focused, add regression tests for behavior changes, and never include real disk images, credentials, private paths, or generated build output in commits.

## License

DiskForge is released under the [MIT License](LICENSE).
