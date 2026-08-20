# Changelog

All notable changes to DiskForge are documented in this file. The project uses semantic versioning for public releases.

## v0.10.0.dev0 — Safe ISO Reconstruction, Legacy IMG/IMA Depth, and Controlled Filesystem Injection

DiskForge v0.10.0.dev0 is an unreleased development checkpoint. It expands verified image-content workflows while preserving the principle that a byte-stream extension or a boot catalog is never treated as permission to make an unsafe or ambiguous modification.

| Area | Additions in v0.10.0.dev0 |
|---|---|
| Rebuild-based ISO editing | ISO content can be rebuilt into a separately named output after explicit file/directory addition, deletion, and directory creation. Every staged file is SHA-256 verified; the source remains unchanged. Rock Ridge and UDF naming profiles are detected and preserved. |
| Controlled El Torito preservation | Safe reconstruction preserves a verified single initial El Torito entry, including the boot image, bootable state, platform ID, media type, load segment, system type, load-sector count, and boot-information-table choice. Boot image and generated catalog paths are protected from edits. Multi-section/multi-boot catalogs, hybrid system areas, and non-unique catalog mappings are rejected rather than rewritten. |
| ISO command and batch closure | `edit-iso` is available in the CLI. Batch schema v4 adds declarative `iso_edit`, with preview-before-write and the same core safety guards. The desktop ISO action now describes its actual safe scope rather than implying that only plain ISO media is accepted. |
| Legacy IMG/IMA creation | IMA is now a distinct first-class raw-image target, while retaining its flat-sector semantics. The desktop, CLI, batch conversion, and format selector support explicit IMG or IMA output. New verified FAT12 profiles cover conventional PC-compatible 5.25-inch and 3.5-inch 160 KB through 2.88 MB layouts, including DMF and 82-track layouts; custom supported CHS geometry is explicit. |
| Legacy image editing | A valid FAT IMA follows the same native workflow as a FAT IMG: browse, internal preview, inject, delete, rename, adjust standard attributes, extract, hash, and convert. The UI offers the full profile directory, IMG/IMA selection, custom geometry, and complete seven-language labels. |
| Controlled NTFS/EXT injection | Optional `ntfsprogs` and `e2fsprogs` adapters can add regular local files to a **new standalone output image**. The source remains SHA-256 unchanged; targets are root-only and must not exist; write-back is preflighted or undo-logged, read back, SHA-256 verified, and reopened/validated before promotion. Desktop, CLI, and batch v4 expose the same copy-on-write contract. |
| Controlled classic HFS injection | Optional `hfsutils` support adds root-level regular local files to a **new standalone classic HFS output** only. Each operation receives an isolated `HOME`; `hls` stderr is parsed for the required absence diagnostic before `hcopy -r`; every raw data fork is read back and SHA-256 verified; the source digest and HFS signature are rechecked before atomic promotion. Desktop, CLI `inject-hfs`/`hfs-inject-status`, batch v4 `hfs_inject`, the graphical designer, and all seven interface languages expose the same contract. HFS+ remains read-only. |
| Verified classic HFS creation | Optional `HfsImageCreator` creates a new standalone classic HFS regular-file image through explicitly available `hformat`. It accepts only a new file target of at least 800 KiB in 512-byte units and a constrained 1–27-character ASCII volume label; it rejects devices, existing targets, partition maps, partition ordinals, `-f`, MFS, and HFS+. Creation allocates a unique sibling temporary file, uses isolated `HOME`, verifies the HFS signature and output SHA-256, then atomically promotes the output. Desktop New Image, CLI `create-hfs`/`hfs-create-status`, batch v4 `hfs_create`, the graphical designer, and seven-language text all expose this exact optional contract. |
| Explicit read-only partition browsing | A validated, caller-selected MBR/GPT table index can now open FAT, NTFS, EXT, classic HFS, or HFS+ partitions through the same core route. FAT retains its established writable session; all non-FAT partitions are passed to the read-only adapter at their exact validated byte offset. Unknown partitions and every non-FAT write request are rejected before an external backend starts. Desktop, CLI, SDK, GUI action state, and tests use this one route. |
| Universal directory reports | Every browsable filesystem now shares a stable, cancellation-aware full traversal for text or HTML directory reports with escaped HTML paths. The report writes only a new local report file; it does not alter the source image. CLI `export-listing`, desktop export/print, and batch v4 `export_listing` can use an explicitly selected read-only partition. The graphical recipe designer and all seven UI languages cover the new operation. |
| FAT regular-file movement | A regular file may now move into an existing directory within a writable FAT image without overwrite. Core preflight rejects the root, missing/non-directory targets, target collisions, read-only sessions, and all directory moves before the backend changes bytes. CLI `move-fat`, SDK `DiskForgeClient.move_fat`, batch v4 `move`, the desktop action, graphical recipe designer, optional validated FAT partition routing, and all seven UI languages expose one consistent contract. |
| Safe ZIP single-image browsing | A regular `.zip` may now open as a **read-only** image container when it contains exactly one safe, root-level, directly browsable image payload. The core streams that payload into an auto-cleaned private temporary session, re-identifies its filesystem, then routes CLI `list`/`extract`/`export-listing`, SDK filesystem/extraction, batch v4 read operations, and desktop browse/preview through the same read-only adapter. The ZIP source never changes. |

