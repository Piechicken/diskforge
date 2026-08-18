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
| Windows x64 | `DiskForge-v0.4.0-windows-x64.zip` | Extract, then run `DiskForge.exe`. |
| Linux x64 | `DiskForge-v0.4.0-linux-x64.zip` | Extract, then run `./DiskForge`. |
| macOS Intel | `DiskForge-v0.4.0-macos-intel-x64.zip` | Extract, then move `DiskForge.app` to Applications. |
| macOS Apple Silicon | `DiskForge-v0.4.0-macos-arm64.zip` | Extract, then move `DiskForge.app` to Applications. |

## Interface languages

DiskForge v0.4.0 localizes its desktop interface at runtime. Select **Tools → Language** to switch immediately between the six United Nations working languages—**Arabic, Chinese, English, French, Russian, and Spanish**—plus **Japanese**. The preference is retained for the next launch. Selecting Arabic switches the complete Qt layout to right-to-left while preserving technical values such as device paths, checksums, file extensions, and the physical-write confirmation phrase `ERASE`.

Read [LOCALIZATION.md](docs/LOCALIZATION.md) for the language matrix, RTL behavior, safety boundaries, and translation-maintenance workflow.

<p align="center">
  <img src="assets/diskforge-arabic-rtl.png" alt="DiskForge interface in Arabic with right-to-left layout" width="700">
</p>

## What it does

DiskForge brings the most useful image-management workflows into one original, auditable application. The main window combines an image explorer, directory table, image metadata panel, activity log, and cancellable progress area. Destructive actions are visually isolated from ordinary browsing and require explicit confirmation.

| Workflow | Native capability | Notes |
|---|---|---|
| Create images | RAW/IMG, FAT12, FAT16, FAT32, DMF-layout FAT12, ISO9660/Joliet | Create editable FAT images, documented 80×2×21-sector DMF-layout image files, or author ISO media from a local directory. |
| Browse and extract | FAT12/16/32, ISO9660/Joliet, and optional NTFS/EXT2/EXT3 read-only backend | Tree view, bulk extraction, image information, MBR/GPT inspection, path-preserving or flattened output, and explicit conflict policy. |
| Change image contents | FAT injection, recursive folders, deletion, rename, timestamps, DOS attributes, and volume labels | ISO, NTFS and EXT are deliberately exposed through read-only paths. |
| Convert formats | RAW/IMG and fixed VHD natively | VHDX, VMDK, and QCOW2 use an explicitly configured `qemu-img` adapter. |
| Compact FAT images | Rebuild-based defragmentation | Writes a new image, preserving the original image as the recovery point. |
| Inspect and repair structures | 512-byte hex viewer/editor, validated FAT boot properties, neutral MBR wrapping for FAT superfloppy images, trailing-zero-sector copy trimming, MBR backup/restore/neutral reset, and GPT CRC diagnostics | Full image or MBR backups are created before protected structural changes; MBR wrapping and trimming always write a new file. |
| Verify and automate | SHA-256, byte-for-byte compare, and versioned JSON batch recipes | Batch supports safe file-image operations, multi-source extraction with planned incrementing names, and deliberately rejects raw-device writes. |
| Annotate and resize | Non-invasive image comments and safe new-file RAW/FAT resize | Raw images refuse shrinking if non-zero tail bytes would be discarded. |
| Build redistributable bundles | Authenticated multi-image `.dfb` containers and SHA-256-verified multi-image self-extracting `.pyz` archives | `.dfb` supports optional scrypt-derived AES-256-GCM encryption, compression, comments, and per-file verification. |
| Read and write physical media | Streamed device imaging and restoration | Rejects system disks, mounted targets, and capacity mismatches; typed confirmation is required. |

## Safety first

> A disk-image utility should make dangerous operations **hard to trigger accidentally**.

DiskForge never mounts an image or writes a physical device automatically. Before a physical write, it checks capacity, mounted state, and system-disk status, then requires the exact phrase `ERASE`. The write path can verify bytes after completion. Boot-sector changes also create a full-image backup first. Always work with disposable test images before operating on irreplaceable media.

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
diskforge-cli iso-boot-info bootable.iso
diskforge-cli export-boot-image bootable.iso boot.img
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
| RAW / IMG / IMA / BIN | Yes | FAT payloads | Yes |
| FAT12 / FAT16 / FAT32 | Yes | Yes | Yes |
| ISO9660 / Joliet | Yes | Read and extract | Create from folder |
| Fixed VHD | Yes | Convert payload | Yes |
| VHDX / VMDK / QCOW2 | With adapter | Through conversion workflow | With adapter |
| NTFS / EXT2 / EXT3 | Signature or partition hint | Read/list/extract with the optional Sleuth Kit backend; never modified | Use a compatible external workflow for writes. |
| DiskForge bundle (`.dfb`) | Header and authenticated manifest | Extract and verify; optional AES-256-GCM password protection | Create from one or more local images. |
| El Torito boot catalog | Inspect | Read-only boot-image export | Existing ISO content is never modified. |
| DMG | Signature hint | Not natively modified | Use a compatible external workflow. |

DiskForge exposes unsupported editing paths honestly instead of attempting unsafe writes. Configure `qemu-img` through **Tools → Preferences** when virtual-disk conversion is needed. NTFS/EXT read-only browsing requires locally installed Sleuth Kit `fls` and `icat` executables; the application never downloads, mounts, or runs an external converter silently.

## Engineering quality

The project includes automated coverage for FAT creation and advanced metadata editing, ISO creation and extraction, fixed VHD creation, checksums, authenticated image bundles, byte comparison, safe resizing, GPT CRC diagnostics, MBR lifecycle protection, read-only EXT integration, self-extractors, device-write safety, boot-sector backup, directory export, and rebuild-based FAT compaction. The GUI is also validated in an off-screen environment. Continuous integration runs tests on Windows, Linux, macOS Intel, and macOS Apple Silicon, then packages each native target.

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
QT_QPA_PLATFORM=offscreen python scripts/gui_i18n_smoke.py
```

Read [BUILDING.md](docs/BUILDING.md) for build and release details. The visual smoke-test note is available in [gui_validation.md](artifacts/gui_validation.md).

## Contributing

Issues and pull requests are welcome. Keep changes focused, add regression tests for behavior changes, and never include real disk images, credentials, private paths, or generated build output in commits.

## License

DiskForge is released under the [MIT License](LICENSE).
