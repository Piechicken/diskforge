# DiskForge Python API

**当前开发分支** exposes **SDK API 1.1**, a typed file-image API through `diskforge.api`. The public facade is deliberately narrower than the desktop application: it supports inspection, checksums, comparison, FAT creation, conversion, validated partition inspection, managed filesystem sessions, extraction, FAT injection, safe ISO replacement, and controlled read-only mounting. It does **not** expose unattended physical-device writes, MBR changes, or device formatting.

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
| `client.create_fat(...)` | Create a new FAT12/16/32 image. | Creates the requested output file. |
| `client.convert(...)` | Convert a file image, optionally with a configured converter. | Requires an explicit destination; source remains unchanged. |
| `client.partitions(image)` | Return validated MBR/GPT partition entries. | Never opens or writes a partition. |
| `client.filesystem(..., partition_index=N)` | Open an explicitly selected FAT MBR/GPT partition in a context manager. | Never silently selects a different FAT volume; resources are always closed. |
| `client.replace_iso_file(source, iso_path, replacement, destination)` | Replace one existing equal-size ISO9660 file into a newly written ISO. | Source ISO and replacement source stay unchanged; output is reopened and verified. |
| `client.mount_capability()` | Report the local OS read-only mount backend. | Diagnostic only; never starts a mount. |
| `client.mount_read_only(image)` / `client.unmount(session)` | Create and release a system-backed image mount session. | Read-only only; callers retain and explicitly release the returned session. |
| `client.filesystem(...)` | Open an image filesystem in a context manager. | Resources are always closed. ISO, NTFS, EXT, HFS, and HFS+ sessions are read-only. |
| `client.extract(...)` | Extract paths to a local directory. | Uses the selected extraction policy; source remains unchanged. |
| `client.inject(...)` | Add local files or directories to FAT. | Only writable FAT sessions are accepted. |

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

## Selected partition and ISO workflows

For a partitioned FAT image, first inspect the validated table and then choose its explicit one-based table index. This prevents an automation host from accidentally acting on the first FAT partition in a multi-volume image.

```python
for partition in client.partitions("disk.img"):
    print(partition.index, partition.filesystem.value, partition.name)

with client.filesystem("disk.img", partition_index=2, writable=False) as filesystem:
    print(filesystem.list_entries("/"))
```

`replace_iso_file()` is intentionally narrower than generic ISO authoring. It only replaces one existing normal ISO file whose replacement has exactly the original logical size; it creates a different output file and verifies the reopened result. Rock Ridge and UDF ISO images are rejected by this safe first implementation.

ZIP-compatible legacy compressed images with `.imz` or `.wlz` extensions are recognized as **single-payload containers** only. DiskForge rejects encrypted, unsafe, non-Deflate/non-Stored, or multi-payload archives; a valid payload is materialized to a caller-owned temporary raw image for read-only browsing. The GUI and CLI can create or extract the same constrained container shape, but this does not claim support for undocumented proprietary extensions beyond that ZIP-compatible profile.

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

Classic HFS and HFS+ browsing is routed through the explicitly installed Sleuth Kit `fls`/`icat` backend. This provides read-only listing and data-fork extraction only; DiskForge does not write HFS/HFS+ volumes, reconstruct resource forks, or attempt a filesystem repair.

`DiskForgeClient` accepts an optional converter implementation. The desktop application uses an explicitly configured `qemu-img` adapter for VHDX, VMDK, QCOW2, and controlled dynamic-VHD export. Dynamic VHD allocation structures are not edited as flat sectors: DiskForge first edits a separate raw FAT work image, then invokes `qemu-img` with `vpc` dynamic options and validates the resulting dynamic VHD footer. The library does not download or invoke an external converter unless the host explicitly provides one.

## Progress and cancellation

Long-running methods accept the project `ProgressCallback` and `CancellationToken` where appropriate. GUI integrations can forward progress events to a task center; command-line integrations can serialize their own progress and result records.

## Versioning

`API_VERSION` identifies the public facade contract independently from the package release version. Additive methods can appear within an API major version. Incompatible API changes require a new API major version and a migration note in the project changelog.

## Error handling

Expected operational failures raise `DiskForgeError` or standard file errors such as `FileNotFoundError`. Hosts should catch these exceptions, show the original diagnostic to the user or log, and avoid treating unsupported writable paths as a request to modify the source image.
