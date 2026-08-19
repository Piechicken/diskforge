from __future__ import annotations

import os
from pathlib import Path

import pytest

from diskforge.core.formats import Dmg2ImgConverter


def test_missing_dmg_adapter_reports_a_read_only_controlled_boundary(tmp_path: Path) -> None:
    converter = Dmg2ImgConverter(str(tmp_path / "not-installed-dmg2img"))
    report = converter.capability_report()

    assert not report.available
    assert report.adapter == "dmg2img"
    assert report.formats == ("dmg-to-raw-hfsplus",)
    assert "not installed" in report.reason.lower()


def test_explicit_dmg_adapter_writes_a_new_output_without_overwrite(tmp_path: Path) -> None:
    if os.name == "nt":
        executable = tmp_path / "dmg2img.cmd"
        executable.write_text(
            "@echo off\r\n"
            "setlocal\r\n"
            ":loop\r\n"
            "if \"%~1\"==\"\" goto done\r\n"
            "if \"%~1\"==\"-o\" (set out=%~2 & shift)\r\n"
            "shift\r\n"
            "goto loop\r\n"
            ":done\r\n"
            "> \"%out%\" <nul set /p =converted\r\n"
            "exit /b 0\r\n",
            encoding="utf-8",
        )
    else:
        executable = tmp_path / "dmg2img"
        executable.write_text(
            "#!/bin/sh\nwhile [ $# -gt 0 ]; do\n  if [ \"$1\" = \"-o\" ]; then out=$2; shift 2; continue; fi\n  shift\ndone\nprintf converted > \"$out\"\n",
            encoding="utf-8",
        )
        executable.chmod(executable.stat().st_mode | 0o111)
    source = tmp_path / "sample.dmg"
    source.write_bytes(b"koly")
    destination = tmp_path / "sample.raw"
    converter = Dmg2ImgConverter(str(executable))

    output = converter.convert(source, destination)

    assert output == destination
    assert destination.read_bytes() == b"converted"
    with pytest.raises(FileExistsError):
        converter.convert(source, destination)


def test_cli_emits_dmg_adapter_capability_report(capsys) -> None:  # type: ignore[no-untyped-def]
    import json

    from diskforge.cli import main

    assert main(["--json", "dmg-adapter-status"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["adapter"] == "dmg2img"
    assert report["formats"] == ["dmg-to-raw-hfsplus"]
    assert isinstance(report["available"], bool)


def test_main_window_enables_dmg_conversion_only_for_dmg(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui.main_window import MainWindow

    dmg = tmp_path / "sample.dmg"
    dmg.write_bytes(b"DMG test")
    raw = tmp_path / "sample.img"
    raw.write_bytes(b"raw test")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    qtbot.addWidget(window)

    window._open_path(dmg)
    assert window.action_convert_dmg.isEnabled()
    window._open_path(raw)
    assert not window.action_convert_dmg.isEnabled()
