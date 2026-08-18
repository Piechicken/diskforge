# Changelog

All notable changes to DiskForge are documented in this file. The project uses semantic versioning for public releases.

## v0.4.0 — Media Compatibility and Boot Workflows

DiskForge v0.4.0 extends the desktop application and command line with portable media-layout, boot-distribution, and multi-image automation workflows. Every transformation that changes image bytes creates a separately named output file; ISO El Torito inspection and boot-image export remain strictly read-only for the source ISO.

| Area | Additions in v0.4.0 |
|---|---|
| Media layouts | Create and positively detect documented 80×2×21-sector FAT12 DMF-layout image files. The workflow creates image files only; it never attempts controller-specific physical floppy formatting. |
| FAT deployment | Create a neutral, single-partition MBR wrapper around a recognized FAT superfloppy image while preserving the original source. The wrapper contains no imported boot program. |
| Conservative trimming | Copy a sector-aligned image after removing only trailing, full zero-filled sectors, with a caller-selected sector-aligned minimum retained size. No filesystem or partition metadata is inferred or repaired. |
| Boot distribution | Inspect ISO9660 El Torito boot catalogs and export a selected declared boot image without modifying the ISO. The command line supports structured JSON output for inspection and export workflows. |
| Automation and archives | Batch schema v3 adds multi-source extraction with safe planned incrementing destination names. Version 2 self-extractors package multiple named images and validate each item before extraction. |
| Desktop and localization | The desktop app adds DMF creation, FAT-to-MBR wrapping, zero-tail trimming, and El Torito inspection/export actions. All seven supported interface languages include labels for the new primary actions. |
| Release delivery | The GitHub Actions release job collects all four platform archives internally, produces checksums, and creates the public release without local artifact download-and-reupload steps. |

### Validation

The release candidate adds regression coverage for DMF geometry and detection, neutral MBR wrapping, conservative zero-tail trimming, El Torito catalog parsing and boot-image export, JSON CLI behavior, multi-source sequence planning, batch v3 extraction, and multi-image self-extractors. The full unit suite and both off-screen GUI smoke scripts are run before publication.

## v0.3.0 — Safe Professional Image Workflows

DiskForge v0.3.0 expands the application from a core image editor into a more complete, auditable workspace. The release preserves the existing safety model: physical-device writes remain foreground-only, system and mounted targets are rejected, and the exact `ERASE` phrase is still required for a write operation.

| Area | Additions in v0.3.0 |
|---|---|
| Secure distribution | New versioned `.dfb` multi-image container with compression, comments, per-item SHA-256 verification, optional scrypt-derived AES-256-GCM encryption, authenticated extraction, and traversal-safe paths. |
| FAT editing | Rename files and directories, edit standard DOS attributes, update creation/modification/access timestamps, and change volume labels. |
| Extraction | Explicit layout choices for preserving paths, flattening output, or ignoring selected subdirectories; explicit conflict policy for stopping, overwriting, skipping, or auto-renaming. |
| Inspection and recovery | Byte-for-byte comparison with first-difference offset; safer RAW/FAT new-file resizing; non-invasive image-comment sidecars; structured FAT OEM/label/serial editing; MBR backup, confirmed restoration, and neutral reset; GPT CRC, bounds, overlap, and backup-header diagnostics. |
| Read-only filesystems | Optional Sleuth Kit adapter for browsing and extracting NTFS and EXT2/EXT3 images without mounting or modifying them. |
| Automation | Batch schema v2 for safe conversions, verification, compare, resize, extraction, FAT injection, and unencrypted bundle workflows; physical-device actions remain rejected. |
| Desktop and CLI | New GUI actions for the major editing and validation workflows, six-column file view with attributes, seven-language labels for the new primary actions, and expanded `diskforge-cli` subcommands with JSON output. |

### Optional integrations

NTFS and EXT2/EXT3 browsing require locally installed Sleuth Kit `fls` and `icat` executables. Virtual-disk conversion for VHDX, VMDK, and QCOW2 continues to require a locally configured `qemu-img` executable. DiskForge does not install, download, mount, or invoke external tools without an explicit user configuration or invocation.

### Validation

The release candidate adds automated tests for encrypted bundle authentication and tamper rejection, FAT metadata persistence, extraction policy behavior, RAW/FAT resizing safety, comparison reports, MBR lifecycle protection, GPT validation, batch v2, CLI workflows, metadata sidecars, and optional real EXT2 read-only integration. Full unit tests and both GUI smoke scripts pass in the release environment.

## v0.2.0 — Multilingual Desktop Interface

Added runtime interface switching for Arabic (RTL), Simplified Chinese, English, French, Russian, Spanish, and Japanese.

## v0.1.0 — Initial Public Release

Introduced cross-platform FAT/ISO image workflows, RAW/IMG, fixed VHD, partition inspection, boot-sector tools, SHA-256 verification, safe physical-device imaging, batch recipes, self-extracting archives, and the Qt desktop interface.
