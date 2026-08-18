"""Boot-sector inspection and carefully scoped editing utilities."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .models import SECTOR_SIZE
from .storage import DiskForgeError, read_sector, write_sector


@dataclass(frozen=True)
class BootSectorInfo:
    oem_name: str
    bytes_per_sector: int | None
    sectors_per_cluster: int | None
    volume_label: str
    filesystem_label: str
    signature_valid: bool
    bootable: bool


def inspect_boot_sector(data: bytes) -> BootSectorInfo:
    if len(data) != SECTOR_SIZE:
        raise ValueError("Boot-sector data must contain exactly 512 bytes.")
    oem = data[3:11].decode("ascii", errors="replace").rstrip()
    bytes_per_sector = int.from_bytes(data[11:13], "little") or None
    sectors_per_cluster = data[13] or None
    fat32 = data[82:90].strip().upper().startswith(b"FAT32")
    label_offset = 71 if fat32 else 43
    fs_offset = 82 if fat32 else 54
    label = data[label_offset:label_offset + 11].decode("ascii", errors="replace").rstrip()
    filesystem = data[fs_offset:fs_offset + 8].decode("ascii", errors="replace").rstrip()
    return BootSectorInfo(oem, bytes_per_sector, sectors_per_cluster, label, filesystem,
                          data[510:512] == b"\x55\xaa", data[0] in {0xEB, 0xE9})


def sector_hexdump(data: bytes, width: int = 16) -> str:
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        hex_part = " ".join(f"{value:02X}" for value in chunk)
        ascii_part = "".join(chr(value) if 32 <= value < 127 else "." for value in chunk)
        lines.append(f"{offset:04X}  {hex_part:<{width * 3 - 1}}  |{ascii_part}|")
    return "\n".join(lines)


def parse_hexdump(text: str) -> bytes:
    """Accept pairs of hexadecimal digits while ignoring whitespace and offsets."""
    pairs: list[str] = []
    for line in text.splitlines():
        body = line.split("|", 1)[0]
        if len(body) >= 4 and all(char in "0123456789abcdefABCDEF" for char in body[:4]):
            body = body[4:]
        for token in body.split():
            if len(token) == 2 and all(char in "0123456789abcdefABCDEF" for char in token):
                pairs.append(token)
    data = bytes.fromhex(" ".join(pairs))
    if len(data) != SECTOR_SIZE:
        raise DiskForgeError(f"Expected 512 bytes in the hex editor, received {len(data)}.")
    return data


def backup_and_write_boot_sector(image: Path | str, data: bytes, sector: int = 0) -> Path:
    """Make a sibling .bak copy prior to replacing a sector in an image file."""
    target = Path(image)
    if len(data) != SECTOR_SIZE:
        raise ValueError("A boot sector must contain exactly 512 bytes.")
    backup = target.with_suffix(target.suffix + ".bootsector.bak")
    shutil.copy2(target, backup)
    write_sector(target, sector, data)
    return backup


def load_boot_sector_file(path: Path | str) -> bytes:
    data = Path(path).read_bytes()
    if len(data) != SECTOR_SIZE:
        raise DiskForgeError("A boot-sector file must be exactly 512 bytes.")
    return data
