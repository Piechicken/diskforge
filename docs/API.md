# DiskForge Python API

**DiskForge v0.10.0** exposes **SDK API 1.1**, a typed file-image API through `diskforge.api`. The public facade is deliberately narrower than the desktop application: it supports inspection, checksums, comparison, FAT creation, conversion, read-only TD0/IMD inspection with strictly proven RAW export, read-only batch image inventory, validated partition inspection, managed filesystem sessions, extraction, FAT injection, file/directory-tree movement, and entry renaming, safe ISO replacement, and controlled read-only mounting. It does **not** expose unattended physical-device writes, MBR changes, device formatting, or the desktop/CLI ISO rebuild editor.

> Physical devices are a foreground desktop workflow. Capacity, mount state, system-disk protection, and the exact `ERASE` confirmation remain outside the unattended API by design.

## Install and create a client

Install the project in the normal way and import `DiskForgeClient`.

```python
from pathlib import Path

from diskforge.api import DiskForgeClient
from diskforge.core.models import FileSystemType

client = DiskForgeClient()
result = client.create_fat(
    Path("lab.img"),
    size_bytes=32 * 1024 * 1024,
    filesystem=FileSystemType.FAT16,
    label="LAB",
)
print(result.destination)
```

| API surface | Purpose | Safety contract |
|---|---|---|
| `client.inspect(image)` | Return recognized format, filesystem, size, and metadata. | Never writes the image. |
| `client.sha256(image)` | Return a streaming SHA-256 digest. | Never writes the image. |
| `client.compare(left, right, ignore_trailing_zero_sectors=False)` | Stream-compare two file images. | The optional zero-tail mode only changes the report; both sources remain unchanged. |
| `client.create_fat(...)` | Create a new FAT12/16/32 image. | Creates the requested output file; an explicit `.ima` path remains a flat, writable IMA sector image. |
| `client.convert(...)` | Convert a file image, optionally with a configured converter. | Requires an explicit destination; source remains unchanged. Native RAW/IMG/IMA conversions preserve the caller-selected target format. |
| `client.partitions(image)` | Return validated MBR/GPT partition entries. | Never opens or writes a partition. |
| `client.filesystem(..., partition_index=N)` | Open one explicitly selected, validated MBR/GPT partition in a context manager. | FAT retains the existing optional writable path; NTFS, EXT, classic HFS, and HFS+ are routed at their exact validated byte offset through the read-only backend. No first-partition inference occurs, and resources are always closed. |
| `client.replace_iso_file(source, iso_path, replacement, destination)` | Replace one existing equal-size ISO9660 file into a newly written ISO. | Source ISO and replacement source stay unchanged; output is reopened and verified. |
| `client.inspect_imd(source)` | Parse IMD track and sector records without source mutation. | Reports whether exact RAW flattening can be proven; it does not treat IMD as a writable filesystem. |
| `client.export_imd_to_raw(source, destination)` | Export a proven rectangular normal-data IMD layout to a new RAW file. | Requires a new local destination; irregular/mapped/missing/deleted/bad layouts are rejected. |
| `client.inspect_td0(source)` | Parse an ordinary uncompressed TD0 track/sector container without source mutation. | Validates the documented header/comment/track/sector CRCs and reports whether exact RAW flattening can be proven; TD0 is not a writable filesystem. |
| `client.export_td0_to_raw(source, destination)` | Export a proven unflagged ordinary TD0 rectangular layout to a new RAW file. | Requires a new local destination; advanced compression, multi-volume, CRC failures, flagged/missing data, mixed density, irregular geometry, and ambiguous sector order are rejected. |
| `client.inventory_images(root, options=None)` | Read local image-file metadata into a filtered `ImageInventory`. | Does not open writable filesystem sessions or modify candidates. It ignores symbolic links, regular files over 16 GiB, and unsupported suffixes; scanning is limited to 10,000 discovered regular files. |
| `client.export_image_inventory(inventory, destination, report_format)` | Atomically write a new JSON, CSV, or HTML image-inventory report. | Destination must be a nonexisting local file outside the scanned root. It never overwrites or creates a report inside the scan tree. |
| `client.mount_capability()` | Report the local OS read-only mount backend. | Diagnostic only; never starts a mount. |
| `client.mount_read_only(image)` / `client.unmount(session)` | Create and release a system-backed image mount session. | Read-only only; callers retain and explicitly release the returned session. |
| `client.filesystem(..., zip_payload=name)` | Open an image filesystem in a context manager. | Resources are always closed. ISO, canonical D64/D71/D81 CBM DOS, NTFS, EXT, HFS, HFS+, and safe ZIP sessions are read-only. A ZIP payload is private temporary data removed when the context ends; a multi-image ZIP requires an exact validated `zip_payload`. |
| `client.extract(..., zip_payload=name)` | Extract paths to a local directory. | Uses the selected extraction policy; source remains unchanged. A multi-image ZIP requires its exact validated payload name. |
| `client.list_zip_image_payloads(...)` | List validated root-level direct-image payload names in a ZIP. | Read-only discovery only; every ZIP member must pass the same safety validation before any name is returned. |
| `client.inject(...)` | Add local files or directories to FAT. | Only writable FAT sessions are accepted. |
| `client.move_fat(image, item_path, target_directory)` | Move one FAT file or directory tree into an existing image directory. | Writable FAT only. The target must already be a directory; root movement, collisions, missing/non-directory targets, and source-tree targets are rejected. Directory movement is cancellable copy-then-delete and is not atomic. |
| `client.rename_fat(image, item_path, new_name)` | Rename one FAT file or directory inside its current parent. | Writable FAT only. A single non-empty entry name is required; existing targets are never replaced. |
| `client.delete_fat(image, item_path, partition_index=None)` | Delete one explicit non-root FAT file or directory tree. | Writable FAT only. The explicit target is checked before deletion; root deletion is refused. A directory-tree deletion is irreversible and is not claimed to be transactional. |
| `client.set_fat_metadata(image, paths, ..., partition_index=None)` | Apply requested standard DOS attributes and/or FAT creation, modification, access times to explicit existing paths. | Writable FAT only. Paths must be nonempty, unique, and non-root; values are explicit, timezone-free FAT times or standard DOS booleans. The ordered updates are observable, but not claimed as a multi-entry transaction. |
| `client.inspect_cpc_dsk(source)` / `client.export_cpc_dsk_to_raw(source, destination)` | Inspect a signed standard/extended CPC DSK container and export only a strictly proven normal layout to a new RAW file. | Read-only only. Signature recognition is required; no filesystem session, general conversion, write, repair, device, weak-sector, or copy-protection support is provided. |
| `client.inspect_d88(source)` / `client.export_d88_to_raw(source, destination)` | Inspect one shape-validated D88 sector container and export only a strictly proven normal layout to a new RAW file. | Read-only only. It requires one exact-size first disk with a validated 0x2A0/0x2B0 first-track offset; no filesystem session, general conversion, write, repair, device, weak-sector, or copy-protection support is provided. |
| `client.list_deleted_fat(image, partition_index=None)` | List conservative FAT12/FAT16 deleted fixed-root-file candidates. | Read-only. Only ordinary 8.3 slots are listed; candidate recovery is available solely for one currently free single cluster. |
| `client.inspect_mfm(source)` | Inspect one canonical HxC MFM bitstream container. | Read-only only. It verifies the packed header, canonical cylinder/side table, 512-byte zero padding, non-overlap, and exact EOF; no bitstream decoding, RAW export, filesystem session, conversion, repair, or write path is exposed. |
| `client.inspect_pfi(source)` | Inspect one canonical PCE PFI v0 flux container. | Read-only only. It validates published big-endian chunk framing, zero-initialized CRC-32, unique track contexts, aligned index lists, bounded pulse tokens, zero-length END, and exact EOF; no flux/sector decoding, RAW export, filesystem session, conversion, repair, or write path is exposed. |
| `client.inspect_woz(source)` | Inspect one canonical WOZ 2.0/2.1 Apple II container. | Read-only only. It validates the fixed WOZ2 signature, optional published CRC-32, canonical INFO/TMAP/TRKS chunk order, INFO v2/v3 constraints, mapped opaque track ranges, optional FLUX consistency, bounded UTF-8 META grammar, and exact EOF; no bitstream/flux/sector decoding, RAW export, filesystem session, conversion, repair, or write path is exposed. |
| `client.inspect_a2r(source)` | Inspect one canonical A2R 3.x flux container. | Read-only only. It validates the fixed A2R3 signature, required first INFO v1 block, bounded little-endian chunk framing, RWCP capture entries, SLVD solved-track entries, UTF-8 META grammar, and exact EOF; no flux/bitstream/sector decoding, RAW export, filesystem session, conversion, repair, or write path is exposed. |
| `client.inspect_d64(source)` | Inspect one canonical 35-track D64 CBM DOS image and its ordinary file chains. | Read-only only. It accepts exactly 174,848 bytes with 256-byte sectors, validates the BAM version/counts, directory chain, ordinary SEQ/PRG/USR chains, and final-sector byte counts; `client.filesystem()` and `client.extract()` can list/extract those verified files. 40-track/error-map variants, REL/GEOS layouts, GCR decoding, repair, conversion, creation, and writes are unavailable. |
| `client.inspect_d71(source)` | Inspect one canonical 70-track double-sided D71 CBM DOS image and its ordinary file chains. | Read-only only. It accepts exactly 349,696 bytes of 256-byte sectors, validates the double-sided flag, side-0 BAM entries, side-1 BAM bitmap/count region, directory chain, ordinary SEQ/PRG/USR chains, final-sector byte counts, and system/data-chain separation; `client.filesystem()` and `client.extract()` can list/extract those verified files. 40-track/error-map variants, REL/GEOS layouts, GCR decoding, repair, conversion, creation, editing, writes, and device routes are unavailable. |
| `client.inspect_d81(source)` | Inspect one canonical 80-track double-sided D81 CBM DOS image and its ordinary file chains. | Read-only only. It accepts exactly 819,200 bytes of 256-byte sectors, validates the 1581 header, both 40-entry BAM sectors, matching disk IDs, each 40-bit allocation bitmap/count, canonical track-40 directory, ordinary SEQ/PRG/USR chains, final-sector byte counts, and system/data-chain separation; `client.filesystem()` and `client.extract()` can list/extract verified files. Error-map variants, extended directories, REL/GEOS/CBM partitions, GCR decoding, repair, conversion, creation, editing, writes, and device routes are unavailable. |
| `client.inspect_g64(source)` | Inspect one canonical G64 v0 1541 GCR container. | Read-only only. It validates the fixed `GCR-1541` version-0 signature, bounded little-endian track and speed tables, opaque stored track allocations, constant or mapped speed zones, non-overlap, and exact EOF; no GCR/sector decoding, RAW export, filesystem session, conversion, repair, or write path is exposed. |
| `client.inspect_g71(source)` | Inspect one canonical G71 v0 double-sided GCR container. | Read-only only. It validates the fixed `GCR-1571` version-0 signature, exactly 168 half-track entries, bounded little-endian track and speed tables, opaque stored-track allocations, constant or mapped speed zones, non-overlap, and exact EOF; no GCR/sector decoding, RAW export, browsing, filesystem session, conversion, repair, or write path is exposed. |
| `client.inspect_p64(source)` | Inspect one canonical P64 v0 1541 NRZI pulse container. | Read-only only. It validates the fixed `P64-1541` version-0 signature, defined flag bits, exact whole-stream and per-chunk CRC-32, bounded HTPx framing, unique half-track/side coordinates, declared range-stream size, empty final DONE, and exact EOF; range-coded NRZI data remains opaque, with no pulse/GCR/sector decoding, RAW export, filesystem session, conversion, repair, or write path exposed. |
| `client.recover_deleted_fat(image, slot_index, destination, partition_index=None)` | Copy one revalidated deleted-file candidate to a new local path. | Never writes the image; `destination` must not exist. The result is a candidate copy, not a name or integrity guarantee. |

