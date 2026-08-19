from __future__ import annotations

import json
from pathlib import Path

from diskforge.cli import main
from diskforge.core.filesystems import FatImageFilesystem, create_fat_image, create_iso_from_directory
from diskforge.core.models import FileSystemType


def _manifest(path: Path, device: Path, *, removable: bool = True) -> Path:
    path.write_text(json.dumps({
        "identifier": str(device), "display_name": "Test removable media", "size": device.stat().st_size,
        "kind": "removable" if removable else "disk", "removable": removable,
        "mounted": False, "system_disk": False,
    }), encoding="utf-8")
    return path


def _mbr_device(path: Path) -> None:
    sector = bytearray(512)
    sector[:16] = b"bootstrap-code!!"
    sector[446 + 4] = 0x0C
    sector[510:512] = b"\x55\xaa"
    path.write_bytes(sector + b"\0" * (8 * 1024 * 1024))


def test_cli_safe_iso_replace_and_fat_output_workflows(tmp_path: Path, capsys) -> None:
    source_tree = tmp_path / "source"
    source_tree.mkdir()
    (source_tree / "payload.txt").write_bytes(b"original")
    source_iso = tmp_path / "source.iso"
    create_iso_from_directory(source_tree, source_iso)
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"updated!")
    replaced = tmp_path / "replaced.iso"

    assert main(["--json", "replace-iso-file", str(source_iso), "/PAYLOAD.TXT", str(replacement), str(replaced)]) == 0
    assert json.loads(capsys.readouterr().out)["destination"] == str(replaced)

    fat = create_fat_image(tmp_path / "source.img", 8 * 1024 * 1024, FileSystemType.FAT16)
    payload = tmp_path / "file.txt"
    payload.write_text("listing", encoding="utf-8")
    filesystem = FatImageFilesystem(fat)
    try:
        filesystem.inject([payload])
    finally:
        filesystem.close()
    listing = tmp_path / "listing.html"
    assert main(["--json", "export-listing", str(fat), str(listing), "--html"]) == 0
    assert json.loads(capsys.readouterr().out)["format"] == "html"
    assert "file.txt" in listing.read_text(encoding="utf-8")
    rebuilt = tmp_path / "rebuilt.img"
    assert main(["--json", "defragment-fat", str(fat), str(rebuilt)]) == 0
    assert json.loads(capsys.readouterr().out)["destination"] == str(rebuilt)


def test_cli_device_mbr_and_removable_format_require_explicit_snapshot(tmp_path: Path, capsys) -> None:
    device_path = tmp_path / "device.img"
    _mbr_device(device_path)
    manifest = _manifest(tmp_path / "device.json", device_path)
    backup = tmp_path / "saved.mbr"

    assert main(["--json", "device-mbr-backup", str(manifest), str(backup)]) == 0
    assert json.loads(capsys.readouterr().out)["operation"] == "backup"
    before_reset = tmp_path / "before-reset.mbr"
    assert main(["--json", "device-mbr-neutralize", str(manifest), str(before_reset), "--confirm", "ERASE"]) == 0
    assert json.loads(capsys.readouterr().out)["verified"] is True
    before_restore = tmp_path / "before-restore.mbr"
    assert main(["--json", "device-mbr-restore", str(manifest), str(backup), str(before_restore), "--confirm", "ERASE"]) == 0
    assert json.loads(capsys.readouterr().out)["operation"] == "restore"

    format_target = tmp_path / "format.img"
    format_target.write_bytes(b"\0" * (8 * 1024 * 1024))
    format_manifest = _manifest(tmp_path / "format.json", format_target)
    assert main(["--json", "format-removable-fat", str(format_manifest), "--fat", "16", "--label", "CLIFORMAT", "--confirm", "FORMAT"]) == 0
    formatted = json.loads(capsys.readouterr().out)
    assert formatted["label"] == "CLIFORMAT"
    assert formatted["verified"] is True


