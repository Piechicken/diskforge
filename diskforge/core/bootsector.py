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


def import_boot_sector_file(image: Path | str, source_file: Path | str, sector: int = 0) -> tuple[BootSectorInfo, Path]:
    """Import a boot-sector file without overwriting the target FAT BPB.

    The source must be a complete, signed 512-byte sector.  Only its executable
    area replaces the corresponding target area; the target jump, BPB, extended
    BPB, volume identity and filesystem label remain intact.  A complete sibling
    image backup is created before any write.
    """
    target = Path(image)
    existing = read_sector(target, sector)
    offset = _boot_code_offset(existing)
    imported = load_boot_sector_file(source_file)
    if imported[510:512] != b"\x55\xaa":
        raise DiskForgeError("The imported boot-sector file has an invalid signature.")
    result = bytearray(existing)
    result[offset:510] = imported[offset:510]
    result[510:512] = b"\x55\xaa"
    backup = backup_and_write_boot_sector(target, bytes(result), sector)
    return inspect_boot_sector(bytes(result)), backup


def _ascii_field(value: str, width: int, description: str, *, allow_empty: bool = False) -> bytes:
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise DiskForgeError(f"{description} must not be empty.")
    try:
        encoded = normalized.encode("ascii")
    except UnicodeEncodeError as exc:
        raise DiskForgeError(f"{description} must contain ASCII characters only.") from exc
    if len(encoded) > width or any(byte < 32 or byte > 126 for byte in encoded):
        raise DiskForgeError(f"{description} must contain 1–{width} printable ASCII characters.")
    return encoded.ljust(width, b" ")


def edit_fat_boot_properties(image: Path | str, *, oem_name: str | None = None,
                             volume_label: str | None = None, serial_number: int | None = None,
                             sector: int = 0) -> tuple[BootSectorInfo, Path]:
    """Safely edit the documented FAT BPB properties and return its backup.

    The function only writes the OEM string, volume label and volume serial
    fields.  It refuses non-FAT sectors and creates a complete image backup
    before committing the changed sector.
    """
    target = Path(image)
    with target.open("rb") as handle:
        handle.seek(sector * SECTOR_SIZE)
        data = bytearray(handle.read(SECTOR_SIZE))
    if len(data) != SECTOR_SIZE:
        raise DiskForgeError("Boot sector is outside the image bounds.")
    details = inspect_boot_sector(bytes(data))
    is_fat32 = details.filesystem_label.upper().startswith("FAT32")
    is_fat = is_fat32 or details.filesystem_label.upper().startswith(("FAT12", "FAT16", "FAT"))
    if not is_fat:
        raise DiskForgeError("Structured boot properties are available for FAT boot sectors only.")
    if oem_name is not None:
        data[3:11] = _ascii_field(oem_name, 8, "OEM name")
    if volume_label is not None:
        data[71 if is_fat32 else 43:(71 if is_fat32 else 43) + 11] = _ascii_field(volume_label, 11, "Volume label")
    if serial_number is not None:
        if not 0 <= serial_number <= 0xFFFFFFFF:
            raise DiskForgeError("Volume serial number must be an unsigned 32-bit integer.")
        offset = 67 if is_fat32 else 39
        data[offset:offset + 4] = serial_number.to_bytes(4, "little")
    backup = backup_and_write_boot_sector(target, bytes(data), sector)
    return inspect_boot_sector(bytes(data)), backup


@dataclass(frozen=True)
class BootTemplate:
    """An original, auditable boot-code template that never replaces a FAT BPB."""

    identifier: str
    name: str
    description: str
    license_notice: str


_BOOT_TEMPLATES = (
    BootTemplate(
        "neutral-halt",
        "Neutral halt",
        "Disables interrupts and halts without accessing disks or displaying third-party code.",
        "Original DiskForge template; MIT licensed.",
    ),
    BootTemplate(
        "diskforge-message",
        "DiskForge message",
        "Displays a short original DiskForge message through BIOS video service, then halts.",
        "Original DiskForge template; MIT licensed.",
    ),
)


def list_boot_templates() -> tuple[BootTemplate, ...]:
    """Return the small, original-only boot template catalog."""
    return _BOOT_TEMPLATES


def _boot_code_offset(data: bytes) -> int:
    details = inspect_boot_sector(data)
    filesystem = details.filesystem_label.upper()
    if filesystem.startswith("FAT32"):
        return 90
    if filesystem.startswith(("FAT12", "FAT16", "FAT")):
        return 62
    raise DiskForgeError("Boot templates are available for FAT boot sectors only.")


def render_boot_template(existing: bytes, identifier: str) -> bytes:
    """Return a template sector while preserving all existing BPB/extended-BPB bytes.

    Neither template embeds external boot code.  They intentionally provide only
    transparent, minimal behavior suitable for educational media and structural
    testing; they are not operating-system loaders.
    """
    if len(existing) != SECTOR_SIZE:
        raise DiskForgeError("Boot-sector data must contain exactly 512 bytes.")
    offset = _boot_code_offset(existing)
    template = next((item for item in _BOOT_TEMPLATES if item.identifier == identifier), None)
    if template is None:
        raise DiskForgeError(f"Unknown boot template: {identifier}")
    result = bytearray(existing)
    # A short jump preserves the FAT BPB placed between byte 3 and the code area.
    jump = offset - 2
    if not 0 <= jump <= 0x7F:
        raise DiskForgeError("FAT boot-code offset cannot be represented by the template jump.")
    result[0:3] = bytes((0xEB, jump, 0x90))
    result[offset:510] = b"\x00" * (510 - offset)
    if identifier == "neutral-halt":
        # cli; hlt; infinite two-byte loop.  This code performs no disk or memory access.
        payload = b"\xFA\xF4\xEB\xFE"
    else:
        message = b"DiskForge boot sector\r\n\x00"
        message_offset = offset + 18
        # cli; cld; AH=teletype; BX=page0/light-gray; SI=message; loop lodsb,
        # test, BIOS int 10h, then halt.  All opcodes are authored for this project.
        payload = (
            b"\xFA\xFC\xB4\x0E\xBB\x07\x00\xBE" + message_offset.to_bytes(2, "little")
            + b"\xAC\x84\xC0\x74\x04\xCD\x10\xEB\xF5\xF4\xEB\xFE" + message
        )
    if offset + len(payload) > 510:
        raise DiskForgeError("Boot template does not fit in the executable boot-sector area.")
    result[offset:offset + len(payload)] = payload
    result[510:512] = b"\x55\xAA"
    return bytes(result)


def apply_boot_template(image: Path | str, identifier: str, sector: int = 0) -> tuple[BootSectorInfo, Path]:
    """Apply an original template after creating a complete image backup."""
    target = Path(image)
    data = read_sector(target, sector)
    rendered = render_boot_template(data, identifier)
    backup = backup_and_write_boot_sector(target, rendered, sector)
    return inspect_boot_sector(rendered), backup
