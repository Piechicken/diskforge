from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge.core.batch import BatchRunner
from diskforge.core.filesystems import create_iso_from_directory
from diskforge.core.storage import DiskForgeError, sha256_file


def _recipe(path: Path, operation: dict[str, object]) -> Path:
    path.write_text(json.dumps({"schema": "diskforge.batch/v4", "operations": [operation]}), encoding="utf-8")
    return path


def test_batch_exports_generic_iso_directory_report_without_changing_source(tmp_path: Path) -> None:
    source_tree = tmp_path / "source"
    source_tree.mkdir()
    (source_tree / "README.TXT").write_text("directory report", encoding="utf-8")
    image = create_iso_from_directory(source_tree, tmp_path / "source.iso")
    report = tmp_path / "report.html"
    recipe = _recipe(tmp_path / "report.json", {
        "kind": "export_listing", "source": str(image), "destination": str(report), "html": True,
    })
    before = sha256_file(image)
    runner = BatchRunner()

    preview = runner.preview(recipe)
    result = runner.run(recipe)

    assert preview == [{
        "index": 0, "name": "export_listing", "kind": "export_listing", "source": str(image),
        "destination": str(report), "will_write": True,
    }]
    assert result.items[0].success
    assert result.items[0].destination == report
    assert "README.TXT" in report.read_text(encoding="utf-8")
    assert sha256_file(image) == before


def test_batch_directory_report_rejects_nonpositive_partition_during_preview(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "invalid-report.json", {
        "kind": "export_listing", "source": "disk.img", "destination": "report.txt", "partition": 0,
    })

    with pytest.raises(DiskForgeError, match="positive integer"):
        BatchRunner().preview(recipe)
