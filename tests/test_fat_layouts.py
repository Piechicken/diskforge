from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from diskforge.core.filesystems import FatImageFilesystem
from diskforge.core.fat_layouts import FatImageLayout, create_fat_image_from_layout
from diskforge.core.media import create_dmf_image
from diskforge.core.storage import DiskForgeError


def test_layout_can_be_imported_from_dmf_template_and_recreated(tmp_path: Path) -> None:
    template = create_dmf_image(tmp_path / "template.dmf", "TEMPLATE")
    layout = FatImageLayout.from_image(template)

    assert layout.size_bytes == template.stat().st_size
    assert layout.sector_size == 512
    assert layout.sectors_per_track == 21
    assert layout.heads == 2
    assert layout.fat_count == 2

    recreated = create_fat_image_from_layout(tmp_path / "recreated.img", layout, label="RECREATED")
    assert recreated.stat().st_size == layout.size_bytes
    assert FatImageLayout.from_image(recreated) == layout
    filesystem = FatImageFilesystem(recreated, read_only=True)
    try:
        assert filesystem.volume_label() == "RECREATED"
    finally:
        filesystem.close()


def test_layout_rejects_invalid_boot_sector_and_unsafe_parameters(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.img"
    invalid.write_bytes(b"\0" * 512)
    with pytest.raises(DiskForgeError, match="valid FAT boot sector"):
        FatImageLayout.from_image(invalid)

    template = create_dmf_image(tmp_path / "template.dmf", "TEMPLATE")
    layout = FatImageLayout.from_image(template)
    with pytest.raises(DiskForgeError, match="power of two"):
        create_fat_image_from_layout(tmp_path / "bad.img", replace(layout, sector_size=768))
    with pytest.raises(DiskForgeError, match="sector-aligned"):
        create_fat_image_from_layout(tmp_path / "unaligned.img", replace(layout, size_bytes=layout.size_bytes + 1))


def test_new_image_dialog_exposes_safe_template_layout_mode(qtbot) -> None:  # type: ignore[no-untyped-def]
    from diskforge.gui.main_window import NewImageDialog

    dialog = NewImageDialog()
    qtbot.addWidget(dialog)
    dialog.kind.setCurrentIndex(dialog.kind.findData("fat_layout"))

    assert dialog.source.isEnabled()
    assert dialog.source_button.isEnabled()
    assert dialog.source_label.text() == "FAT layout template"
    assert not dialog.size.isEnabled()
    assert not dialog.fat.isEnabled()
    assert "template is never modified" in dialog.help.text()