def test_cli_mount_status_reports_controlled_read_only_capability(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["--json", "mount-status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["read_only"] is True
    assert {"platform", "available", "reason"} <= set(payload)


def test_cli_create_dynamic_vhd_routes_explicit_converter_and_json(monkeypatch, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    import diskforge.cli as cli

    source = tmp_path / "source.img"
    destination = tmp_path / "dynamic.vhd"
    source.write_bytes(b"source")
    captured: dict[str, object] = {}

    def export(origin, output, converter, *, overwrite=False):  # type: ignore[no-untyped-def]
        captured.update({"origin": origin, "output": output, "executable": converter.executable, "overwrite": overwrite})
        return type("Result", (), {"source": origin, "destination": output, "virtual_size": 8192})()

    monkeypatch.setattr(cli, "create_dynamic_vhd_from_raw", export)
    assert main(["--json", "create-dynamic-vhd", str(source), str(destination), "--qemu-img", "chosen-qemu-img"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert captured == {"origin": source, "output": destination, "executable": "chosen-qemu-img", "overwrite": False}
    assert payload["disk_type"] == "dynamic"


def test_cli_create_and_extract_legacy_zip_container(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source.img"
    source.write_bytes(b"legacy payload")
    container = tmp_path / "source.imz"
    extracted = tmp_path / "extracted.img"

    assert main(["--json", "create-legacy-zip", str(source), str(container), "--format", "imz"]) == 0
    packed = json.loads(capsys.readouterr().out)
    assert packed["payload"] == "source.img"
    assert container.is_file()

    assert main(["--json", "extract-legacy-zip", str(container), str(extracted)]) == 0
    unpacked = json.loads(capsys.readouterr().out)
    assert unpacked["payload_bytes"] == len(b"legacy payload")
    assert extracted.read_bytes() == b"legacy payload"


def test_cli_floppy_format_status_reports_capability_without_executing(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["--json", "floppy-format-status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"platform", "available", "reason"} <= set(payload)


def test_cli_ufi_floppy_commands_use_explicit_snapshot_and_capacity(monkeypatch, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    import diskforge.cli as cli

    calls: list[tuple[str, object]] = []

    class Formatter:
        def usb_capability_report(self):  # type: ignore[no-untyped-def]
            return type("Report", (), {"as_mapping": lambda self: {"platform": "Linux", "available": True, "reason": "test"}})()

        def discover_usb(self, device):  # type: ignore[no-untyped-def]
            calls.append(("discover", device.identifier))
            return type("Discovery", (), {"identifier": device.identifier, "supported_capacities": (1474560,)})()

        def format_usb(self, device, capacity, confirm):  # type: ignore[no-untyped-def]
            calls.append(("format", (device.identifier, capacity, confirm)))

            class Result:
                def __init__(self) -> None:
                    self.identifier = device.identifier
                    self.backend = "ufiformat"
                    self.verified = True

            return Result()

    monkeypatch.setattr(cli, "FloppyControllerFormatter", Formatter)
    device = tmp_path / "sg4"
    device.write_bytes(b"\0" * 1024)
    manifest = _manifest(tmp_path / "ufi.json", device)
    assert main(["--json", "usb-floppy-format-status"]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is True
    assert main(["--json", "discover-ufi-floppy", str(manifest)]) == 0
    assert json.loads(capsys.readouterr().out)["supported_capacities"] == [1474560]
    assert main(["--json", "format-ufi-floppy", str(manifest), "--capacity", "1474560", "--confirm", "FORMAT_FLOPPY"]) == 0
    assert json.loads(capsys.readouterr().out)["backend"] == "ufiformat"
    assert calls == [("discover", str(device)), ("format", (str(device), 1474560, "FORMAT_FLOPPY"))]


def test_cli_rebuilds_standard_iso_after_explicit_edits(tmp_path: Path, capsys) -> None:
    source_tree = tmp_path / "source-iso"
    (source_tree / "folder").mkdir(parents=True)
    (source_tree / "KEEP.TXT").write_text("keep", encoding="utf-8")
    (source_tree / "folder" / "OLD.TXT").write_text("remove", encoding="utf-8")
    source = create_iso_from_directory(source_tree, tmp_path / "source.iso")
    added = tmp_path / "ADDED.TXT"
    added.write_text("added", encoding="utf-8")
    destination = tmp_path / "edited.iso"

    assert main([
        "--json", "edit-iso", str(source), str(destination), "--add", str(added),
        "--delete", "/folder/OLD.TXT", "--mkdir", "/empty", "--target-directory", "/folder",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["destination"] == str(destination)
    assert payload["files_added"] == ["/FOLDER/ADDED.TXT"]
    assert payload["paths_deleted"] == ["/folder/OLD.TXT"]
    assert payload["directories_created"] == ["/empty"]