## Managed filesystem session

Use `filesystem()` as a context manager. The session is closed even if an operation raises an exception.

```python
from diskforge.api import DiskForgeClient

client = DiskForgeClient()
with client.filesystem("lab.img", writable=True) as filesystem:
    filesystem.inject(["README.TXT"], "/")
    entries = filesystem.list_dir("/")
    print([entry.name for entry in entries])
```

## Read-only ZIP image containers

A regular `.zip` can be used as a **read-only image container** through `filesystem()` and `extract()` when it contains one to 64 safe root-level image payloads. Every member must be unencrypted, use Stored or Deflated compression, be nonempty and no larger than 2 GiB, use an approved direct-image suffix (including validated legacy RAW aliases), and re-identify as a supported browsable filesystem after materialization. `list_zip_image_payloads()` first returns the validated names. A sole payload opens automatically; if there are multiple payloads, pass one exact name as `zip_payload`. The SDK streams only that selected payload into a private temporary file and removes it when the context closes, including when the operation raises.

```python
client = DiskForgeClient()
payloads = client.list_zip_image_payloads("archive.zip")
with client.filesystem("archive.zip", zip_payload=payloads[0]) as filesystem:
    print([entry.path for entry in filesystem.list_entries("/")])

outputs = client.extract("archive.zip", ["/README.TXT"], "extracted", zip_payload=payloads[0])
```

