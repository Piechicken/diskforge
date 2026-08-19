from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from diskforge.cli import main
from diskforge.core.storage import sha256_file


def test_cli_reports_optional_filesystem_inject_capabilities(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["--json", "ntfs-inject-status", "--ntfscp", "missing-ntfscp"]) == 0
    ntfs = json.loads(capsys.readouterr().out)
    assert ntfs["adapter"] == "ntfsprogs"
    assert ntfs["available"] is False

    assert main(["--json", "ext-inject-status", "--debugfs", "missing-debugfs"]) == 0
    ext = json.loads(capsys.readouterr().out)
    assert ext["adapter"] == "e2fsprogs"
    assert ext["available"] is False

    assert main(["--json", "hfs-inject-status", "--hmount", "missing-hmount"]) == 0
    hfs = json.loads(capsys.readouterr().out)
    assert hfs["adapter"] == "hfsutils"
    assert hfs["available"] is False


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("mkntfs", "ntfscp", "ntfsls", "ntfscat")), reason="optional ntfsprogs tools unavailable")
def test_cli_inject_ntfs_creates_verified_copy(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    source, destination, payload = tmp_path / "source.ntfs", tmp_path / "output.ntfs", tmp_path / "PAYLOAD.TXT"
    source.write_bytes(b"\0" * (64 * 1024 * 1024))
    payload.write_bytes(b"CLI NTFS payload\n")
    subprocess.run(["mkntfs", "-F", "-Q", "-s", "512", "-S", "63", "-H", "16", "-p", "0", str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    before = sha256_file(source)

    assert main(["--json", "inject-ntfs", str(source), str(destination), str(payload)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["destination"] == str(destination)
    assert result["target_paths"] == ["/PAYLOAD.TXT"]
    assert result["payload_sha256"] == [sha256_file(payload)]
    assert sha256_file(source) == before


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("mke2fs", "debugfs", "e2fsck")), reason="optional e2fsprogs tools unavailable")
def test_cli_inject_ext_creates_verified_copy(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    source, destination, payload = tmp_path / "source.ext4", tmp_path / "output.ext4", tmp_path / "PAYLOAD.TXT"
    source.write_bytes(b"\0" * (64 * 1024 * 1024))
    payload.write_bytes(b"CLI EXT payload\n")
    subprocess.run(["mke2fs", "-q", "-t", "ext4", "-F", str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    before = sha256_file(source)

    assert main(["--json", "inject-ext", str(source), str(destination), str(payload)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["destination"] == str(destination)
    assert result["target_paths"] == ["/PAYLOAD.TXT"]
    assert result["payload_sha256"] == [sha256_file(payload)]
    assert sha256_file(source) == before


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("hformat", "hmount", "hcopy", "hls")), reason="optional hfsutils tools unavailable")
def test_cli_inject_hfs_creates_verified_copy(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    source, destination, payload = tmp_path / "source.hfs", tmp_path / "output.hfs", tmp_path / "PAYLOAD.TXT"
    source.write_bytes(b"\0" * (800 * 1024))
    payload.write_bytes(b"CLI classic HFS payload\n")
    subprocess.run(["hformat", "-l", "DISKFORGE", str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    before = sha256_file(source)

    assert main(["--json", "inject-hfs", str(source), str(destination), str(payload)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["destination"] == str(destination)
    assert result["target_paths"] == [":PAYLOAD.TXT"]
    assert result["payload_sha256"] == [sha256_file(payload)]
    assert sha256_file(source) == before
