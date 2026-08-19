from __future__ import annotations

import json
from pathlib import Path

import pycdlib
import pytest

from diskforge.cli import main
from diskforge.core.eltorito import inspect_eltorito
from diskforge.core.filesystems import IsoImageFilesystem, create_iso_from_directory


@pytest.mark.parametrize(("rock_ridge", "udf"), [(True, False), (False, True), (True, True)])
def test_create_iso_can_include_rock_ridge_and_udf_profiles(tmp_path: Path, rock_ridge: bool, udf: bool) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "Mixed Name.txt").write_text("profile payload", encoding="utf-8")
    image = create_iso_from_directory(source, tmp_path / "profile.iso", rock_ridge=rock_ridge, udf=udf)

    iso = pycdlib.PyCdlib()
    iso.open(str(image))
    try:
        assert iso.has_joliet()
        assert iso.has_rock_ridge() is rock_ridge
        assert iso.has_udf() is udf
        if rock_ridge:
            assert iso.get_record(rr_path="/nested/Mixed Name.txt") is not None
        if udf:
            assert iso.get_record(udf_path="/nested/Mixed Name.txt") is not None
    finally:
        iso.close()
    filesystem = IsoImageFilesystem(image)
    try:
        extracted = filesystem.extract(["/nested/Mixed Name.txt"], tmp_path / "extract")
    finally:
        filesystem.close()
    assert extracted[0].read_text(encoding="utf-8") == "profile payload"


def test_cli_create_iso_with_extended_profiles(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.txt").write_text("payload", encoding="utf-8")
    image = tmp_path / "profile.iso"

    assert main(["--json", "create-iso", str(source), str(image), "--rock-ridge", "--udf"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["rock_ridge"] is True
    assert payload["udf"] is True
    iso = pycdlib.PyCdlib()
    iso.open(str(image))
    try:
        assert iso.has_rock_ridge() is True
        assert iso.has_udf() is True
    finally:
        iso.close()


def test_create_profiled_bootable_iso_preserves_boot_catalog(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    boot = tmp_path / "boot.img"
    boot.write_bytes(b"\0" * 2048)
    image = create_iso_from_directory(source, tmp_path / "bootable.iso", boot_image=boot, rock_ridge=True, udf=True)

    catalog = inspect_eltorito(image)
    assert len(catalog.images) == 1
    assert catalog.images[0].bootable is True