### Development validation

The current v0.10.0.dev0 checkpoint passes **350 tests**, has **3 explicitly skipped optional real-fixture tests**, and emits **zero warnings** under `QT_QPA_PLATFORM=offscreen pytest -W error`. The regression set includes standard/Rock Ridge/UDF ISO rebuilds, protected single-entry El Torito preservation and rejection boundaries, 15 legacy FAT12 profiles, IMG/IMA editing and conversion, desktop creation, CLI creation, batch IMA conversion, batch schema v4, seven-language catalog coverage, optional `ntfsprogs`/`e2fsprogs` integration checks for controlled NTFS/EXT injection, an `hfsutils` synthetic 800 KiB classic-HFS copy-on-write suite covering isolated state, duplicate-target refusal, raw-data-fork read-back SHA-256, CLI, GUI, and batch execution, and a classic-HFS creation suite covering constrained labels/sizes, absent/existing/device targets, signature/SHA-256 verification, CLI JSON, visual creation, and v4 recipe serialization. It additionally covers explicit non-FAT MBR/GPT read-only offsets, source-safe text/HTML directory reports, CLI/SDK/desktop routing, batch `export_listing`, graphical recipe round-tripping, seven-language no-fallback catalog entries, and FAT regular-file movement through core, CLI JSON, SDK, batch preview/execution, desktop action state, and visual recipe round-trip tests. It further covers safe ZIP single-image materialization, source hash preservation, payload re-identification, unsafe entry and compression rejection, cancellation cleanup, CLI/SDK/batch read paths, conversion/write refusal, and desktop read-only action state.

### Explicit boundaries

v0.10.0.dev0 does **not** claim editable support for every historical floppy encoding. A regular ZIP is not a generic image filesystem or conversion format: only one root-level, unencrypted Stored/Deflated `.img`, `.ima`, `.bin`, `.dd`, `.dmf`, `.iso`, or `.hfs` payload no larger than 2 GiB can be materialized for browsing; multiple or directory entries, unsafe names, unknown methods, empty/oversized/unknown payloads, recursive containers, virtual-disk chains, and all ZIP writes are rejected. Temporary payloads are removed on close, error, or cancellation.  FAT movement supports **regular files only**: it requires an existing target directory, never overwrites or merges entries, and deliberately rejects directory moves because the available generic directory path is copy-then-delete rather than atomic. Same-directory renaming remains a distinct `rename` workflow.  Flat-sector FAT creation supports 512, 1024, 2048, and 4096-byte sectors. 128/256-byte-sector media, GCR or variable-sector encodings, hard-sectored disks, copy-protected tracks, non-FAT filesystems, and flux/bitcell captures remain raw-byte inspection, preservation, checksum, and comparison workflows unless and until a separately validated track-level backend exists. NTFS/EXT/classic-HFS injection is **optional external-backend support**, not native or universal writing: it rejects partition-offset and physical-device paths, pre-existing targets, directories, metadata/ACL/ADS work, delete/rename, and all in-place writes. Classic HFS transfers raw data forks only; no MacBinary, Finder metadata, or resource-fork reconstruction is claimed. HFS+ remains read-only; no journaled HFS+ write or filesystem repair is claimed.

