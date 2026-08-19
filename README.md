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
  <a href="README.es.md">Español</a>
</p>

> **DiskForge gives disk images a real desktop workspace.** Create, inspect, browse, extract, inject, convert, verify, and safely restore images without treating a physical drive as an afterthought.

## Release downloads

The first public release provides four native desktop builds. Download the package matching your operating system from the [Releases page](https://github.com/Piechicken/diskforge/releases): **Windows x64**, **Linux x64**, **macOS Intel**, or **macOS Apple Silicon**. Each package is built and validated in GitHub Actions on its target runner.

| Platform | Package | Launch |
|---|---|---|
| Windows x64 | `DiskForge-v0.8.0-windows-x64.zip` | Extract, then run `DiskForge.exe`. |
| Linux x64 | `DiskForge-v0.8.0-linux-x64.zip` | Extract, then run `./DiskForge`. |
| macOS Intel | `DiskForge-v0.8.0-macos-intel-x64.zip` | Extract, then move `DiskForge.app` to Applications. |
| macOS Apple Silicon | `DiskForge-v0.8.0-macos-arm64.zip` | Extract, then move `DiskForge.app` to Applications. |

## Interface languages

DiskForge v0.9.0 localizes the document workspace and the FAT-template, safe boot-code import, editable fixed-VHD, partition-selection, safe ISO replacement, legacy ZIP-container, read-only mount, device MBR, removable-media, controller-floppy, and guarded UFI USB floppy paths at runtime. Select **Tools → Language** to switch immediately between the six United Nations working languages—**Arabic, Chinese, English, French, Russian, and Spanish**—plus **Japanese**. The preference is retained for the next launch. Selecting Arabic switches the complete Qt layout to right-to-left while preserving technical values such as device paths, checksums, file extensions, and the physical-write confirmation phrase `ERASE`. UFI UI coverage does not imply completed real-hardware formatting acceptance.

Read [LOCALIZATION.md](docs/LOCALIZATION.md) for the language matrix, RTL behavior, safety boundaries, and translation-maintenance workflow.

<p align="center">
  <img src="assets/diskforge-arabic-rtl.png" alt="DiskForge interface in Arabic with right-to-left layout" width="700">
</p>

## What it does

DiskForge brings the most useful image-management workflows into one original, auditable application. The main window combines an image explorer, directory table, image metadata panel, activity log, and cancellable progress area. Destructive actions are visually isolated from ordinary browsing and require explicit confirmation.

| Workflow | Native capability | Notes |
|---|---|---|
| Create images | RAW/IMG/IMA, FAT12, FAT16, FAT32, verified legacy FAT12 floppy profiles, DMF-layout FAT12, FAT templates, ISO9660/Joliet/Rock Ridge/UDF | Create editable FAT images from standard presets, a validated FAT BPB template, or explicit IMG/IMA legacy floppy profiles. The legacy directory covers conventional PC-compatible 160 KiB through 2.88 MiB layouts and custom supported CHS geometry. ISO media can be created from a local directory with optional El Torito boot media. |
| Browse and extract | FAT12/16/32—including validated unlabeled legacy DOS floppy media—ISO9660/Joliet, fixed VHD data views, and optional NTFS/EXT2/EXT3 read-only backend | Deterministic paged trees and sortable tables avoid unbounded directory rendering. Double-click opens a non-executing document workspace for text, images, common archives, legacy setup packages, executables, and binary data. Text documents can be found, saved as a copy, and—only for writable FAT entries—edited and saved back. Fixed VHD normally opens through a temporary read-only RAW data view; a validated independent fixed-VHD copy may be reopened as a writable FAT session. |
| Change image contents | FAT injection, recursive folders, deletion, rename, timestamps, DOS attributes, and volume labels; safe rebuild-based ISO edits; optional controlled NTFS/EXT injection | Valid FAT payloads inside IMG and IMA share the same editable path. ISO changes always write a separate rebuilt image and verify staged content. Rock Ridge/UDF profiles are preserved; only a verified single-entry El Torito catalog is rebuilt, while multi-boot, hybrid, and ambiguous boot layouts are rejected. With explicitly available `ntfsprogs` or `e2fsprogs`, NTFS/EXT can receive new root-directory regular files only in a separately verified output image; no source, partition-offset, metadata, rename, delete, or overwrite write is allowed. |
| Convert formats | RAW/IMG/IMA and fixed VHD natively | IMG and IMA preserve their explicitly selected raw-image extension during conversion. VHDX, VMDK, and QCOW2 use an explicitly configured `qemu-img` adapter with visible capability reporting and cancellation. A separately configured `dmg2img` adapter can only create a new raw output from DMG; DiskForge does not mount or write DMG files. |
| Compact FAT images | Rebuild-based defragmentation | Writes a new image, preserving the original image as the recovery point. |
| Inspect and repair structures | 512-byte hex viewer/editor, validated FAT boot properties, original neutral/message templates, neutral MBR wrapping and deployment planning for FAT superfloppy images, trailing-zero-sector copy trimming, MBR backup/restore/neutral reset, and GPT CRC diagnostics | Full image or MBR backups are created before protected structural changes. Templates preserve BPB fields and use no imported boot program; wrapping, deployment preparation, and trimming always write a new file. |
| Verify and automate | SHA-256, byte-for-byte compare, graphical batch recipe studio, preflight plans, per-item result review, and versioned JSON recipes | Schema v4 adds declarative `iso_edit`, `ntfs_inject`, and `ext_inject`; all recipe writes can be previewed before execution and raw-device writes remain rejected. The visual designer covers conversion—including IMA target selection—validation, comparison, resize, injection, extraction, and container recipes. Comparisons can optionally report only full trailing zero sectors as ignored. |
| Annotate and resize | Non-invasive image comments and safe new-file RAW/FAT resize | Raw images refuse shrinking if non-zero tail bytes would be discarded. |
| Build redistributable bundles | Authenticated multi-image `.dfb` containers and SHA-256-verified multi-image self-extracting `.pyz` archives | `.dfb` supports optional scrypt-derived AES-256-GCM encryption, compression, comments, and per-file verification. Each native platform package also includes a separate `DiskForgeExtractor` that verifies and extracts `.pyz` payloads without requiring the recipient to pre-install Python. |
| Read and write physical media | Streamed device imaging and restoration | Rejects system disks, mounted targets, and capacity mismatches; typed confirmation is required. Detected optical media are read-only and export to ISO by default. |
| Low-level floppy formatting | Linux controller floppy and detected UFI USB floppy backends | `fdformat` is limited to standard controller nodes. A UFI USB candidate must be sysfs-associated with removable media, prove itself through `ufiformat -i`, use an explicitly reported capacity and the `FORMAT_FLOPPY` phrase, and is always verified with `-V`. FAT creation remains a separate, newly confirmed operation; real hardware acceptance is still required for each drive model. |

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
diskforge-cli ntfs-inject-status
diskforge-cli ext-inject-status
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
| FAT12 / FAT16 / FAT32 | Yes | Yes | Yes |
| ISO9660 / Joliet / Rock Ridge / UDF | Yes | Read/extract; safely rebuild into a separate edited image | Create from folder; Rock Ridge/UDF profile creation |
| Fixed VHD | Yes | Temporary read-only data view and conversion | Yes |
| VHDX / VMDK / QCOW2 | With adapter | Temporary read-only RAW view after configured conversion | With adapter |
| NTFS / EXT2 / EXT3 / EXT4 | Signature or partition hint | Read/list/extract with the optional Sleuth Kit backend; optional controlled new-output root-file injection with configured `ntfsprogs` / `e2fsprogs` | External backend only: standalone offset-0 volumes, new regular root files, no overwrite; source SHA-256, read-back SHA-256, and filesystem validation are required. |
| HFS / HFS+ | Signature or partition hint | Read/list/data-fork extract with the optional Sleuth Kit backend | Read-only; no journaled HFS+ write, resource-fork reconstruction, or filesystem repair. |
| DiskForge bundle (`.dfb`) | Header and authenticated manifest | Extract and verify; optional AES-256-GCM password protection | Create from one or more local images. |
| El Torito boot catalog | Inspect | Export boot image; safely preserve one verified initial entry during ISO rebuild | Create new bootable ISO media from a directory and optional local boot image. Multi-section/multi-boot, hybrid-system-area, or ambiguous mappings are rejected during rebuild. |
| DMG | Signature hint | Not natively modified | Use a compatible external workflow. |

DiskForge exposes unsupported editing paths honestly instead of attempting unsafe writes. Legacy profile creation is intentionally limited to flat, FAT-compatible sectors of 512, 1024, 2048, or 4096 bytes; 128/256-byte-sector media, GCR or variable-sector encodings, hard-sectored disks, non-FAT filesystems, copy-protected tracks, and flux/bitcell captures remain raw preservation/inspection workflows. Configure `qemu-img` through **Tools → Preferences** when virtual-disk conversion is needed. NTFS/EXT read-only browsing requires locally installed Sleuth Kit `fls` and `icat`; optional controlled injection requires explicitly configured `ntfscp`/`ntfsls`/`ntfscat` or `debugfs`/`e2fsck`. DiskForge never downloads, mounts, or runs an external converter silently. Read [FILESYSTEM_INJECTION.md](docs/FILESYSTEM_INJECTION.md) for the exact copy-on-write contract and unsupported paths.

## Engineering quality

The project includes automated coverage for FAT creation and advanced metadata editing, bootable ISO creation and El Torito inspection, original boot template BPB preservation, fixed VHD temporary browsing and cleanup, deployment planning, conservative zero-tail reports, native drag-and-drop contracts, complete graphical batch-recipe editing and no-side-effect preflight, document preview/find/save-back behavior, paged directory traversal, seven-language coverage for the complete workspace, public API sessions, portable settings, task-center history, persistent directory views and font preferences, theme selection, cross-platform optical-device classification, checksums, authenticated image bundles, safe resizing, GPT CRC diagnostics, MBR lifecycle protection, read-only EXT integration, self-extractors, device-write safety, directory export, and rebuild-based FAT compaction. pytest uses strict configuration, strict marker checks, and warning-as-error behavior; the GUI is also validated in an off-screen environment. Continuous integration runs the same quality gate on Windows, Linux, macOS Intel, and macOS Apple Silicon, then packages each native target. Version tags are validated against project metadata and a pre-existing release causes publication to fail rather than overwrite its assets.

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
QT_QPA_PLATFORM=offscreen python scripts/gui_i18n_smoke.py
```

Read [BUILDING.md](docs/BUILDING.md) for build and release details, [API.md](docs/API.md) for the stable Python integration facade, [VALIDATION.md](docs/VALIDATION.md) for optional real-filesystem and UFI hardware acceptance, [FILESYSTEM_INJECTION.md](docs/FILESYSTEM_INJECTION.md) for optional NTFS/EXT write constraints, and [COMPLETION_ACCEPTANCE.md](docs/COMPLETION_ACCEPTANCE.md) for the auditable convergence boundary. The visual smoke-test note is available in [gui_validation.md](artifacts/gui_validation.md).

## Contributing

Issues and pull requests are welcome. Keep changes focused, add regression tests for behavior changes, and never include real disk images, credentials, private paths, or generated build output in commits.

## License

DiskForge is released under the [MIT License](LICENSE).
