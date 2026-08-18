# Changelog

All notable changes to DiskForge are documented in this file. The project uses semantic versioning for public releases.

## v0.6.0 — Converged Boot, Deployment, Virtual-Disk, and Workflow Studio

DiskForge v0.6.0 is a consolidated capability release rather than a narrow workflow patch. It connects image creation, boot preparation, virtual-disk browsing, deploy planning, automation preflight, portable settings, and visible task history through the same safety model: source images remain intact until an explicit output is chosen, physical writes retain the existing foreground `ERASE` confirmation, and unattended batch recipes still reject raw-device actions.

| Area | Additions in v0.6.0 |
|---|---|
| Bootable ISO authoring | Create ISO9660/Joliet images with an optional local El Torito boot image, standard media mode, platform ID, load segment, and optional boot-information table. External boot images are copied into the new ISO; the source file remains unchanged. |
| Original boot templates | A small, auditable catalog provides a neutral halt sector and a DiskForge message sector. Templates preserve the existing FAT BPB, replace only executable boot-code bytes, use no imported boot program, and create a complete image backup before application. |
| Virtual-disk browsing | Fixed VHD images now open through an isolated temporary RAW data view that excludes the VHD footer. VHDX, VMDK, and QCOW2 use the same read-only temporary workflow after an explicitly configured converter is available. Temporary copies are removed on close. |
| FAT deployment | Prepare a fresh neutral-MBR single-partition deployment image, review its LBA and partition details, and only then choose the separately protected physical-device operation if required. The command line can create and emit a structured deployment plan without touching a device. |
| Conservative device reports | Byte comparison can optionally report equal data after ignoring only full, sector-aligned trailing zero sectors. Default comparison behavior remains strict, and no input is ever modified. |
| Automation and API | Batch recipes gain a no-side-effect preflight plan and CLI `--dry-run`; the desktop reviews this plan before execution. A typed `diskforge.api` facade exposes safe inspection, hashing, FAT creation, content operations, comparison, conversion, and managed filesystem sessions for Python hosts. |
| Desktop resilience | The workspace includes a task center showing queued, running, completed, failed, and cancellation states; persistent interface font family and size controls; explicit portable INI settings via `--portable`, `--portable=DIR`, `--portable-directory DIR`, or `DISKFORGE_PORTABLE_DIR`; and seven-language labels for the new primary controls. |
| Validation | New regression coverage exercises bootable ISO creation, original template BPB preservation and backups, temporary VHD browser cleanup, deployment planning, zero-tail reporting, batch preflight, public API, portable settings, task center, font preferences, CLI JSON behavior, and the desktop VHD browse path. |

### Validation

The full suite runs under strict pytest configuration with warnings promoted to errors. Project modules compile before test execution, and both off-screen desktop smoke scripts run after the complete suite. The source and continuous-integration configuration retain the same warning policy.

## v0.5.0 — Modern Workspace, Drag-and-Drop, and Strict Quality

DiskForge v0.5.0 turns routine image work into a more direct desktop workflow. The release introduces native file-manager drag-and-drop while preserving the product’s safety model: only local file URLs are accepted, injection is enabled only for writable FAT images, and drag-out always extracts copies into an isolated temporary workspace.

| Area | Additions in v0.5.0 |
|---|---|
| Native drag-and-drop | Drag local files or folders onto a writable FAT image to inject them. Drop on a displayed image folder to target that folder. Drag selected FAT, ISO, NTFS, or EXT image entries out to another local application after a temporary, copy-only extraction. |
| Desktop workspace | New professional light and midnight themes; a branded workspace header; high-contrast focus, selection, progress, panel, tab, and menu states; persistent detailed-table and icon-grid directory views; sorting and per-view selection restoration. |
| Everyday navigation | Persistent recent-image menu with dead-path cleanup; double-click safe preview through a temporary extracted copy and the system default application; execution-risk extensions require an explicit confirmation. |
| Guided automation | A graphical batch extraction designer collects multiple image sources, previews validated incrementing output names, selects extraction and conflict policy, writes schema-v3 JSON, and can run the saved recipe immediately. |
| Optical media | Linux `rom` devices are identified as read-only optical media. The device workflow defaults these sources to an `.iso` export path and blocks accidental writes. |
| Localization | New primary desktop actions are catalogued in Simplified Chinese, English, Spanish, French, Russian, Arabic, and Japanese. |
| Quality gate | pytest now uses strict configuration and marker checks, promotes warnings to errors, and runs in that mode in continuous integration. The known legacy namespace warning is isolated only around the third-party FAT adapter import; all DiskForge code and all other warning sources remain strict. |
| CI maintenance | Official hosted-runner actions use current Node.js-24-compatible majors, removing obsolete action-runtime diagnostics while retaining direct internal artifact aggregation and four-platform release packaging. |

### Validation

The release candidate adds tests for local URL drop acceptance and rejection, target-directory resolution, drag-out requests, graphical batch recipe creation and validation, persistent directory view switching, light/dark theme selection, and Linux optical-device classification. The full suite runs cleanly with strict pytest warning handling, while both off-screen GUI smoke scripts run without platform-plugin diagnostic output.

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
