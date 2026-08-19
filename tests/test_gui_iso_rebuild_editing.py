from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog

from diskforge.core.filesystems import create_iso_from_directory
from diskforge.gui.main_window import MainWindow


def test_gui_rebuilds_iso_after_selecting_local_file(monkeypatch, qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    source_tree = tmp_path / "source"
    source_tree.mkdir()
    (source_tree / "KEEP.TXT").write_text("keep", encoding="utf-8")
    source = create_iso_from_directory(source_tree, tmp_path / "source.iso")
    added = tmp_path / "ADDED.TXT"
    added.write_text("added", encoding="utf-8")
    destination = tmp_path / "edited.iso"
    window = MainWindow()
    qtbot.addWidget(window)
    window._open_path(source)
    assert window.action_edit_iso.isEnabled()

    monkeypatch.setattr(QInputDialog, "getItem", lambda *args, **kwargs: ("Add local file…", True))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(added), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(destination), ""))

    def run_now(_title, function, *args, on_result=None, **kwargs):  # type: ignore[no-untyped-def]
        result = function()
        if on_result:
            on_result(result)

    monkeypatch.setattr(window, "_run_worker", run_now)
    window.edit_standard_iso()

    assert destination.is_file()
    assert window.current_path == destination
    assert {entry.path for entry in window.current_entries} == {"/ADDED.TXT", "/KEEP.TXT"}
