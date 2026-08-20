# Controlled NTFS, EXT, and Classic HFS Image Workflows

DiskForge can optionally add local regular files to a **standalone NTFS**, **EXT2/EXT3/EXT4**, or **classic HFS** filesystem image. This is deliberately a **copy-on-write injection workflow**, not a general writable-filesystem claim. Every operation creates a separately named output, leaves the selected source unchanged, and promotes the output only after read-back hash verification and filesystem-specific validation.

> DiskForge never downloads, bundles, mounts through the host operating system, or silently invokes an external filesystem writer. The required local command-line tools must already be available on the host or supplied explicitly on the command line.

## Supported scope

| Filesystem | Required optional tools | Accepted source | Allowed change | Output checks |
|---|---|---|---|---|
| NTFS | `ntfscp`, `ntfsls`, `ntfscat` | One offset-0 NTFS volume in a regular file | Add one or more new regular local files to the volume root | `ntfscp -n` preflight, target-absence check, `ntfscat` SHA-256 read-back, source SHA-256 recheck, NTFS signature recheck |
| EXT2/3/4 | `debugfs`, `e2fsck` | One offset-0 EXT filesystem in a regular file | Add one or more new regular local files to the volume root | command-file write with an undo log, `debugfs dump` SHA-256 read-back, `e2fsck -fn` clean check, source SHA-256 recheck, EXT signature recheck |
| Classic HFS | `hmount`, `hcopy`, `hls` | One offset-0 classic HFS volume in a regular file | Add one or more new root-level regular local files as **raw data forks only** | isolated `HOME`, `hls -1 -N` diagnostic target-absence check, `hcopy -r` SHA-256 read-back, source SHA-256 recheck, HFS signature recheck |

The `ntfscp` manual documents copy-to-volume behavior and a `--no-action` preflight mode.[1] The `debugfs` manual documents read-write opening of an EXT image file, command files, undo logging, and the `write` command that creates a filesystem file from a local one.[2] [3] The classic HFS utilities expose virtual mounting, listing, and host-to-volume copying; their current-volume state is stored in `$HOME/.hcwd`.[4] [5] [6]

## Verified classic HFS image creation

DiskForge can also **create a new standalone classic HFS image** through the optional local `hformat` backend. This is a separate lifecycle operation, not an extension of HFS+ support. The public `hformat` contract requires an existing writable regular file, documents **800 KiB** as the minimum volume size, and accepts a 1–27 character volume name without a colon.[9] DiskForge applies a narrower portable label policy: 1–27 ASCII characters beginning with a letter or digit and containing only letters, digits, spaces, dots, underscores, or hyphens.

| Contract | Enforced behavior |
|---|---|
| New regular-file output only | Existing output paths, `/dev/*`, Windows raw-device paths, partition selectors, partition maps, and physical media are rejected. |
| Explicit preallocation | A unique sibling temporary file is created at a caller-selected byte size of at least 800 KiB and divisible by 512. |
| Non-destructive hformat invocation | DiskForge invokes only `hformat -l LABEL TEMPFILE`; it never passes a partition ordinal or the destructive `-f` option. |
| Isolated command state | Each backend invocation receives a fresh temporary `HOME`, so `hfsutils` current-volume state cannot leak between operations. |
| Verification and promotion | DiskForge checks the output as classic HFS, calculates SHA-256, and atomically promotes it to the requested new destination only after all checks pass. |

The desktop **New image** dialog exposes **Classic HFS image (optional hfsutils)** with a dedicated KiB field that starts at 800 KiB. If `hformat` is not locally available, the dialog explains that the optional backend is unavailable and does not create an image. HFS+ remains read-only in all desktop paths.

## Safety contract

DiskForge creates a sibling temporary copy of the source image before it calls any external writer. If a preflight, writer, read-back hash, signature check, source-hash check, or filesystem check fails, the temporary output is removed and the requested destination is never created.

| Protection | Rationale |
|---|---|
| No physical device paths | The adapters accept regular image files only; they never target `/dev/*`, Windows raw-device paths, or a host disk. |
| No partition offsets | Whole-disk images and images with an internal filesystem partition are rejected; DiskForge does not infer an offset or slice an image internally. |
| New destination required | An existing destination path is rejected, so the workflow cannot overwrite an unrelated output. |
| Root-only regular files | No directories, links, streams, metadata, ACLs, attributes, resource forks, rename, deletion, or overwrite operations are exposed. |
| Safe filename policy | NTFS targets use Windows-compatible names; EXT targets use a deliberately restricted command-safe ASCII name set; classic HFS targets use 1–31 character ASCII root basenames without colon or glob characters. |
| Source SHA-256 recheck | The source digest is compared before and after every operation. A changed source causes output disposal. |
| Read-back verification | Each injected file is extracted from the temporary image and must equal the local input by SHA-256. |

The NTFS adapter never passes `--force`, named-stream, attribute, or inode options. It explicitly checks that a target is absent because `ntfscp` can overwrite an existing destination.[1] The EXT adapter never uses `debugfs` force, catastrophic, or disabled-checksum modes; it requires a non-empty undo log and an `e2fsck -fn` result of zero. The `debugfs` documentation cautions that it is a debugging tool, which is why DiskForge exposes only this narrow, fully verified operation.[2]

The classic HFS adapter never calls delete, rename, or format commands. `hfsutils` tracks its current virtual volume in `$HOME/.hcwd`, so DiskForge creates a fresh private `HOME` for every operation and discards it when verification finishes.[4] [5] Importantly, `hls` can report status zero even when a named target does not exist; DiskForge requires its standardized `no such file or directory` diagnostic before calling `hcopy`. This preflight is mandatory because `hcopy` can otherwise complete a duplicate copy without signalling that an existing HFS target was replaced. The first implementation uses `hcopy -r`, which transfers the raw data fork only; it never claims MacBinary, resource-fork, Finder type/creator, or metadata preservation.[6]