`client.filesystem("archive.zip", writable=True)`, `client.inject("archive.zip", ...)`, `client.move_fat("archive.zip", ...)`, and `client.convert("archive.zip", ...)` are deliberately rejected. ZIP containers are not generic archives, recursive image sources, or filesystem-editing targets; folders, unsafe names, encryption, unknown compression methods, empty/oversized/unrecognizable payloads, more than 64 entries, and all ZIP writes are rejected.

## IMD inspection and strict RAW export

`inspect_imd()` reads ImageDisk track records without changing the container and returns its text description, geometry, sector data types, and an `exportable` proof result. `export_imd_to_raw()` is deliberately separate from general conversion: it creates a new RAW file only when every track proves a complete rectangular CHS layout with fixed sector count and size, consecutive `1..N` IDs, no optional cylinder/head maps, and normal (including normal compressed-fill) data in every sector.

```python
inspection = client.inspect_imd("legacy.imd")
if inspection.exportable:
    result = client.export_imd_to_raw("legacy.imd", "exported.img")
```

Irregular geometry, variable layouts, duplicate tracks, maps, missing/deleted/bad sectors, trailing bytes, source writes, output overwrite, device targets, IMD writing, and bitstream/flux reconstruction are outside this contract.

## TD0 inspection and strict RAW export

