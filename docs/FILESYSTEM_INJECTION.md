# Controlled NTFS and EXT File Injection

DiskForge can optionally add local regular files to an existing **standalone NTFS** or **EXT2/EXT3/EXT4** filesystem image. This is deliberately a **copy-on-write injection workflow**, not a general writable-filesystem claim. It creates a separately named output, keeps the selected source unchanged, and promotes the output only after read-back hash verification and filesystem validation.

> DiskForge never downloads, bundles, mounts, or invokes an external filesystem writer silently. The required local tools must already be available on the host or supplied explicitly on the command line.

## Supported scope

| Filesystem | Required optional tools | Accepted source | Allowed change | Output checks |
|---|---|---|---|---|
| NTFS | `ntfscp`, `ntfsls`, `ntfscat` | One offset-0 NTFS volume in a regular file | Add one or more new regular local files to the volume root | `ntfscp -n` preflight, target-absence check, `ntfscat` SHA-256 read-back, source SHA-256 recheck, NTFS signature recheck |
| EXT2/3/4 | `debugfs`, `e2fsck` | One offset-0 EXT filesystem in a regular file | Add one or more new regular local files to the volume root | command-file write with an undo log, `debugfs dump` SHA-256 read-back, `e2fsck -fn` clean check, source SHA-256 recheck, EXT signature recheck |

The `ntfscp` manual documents copy-to-volume behavior and a `--no-action` preflight mode.[1] The `debugfs` manual documents read-write opening of an EXT image file, command files, undo logging, and the `write` command that creates a filesystem file from a local one.[2] [3]

## Safety contract

DiskForge creates a sibling temporary copy of the source image before it calls any external writer. If a preflight, writer, read-back hash, signature check, source-hash check, or filesystem check fails, the temporary output is removed and the requested destination is never created.

| Protection | Rationale |
|---|---|
| No physical device paths | The adapter accepts regular image files only; it never targets `/dev/*` or a host disk. |
| No partition offsets | Whole-disk images and images with an internal filesystem partition are rejected; DiskForge does not infer an offset or slice an image internally. |
| New destination required | An existing destination path is rejected, so the workflow cannot overwrite an unrelated output. |
| Root-only regular files | No directories, links, streams, metadata, ACLs, attributes, resource forks, rename, deletion, or overwrite operations are exposed. |
| Safe filename policy | NTFS targets use Windows-compatible names; EXT targets use a deliberately restricted command-safe ASCII name set. |
| Source SHA-256 recheck | The source digest is compared before and after every operation. A changed source causes output disposal. |
| Read-back verification | Each injected file is extracted from the temporary image and must equal the local input by SHA-256. |

The NTFS adapter never passes `--force`, named-stream, attribute, or inode options. It explicitly checks that a target is absent because `ntfscp` can overwrite an existing destination.[1] The EXT adapter never uses `debugfs` force, catastrophic, or disabled-checksum modes; it requires a non-empty undo log and an `e2fsck -fn` result of zero. The `debugfs` documentation cautions that it is a debugging tool, which is why DiskForge exposes only this narrow, fully verified operation.[2]

## Desktop workflow

Open a standalone NTFS or EXT image. The **Image** menu enables **Inject files safely into new NTFS/EXT image…** only for those filesystems. DiskForge first reports whether the required optional backend is available. It then asks for one or more regular local files and a new output image path. After completion, DiskForge opens the verified output image; it does not replace the image that was open when the workflow started.

## Command-line workflow

Use the status commands before invoking an optional backend:

```bash
diskforge-cli --json ntfs-inject-status
diskforge-cli --json ext-inject-status

# The source remains unchanged; the destination must not exist.
diskforge-cli --json inject-ntfs source.ntfs injected.ntfs README.TXT NOTICE.TXT
diskforge-cli --json inject-ext source.ext4 injected.ext4 README.TXT
```

The result JSON contains the source and destination paths, the source SHA-256, root target paths, and each verified payload SHA-256. Explicit executable paths can be supplied with `--ntfscp`, `--ntfsls`, and `--ntfscat` for NTFS, or `--debugfs` and `--e2fsck` for EXT.

## Batch schema v4

Batch recipes expose separate `ntfs_inject` and `ext_inject` kinds. Both require `source`, `destination`, and a non-empty string array of `sources`; they are shown as writes in a batch preview and reject raw-device actions.

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
    }
  ]
}
```

Optional executable paths may be set as `ntfscp_executable`, `ntfsls_executable`, and `ntfscat_executable` for NTFS, or `debugfs_executable` and `e2fsck_executable` for EXT. They are intentionally per-recipe rather than guessed or downloaded.

## Explicit exclusions

This feature does not write HFS or HFS+, including journaled HFS+ volumes. HFS+ has complex catalog, allocation, extent, attribute, startup, fork, and journal structures; its published format specification is not a portable write API.[4] On Linux, HFS+ write access is commonly constrained by journaling state and should not be enabled by changing an irreplaceable source image.[5]

NTFS and EXT file-level browse/extract adapters remain useful independently of this workflow. The controlled writer does not add full edit parity: it does not support nested targets, content replacement, directory creation, deletion, renaming, symlinks, hard links, ADS, ACLs, xattrs, ownership, compression controls, journal management, recovery, repair, encrypted media, dynamic container formats, or partitioned disk images. Use an appropriate specialized environment for those operations.

## References

[1]: https://linux.die.net/man/8/ntfscp "ntfscp(8) — copy file to an NTFS volume"
[2]: https://manpages.debian.org/testing/e2fsprogs/debugfs.8.en.html "debugfs(8) — ext2/ext3/ext4 filesystem debugger"
[3]: https://man7.org/linux/man-pages/man8/debugfs.8.html "debugfs(8) — Linux manual page"
[4]: https://developer.apple.com/library/archive/technotes/tn/tn1150.html "Technical Note TN1150: HFS Plus Volume Format"
[5]: https://help.ubuntu.com/community/hfsplus "Ubuntu Community Help: hfsplus"
