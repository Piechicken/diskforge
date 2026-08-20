from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from diskforge.core.storage import DiskForgeError
from diskforge.gui.batch_designer import BatchDesignerDialog


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_batch_designer_generates_safe_v4_sequence_recipe(tmp_path: Path) -> None:
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
    assert recipe["schema"] == "diskforge.batch/v4"
    assert operation["sources"] == [str(first), str(second)]
    assert operation["sequence"] == {"prefix": "archive-", "start": 1, "width": 4, "step": 1, "suffix": ""}


def test_batch_designer_rejects_missing_sources(tmp_path: Path) -> None:
    _application()
    dialog = BatchDesignerDialog()
    dialog.sources.setPlainText(str(tmp_path / "missing.img"))
    dialog.destination_root.setText(str(tmp_path / "output"))
    with pytest.raises(DiskForgeError, match="must exist"):
        dialog.recipe()


def test_batch_designer_reopens_multi_operation_recipe(tmp_path: Path) -> None:
    _application()
    source = tmp_path / "source.img"
    source.write_bytes(b"source")
    destination = tmp_path / "destination.img"
    recipe = {
        "schema": "diskforge.batch/v3",
        "operations": [
            {"name": "Archive conversion", "kind": "convert", "source": str(source), "destination": str(destination), "format": "raw"},
            {"name": "Verify archive", "kind": "verify", "source": str(source), "sha256": "0" * 64},
            {"name": "Read-only comparison", "kind": "compare", "source": str(source), "destination": str(destination)},
            {"name": "Resize copy", "kind": "resize", "source": str(source), "destination": str(tmp_path / "resized.img"), "size_bytes": 4096},
            {"name": "Create container", "kind": "bundle", "sources": [str(source)], "destination": str(tmp_path / "archive.dfb")},
        ],
    }
    dialog = BatchDesignerDialog(recipe=recipe)
    assert dialog.operations_table.rowCount() == 5
    assert dialog.recipe() == {**recipe, "schema": "diskforge.batch/v4"}


def test_batch_designer_offers_ima_as_a_conversion_target(tmp_path: Path) -> None:
    _application()
    source = tmp_path / "source.img"
    source.write_bytes(b"source")
    destination = tmp_path / "target.ima"
    dialog = BatchDesignerDialog()
    convert_index = dialog.kind_choice.findData("convert")
    ima_index = dialog.format_choice.findData("ima")
    assert convert_index >= 0 and ima_index >= 0
    dialog.kind_choice.setCurrentIndex(convert_index)
    dialog.source.setText(str(source))
    dialog.destination.setText(str(destination))
    dialog.format_choice.setCurrentIndex(ima_index)

    operation = dialog.recipe()["operations"][0]
    assert operation["kind"] == "convert"
    assert operation["format"] == "ima"


def test_batch_designer_rejects_raw_device_recipe() -> None:
    _application()
    with pytest.raises(DiskForgeError, match="Raw device"):
        BatchDesignerDialog(recipe={"schema": "diskforge.batch/v3", "operations": [{"kind": "write_device"}]})


def test_batch_designer_serializes_classic_hfs_creation(tmp_path: Path) -> None:
    _application()
    destination = tmp_path / "created.hfs"
    dialog = BatchDesignerDialog()
    kind_index = dialog.kind_choice.findData("hfs_create")
    assert kind_index >= 0
    dialog.kind_choice.setCurrentIndex(kind_index)
    dialog.destination.setText(str(destination))
    dialog.size_bytes.setText(str(800 * 1024))
    dialog.volume_label.setText("DISKFORGE")

    recipe = dialog.recipe()
    operation = recipe["operations"][0]

    assert operation == {
        "name": dialog.kind_choice.currentText(), "kind": "hfs_create",
        "destination": str(destination), "size_bytes": 800 * 1024, "label": "DISKFORGE",
    }
    reopened = BatchDesignerDialog(recipe=recipe)
    assert reopened.destination.text() == str(destination)
    assert reopened.size_bytes.text() == str(800 * 1024)
    assert reopened.volume_label.text() == "DISKFORGE"
    assert "new image" in reopened._summary(operation)


