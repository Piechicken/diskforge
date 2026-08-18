from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from diskforge.core.models import FileSystemType
from diskforge.core.readonly_fs import SleuthKitImageFilesystem


pytestmark = pytest.mark.skipif(
    not all(shutil.which(command) for command in ("fls", "icat", "mkfs.ext2", "debugfs")),
    reason="Sleuth Kit and ext2 fixture tools are not installed",
)


def _run(args: list[str]) -> None:
    completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


def test_sleuthkit_ext2_read_only_browse_and_extract(tmp_path: Path) -> None:
    image = tmp_path / "sample.ext2"
    host = tmp_path / "hello.txt"
    host.write_text("hello from ext2", encoding="utf-8")
    _run(["dd", "if=/dev/zero", f"of={image}", "bs=1M", "count=8", "status=none"])
    _run(["mkfs.ext2", "-q", "-F", str(image)])
    _run(["debugfs", "-w", "-R", "mkdir /nested", str(image)])
    _run(["debugfs", "-w", "-R", f"write {host} /nested/hello.txt", str(image)])

    filesystem = SleuthKitImageFilesystem(image, FileSystemType.EXT)
    try:
        root = filesystem.list_entries("/")
        assert any(entry.name == "nested" and entry.is_dir for entry in root)
        child = filesystem.list_entries("/nested")
        assert len(child) == 1
        assert child[0].name == "hello.txt"
        assert child[0].attributes.startswith("inode:")
        output = filesystem.extract(["/nested/hello.txt"], tmp_path / "extract")
        assert output[0].read_text(encoding="utf-8") == "hello from ext2"
    finally:
        filesystem.close()
