from __future__ import annotations

from pathlib import Path

from diskforge.core.device_queue import DeviceReadRequest, read_device_queue
from diskforge.core.models import DeviceInfo, DeviceKind


def _device(path: Path) -> DeviceInfo:
    return DeviceInfo(str(path), path.name, path.stat().st_size, DeviceKind.REMOVABLE, removable=True)


def test_read_device_queue_copies_each_read_only_source_and_emits_hash_audit(tmp_path: Path) -> None:
    first = tmp_path / "device-one.bin"
    second = tmp_path / "device-two.bin"
    first.write_bytes(b"first-device")
    second.write_bytes(b"second-device")

    report = read_device_queue([
        DeviceReadRequest(_device(first), tmp_path / "one.img"),
        DeviceReadRequest(_device(second), tmp_path / "two.img"),
    ])

    assert report.succeeded == 2
    assert report.failed == 0
    assert (tmp_path / "one.img").read_bytes() == first.read_bytes()
    assert (tmp_path / "two.img").read_bytes() == second.read_bytes()
    assert all(item.sha256 and item.bytes_copied > 0 for item in report.items)


def test_read_device_queue_can_continue_after_a_failed_item(tmp_path: Path) -> None:
    valid = tmp_path / "valid.bin"
    valid.write_bytes(b"valid")
    missing = tmp_path / "missing.bin"
    missing_device = DeviceInfo(str(missing), "missing", 7, DeviceKind.REMOVABLE, removable=True)

    report = read_device_queue([
        DeviceReadRequest(missing_device, tmp_path / "missing.img"),
        DeviceReadRequest(_device(valid), tmp_path / "valid.img"),
    ], continue_on_error=True)

    assert report.succeeded == 1
    assert report.failed == 1
    assert (tmp_path / "valid.img").read_bytes() == b"valid"


def test_cli_runs_read_only_device_queue_and_emits_audit_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    import json

    from diskforge.cli import main

    source = tmp_path / "device.bin"
    source.write_bytes(b"queue source")
    manifest = tmp_path / "queue.json"
    destination = tmp_path / "capture.img"
    manifest.write_text(json.dumps({
        "requests": [{
            "identifier": str(source), "display_name": "fixture", "size": source.stat().st_size,
            "kind": "removable", "destination": str(destination),
        }],
    }), encoding="utf-8")

    assert main(["--json", "read-device-queue", str(manifest)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["succeeded"] == 1
    assert payload["failed"] == 0
    assert payload["items"][0]["destination"] == str(destination)
    assert destination.read_bytes() == source.read_bytes()


def test_main_window_exposes_separate_read_only_media_queue_action(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QSettings

    from diskforge.gui.main_window import MainWindow

    window = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    assert window.action_device_read_queue.text() == "Batch read physical media…"
