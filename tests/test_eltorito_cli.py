from __future__ import annotations

import json
from pathlib import Path

import pycdlib

from diskforge.cli import main


def _make_iso(path: Path, payload: bytes) -> Path:
    boot = path.with_suffix(".boot")
    boot.write_bytes(payload)
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3)
    try:
        iso.add_file(str(boot), iso_path="/BOOT.IMG;1")
        iso.add_eltorito("/BOOT.IMG;1", boot_load_size=1, media_name="noemul")
        iso.write(str(path))
    finally:
        iso.close()
    return path


def test_cli_eltorito_inspection_and_export(tmp_path: Path, capsys) -> None:
    payload = b"B" * 512
    source = _make_iso(tmp_path / "bootable.iso", payload)
    assert main(["--json", "iso-boot-info", str(source)]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog["images"][0]["bytes"] == 512
    exported = tmp_path / "boot.img"
    assert main(["--json", "export-boot-image", str(source), str(exported)]) == 0
    assert json.loads(capsys.readouterr().out)["bytes"] == 512
    assert exported.read_bytes() == payload
