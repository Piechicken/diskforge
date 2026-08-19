from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from diskforge.core.formats import inspect_image
from diskforge.core.models import FileSystemType, ImageFormat, ImageInfo
from diskforge.gui import main_window as window_module
from diskforge.gui.main_window import MainWindow


@pytest.mark.parametrize("filesystem", [FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS])
def test_gui_controlled_inject_action_is_enabled_for_supported_filesystems(qtbot, tmp_path: Path, filesystem: FileSystemType) -> None:  # type: ignore[no-untyped-def]
    image = tmp_path / f"source.{filesystem.value.lower().replace('+', 'plus')}"
    image.write_bytes(b"\0")
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    window.current_info = ImageInfo(image, ImageFormat.IMG, image.stat().st_size, filesystem=filesystem)
    window.current_fs = None
    window._update_action_state()

    assert window.action_controlled_inject.isEnabled()


def test_gui_controlled_inject_action_keeps_hfs_plus_read_only(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    image = tmp_path / "source.hfsplus"
    image.write_bytes(b"\0")
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    window.current_info = ImageInfo(image, ImageFormat.IMG, image.stat().st_size, filesystem=FileSystemType.HFS_PLUS)
    window.current_fs = None
    window._update_action_state()

    assert not window.action_controlled_inject.isEnabled()


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("mkntfs", "ntfscp", "ntfsls", "ntfscat")), reason="optional ntfsprogs tools unavailable")
def test_gui_safely_injects_ntfs_into_new_output(monkeypatch, qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    source, destination, payload = tmp_path / "source.ntfs", tmp_path / "verified.ntfs", tmp_path / "PAYLOAD.TXT"
    source.write_bytes(b"\0" * (64 * 1024 * 1024))
    payload.write_bytes(b"GUI NTFS payload\n")
    subprocess.run(["mkntfs", "-F", "-Q", "-s", "512", "-S", "63", "-H", "16", "-p", "0", str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = source
    window.current_info = inspect_image(source)
    window.current_fs = None
    window._update_action_state()
    opened: list[Path] = []

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([str(payload)], ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(destination), ""))
    monkeypatch.setattr(window, "_open_path", lambda path: opened.append(Path(path)))

    def run_now(_title, function, *args, on_result=None, **kwargs):  # type: ignore[no-untyped-def]
        result = function()
        if on_result:
            on_result(result)

    monkeypatch.setattr(window, "_run_worker", run_now)
    window.inject_files_safely()

    assert destination.is_file()
    assert opened == [destination]


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("hformat", "hmount", "hcopy", "hls")), reason="optional hfsutils tools unavailable")
def test_gui_safely_injects_classic_hfs_into_new_output(monkeypatch, qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    source, destination, payload = tmp_path / "source.hfs", tmp_path / "verified.hfs", tmp_path / "PAYLOAD.TXT"
    source.write_bytes(b"\0" * (800 * 1024))
    payload.write_bytes(b"GUI classic HFS payload\n")
    subprocess.run(["hformat", "-l", "DISKFORGE", str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = source
    window.current_info = inspect_image(source)
    window.current_fs = None
    window._update_action_state()
    opened: list[Path] = []

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args, **kwargs: ([str(payload)], ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(destination), ""))
    monkeypatch.setattr(window, "_open_path", lambda path: opened.append(Path(path)))

    def run_now(_title, function, *args, on_result=None, **kwargs):  # type: ignore[no-untyped-def]
        result = function()
        if on_result:
            on_result(result)

    monkeypatch.setattr(window, "_run_worker", run_now)
    window.inject_files_safely()

    assert destination.is_file()
    assert opened == [destination]


def test_gui_shows_optional_backend_message_without_opening_dialog(monkeypatch, qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    image = tmp_path / "source.ntfs"
    image.write_bytes(b"\0" * (4096 + 1))
    with image.open("r+b") as handle:
        handle.seek(3)
        handle.write(b"NTFS    ")
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    window.current_info = inspect_image(image)
    notices: list[tuple[str, str]] = []

    class MissingInjector:
        def capability_report(self):
            return type("Report", (), {"available": False, "reason": "configured test backend missing"})()

    monkeypatch.setattr(window_module, "NtfsFileInjector", MissingInjector)
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, text: notices.append((title, text)))
    window.inject_files_safely()

    assert notices == [("Optional backend unavailable", "configured test backend missing")]
