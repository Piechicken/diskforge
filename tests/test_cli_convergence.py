from __future__ import annotations

import json
from pathlib import Path

from diskforge.cli import main
from diskforge.core.filesystems import create_fat_image
from diskforge.core.models import FileSystemType


def test_cli_creates_bootable_iso_and_reports_catalog(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source"
    source.mkdir()
    (source / "readme.txt").write_text("bootable", encoding="utf-8")
    boot = tmp_path / "boot.img"
    boot.write_bytes(b"\x00" * 2048)
    output = tmp_path / "bootable.iso"
    assert main(["--json", "create-iso", str(source), str(output), "--boot-image", str(boot)]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["boot_image"] == str(boot)
    assert main(["--json", "iso-boot-info", str(output)]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert len(catalog["images"]) == 1


def test_cli_compare_reports_ignored_zero_tail(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    left, right = tmp_path / "left.img", tmp_path / "right.img"
    left.write_bytes(b"A" * 512)
    right.write_bytes(b"A" * 512 + b"\x00" * 512)
    assert main(["--json", "compare", str(left), str(right), "--ignore-trailing-zero-sectors"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ignored_destination_zero_tail"] == 512


def test_cli_lists_and_applies_original_boot_template_with_confirmation(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    image = create_fat_image(tmp_path / "template.img", 32 * 1024 * 1024, FileSystemType.FAT16, "CLI")
    assert main(["--json", "boot-templates"]) == 0
    templates = json.loads(capsys.readouterr().out)
    assert {item["id"] for item in templates} == {"neutral-halt", "diskforge-message"}
    assert main(["apply-boot-template", str(image), "neutral-halt", "--confirm", "WRONG"]) == 2
    assert main(["--json", "apply-boot-template", str(image), "neutral-halt", "--confirm", "APPLY_TEMPLATE"]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert Path(applied["backup"]).is_file()


def test_cli_prepares_fat_deployment_without_device_write(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    image = create_fat_image(tmp_path / "deploy.img", 32 * 1024 * 1024, FileSystemType.FAT16, "DEPLOY")
    prepared = tmp_path / "prepared.img"
    assert main(["--json", "prepare-fat-deployment", str(image), str(prepared)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["prepared_image"] == str(prepared)
    assert plan["requires_confirmation"] is True
    assert prepared.is_file()