`inspect_td0()` reads an ordinary uncompressed `TD` TeleDisk container without modifying it. It validates the documented A097 CRCs for the file header, optional comment, every track header, and every sector record; it also validates the exact output length of raw, repeated-pattern, and RLE sector encodings. `export_td0_to_raw()` is deliberately separate from general conversion and creates a new RAW file only when the source proves a complete zero-origin rectangular CHS layout with fixed geometry, matching logical and physical sector coordinates, consecutive `1..N` IDs, no density flag or sector status flags, exact EOF, and exactly reconstructed sector data.

```python
inspection = client.inspect_td0("legacy.td0")
if inspection.exportable:
    result = client.export_td0_to_raw("legacy.td0", "exported.img")
```

Lowercase `td` advanced compression, multi-volume sequences, any CRC mismatch, trailing bytes, missing/duplicate/CRC-error/deleted/DOS-skipped/no-ID sectors, mixed density, variable or incomplete geometry, source writes, output overwrite, device targets, TD0 writing, filesystem editing, repair, and bitstream/flux reconstruction are outside this contract. `client.filesystem("legacy.td0")` and `client.convert("legacy.td0", ...)` are explicitly rejected rather than silently treating the container as a raw image.

## Read-only batch image inventory

`inventory_images()` scans one existing non-symlink local directory and returns records for recognized candidate suffixes. `ImageInventoryOptions` can opt into recursive discovery, extension, recognized-format, filesystem, byte-size, and SHA-256-prefix filters, plus per-record SHA-256 and partition summaries. Filtering is metadata-led: unrecognized or malformed candidate observations are preserved with an `error` field unless a selected format/filesystem filter excludes them.

