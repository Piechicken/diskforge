"""Guided, safe batch-recipe authoring for DiskForge desktop users."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from diskforge.core.models import ConflictPolicy, ExtractionLayout
from diskforge.core.sequence import SequencePattern, planned_paths
from diskforge.core.storage import DiskForgeError


class BatchDesignerDialog(QDialog):
    """Author a constrained v3 extraction recipe without hand-writing JSON."""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Batch extraction designer")
        self.resize(660, 560)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Create a safe multi-image extraction recipe. Physical devices are deliberately unavailable in unattended recipes."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.sources = QPlainTextEdit()
        self.sources.setPlaceholderText("One disk-image path per line")
        self.sources.setFixedHeight(135)
        choose_sources = QPushButton("Add images…")
        choose_sources.clicked.connect(self._choose_sources)
        source_row = QVBoxLayout()
        source_row.addWidget(self.sources)
        source_row.addWidget(choose_sources)
        form.addRow("Source images", source_row)

        self.destination_root = QLineEdit()
        choose_destination = QPushButton("Browse…")
        choose_destination.clicked.connect(self._choose_destination)
        destination_row = QHBoxLayout()
        destination_row.addWidget(self.destination_root)
        destination_row.addWidget(choose_destination)
        form.addRow("Destination root", destination_row)

        self.prefix = QLineEdit("image-")
        self.suffix = QLineEdit("")
        self.start = QSpinBox()
        self.start.setRange(0, 2_147_483_647)
        self.start.setValue(1)
        self.width = QSpinBox()
        self.width.setRange(1, 12)
        self.width.setValue(3)
        self.step = QSpinBox()
        self.step.setRange(1, 2_147_483_647)
        self.step.setValue(1)
        form.addRow("Name prefix", self.prefix)
        form.addRow("Name suffix", self.suffix)
        form.addRow("First number", self.start)
        form.addRow("Number width", self.width)
        form.addRow("Number step", self.step)

        self.layout_choice = QComboBox()
        self.layout_choice.addItem("Preserve image paths", ExtractionLayout.PRESERVE_PATHS)
        self.layout_choice.addItem("Extract all files into one directory", ExtractionLayout.FLATTEN)
        self.layout_choice.addItem("Ignore selected subdirectories", ExtractionLayout.IGNORE_SUBDIRECTORIES)
        self.conflict_choice = QComboBox()
        self.conflict_choice.addItem("Stop on existing file", ConflictPolicy.ERROR)
        self.conflict_choice.addItem("Overwrite existing file", ConflictPolicy.OVERWRITE)
        self.conflict_choice.addItem("Skip existing file", ConflictPolicy.SKIP)
        self.conflict_choice.addItem("Rename conflicting file", ConflictPolicy.RENAME)
        form.addRow("Extraction layout", self.layout_choice)
        form.addRow("Existing files", self.conflict_choice)
        layout.addLayout(form)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        for widget in (self.sources, self.destination_root, self.prefix, self.suffix):
            if isinstance(widget, QPlainTextEdit):
                widget.textChanged.connect(self.update_preview)
            else:
                widget.textChanged.connect(self.update_preview)
        for widget in (self.start, self.width, self.step):
            widget.valueChanged.connect(self.update_preview)
        self.update_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_sources(self) -> None:
        values, _ = QFileDialog.getOpenFileNames(self, "Choose source images", "", "Disk images (*.img *.ima *.bin *.dd *.dmf *.iso *.vhd *.vhdx *.vmdk *.qcow2);;All files (*)")
        if values:
            current = [line for line in self.sources.toPlainText().splitlines() if line.strip()]
            self.sources.setPlainText("\n".join([*current, *values]))

    def _choose_destination(self) -> None:
        value = QFileDialog.getExistingDirectory(self, "Choose batch destination root", self.destination_root.text())
        if value:
            self.destination_root.setText(value)

    def source_paths(self) -> list[Path]:
        return [Path(line.strip()) for line in self.sources.toPlainText().splitlines() if line.strip()]

    def sequence(self) -> SequencePattern:
        return SequencePattern(
            prefix=self.prefix.text(), suffix=self.suffix.text(), start=self.start.value(),
            width=self.width.value(), step=self.step.value(),
        )

    def update_preview(self) -> None:
        try:
            pattern = self.sequence()
            sources = self.source_paths()
            preview = pattern.preview(max(1, min(len(sources), 8)))
            self.preview.setText("Planned destination folders: " + ", ".join(preview))
        except DiskForgeError as exc:
            self.preview.setText(f"Naming error: {exc}")

    def recipe(self) -> dict:
        sources = self.source_paths()
        if not sources:
            raise DiskForgeError("Add at least one source image.")
        if not all(path.is_file() for path in sources):
            raise DiskForgeError("Every selected source image must exist.")
        root = Path(self.destination_root.text().strip())
        if not str(root):
            raise DiskForgeError("Choose a destination root directory.")
        pattern = self.sequence()
        # Validate generated names before saving, without creating output folders.
        planned_paths(root, pattern, len(sources))
        return {
            "schema": "diskforge.batch/v3",
            "operations": [{
                "name": "Sequential extraction",
                "kind": "extract",
                "sources": [str(path) for path in sources],
                "destination_root": str(root),
                "sequence": {
                    "prefix": pattern.prefix, "start": pattern.start, "width": pattern.width,
                    "step": pattern.step, "suffix": pattern.suffix,
                },
                "paths": ["/"],
                "layout": ExtractionLayout(str(self.layout_choice.currentData())).value,
                "on_conflict": ConflictPolicy(str(self.conflict_choice.currentData())).value,
            }],
        }

    def write_recipe(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.recipe(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path