## v0.9.0 — Controlled Media Depth, Read-Only Reach, and Verifiable Delivery

DiskForge v0.9.0 broadens the auditable image-management workspace while preserving the project’s core rule: a new capability is not presented as native, writable, cross-platform, or hardware-validated when its backend and evidence do not support that claim.

| Area | Additions in v0.9.0 |
|---|---|
| ISO safe replacement | Replace one ordinary ISO9660/Joliet file only when the replacement has exactly the same logical length. DiskForge writes a separate copy, reopens it, validates the replaced payload hash, and confirms that the source ISO remains unchanged. UDF, Rock Ridge, multi-extent, directory, and size-changing paths are rejected. |
| Explicit partition workflows | MBR/GPT partition inspection now yields stable, explicit indices. FAT partitions can be deliberately selected for browsing and editing; no first-partition inference is used. NTFS, EXT, HFS, and HFS+ retain read-only filesystem adapters with explicit byte offsets. |
| Controlled device lifecycle | Safe device-MBR backup, restore, and neutralization use device snapshots, mounted/system-device refusal, backup preservation, confirmation phrases, readback verification, CLI JSON, and desktop entry points. Removable-media FAT formatting is separately guarded and reopens the completed filesystem for verification. |
| Read-only filesystem and mounting paths | DiskForge adds controlled read-only native-system mount sessions for supported host backends, plus HFS/HFS+ Sleuth Kit listing and data-fork extraction. NTFS, EXT, HFS, and HFS+ remain read-only; no mutation, repair, resource-fork fidelity, or silent tool installation is claimed. |
| Virtual and legacy containers | A configured qemu-img adapter exports verified dynamic VHD from an independent raw FAT work image. ZIP-compatible IMZ/WLZ single-payload legacy containers support safe creation and extraction; this is a transparent compatible subset, not a claim of complete historical proprietary-container support. |
| UFI USB floppy safety | Linux adds a capability-gated UFI USB floppy path. It accepts only sysfs-associated removable generic-SCSI nodes, requires `ufiformat -i` discovery, demands an explicitly reported capacity and `FORMAT_FLOPPY`, always uses `-V`, and never uses `-F`. Controller `fdformat` remains separate. |
| Native verified extraction | Every platform package now includes a separate `DiskForgeExtractor` executable. It verifies and extracts existing DiskForge `.pyz` bundles without requiring recipients to pre-install Python; it validates manifest paths, lengths, and SHA-256 values and does not append data to the desktop application binary. |
| Batch, CLI, GUI, and localization | Batch schema v4 adds safe legacy-container and ISO-replacement operations. CLI and Qt workflows cover the new supported paths; all primary GUI strings are translated across Simplified Chinese, English, Spanish, French, Russian, Arabic, and Japanese. |
| Real-sample acceptance | Optional, out-of-repository acceptance tests cover publicly available NTFS, EXT4, and journaled HFS+ samples when a licensed local fixture directory and Sleuth Kit are present. Standard CI skips these tests explicitly rather than downloading binary corpora. |

### Validation

The release candidate passes **185 strict pytest tests with 3 explicitly skipped optional real-fixture tests and zero warnings** in the ordinary test environment. With documented local fixtures available, the optional NTFS, EXT4, and HFS+ acceptance set passes **3/3**. GitHub Actions successfully ran the strict test and native packaging jobs on **Windows x64, Linux x64, macOS Intel, and macOS Apple Silicon**; all four generated platform packages include the independent verified extractor.

### Explicit boundaries

v0.9.0 does **not** claim NTFS/EXT/HFS/HFS+ writing or repair; UDF/Rock Ridge ISO replacement; complete compatibility with undocumented historical compressed containers; a bundled filesystem driver; or real-hardware UFI USB floppy validation. The UFI workflow is implemented and simulation-tested, but real low-level formatting/readback remains deferred because no disposable physical floppy media was supplied. Any future hardware result must be documented separately rather than retroactively inferred from CI.

## v0.8.0 — Verified Layouts, Safe Boot Import, and Controlled Media Workflows

DiskForge v0.8.0 extends the usable image-editing core without converting optional adapters or unavailable hardware control into false native claims. The release makes reproducible FAT layout creation, boot-code import, and fixed-VHD FAT editing concrete, auditable workflows. It also adds explicit capability reporting and cancellation for external virtual-disk and DMG bridges, plus an independent read-only physical-media acquisition queue.

