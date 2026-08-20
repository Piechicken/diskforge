# DiskForge Python API

**DiskForge v0.10.0.dev0** exposes **SDK API 1.1**, a typed file-image API through `diskforge.api`. The public facade is deliberately narrower than the desktop application: it supports inspection, checksums, comparison, FAT creation, conversion, read-only batch image inventory, validated partition inspection, managed filesystem sessions, extraction, FAT injection and regular-file movement, safe ISO replacement, and controlled read-only mounting. It does **not** expose unattended physical-device writes, MBR changes, device formatting, or the desktop/CLI ISO rebuild editor.

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
| `client.inventory_images(root, options=None)` | Read local image-file metadata into a filtered `ImageInventory`. | Does not open writable filesystem sessions or modify candidates. It ignores symbolic links, regular files over 16 GiB, and unsupported suffixes; scanning is limited to 10,000 discovered regular files. |
| `client.export_image_inventory(inventory, destination, report_format)` | Atomically write a new JSON, CSV, or HTML image-inventory report. | Destination must be a nonexisting local file outside the scanned root. It never overwrites or creates a report inside the scan tree. |
| `client.mount_capability()` | Report the local OS read-only mount backend. | Diagnostic only; never starts a mount. |
| `client.mount_read_only(image)` / `client.unmount(session)` | Create and release a system-backed image mount session. | Read-only only; callers retain and explicitly release the returned session. |
| `client.filesystem(...)` | Open an image filesystem in a context manager. | Resources are always closed. ISO, NTFS, EXT, HFS, HFS+, and safe ZIP single-image sessions are read-only. A ZIP payload is private temporary data removed when the context ends. |
| `client.extract(...)` | Extract paths to a local directory. | Uses the selected extraction policy; source remains unchanged. |
| `client.inject(...)` | Add local files or directories to FAT. | Only writable FAT sessions are accepted. |
| `client.move_fat(image, item_path, target_directory)` | Move one regular FAT image file into an existing image directory. | Only writable FAT images are accepted. The target must already be a directory; root movement, collisions, missing/non-directory targets, read-only sessions, and all directory moves are rejected before the backend mutation. |
| `client.list_deleted_fat(image, partition_index=None)` | List conservative FAT12/FAT16 deleted fixed-root-file candidates. | Read-only. Only ordinary 8.3 slots are listed; candidate recovery is available solely for one currently free single cluster. |
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

## ZIP single-image containers

A regular `.zip` can be used as a **read-only image container** through `filesystem()` and `extract()` when it contains exactly one safe root-level image payload. The payload must be unencrypted, use Stored or Deflated compression, be nonempty and no larger than 2 GiB, use one of `.img`, `.ima`, `.bin`, `.dd`, `.dmf`, `.iso`, or `.hfs`, and re-identify as a supported browsable filesystem after materialization. The SDK streams it into a private temporary file and removes that file when the context closes, including when the operation raises.

```python
client = DiskForgeClient()
with client.filesystem("archive.zip") as filesystem:
    print([entry.path for entry in filesystem.list_entries("/")])

outputs = client.extract("archive.zip", ["/README.TXT"], "extracted")
```

`client.filesystem("archive.zip", writable=True)`, `client.inject("archive.zip", ...)`, `client.move_fat("archive.zip", ...)`, and `client.convert("archive.zip", ...)` are deliberately rejected. ZIP containers are not generic archives, recursive image sources, or filesystem-editing targets; multiple entries, directories, unsafe names, encryption, unknown compression methods, empty/oversized/unrecognizable payloads, and all ZIP writes are rejected.

## IMD inspection and strict RAW export

`inspect_imd()` reads ImageDisk track records without changing the container and returns its text description, geometry, sector data types, and an `exportable` proof result. `export_imd_to_raw()` is deliberately separate from general conversion: it creates a new RAW file only when every track proves a complete rectangular CHS layout with fixed sector count and size, consecutive `1..N` IDs, no optional cylinder/head maps, and normal (including normal compressed-fill) data in every sector.

```python
inspection = client.inspect_imd("legacy.imd")
if inspection.exportable:
    result = client.export_imd_to_raw("legacy.imd", "exported.img")
```

Irregular geometry, variable layouts, duplicate tracks, maps, missing/deleted/bad sectors, trailing bytes, source writes, output overwrite, device targets, IMD writing, and bitstream/flux reconstruction are outside this contract.

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

## FAT regular-file movement

Use `move_fat()` when a caller needs to relocate **one regular file** within a writable FAT image. The method returns the new image-internal POSIX path. It does not infer or create a destination directory and never overwrites an existing entry.

```python
client = DiskForgeClient()
destination = client.move_fat("lab.img", "/README.TXT", "/DOCS")
assert destination == "/DOCS/README.TXT"
```

Directory movement is deliberately absent from the stable API. The available generic directory operation copies and then deletes its source, so it cannot provide the same atomic, preflighted single-item contract. Use `rename()` inside a managed FAT session for same-directory renaming.

## Selected partition and ISO workflows

For a partitioned image, first inspect the validated table and then choose an explicit one-based table index. This prevents an automation host from accidentally acting on the first compatible volume in a multi-volume image. FAT partitions retain the established writable session when `writable=True`; NTFS, EXT, classic HFS, and HFS+ partitions are opened only through the read-only backend at the selected partition offset.

```python
for partition in client.partitions("disk.img"):
    print(partition.index, partition.filesystem.value, partition.name)

with client.filesystem("disk.img", partition_index=2, writable=False) as filesystem:
    print(filesystem.list_entries("/"))  # FAT, NTFS, EXT, classic HFS, or HFS+
```

`replace_iso_file()` is intentionally narrower than generic ISO authoring. It only replaces one existing normal ISO file whose replacement has exactly the original logical size; it creates a different output file and verifies the reopened result. The desktop and CLI additionally expose a rebuild-based ISO editor that preserves verified Rock Ridge/UDF profiles and a verified single initial El Torito entry; it remains outside the stable SDK facade during API 1.1.

A valid FAT IMA can be opened through `client.filesystem(..., writable=True)` just like a FAT IMG and can therefore be listed, extracted, injected, moved as a regular file, renamed, and otherwise edited through the same managed FAT session. The verified named legacy-floppy profile directory and custom-geometry validation are deliberately exposed by the desktop, CLI `create-legacy-floppy`, and `diskforge.core.legacy_floppy` service during this SDK version; they are not yet advertised as a stable `DiskForgeClient` method.

ZIP-compatible legacy compressed images with `.imz` or `.wlz` extensions are recognized as **single-payload containers** only. Ordinary `.zip` single-image containers use the separate, stricter direct-browse contract above. DiskForge rejects encrypted, unsafe, non-Deflate/non-Stored, or multi-payload legacy archives; a valid payload is materialized to a caller-owned temporary raw image for read-only browsing. The GUI and CLI can create or extract the same constrained container shape, but this does not claim support for undocumented proprietary extensions beyond that ZIP-compatible profile.

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
