from __future__ import annotations

import json
from pathlib import Path

from diskforge.core.batch import BatchRunner
from diskforge.core.legacy_floppy import create_legacy_fat_floppy_profile
from diskforge.core.formats import inspect_image
from diskforge.core.models import ImageFormat
from diskforge.core.storage import sha256_file


def test_batch_v4_converts_img_to_explicit_ima(tmp_path: Path) -> None:
    source = create_legacy_fat_floppy_profile(
        tmp_path / "source", "pc35_dsdd_720", image_format=ImageFormat.IMG,
    )
    destination = tmp_path / "converted.ima"
    recipe = tmp_path / "convert.json"
    recipe.write_text(json.dumps({
        "schema": "diskforge.batch/v4",
        "operations": [{
            "kind": "convert", "source": str(source), "destination": str(destination), "format": "ima",
        }],
    }), encoding="utf-8")

    runner = BatchRunner()
    preview = runner.preview(recipe)
    assert preview[0]["kind"] == "convert"
    assert preview[0]["will_write"] is True
    result = runner.run(recipe)

    assert result.items[0].success is True
    assert inspect_image(destination).image_format == ImageFormat.IMA
    assert sha256_file(destination) == sha256_file(source)