## Desktop workflow

Open a standalone NTFS, EXT, or classic HFS image. The **Image** menu enables **Inject files safely into new NTFS/EXT/classic HFS image…** only for those filesystems. HFS+ does **not** enable this action and remains read-only. DiskForge first reports whether the required optional backend is available. It then asks for one or more regular local files and a new output image path. After completion, DiskForge opens the verified output image; it does not replace the image that was open when the workflow started.

## Command-line workflow

Use the status commands before invoking an optional backend:

```bash
diskforge-cli --json ntfs-inject-status
diskforge-cli --json ext-inject-status
diskforge-cli --json hfs-inject-status
diskforge-cli --json hfs-create-status

# The source remains unchanged; each injection destination must not already exist.
diskforge-cli --json inject-ntfs source.ntfs injected.ntfs README.TXT NOTICE.TXT
diskforge-cli --json inject-ext source.ext4 injected.ext4 README.TXT
diskforge-cli --json inject-hfs source.hfs injected.hfs README.TXT

# The output must not exist; this creates and verifies a new 800 KiB classic HFS image.
diskforge-cli --json create-hfs created.hfs --size-kib 800 --label DISKFORGE
```

Injection result JSON contains the source and destination paths, the source SHA-256, root target paths, and every verified payload SHA-256. `create-hfs` returns its path, label, byte size, and output SHA-256. Explicit executable paths can be supplied with `--ntfscp`, `--ntfsls`, and `--ntfscat` for NTFS; `--debugfs` and `--e2fsck` for EXT; `--hmount`, `--hcopy`, and `--hls` for classic-HFS injection; or `--hformat` for classic-HFS creation.

## Batch schema v4

Batch recipes expose separate `ntfs_inject`, `ext_inject`, `hfs_inject`, and `hfs_create` kinds. Injection operations require `source`, `destination`, and a non-empty string array of `sources`. `hfs_create` requires a new `destination`, `size_bytes`, and `label`. All appear as writes in a batch preview and reject raw-device actions.

```json
{
  "schema": "diskforge.batch/v4",
  "operations": [
    {
      "kind": "ntfs_inject",
      "source": "source.ntfs",
      "destination": "injected.ntfs",
      "sources": ["README.TXT", "NOTICE.TXT"]
    },
    {
      "kind": "ext_inject",
      "source": "source.ext4",
      "destination": "injected.ext4",
      "sources": ["README.TXT"]
    },
    {
      "kind": "hfs_inject",
      "source": "source.hfs",
      "destination": "injected.hfs",
      "sources": ["README.TXT"]
    },
    {
      "kind": "hfs_create",
      "destination": "created.hfs",
      "size_bytes": 819200,
      "label": "DISKFORGE"
    }
  ]
}
```

Optional executable paths may be set as `ntfscp_executable`, `ntfsls_executable`, and `ntfscat_executable` for NTFS; `debugfs_executable` and `e2fsck_executable` for EXT; `hmount_executable`, `hcopy_executable`, and `hls_executable` for classic-HFS injection; or `hformat_executable` for classic-HFS creation. They are intentionally per-recipe rather than guessed or downloaded.

## Explicit exclusions

This feature does **not** write HFS+, including journaled HFS+ volumes. `hfsutils` supports classic HFS commands, not HFS+.[4] HFS+ has complex catalog, allocation, extent, attribute, startup, fork, and journal structures; its published format specification is not a portable write API.[7] On Linux, HFS+ write access is commonly constrained by journaling state and should not be enabled by changing an irreplaceable source image.[8]

Classic HFS creation does not format existing files, devices, partitions, partition maps, or physical media; it does not accept MFS, HFS+, a partition selector, `hformat -f`, or a dynamic image container. Classic HFS injection does not create directories, preserve resource forks, preserve Finder metadata, write MacBinary, replace files, remove files, rename entries, change volume metadata, repair a volume, accept MFS, process a partition map, or support dynamic image containers. NTFS and EXT file-level browse/extract adapters remain useful independently of this workflow. The controlled writers do not add full edit parity: they do not support nested targets, content replacement, directory creation, deletion, renaming, symlinks, hard links, ADS, ACLs, xattrs, ownership, compression controls, journal management, recovery, repair, encrypted media, dynamic container formats, or partitioned disk images.

## References

[1]: https://linux.die.net/man/8/ntfscp "ntfscp(8) — copy file to an NTFS volume"
[2]: https://manpages.debian.org/testing/e2fsprogs/debugfs.8.en.html "debugfs(8) — ext2/ext3/ext4 filesystem debugger"
[3]: https://man7.org/linux/man-pages/man8/debugfs.8.html "debugfs(8) — Linux manual page"
[4]: https://manpages.ubuntu.com/manpages/bionic/man1/hfsutils.1.html "hfsutils(1) — classic HFS utility suite"
[5]: https://manpages.ubuntu.com/manpages/jammy/man1/hmount.1.html "hmount(1) — add an HFS volume to the known-volume list"
[6]: https://manpages.ubuntu.com/manpages/jammy/man1/hcopy.1.html "hcopy(1) — copy files from or to an HFS volume"
[7]: https://developer.apple.com/library/archive/technotes/tn/tn1150.html "Technical Note TN1150: HFS Plus Volume Format"
[8]: https://help.ubuntu.com/community/hfsplus "Ubuntu Community Help: hfsplus"
[9]: https://manpages.ubuntu.com/manpages/jammy/man1/hformat.1.html "hformat(1) — create a new HFS filesystem"
