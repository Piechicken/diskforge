from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QDialog, QFileDialog

import diskforge.gui.main_window as main_window_module
from diskforge.core.formats import ConverterCapabilityReport
from diskforge.gui.main_window import MainWindow, NewImageDialog


def _select_combo_data(combo, value) -> None:  # type: ignore[no-untyped-def]
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_new_image_dialog_exposes_classic_hfs_creation_controls(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = NewImageDialog()
    qtbot.addWidget(dialog)
    _select_combo_data(dialog.kind, "hfs")
    dialog.show()

    assert dialog.size.isEnabled() is False
    assert dialog.hfs_size.isVisible()
    assert dialog.hfs_size.value() == 800
    assert "standalone classic HFS" in dialog.help.text()
    assert "HFS+" in dialog.help.text()


def test_new_image_delegates_verified_classic_hfs_creation(qtbot, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow()
    qtbot.addWidget(window)
    dialog = NewImageDialog(window)
    qtbot.addWidget(dialog)
    _select_combo_data(dialog.kind, "hfs")
    dialog.hfs_size.setValue(800)
    dialog.label.setText("DISKFORGE")
    monkeypatch.setattr(dialog, "exec", lambda: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(main_window_module, "NewImageDialog", lambda parent: dialog)

    output = tmp_path / "created.hfs"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(output), ""))
    calls: list[tuple[Path, int, str]] = []

    class FakeCreator:
        def capability_report(self) -> ConverterCapabilityReport:
            return ConverterCapabilityReport("hfsutils", True, "hformat", ("classic-hfs-regular-file-creation",), "available")

        def create(self, destination, size_bytes, label, *, progress=None, token=None):  # type: ignore[no-untyped-def]
            calls.append((Path(destination), size_bytes, label))
            return SimpleNamespace(destination=Path(destination))

    monkeypatch.setattr(main_window_module, "HfsImageCreator", FakeCreator)

    def run_now(_title, function, *args, on_result=None, **kwargs):  # type: ignore[no-untyped-def]
        result = function()
        if on_result:
            on_result(result)

    opened: list[Path] = []
    monkeypatch.setattr(window, "_run_worker", run_now)
    monkeypatch.setattr(window, "_open_path", lambda path: opened.append(Path(path)))

    window.new_image()

    assert calls == [(output, 800 * 1024, "DISKFORGE")]
    assert opened == [output]