| Area | Additions in v0.8.0 |
|---|---|
| Reproducible FAT layouts | A validated FAT BPB layout can be imported from a complete image template, inspected through CLI JSON, and used by the desktop to create a new editable FAT image. Unsupported sector sizes, FAT counts, geometry, media descriptors, and size mismatches are rejected before creation. |
| Safe boot-sector import | Signed 512-byte sector files can be imported through a dedicated safe path. DiskForge preserves the target FAT jump/BPB/extended-BPB data, replaces only executable boot-code bytes, and creates a complete sibling image backup before any write. The CLI requires the exact `IMPORT_BOOT_SECTOR` confirmation phrase. |
| Editable fixed VHD copies | A fixed VHD containing FAT can now be copied to a separately named editable VHD. The virtual data region and footer are validated before and after copying, and the editable copy is reopened as a writable FAT session. Original VHD files remain read-only; dynamic VHD remains outside this native write path. |
| Optional converter contracts | The qemu-img path now provides an explicit capability report for VHDX, VMDK, and QCOW2, detects an unavailable executable, and terminates a configured conversion process when a task is cancelled. These remain optional external adapters rather than native format implementations. |
| Controlled DMG bridge | A separately configured `dmg2img` adapter can create a new raw HFS+ output from a DMG. DiskForge does not mount, edit, or write DMG files; unavailable adapters are reported clearly and no third-party tool is downloaded automatically. |
| Read-only device acquisition queue | A new desktop and CLI queue only reads selected removable or optical media to independently named image files. Each successful item receives a SHA-256 audit entry. It has no write-device option; the pre-existing guarded foreground write workflow remains separate. |
| Seven-language coverage | The FAT layout, boot import, fixed-VHD, converter, DMG, and media-acquisition user paths have complete Simplified Chinese, English, Spanish, French, Russian, Arabic, and Japanese catalog entries guarded against English fallback. |

### Validation

The release candidate passes **130 tests** under strict pytest configuration with all Python warnings treated as errors. It includes core, CLI, GUI-discovery, failure, cancellation, backup, and localization regressions for the new workflows. Both user-provided historical FAT12 floppy samples were opened and enumerated again; the mouse-driver image’s `README.TXT` was extracted as readable text without invoking a system default application. The packaged Linux application was rebuilt, verified to contain the runtime icon, launched offscreen without application diagnostics, and checked for missing new-core-module imports.

### Explicit boundaries

v0.8.0 does **not** claim native NTFS/EXT writing, dynamic-VHD writing, generic HFS/HFS+ browsing, arbitrary DMG editing, controller-level physical floppy formatting, or real-hardware validation where no such device was available. Optional adapters are visible only when a user configures them; their availability and scope are reported rather than inferred.

## v0.7.5 — Document Workspace, Scalable Browsing, and Immutable Releases

DiskForge v0.7.5 completes the transition from a file-inspection dialog to a coherent image-document workspace. The release makes the supported FAT workflow genuinely editable, keeps ISO/NTFS/EXT paths correctly read-only, gives large directories bounded and repeatable navigation, and locks versioned release assets against accidental replacement.

