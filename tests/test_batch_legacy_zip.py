from __future__ import annotations

import json
from pathlib import Path

from diskforge.core.batch import BatchRunner


def test_batch_v4_creates_and_extracts_safe_legacy_zip_container(tmp_path: Path) -> None:
    source = tmp_path / "source.img"
    source.write_bytes(b"batch legacy payload")
    container = tmp_path / "source.imz"
    extracted = tmp_path / "out.img"
    recipe = tmp_path / "batch.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [
            {"name": "pack", "kind": "legacy_compress", "source": str(source), "destination": str(container), "format": "imz"},
            {"name": "unpack", "kind": "legacy_extract", "source": str(container), "destination": str(extracted)},
        ],
    }), encoding="utf-8")

    runner = BatchRunner()
    preview = runner.preview(recipe)
    assert [item["kind"] for item in preview] == ["legacy_compress", "legacy_extract"]
    assert all(item["will_write"] for item in preview)
    result = runner.run(recipe)

    assert len(result.items) == 2
    assert all(item.success for item in result.items)
    assert extracted.read_bytes() == source.read_bytes()