```python
from pathlib import Path
from diskforge.core.inventory import ImageInventoryOptions

inventory = client.inventory_images(
    Path("lab-images"),
    ImageInventoryOptions(recursive=True, include_sha256=True, filesystems=(FileSystemType.FAT16,)),
)
report = client.export_image_inventory(inventory, Path("lab-images-report.json"), "json")
print(report.destination)
```

The report writer supports only `json`, `csv`, and `html`, writes through a sibling temporary file and hard-link promotion, refuses an existing or symbolic-link destination, and refuses a destination resolved within the scanned root. It is intentionally not a batch v4 operation: no unattended recipe path invokes it in this release. The scan does not follow links, does not inspect physical devices, and accepts at most 10,000 discovered regular files, each no larger than 16 GiB.

## FAT deleted root-file candidate recovery

`list_deleted_fat()` and `recover_deleted_fat()` expose a deliberately narrow read-only convenience for FAT12/FAT16 **fixed root-directory** deletion records. They do not mutate the image. A candidate must be an ordinary deleted 8.3 slot with a positive declared size that fits one data cluster; before copying, the SDK rereads the slot and requires the start-cluster FAT item to be currently free. Recovery writes exactly the declared byte count to a **new local file** and returns its `Path`.

```python
candidates = client.list_deleted_fat("legacy.img")
candidate = next(item for item in candidates if item.recoverable)
output = client.recover_deleted_fat("legacy.img", candidate.slot_index, "recovered.bin")
```

The deleted first filename character is unrecoverable from a normal FAT deletion record. A free cluster can nevertheless contain stale or overwritten bytes, so neither original name nor file integrity is asserted. FAT32, subdirectories, long names, zero-length entries, multi-cluster chains, non-free clusters, source-image writes, output overwrite, device recovery, and batch recovery are deliberately unsupported.

## CPC DSK inspection and strict RAW export

`inspect_cpc_dsk()` reports only signed standard/extended CPC DSK container structure. `export_cpc_dsk_to_raw()` creates a new RAW file only when every declared physical track/side is present and consistent, controller status is clean, sector sizes/counts are fixed, IDs are consecutive, and each sector has exactly one normal-size data payload. The source is never changed and an existing destination is rejected.

The SDK rejects ambiguous extension-only input, unformatted tracks, status or coordinate anomalies, variable geometry, short/long/multi-copy sectors, trailing bytes, source-equal or existing destinations, devices, filesystem access, generic conversion, editing, repair, copy-protection, weak-sector, bitstream, and flux claims.

## D88 inspection and strict RAW export

`inspect_d88()` reports the first, exact-size D88 disk only after validating its 0x2A0/0x2B0 first-track shape, disk size, increasing track offsets, and sector record extents. `export_d88_to_raw()` creates a new RAW output only after a complete normal rectangular geometry is proven: clean status, no deleted data, fixed sector size/count, consecutive IDs, and exact data lengths are mandatory.

The SDK rejects multi-disk or trailing data, malformed offsets, incomplete geometry, anomalous sectors, source-equal or existing destinations, devices, filesystem access, generic conversion, editing, repair, copy-protection, weak-sector, bitstream, and flux claims.

## Explicit FAT metadata updates

`set_fat_metadata()` applies caller-selected standard DOS attributes (`read_only`, `hidden`, `system`, `archive`) and/or FAT `created`, `modified`, and `accessed` times to one or more **explicit** paths. Every requested attribute is a boolean; every requested time is a naive `datetime` with a year from 1980 through 2107. Omitted fields stay unchanged. The method returns one `FatMetadataResult` per completed path in caller order and accepts an explicit FAT partition index when needed.

