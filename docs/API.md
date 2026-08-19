# DiskForge Python API

**DiskForge v0.7.5** exposes a small, typed file-image API through `diskforge.api`. The public facade is deliberately narrower than the desktop application: it supports inspection, checksums, comparison, FAT creation, conversion, managed filesystem sessions, extraction, and FAT injection. It does **not** expose unattended physical-device writes.

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
| `client.filesystem(...)` | Open an image filesystem in a context manager. | Resources are always closed. ISO, NTFS, and EXT sessions are read-only. |
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

## Conversion adapters

`DiskForgeClient` accepts an optional converter implementation. The desktop application uses an explicitly configured `qemu-img` adapter for VHDX, VMDK, and QCOW2. The library does not download or invoke an external converter unless the host explicitly provides one.

## Progress and cancellation

Long-running methods accept the project `ProgressCallback` and `CancellationToken` where appropriate. GUI integrations can forward progress events to a task center; command-line integrations can serialize their own progress and result records.

## Versioning

`API_VERSION` identifies the public facade contract independently from the package release version. Additive methods can appear within an API major version. Incompatible API changes require a new API major version and a migration note in the project changelog.

## Error handling

Expected operational failures raise `DiskForgeError` or standard file errors such as `FileNotFoundError`. Hosts should catch these exceptions, show the original diagnostic to the user or log, and avoid treating unsupported writable paths as a request to modify the source image.
