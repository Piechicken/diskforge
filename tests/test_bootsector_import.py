from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.bootsector import import_boot_sector_file
from diskforge.core.filesystems import create_fat_image
from diskforge.core.models import FileSystemType
from diskforge.core.storage import DiskForgeError, read_sector


def test_import_boot_sector_file_preserves_target_fat_bpb_and_creates_backup(tmp_path: Path) -> None:
    image = create_fat_image(tmp_path / "target.img", 2 * 1024 * 1024, FileSystemType.FAT12, "TARGET")
    original = read_sector(image, 0)
    source = bytearray(original)
    source[62:510] = b"\x90" * (510 - 62)
    source[510:512] = b"\x55\xaa"
    source_file = tmp_path / "boot.bin"
    source_file.write_bytes(source)

    info, backup = import_boot_sector_file(image, source_file)

    written = read_sector(image, 0)
    assert backup.read_bytes() == original + image.read_bytes()[512:]
    assert written[:62] == original[:62]
    assert written[62:510] == source[62:510]
    assert written[510:512] == b"\x55\xaa"
    assert info.filesystem_label.startswith("FAT")


def test_import_boot_sector_file_rejects_invalid_signature_without_modifying_image(tmp_path: Path) -> None:
    image = create_fat_image(tmp_path / "target.img", 2 * 1024 * 1024, FileSystemType.FAT12)
    original = image.read_bytes()
    invalid = tmp_path / "invalid.bin"
    invalid.write_bytes(b"\x90" * 512)

    with pytest.raises(DiskForgeError, match="signature"):
        import_boot_sector_file(image, invalid)

    assert image.read_bytes() == original
    assert not image.with_suffix(image.suffix + ".bootsector.bak").exists()


def test_cli_import_boot_sector_requires_explicit_confirmation_and_reports_backup(tmp_path: Path, capsys) -> None:
    import json

    from diskforge.cli import main

    image = create_fat_image(tmp_path / "target.img", 2 * 1024 * 1024, FileSystemType.FAT12)
    source = bytearray(read_sector(image, 0))
    source[62:510] = b"\xF4" * (510 - 62)
    source_file = tmp_path / "boot.bin"
    source_file.write_bytes(source)

    assert main(["import-boot-sector", str(image), str(source_file), "--confirm", "NO"]) == 2
    assert "IMPORT_BOOT_SECTOR" in capsys.readouterr().err

    assert main(["--json", "import-boot-sector", str(image), str(source_file), "--confirm", "IMPORT_BOOT_SECTOR"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["backup"] == str(image.with_suffix(image.suffix + ".bootsector.bak"))
    assert payload["filesystem"].startswith("FAT")


def test_boot_sector_dialog_exposes_safe_boot_code_import(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QPushButton

    from diskforge.gui.main_window import BootSectorDialog

    image = create_fat_image(tmp_path / "target.img", 2 * 1024 * 1024, FileSystemType.FAT12)
    dialog = BootSectorDialog(image)
    qtbot.addWidget(dialog)
    assert "Import boot code safely…" in {button.text() for button in dialog.findChildren(QPushButton)}