```python
from datetime import datetime

results = client.set_fat_metadata(
    "lab.img",
    ["/README.TXT", "/DOCS/NOTES.TXT"],
    hidden=True,
    modified=datetime(2024, 6, 15, 12, 34, 56),
)
print([result.path for result in results])
```

The SDK rejects an empty/no-op request, duplicate or root paths, timezone-aware or FAT-unrepresentable times, read-only sessions, non-FAT images, and non-FAT selected partitions. It does not interpret wildcards, recurse through directories, infer a current time, change content/ACLs/ownership, write devices, or claim atomic rollback across multiple directory entries.

## FAT file and directory-tree movement

Use `move_fat()` to relocate one regular file or a complete directory tree into an existing directory of a writable FAT image. The method returns the new image-internal POSIX path; it never infers or creates a target directory and never overwrites an existing entry. A file uses the filesystem move primitive. A directory tree uses cancellable copy-then-delete: cancellation or a copy failure retains the source, while a source-removal failure deliberately retains both trees for manual resolution. It is therefore not claimed to be atomic.

```python
client = DiskForgeClient()
destination = client.move_fat("lab.img", "/README.TXT", "/DOCS")
assert destination == "/DOCS/README.TXT"
```

The target must be an existing directory, and a directory cannot target itself or any descendant. `rename_fat()` supplies same-parent renaming for exactly one FAT file or directory. Its new name must be one non-empty entry name; it never replaces an existing entry.

```python
renamed = client.rename_fat("lab.img", "/DOCS/README.TXT", "NOTES.TXT")
assert renamed == "/DOCS/NOTES.TXT"
```

## Selected partition and ISO workflows

For a partitioned image, first inspect the validated table and then choose an explicit one-based table index. This prevents an automation host from accidentally acting on the first compatible volume in a multi-volume image. FAT partitions retain the established writable session when `writable=True`; NTFS, EXT, classic HFS, and HFS+ partitions are opened only through the read-only backend at the selected partition offset.

```python
for partition in client.partitions("disk.img"):
    print(partition.index, partition.filesystem.value, partition.name)

with client.filesystem("disk.img", partition_index=2, writable=False) as filesystem:
    print(filesystem.list_entries("/"))  # FAT, NTFS, EXT, classic HFS, or HFS+
```

`replace_iso_file()` is intentionally narrower than generic ISO authoring. It only replaces one existing normal ISO file whose replacement has exactly the original logical size; it creates a different output file and verifies the reopened result. The desktop and CLI additionally expose a rebuild-based ISO editor that preserves verified Rock Ridge/UDF profiles and a verified single initial El Torito entry; it remains outside the stable SDK facade during API 1.1.

A valid FAT IMA can be opened through `client.filesystem(..., writable=True)` just like a FAT IMG and can therefore be listed, extracted, injected, moved as a file or directory tree, renamed, and otherwise edited through the same managed FAT session. The verified named legacy-floppy profile directory and custom-geometry validation are deliberately exposed by the desktop, CLI `create-legacy-floppy`, and `diskforge.core.legacy_floppy` service during this SDK version; they are not yet advertised as a stable `DiskForgeClient` method.

ZIP-compatible legacy compressed images with `.imz` or `.wlz` extensions are recognized as **single-payload containers** only. Ordinary `.zip` image containers use the separate, stricter direct-browse contract above. DiskForge rejects encrypted, unsafe, non-Deflate/non-Stored, or multi-payload legacy archives; a valid payload is materialized to a caller-owned temporary raw image for read-only browsing. The GUI and CLI can create or extract the same constrained container shape, but this does not claim support for undocumented proprietary extensions beyond that ZIP-compatible profile.

## Optional controlled NTFS, EXT, and classic-HFS image workflows

