from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.bootsector import apply_boot_template, list_boot_templates, render_boot_template
from diskforge.core.filesystems import create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.storage import DiskForgeError, read_sector


def test_original_templates_preserve_fat_bpb_and_signature(tmp_path: Path) -> None:
    image = create_fat_image(tmp_path / "template.img", 32 * 1024 * 1024, FileSystemType.FAT16, "TEMPLATE")
    sector = read_sector(image, 0)
    identifiers = {template.identifier for template in list_boot_templates()}
    assert identifiers == {"neutral-halt", "diskforge-message"}
    for identifier in identifiers:
        rendered = render_boot_template(sector, identifier)
        assert rendered[3:62] == sector[3:62]
        assert rendered[510:512] == b"\x55\xAA"
        assert rendered != sector


def test_applying_template_creates_complete_backup(tmp_path: Path) -> None:
    image = create_fat_image(tmp_path / "apply.img", 32 * 1024 * 1024, FileSystemType.FAT16, "APPLY")
    before = image.read_bytes()
    info, backup = apply_boot_template(image, "diskforge-message")
    assert backup.read_bytes() == before
    assert info.signature_valid
    assert image.read_bytes() != before


def test_unknown_template_is_rejected(tmp_path: Path) -> None:
    image = create_fat_image(tmp_path / "unknown.img", 32 * 1024 * 1024, FileSystemType.FAT16, "UNKNOWN")
    with pytest.raises(DiskForgeError, match="Unknown boot template"):
        render_boot_template(read_sector(image, 0), "not-a-template")
