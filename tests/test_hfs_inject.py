from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from diskforge.core.hfs_inject import HfsFileInjector
from diskforge.core.storage import DiskForgeError, sha256_file


_HFS_TOOLS = ("hformat", "hmount", "hcopy", "hls")


def test_hfs_injector_reports_missing_optional_backend_and_refuses_use(tmp_path: Path) -> None:
    injector = HfsFileInjector("missing-hmount", "missing-hcopy", "missing-hls")
    report = injector.capability_report()

    assert report.available is False
    assert report.adapter == "hfsutils"
    with pytest.raises(DiskForgeError, match="requires explicitly configured"):
        injector.inject(tmp_path / "source.hfs", tmp_path / "output.hfs", [tmp_path / "payload.txt"])


@pytest.mark.parametrize(
    "name",
    ["", ".hidden", "colon:name", "glob*.txt", "question?.txt", "slash/name", "unicode-文件.txt", "x" * 32],
)
def test_hfs_injector_rejects_unsafe_payload_names(name: str) -> None:
    with pytest.raises(DiskForgeError):
        HfsFileInjector._target_name(name)


@pytest.mark.parametrize("name", ["PAYLOAD.TXT", "Read Me.txt", "A-1_.bin", "x" * 31])
def test_hfs_injector_accepts_safe_root_payload_names(name: str) -> None:
    assert HfsFileInjector._target_name(name) == ":" + name


@pytest.mark.skipif(not all(shutil.which(tool) for tool in _HFS_TOOLS), reason="optional hfsutils tools unavailable")
def test_hfs_injector_copy_on_write_injects_and_validates_classic_hfs(tmp_path: Path) -> None:
    source = tmp_path / "source.hfs"
    destination = tmp_path / "output.hfs"
    payload = tmp_path / "PAYLOAD.TXT"
    payload.write_bytes(b"DiskForge verified classic HFS payload\n")
    source.write_bytes(b"\0" * (800 * 1024))
    subprocess.run(
        ["hformat", "-l", "DISKFORGE", str(source)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    before = sha256_file(source)
    injector = HfsFileInjector()

    result = injector.inject(source, destination, [payload])

    assert result.destination == destination
    assert result.target_paths == (":PAYLOAD.TXT",)
    assert result.payload_sha256 == (sha256_file(payload),)
    assert sha256_file(source) == before
    assert destination.is_file()
    assert sha256_file(destination) != before

    with pytest.raises(DiskForgeError, match="refuses to overwrite existing target"):
        injector.inject(destination, tmp_path / "second-output.hfs", [payload])