`DiskForgeClient.filesystem(..., writable=True)` remains **FAT-only**, including explicit FAT partitions. The desktop, CLI, batch schema v4, and the explicit core adapters `diskforge.core.ntfs_inject.NtfsFileInjector`, `diskforge.core.ext_inject.ExtFileInjector`, and `diskforge.core.hfs_inject.HfsFileInjector` offer separate optional copy-on-write workflows for NTFS, EXT, and **classic HFS**. These adapters require already installed external tools, create a new standalone output file, and accept only new root-directory regular files. They SHA-256-check the source before and after, read back each payload for SHA-256 comparison, and validate the output filesystem signature before it is promoted. They deliberately reject physical devices, partition offsets, existing targets, folders, metadata, ACL/ADS work, rename, delete, and in-place writes.

The adjacent core service `diskforge.core.hfs_create.HfsImageCreator` creates a **new** standalone classic-HFS regular-file image through an explicitly available `hformat` executable. Its `create(destination, size_bytes, label, progress=None, token=None)` method rejects an existing output, device-like paths, sizes below 800 KiB or not divisible by 512, and labels outside a conservative 1–27-character ASCII-safe subset. It creates a unique sibling temporary file, formats only that file with `hformat -l`, isolates `HOME`, verifies the HFS signature and output SHA-256, then atomically promotes the result. `HfsCreationResult` exposes `destination`, `label`, `bytes_created`, and `sha256`. It never passes a partition ordinal or `-f`, and it is not exposed as a writable SDK filesystem session.

The classic-HFS adapter isolates `HOME` for every `hfsutils` operation, requires the `hls` absence diagnostic before invoking `hcopy`, and transfers raw data forks only. It does not preserve MacBinary data, resource forks, Finder metadata, or type/creator attributes. HFS+ is not accepted by this adapter and remains read-only.

This is not an SDK-session mutation guarantee and is not a native cross-platform writer: hosts must explicitly provide `ntfscp`/`ntfsls`/`ntfscat` for NTFS, `debugfs`/`e2fsck` for EXT, `hmount`/`hcopy`/`hls` for classic-HFS injection, or `hformat` for classic-HFS creation. See [FILESYSTEM_INJECTION.md](FILESYSTEM_INJECTION.md) for the exact contract, backend constraints, and citations.

## Read-only mount sessions

`mount_read_only()` selects an available OS backend (`udisksctl` on Linux, PowerShell on Windows, or `hdiutil` on macOS). The method never requests a writable attachment. A session should be released in a `finally` block:

```python
session = client.mount_read_only("archive.vhd")
try:
    print(session.mount_point)
finally:
    client.unmount(session)
```

> Mount capability depends on local OS services and permissions. An unavailable backend raises a diagnostic `DiskForgeError`; the API never installs a backend, driver, or helper automatically.

## Conversion adapters

Classic HFS and HFS+ browsing is routed through the explicitly installed Sleuth Kit `fls`/`icat` backend. This provides read-only listing and data-fork extraction only. The separate `HfsFileInjector` may create a verified new **classic HFS** output with root-level raw-data-fork files under its documented copy-on-write contract, and `HfsImageCreator` may create a verified empty standalone classic-HFS regular-file image under its separately constrained contract. Neither makes an SDK session writable or writes HFS+ volumes, reconstructs resource forks, or attempts a filesystem repair.

`DiskForgeClient` accepts an optional converter implementation. The desktop application uses an explicitly configured `qemu-img` adapter for VHDX, VMDK, QCOW2, and controlled dynamic-VHD export. Dynamic VHD allocation structures are not edited as flat sectors: DiskForge first edits a separate raw FAT work image, then invokes `qemu-img` with `vpc` dynamic options and validates the resulting dynamic VHD footer. The library does not download or invoke an external converter unless the host explicitly provides one.

## Progress and cancellation

Long-running methods accept the project `ProgressCallback` and `CancellationToken` where appropriate. GUI integrations can forward progress events to a task center; command-line integrations can serialize their own progress and result records.

## Versioning

`API_VERSION` identifies the public facade contract independently from the package release version. Additive methods can appear within an API major version. Incompatible API changes require a new API major version and a migration note in the project changelog.

## Error handling

Expected operational failures raise `DiskForgeError` or standard file errors such as `FileNotFoundError`. Hosts should catch these exceptions, show the original diagnostic to the user or log, and avoid treating unsupported writable paths as a request to modify the source image.
