from __future__ import annotations

import json
from pathlib import Path

from diskforge.cli import main
from diskforge.core.formats import QemuImgConverter


def test_missing_converter_reports_explicit_unsupported_formats_without_execution(tmp_path: Path) -> None:
    converter = QemuImgConverter(str(tmp_path / "not-installed-qemu-img"))

    report = converter.capability_report()

    assert not report.available
    assert report.executable is not None
    assert set(report.formats) == {"vhdx", "vmdk", "qcow2"}
    assert "not installed" in report.reason.lower()


def test_cli_emits_converter_capability_report(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["--json", "converter-status"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["adapter"] == "qemu-img"
    assert set(report["formats"]) == {"vhdx", "vmdk", "qcow2"}
    assert isinstance(report["available"], bool)


def test_configured_converter_process_is_terminated_when_cancelled(tmp_path: Path) -> None:
    import os
    from threading import Timer

    import pytest

    from diskforge.core.storage import CancellationToken, OperationCancelled

    executable = tmp_path / "slow-converter"
    executable.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | os.stat_result((0,) * 10).st_mode | 0o111)
    converter = QemuImgConverter(str(executable))
    token = CancellationToken()
    timer = Timer(0.2, token.cancel)
    timer.start()
    try:
        with pytest.raises(OperationCancelled):
            converter._run(["convert"], token)
    finally:
        timer.cancel()
