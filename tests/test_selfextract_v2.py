from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from diskforge.core.selfextract import create_self_extractor


def test_multi_image_self_extractor_selects_and_verifies_payloads(tmp_path: Path) -> None:
    first = tmp_path / "first.img"
    second = tmp_path / "second.img"
    first.write_bytes(b"first payload")
    second.write_bytes(b"second payload")
    package = create_self_extractor([first, second], tmp_path / "bundle.pyz", description="two images")
    destination = tmp_path / "selected"
    completed = subprocess.run(
        [sys.executable, str(package), str(destination), "--name", "second.img"],
        capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not (destination / "first.img").exists()
    assert (destination / "second.img").read_bytes() == b"second payload"
    repeated = subprocess.run([sys.executable, str(package), str(destination), "--name", "second.img"], capture_output=True, text=True)
    assert repeated.returncode != 0


def test_self_extractor_rejects_duplicate_payload_names(tmp_path: Path) -> None:
    first_dir, second_dir = tmp_path / "one", tmp_path / "two"
    first_dir.mkdir()
    second_dir.mkdir()
    first = first_dir / "same.img"
    second = second_dir / "same.img"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    with pytest.raises(Exception, match="unique"):
        create_self_extractor([first, second], tmp_path / "duplicate.pyz")