| Area | Additions in v0.7.5 |
|---|---|
| Correct filesystem routing | FAT, ISO9660, and supported fixed-VHD browsing sessions now remain in their native adapters. The optional Sleuth Kit path is selected only for actual NTFS or EXT filesystems, removing false “unsupported” errors while keeping NTFS/EXT read-only. |
| Document-style internal preview | Preview is now an in-application document workspace with readable text layout, encoding-aware editing where allowed, find, save-copy, and explicit save-back into writable FAT images. Office and OpenDocument containers yield safe extracted text where available; executable and binary data stay non-executing. Long zero-filled binary spans are collapsed instead of rendered as pages of dots. |
| Batch recipe studio | The graphical designer can now create, review, reopen, and run safe recipes for conversion, validation, comparison, resize, injection, extraction, and container operations. A result dialog presents every item’s status and detail. Physical-device actions remain deliberately rejected from unattended recipes. |
| Scalable image browsing | Directory services now provide deterministic pages, full walks, and cache clearing. The desktop displays a controlled “load more” path and preserves sorting rather than attempting unbounded table population. Listing export and printing use the same complete traversal for FAT, ISO, NTFS, and EXT. |
| Complete seven-language interface | All document-workspace controls, batch workflow states, filesystem guidance, and dynamically generated About content are covered in Simplified Chinese, English, Spanish, French, Russian, Arabic, and Japanese, with regression checks against English fallback. |
| Native application identity | A new transparent source icon was authored for this release and regenerated as runtime PNG plus native Windows ICO and macOS ICNS assets. Bundled applications resolve the runtime PNG from the PyInstaller resource directory and have been startup-checked after packaging. |
| Optical-media recognition | Windows and macOS optical devices now receive capacity, media type, and removable/read-only properties consistently with the existing safe-device model. |
| Immutable publication | CI publishes only from `v*` tags, verifies that the tag exactly matches project metadata, and fails if a release already exists. No release command can overwrite a versioned asset. |
| Clean release ergonomics | The obsolete Qt high-DPI attribute was removed. The expected offscreen-platform `propagateSizeHints` notice is filtered only in that platform’s message handler; all Python warnings remain strict errors and other Qt diagnostics remain visible. The native build no longer over-collects unused `jaraco` and full `setuptools` development trees. |

### Validation

The release candidate passes **102 tests** under strict pytest configuration with all warnings promoted to errors. Both user-supplied historical floppy samples were opened directly: the Windows setup disk exposes its expected drivers and setup files, while the mouse-driver image exposes its DOS/Windows folders, installer payload, and readable `README.TXT`. The packaged Linux application was then launched offscreen with its actual bundled icon and emitted no application startup diagnostics.

## v0.7.0 — Legacy Media Compatibility and Native Preview

DiskForge v0.7.0 resolves the historical-media interoperability path with sample-led FAT detection and a non-executing desktop preview experience. The release keeps image bytes untouched during inspection, treats legacy media as a valid source rather than a recovery problem, and preserves the existing protection boundaries for all write operations.

| Area | Additions in v0.7.0 |
|---|---|
| Legacy FAT recognition | FAT12, FAT16, and FAT32 are now detected from a validated BPB, boot signature, geometry, media descriptor, filesystem bounds, and available reserved-FAT evidence. The optional display-label field is no longer required, allowing older 360 KB and 1.44 MB DOS-style floppy images to open normally. `.IMA` is correctly treated as a RAW/IMG alias. |
| Reliable historical browsing | Partition-offset discovery now uses the same BPB validation as image inspection. Historical FAT media can therefore move from image information to root-directory browsing through one consistent, read-only-safe path. The isolated third-party dirty-volume advisory is suppressed only while opening such a volume; all other warnings retain the strict policy. |
| Native file preview | Double-click and Preview now extract to an isolated temporary workspace and display bounded, non-executing internal results. Text, images, ZIP, TAR, GZip, standard CAB listings, InstallShield `ISc(` setup headers, SZDD signatures, DOS MZ, NE, PE, and generic binary data have appropriate text, rendered-image, archive-index, executable-structure, or hexadecimal views. No system default application is needed for a basic inspection. |
| Localization | Workspace branding and the new preview workflow—including historical package labels and executable safety messages—are catalogued in Simplified Chinese, English, Spanish, French, Russian, Arabic, and Japanese. A regression test verifies that core preview labels cannot fall back to English in non-English interfaces. |
| Application icon | DiskForge now ships a coherent navy, silver, and amber disk-and-forge application icon. Runtime PNG assets and native Windows ICO/macOS ICNS derivatives are included in source and native packages. |
| Verification hygiene | The offscreen image-open smoke test now configures Qt logging before import, eliminating the non-actionable `propagateSizeHints` platform diagnostic without weakening Python warning-as-error checks. |

### Validation

The release candidate adds synthetic regression coverage for a valid unlabeled 360 KB FAT12 superfloppy, `.IMA` aliases, non-executing text/archive/executable preview classification, seven-language preview labels, and application icon loading. Both supplied historical floppy images were also opened read-only and used to verify actual DOS executable, text, and InstallShield package preview classification. The full strict suite completes with 89 passing tests and no warnings; all three offscreen desktop smoke scripts emit zero bytes on standard error.

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
