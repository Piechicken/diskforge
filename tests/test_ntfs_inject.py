from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from diskforge.core.ntfs_inject import NtfsFileInjector
from diskforge.core.storage import DiskForgeError, sha256_file


_NTFS_TOOLS = ("mkntfs", "ntfscp", "ntfsls", "ntfscat")


def test_ntfs_injector_reports_missing_optional_backend_and_refuses_use(tmp_path: Path) -> None:
    injector = NtfsFileInjector("missing-ntfscp", "missing-ntfsls", "missing-ntfscat")
    report = injector.capability_report()

    assert report.available is False
    assert report.adapter == "ntfsprogs"
    with pytest.raises(DiskForgeError, match="requires explicitly configured"):
        injector.inject(tmp_path / "source.ntfs", tmp_path / "output.ntfs", [tmp_path / "payload.txt"])


@pytest.mark.parametrize("name", ["CON", "report?.txt", "trailing.", "trailing "])
def test_ntfs_injector_rejects_windows_unsafe_payload_names(name: str) -> None:
    with pytest.raises(DiskForgeError):
        NtfsFileInjector._target_name(name)


@pytest.mark.skipif(not all(shutil.which(tool) for tool in _NTFS_TOOLS), reason="optional ntfsprogs tools unavailable")
def test_ntfs_injector_copy_on_write_injects_and_verifies_regular_files(tmp_path: Path) -> None:
    source = tmp_path / "source.ntfs"
    destination = tmp_path / "output.ntfs"
    payload = tmp_path / "PAYLOAD.TXT"
    payload.write_bytes(b"DiskForge verified NTFS payload\n")
    source.write_bytes(b"\0" * (64 * 1024 * 1024))
    subprocess.run(
        ["mkntfs", "-F", "-Q", "-s", "512", "-S", "63", "-H", "16", "-p", "0", "-L", "DISKFORGE", str(source)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    before = sha256_file(source)
    injector = NtfsFileInjector()

    result = injector.inject(source, destination, [payload])

    assert result.destination == destination
    assert result.target_paths == ("/PAYLOAD.TXT",)
    assert result.payload_sha256 == (sha256_file(payload),)
    assert sha256_file(source) == before
    assert destination.is_file()
    assert sha256_file(destination) != before

    with pytest.raises(DiskForgeError, match="refuses to overwrite existing target"):
        injector.inject(destination, tmp_path / "second-output.ntfs", [payload])
