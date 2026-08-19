from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from diskforge.core.ext_inject import ExtFileInjector
from diskforge.core.storage import DiskForgeError, sha256_file


_EXT_TOOLS = ("mke2fs", "debugfs", "e2fsck")


def test_ext_injector_reports_missing_optional_backend_and_refuses_use(tmp_path: Path) -> None:
    injector = ExtFileInjector("missing-debugfs", "missing-e2fsck")
    report = injector.capability_report()

    assert report.available is False
    assert report.adapter == "e2fsprogs"
    with pytest.raises(DiskForgeError, match="requires explicitly configured"):
        injector.inject(tmp_path / "source.ext4", tmp_path / "output.ext4", [tmp_path / "payload.txt"])


@pytest.mark.parametrize("name", ["spaces are unsafe.txt", "semi;colon.txt", "pipe|name", ".hidden"])
def test_ext_injector_rejects_command_unsafe_payload_names(tmp_path: Path, name: str) -> None:
    payload = tmp_path / name
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text("payload", encoding="utf-8")

    with pytest.raises(DiskForgeError):
        ExtFileInjector._target_path(payload)


@pytest.mark.skipif(not all(shutil.which(tool) for tool in _EXT_TOOLS), reason="optional e2fsprogs tools unavailable")
def test_ext_injector_copy_on_write_injects_and_validates_ext4(tmp_path: Path) -> None:
    source = tmp_path / "source.ext4"
    destination = tmp_path / "output.ext4"
    payload = tmp_path / "PAYLOAD.TXT"
    payload.write_bytes(b"DiskForge verified EXT payload\n")
    source.write_bytes(b"\0" * (64 * 1024 * 1024))
    subprocess.run(
        ["mke2fs", "-q", "-t", "ext4", "-F", str(source)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    before = sha256_file(source)
    injector = ExtFileInjector()

    result = injector.inject(source, destination, [payload])

    assert result.destination == destination
    assert result.target_paths == ("/PAYLOAD.TXT",)
    assert result.payload_sha256 == (sha256_file(payload),)
    assert sha256_file(source) == before
    assert destination.is_file()
    assert sha256_file(destination) != before

    with pytest.raises(DiskForgeError, match="refuses to overwrite existing target"):
        injector.inject(destination, tmp_path / "second-output.ext4", [payload])