@pytest.mark.parametrize("kind", ["ntfs_inject", "ext_inject", "hfs_inject"])
def test_batch_designer_serializes_controlled_filesystem_injection(tmp_path: Path, kind: str) -> None:
    _application()
    source = tmp_path / f"source.{kind}"
    payload = tmp_path / "PAYLOAD.TXT"
    destination = tmp_path / f"output.{kind}"
    source.write_bytes(b"source")
    payload.write_bytes(b"payload")
    dialog = BatchDesignerDialog()
    kind_index = dialog.kind_choice.findData(kind)
    assert kind_index >= 0
    dialog.kind_choice.setCurrentIndex(kind_index)
    dialog.source.setText(str(source))
    dialog.destination.setText(str(destination))
    dialog.sources.setPlainText(str(payload))

    operation = dialog.recipe()["operations"][0]

    assert operation == {
        "name": dialog.kind_choice.currentText(),
        "kind": kind,
        "source": str(source),
        "destination": str(destination),
        "sources": [str(payload)],
    }


def test_batch_designer_serializes_read_only_directory_report(tmp_path: Path) -> None:
    _application()
    source = tmp_path / "partitioned.img"
    destination = tmp_path / "report.html"
    source.write_bytes(b"source")
    dialog = BatchDesignerDialog()
    kind_index = dialog.kind_choice.findData("export_listing")
    assert kind_index >= 0
    dialog.kind_choice.setCurrentIndex(kind_index)
    dialog.source.setText(str(source))
    dialog.destination.setText(str(destination))
    dialog.partition_index.setText("2")
    dialog.html_listing.setChecked(True)

    operation = dialog.recipe()["operations"][0]

    assert operation == {
        "name": dialog.kind_choice.currentText(),
        "kind": "export_listing",
        "source": str(source),
        "destination": str(destination),
        "html": True,
        "partition": 2,
    }
    reopened = BatchDesignerDialog(recipe={"schema": "diskforge.batch/v4", "operations": [operation]})
    assert reopened.source.text() == str(source)
    assert reopened.destination.text() == str(destination)
    assert reopened.partition_index.text() == "2"
    assert reopened.html_listing.isChecked()



def test_batch_designer_serializes_regular_fat_file_move(tmp_path: Path) -> None:
    _application()
    source = tmp_path / "source.img"
    source.write_bytes(b"source")
    dialog = BatchDesignerDialog()
    kind_index = dialog.kind_choice.findData("move")
    assert kind_index >= 0
    dialog.kind_choice.setCurrentIndex(kind_index)
    dialog.source.setText(str(source))
    dialog.item_path.setText("/payload.txt")
    dialog.target_directory.setText("/archive")
    dialog.partition_index.setText("2")

    operation = dialog.recipe()["operations"][0]

    assert operation == {
        "name": dialog.kind_choice.currentText(), "kind": "move", "source": str(source),
        "item_path": "/payload.txt", "target_directory": "/archive", "partition": 2,
    }
    reopened = BatchDesignerDialog(recipe={"schema": "diskforge.batch/v4", "operations": [operation]})
    assert reopened.source.text() == str(source)
    assert reopened.item_path.text() == "/payload.txt"
    assert reopened.target_directory.text() == "/archive"
    assert reopened.partition_index.text() == "2"
    assert reopened._summary(operation).endswith("→ /archive")


def test_batch_designer_rejects_invalid_fat_file_move_partition(tmp_path: Path) -> None:
    _application()
    source = tmp_path / "source.img"
    source.write_bytes(b"source")
    dialog = BatchDesignerDialog()
    kind_index = dialog.kind_choice.findData("move")
    assert kind_index >= 0
    dialog.kind_choice.setCurrentIndex(kind_index)
    dialog.source.setText(str(source))
    dialog.item_path.setText("/payload.txt")
    dialog.target_directory.setText("/archive")
    dialog.partition_index.setText("0")

    with pytest.raises(DiskForgeError, match="positive integer"):
        dialog.recipe()
