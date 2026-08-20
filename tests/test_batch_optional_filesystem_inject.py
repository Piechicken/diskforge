from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from diskforge.core.batch import BatchRunner
from diskforge.core.storage import DiskForgeError, sha256_file


def test_batch_preview_rejects_empty_controlled_injection_sources(tmp_path: Path) -> None:
    recipe = tmp_path / "invalid.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "hfs_inject", "source": "source.hfs", "destination": "output.hfs", "sources": []}],
    }), encoding="utf-8")

    with pytest.raises(DiskForgeError, match="non-empty string list"):
        BatchRunner().preview(recipe)


def test_batch_preview_rejects_incomplete_hfs_create(tmp_path: Path) -> None:
    recipe = tmp_path / "invalid-hfs-create.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "hfs_create", "destination": "output.hfs", "label": "DISKFORGE"}],
    }), encoding="utf-8")

    with pytest.raises(DiskForgeError, match="size_bytes"):
        BatchRunner().preview(recipe)


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("mkntfs", "ntfscp", "ntfsls", "ntfscat")), reason="optional ntfsprogs tools unavailable")
def test_batch_v4_ntfs_inject_creates_new_verified_output(tmp_path: Path) -> None:
    source, output, payload = tmp_path / "source.ntfs", tmp_path / "output.ntfs", tmp_path / "PAYLOAD.TXT"
    source.write_bytes(b"\0" * (64 * 1024 * 1024))
    payload.write_bytes(b"Batch NTFS payload\n")
    subprocess.run(["mkntfs", "-F", "-Q", "-s", "512", "-S", "63", "-H", "16", "-p", "0", str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    before = sha256_file(source)
    recipe = tmp_path / "ntfs.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "ntfs_inject", "source": str(source), "destination": str(output), "sources": [str(payload)]}],
    }), encoding="utf-8")

    preview = BatchRunner().preview(recipe)
    result = BatchRunner().run(recipe)

    assert preview[0]["will_write"] is True
    assert result.succeeded == 1
    assert output.is_file()
    assert sha256_file(source) == before


@pytest.mark.skipif(not shutil.which("hformat"), reason="optional hfsutils hformat unavailable")
def test_batch_v4_hfs_create_makes_new_verified_output(tmp_path: Path) -> None:
    output = tmp_path / "created.hfs"
    recipe = tmp_path / "hfs-create.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{
            "kind": "hfs_create", "destination": str(output), "size_bytes": 800 * 1024,
            "label": "DISKFORGE",
        }],
    }), encoding="utf-8")

    preview = BatchRunner().preview(recipe)
    result = BatchRunner().run(recipe)

    assert preview[0]["will_write"] is True
    assert preview[0]["source"] is None
    assert result.succeeded == 1
    assert output.is_file()
    assert output.stat().st_size == 800 * 1024


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("hformat", "hmount", "hcopy", "hls")), reason="optional hfsutils tools unavailable")
def test_batch_v4_hfs_inject_creates_new_verified_output(tmp_path: Path) -> None:
    source, output, payload = tmp_path / "source.hfs", tmp_path / "output.hfs", tmp_path / "PAYLOAD.TXT"
    source.write_bytes(b"\0" * (800 * 1024))
    payload.write_bytes(b"Batch classic HFS payload\n")
    subprocess.run(["hformat", "-l", "DISKFORGE", str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    before = sha256_file(source)
    recipe = tmp_path / "hfs.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "hfs_inject", "source": str(source), "destination": str(output), "sources": [str(payload)]}],
    }), encoding="utf-8")

    preview = BatchRunner().preview(recipe)
    result = BatchRunner().run(recipe)

    assert preview[0]["will_write"] is True
    assert result.succeeded == 1
    assert output.is_file()
    assert sha256_file(source) == before


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("mke2fs", "debugfs", "e2fsck")), reason="optional e2fsprogs tools unavailable")
def test_batch_v4_ext_inject_creates_new_verified_output(tmp_path: Path) -> None:
    source, output, payload = tmp_path / "source.ext4", tmp_path / "output.ext4", tmp_path / "PAYLOAD.TXT"
    source.write_bytes(b"\0" * (64 * 1024 * 1024))
    payload.write_bytes(b"Batch EXT payload\n")
    subprocess.run(["mke2fs", "-q", "-t", "ext4", "-F", str(source)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    before = sha256_file(source)
    recipe = tmp_path / "ext.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{"kind": "ext_inject", "source": str(source), "destination": str(output), "sources": [str(payload)]}],
    }), encoding="utf-8")

    preview = BatchRunner().preview(recipe)
    result = BatchRunner().run(recipe)

    assert preview[0]["will_write"] is True
    assert result.succeeded == 1
    assert output.is_file()
    assert sha256_file(source) == before
