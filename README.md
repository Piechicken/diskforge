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
| Windows x64 | `DiskForge-v0.1.0-windows-x64.zip` | Extract, then run `DiskForge.exe`. |
| Linux x64 | `DiskForge-v0.1.0-linux-x64.zip` | Extract, then run `./DiskForge`. |
| macOS Intel | `DiskForge-v0.1.0-macos-intel-x64.zip` | Extract, then move `DiskForge.app` to Applications. |
| macOS Apple Silicon | `DiskForge-v0.1.0-macos-arm64.zip` | Extract, then move `DiskForge.app` to Applications. |

## What it does

DiskForge brings the most useful image-management workflows into one original, auditable application. The main window combines an image explorer, directory table, image metadata panel, activity log, and cancellable progress area. Destructive actions are visually isolated from ordinary browsing and require explicit confirmation.

| Workflow | Native capability | Notes |
|---|---|---|
| Create images | RAW/IMG, FAT12, FAT16, FAT32, ISO9660/Joliet | Create editable FAT images or author ISO media from a local directory. |
| Browse and extract | FAT12/16/32 and ISO9660/Joliet | Tree view, bulk extraction, image information, and MBR/GPT inspection. |
| Change image contents | FAT injection, recursive folders, deletion, timestamp editing | ISO files are treated as read-only media and can be rebuilt from a folder. |
| Convert formats | RAW/IMG and fixed VHD natively | VHDX, VMDK, and QCOW2 use an explicitly configured `qemu-img` adapter. |
| Compact FAT images | Rebuild-based defragmentation | Writes a new image, preserving the original image as the recovery point. |
| Inspect boot sectors | 512-byte hex viewer/editor and sector import | Creates a full image backup before boot-sector replacement. |
| Verify and automate | SHA-256, JSON batch recipes, audited logs | Unattended batch recipes deliberately reject raw-device writes. |
| Build redistributable bundles | SHA-256-verified self-extracting `.pyz` archives | Can be packaged in a native launcher workflow. |
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
| NTFS / EXT / DMG | Signature or partition hint | Not natively modified | Use a compatible external workflow |

DiskForge exposes unsupported editing paths honestly instead of attempting unsafe writes. Configure `qemu-img` through **Tools → Preferences** when virtual-disk conversion is needed; the application never downloads or runs an external converter silently.

## Engineering quality

The project includes automated coverage for FAT creation and editing, ISO creation and extraction, fixed VHD creation, checksums, MBR parsing, self-extractors, device-write safety, boot-sector backup, directory export, and rebuild-based FAT compaction. The GUI is also validated in an off-screen environment. Continuous integration runs tests on Windows, Linux, macOS Intel, and macOS Apple Silicon, then packages each native target.

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
```

Read [BUILDING.md](docs/BUILDING.md) for build and release details. The visual smoke-test note is available in [gui_validation.md](artifacts/gui_validation.md).

## Contributing

Issues and pull requests are welcome. Keep changes focused, add regression tests for behavior changes, and never include real disk images, credentials, private paths, or generated build output in commits.

## License

DiskForge is released under the [MIT License](LICENSE).
