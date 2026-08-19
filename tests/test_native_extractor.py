from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from diskforge.core.selfextract import create_self_extractor
from diskforge.extractor import extract_self_extractor, main


def test_native_extractor_verifies_existing_pyz_payloads_without_python_launcher(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    first = tmp_path / "first.img"
    second = tmp_path / "second.img"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    archive = create_self_extractor([first, second], tmp_path / "bundle.pyz")
    destination = tmp_path / "out"

    assert main([str(archive), str(destination), "--name", "second.img"]) == 0
    assert "Extracted and verified" in capsys.readouterr().out
    assert not (destination / "first.img").exists()
    assert (destination / "second.img").read_bytes() == b"second"
    with pytest.raises(SystemExit):
        main([str(archive), str(destination), "--name", "second.img"])


def test_native_extractor_rejects_unsafe_manifest_name(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.pyz"
    manifest = {"format": "diskforge-self-extractor-v2", "items": [{"name": "../escape.img", "sha256": "0" * 64, "size": 0}]}
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("manifest.json", json.dumps(manifest))
        handle.writestr("payload/../escape.img", b"")
    with pytest.raises(ValueError, match="unsafe"):
        extract_self_extractor(archive, tmp_path / "out")
