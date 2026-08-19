from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog

import diskforge.gui.main_window as main_window_module
from diskforge.core.legacy_floppy import LEGACY_FLOPPY_PROFILES
from diskforge.core.models import ImageFormat
from diskforge.gui.main_window import ConvertDialog, MainWindow, NewImageDialog


def _select_combo_data(combo, value) -> None:  # type: ignore[no-untyped-def]
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_new_image_dialog_exposes_full_legacy_img_ima_profile_workflow(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = NewImageDialog()
    qtbot.addWidget(dialog)
    _select_combo_data(dialog.kind, "legacy_floppy")
    dialog.show()

    assert dialog.legacy_profile.count() == len(LEGACY_FLOPPY_PROFILES)
    assert dialog.legacy_profile.isVisible()
    assert dialog.legacy_format.isVisible()
    assert ImageFormat(str(dialog.legacy_format.currentData())) == ImageFormat.IMA
    assert dialog.size.isEnabled() is False
    assert dialog.help.text().startswith("Creates an editable FAT12 IMG or IMA")

    dialog.legacy_custom.setChecked(True)
    assert dialog.legacy_profile.isEnabled() is False
    assert dialog.legacy_geometry_widget.isEnabled() is True


def test_new_image_dialog_creates_selected_legacy_ima_and_img(qtbot, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow()
    qtbot.addWidget(window)
    dialog = NewImageDialog(window)
    qtbot.addWidget(dialog)
    _select_combo_data(dialog.kind, "legacy_floppy")
    _select_combo_data(dialog.legacy_profile, "pc525_dsdd_360")
    monkeypatch.setattr(dialog, "exec", lambda: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(main_window_module, "NewImageDialog", lambda parent: dialog)

    ima_base = tmp_path / "legacy-output"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(ima_base), ""))

    def run_now(_title, function, *args, on_result=None, **kwargs):  # type: ignore[no-untyped-def]
        result = function()
        if on_result:
            on_result(result)

    monkeypatch.setattr(window, "_run_worker", run_now)
    window.new_image()
    ima = ima_base.with_suffix(".ima")
    assert ima.is_file()
    assert ima.stat().st_size == 368_640
    assert window.current_path == ima

    _select_combo_data(dialog.legacy_format, ImageFormat.IMG)
    img_base = tmp_path / "legacy-output-img"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(img_base), ""))
    window.new_image()
    img = img_base.with_suffix(".img")
    assert img.is_file()
    assert img.stat().st_size == 368_640
    assert window.current_path == img


def test_convert_dialog_offers_ima_target_and_suggests_ima_extension(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    dialog = ConvertDialog(tmp_path / "source.img")
    qtbot.addWidget(dialog)
    _select_combo_data(dialog.format, ImageFormat.IMA)

    assert dialog.destination.text().endswith(".ima")
