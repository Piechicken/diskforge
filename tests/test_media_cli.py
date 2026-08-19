from __future__ import annotations

import json
from pathlib import Path

from diskforge.cli import main
from diskforge.core.filesystems import create_fat_image
from diskforge.core.models import FileSystemType


def test_cli_media_workflows_emit_json(tmp_path: Path, capsys) -> None:
    dmf = tmp_path / "media.dmf"
    assert main(["--json", "create-dmf", str(dmf), "--label", "CLI-DMF"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bytes"] == 80 * 2 * 21 * 512

    source = create_fat_image(tmp_path / "source.img", 2 * 1024 * 1024, FileSystemType.FAT12)
    wrapped = tmp_path / "wrapped.img"
    assert main(["--json", "wrap-mbr", str(source), str(wrapped)]) == 0
    assert json.loads(capsys.readouterr().out)["start_lba"] == 1

    raw = tmp_path / "raw.img"
    raw.write_bytes(b"Z" * 512 + b"\x00" * 512)
    trimmed = tmp_path / "trimmed.img"
    assert main(["--json", "trim-zero-tail", str(raw), str(trimmed)]) == 0
    assert json.loads(capsys.readouterr().out)["bytes_removed"] == 512


def test_cli_inspects_and_recreates_fat_layout(tmp_path: Path, capsys) -> None:
    template = tmp_path / "template.dmf"
    assert main(["--json", "create-dmf", str(template), "--label", "TEMPLATE"]) == 0
    capsys.readouterr()

    assert main(["--json", "fat-layout", str(template)]) == 0
    layout = json.loads(capsys.readouterr().out)
    assert layout["sectors_per_track"] == 21
    assert layout["heads"] == 2

    recreated = tmp_path / "recreated.img"
    assert main(["--json", "create-fat-from-layout", str(template), str(recreated), "--label", "RECREATED"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] == str(recreated)
    assert payload["layout"] == layout
