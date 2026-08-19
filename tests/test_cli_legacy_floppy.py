from __future__ import annotations

import json
from pathlib import Path

from diskforge.cli import main
from diskforge.core.formats import inspect_image
from diskforge.core.models import FileSystemType, ImageFormat


def test_cli_creates_profiled_ima_with_structured_geometry(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    base = tmp_path / "legacy"

    assert main(["--json", "create-legacy-floppy", str(base), "--profile", "pc525_dsdd_360", "--label", "CLIIMA"]) == 0

    payload = json.loads(capsys.readouterr().out)
    created = Path(payload["path"])
    assert created == base.with_suffix(".ima")
    assert payload["format"] == "ima"
    assert payload["profile"] == "pc525_dsdd_360"
    assert payload["bytes"] == 368_640
    assert payload["geometry"] == {"cylinders": 40, "heads": 2, "sectors_per_track": 9, "sector_size": 512}
    assert inspect_image(created).filesystem == FileSystemType.FAT12


def test_cli_creates_custom_img_and_rejects_ambiguous_parameters(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    base = tmp_path / "custom"
    assert main([
        "--json", "create-legacy-floppy", str(base), "--format", "img", "--cylinders", "40", "--heads", "1",
        "--sectors-per-track", "9", "--label", "CUSTOM",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    created = Path(payload["path"])
    assert created == base.with_suffix(".img")
    assert payload["profile"] is None
    assert inspect_image(created).image_format == ImageFormat.IMG

    assert main([
        "create-legacy-floppy", str(tmp_path / "invalid"), "--profile", "pc525_dsdd_360", "--heads", "2",
    ]) == 2
    assert "either a legacy floppy profile or custom geometry" in capsys.readouterr().err
