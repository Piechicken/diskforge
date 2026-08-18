from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from diskforge.core.storage import DiskForgeError
from diskforge.gui.batch_designer import BatchDesignerDialog


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_batch_designer_generates_safe_v3_sequence_recipe(tmp_path: Path) -> None:
    _application()
    first = tmp_path / "first.img"
    second = tmp_path / "second.img"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    dialog = BatchDesignerDialog()
    dialog.sources.setPlainText(f"{first}\n{second}")
    dialog.destination_root.setText(str(tmp_path / "output"))
    dialog.prefix.setText("archive-")
    dialog.width.setValue(4)
    recipe = dialog.recipe()
    operation = recipe["operations"][0]
    assert recipe["schema"] == "diskforge.batch/v3"
    assert operation["sources"] == [str(first), str(second)]
    assert operation["sequence"] == {"prefix": "archive-", "start": 1, "width": 4, "step": 1, "suffix": ""}


def test_batch_designer_rejects_missing_sources(tmp_path: Path) -> None:
    _application()
    dialog = BatchDesignerDialog()
    dialog.sources.setPlainText(str(tmp_path / "missing.img"))
    dialog.destination_root.setText(str(tmp_path / "output"))
    with pytest.raises(DiskForgeError, match="must exist"):
        dialog.recipe()
