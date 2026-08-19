# Legacy IMG/IMA Floppy Profiles

DiskForge treats **IMG** and **IMA** as explicit flat-sector output choices. The extensions preserve the caller's workflow intent; neither extension can, by itself, identify a physical drive, media coating, controller, or historical operating system. For that reason, creation never infers a geometry from a requested file size. The user chooses a named profile or enters a custom CHS geometry.

> A profile creates a new **FAT12** image, reopens it, and verifies its file length and BPB sector-size, sectors-per-track, and heads values before returning it. It does not format a physical disk.

## Built-in verified profiles

All built-in profiles use 512-byte sectors. Capacity is calculated as `cylinders × heads × sectors per track × 512`. The conventional PC-compatible layouts derive from the historical DOS/Windows format tables and drive-geometry references.[1] [2]

| Identifier | Visible profile | Geometry (C×H×S×B) | Bytes | Formatted capacity |
|---|---|---:|---:|---:|
| `pc525_ssdd_160` | 5.25″ SS/DD | 40×1×8×512 | 163,840 | 160 KiB |
| `pc525_ssdd_180` | 5.25″ SS/DD | 40×1×9×512 | 184,320 | 180 KiB |
| `pc525_dsdd_320` | 5.25″ DS/DD | 40×2×8×512 | 327,680 | 320 KiB |
| `pc525_dsdd_360` | 5.25″ DS/DD | 40×2×9×512 | 368,640 | 360 KiB |
| `pc525_qd_640` | 5.25″ DS/QD | 80×2×8×512 | 655,360 | 640 KiB |
| `pc525_qd_720` | 5.25″ DS/QD | 80×2×9×512 | 737,280 | 720 KiB |
| `pc525_dshd_1200` | 5.25″ DS/HD | 80×2×15×512 | 1,228,800 | 1,200 KiB |
| `pc35_ssdd_320` | 3.5″ SS/DD | 80×1×8×512 | 327,680 | 320 KiB |
| `pc35_ssdd_360` | 3.5″ SS/DD | 80×1×9×512 | 368,640 | 360 KiB |
| `pc35_dsdd_640` | 3.5″ DS/DD | 80×2×8×512 | 655,360 | 640 KiB |
| `pc35_dsdd_720` | 3.5″ DS/DD | 80×2×9×512 | 737,280 | 720 KiB |
| `pc35_dshd_1440` | 3.5″ DS/HD | 80×2×18×512 | 1,474,560 | 1,440 KiB |
| `pc35_dshd_dmf_1680` | 3.5″ DS/HD DMF | 80×2×21×512 | 1,720,320 | 1,680 KiB |
| `pc35_dshd_82track_1722` | 3.5″ DS/HD, 82 tracks | 82×2×21×512 | 1,763,328 | 1,722 KiB |
| `pc35_dsed_2880` | 3.5″ DS/ED | 80×2×36×512 | 2,949,120 | 2,880 KiB |

The standard 1.44 MB profile contains 1,474,560 bytes, conventionally described as 1,440 KiB; this naming convention differs from decimal-megabyte labeling.[3]

## Desktop, command-line, and batch use

In the desktop application, choose **New image → Legacy FAT floppy image (IMG/IMA)**. Select either the profile list or **Use custom legacy geometry**, then select **IMA** or **IMG**. The result opens directly as a writable FAT session.

```bash
# Named 360 KiB IMA profile
diskforge-cli create-legacy-floppy setup-disk --profile pc525_dsdd_360 --format ima

# Explicit 720 KiB IMG geometry
diskforge-cli create-legacy-floppy transfer-disk --format img \
  --cylinders 80 --heads 2 --sectors-per-track 9 --sector-size 512

# An existing valid FAT IMA can enter the ordinary content workflow
diskforge-cli inject setup-disk.ima README.TXT
diskforge-cli convert setup-disk.ima setup-disk.img --format img
```

Batch schema v4 can use `"format": "ima"` in a normal `convert` operation. It is intentionally not necessary to define a separate conversion algorithm for IMA: an IMA is a flat raw sector image with an explicit output extension.

## Safety and compatibility boundaries

The native formatter supports **512, 1024, 2048, and 4096-byte sectors** because those are the sector sizes accepted and validated by the portable FAT backend. A custom geometry is rejected if a field does not fit its FAT BPB representation or if its image size is not sector aligned.

DiskForge does not claim file-level editing for every historical floppy format. 128/256-byte-sector media, hard-sectored layouts, GCR and variable-sector encodings, non-FAT filesystems, copy-protection schemes, and flux/bitcell captures require a track-aware backend and, in several cases, original controller behavior. These inputs can remain valuable raw evidence: DiskForge can preserve, hash, compare, inspect, and copy their bytes, but does not relabel them as writable FAT images.

## References

[1]: https://www.classicdosgames.com/tutorials/disks.html "A Comprehensive Guide to Disks"
[2]: https://en.wikipedia.org/wiki/List_of_floppy_disk_formats "List of floppy disk formats"
[3]: http://www.os2museum.com/wp/floppy-capacity-math/ "Floppy Capacity Math"
