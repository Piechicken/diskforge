"""Visual, safe batch-recipe authoring for DiskForge desktop users."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from diskforge.core.models import ConflictPolicy, ExtractionLayout, ImageFormat, OperationKind
from diskforge.core.sequence import SequencePattern, planned_paths
from diskforge.core.storage import DiskForgeError


_EDITABLE_KINDS = (
    OperationKind.EXTRACT,
    OperationKind.EXPORT_LISTING,
    OperationKind.CONVERT,
    OperationKind.VERIFY,
    OperationKind.COMPARE,
    OperationKind.RESIZE,
    OperationKind.INJECT,
    OperationKind.NTFS_INJECT,
    OperationKind.EXT_INJECT,
    OperationKind.HFS_INJECT,
    OperationKind.HFS_CREATE,
    OperationKind.BUNDLE,
    OperationKind.UNBUNDLE,
)


class BatchDesignerDialog(QDialog):
    """Author, reopen, and revise safe multi-operation batch recipes visually."""

    def __init__(self, parent=None, recipe: dict[str, Any] | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Batch workflow designer")
        self.resize(820, 720)
        self._operations: list[dict[str, Any]] = []
        self._editing_index: int | None = None

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Compose a visual image workflow, review its plan, and reopen it later. "
            "Raw-device read, write, format, and repartition actions are deliberately unavailable in unattended recipes."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.operations_table = QTableWidget(0, 3)
        self.operations_table.setHorizontalHeaderLabels(["Order", "Operation", "Summary"])
        self.operations_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.operations_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.operations_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.operations_table.itemSelectionChanged.connect(self._load_selected_operation)
        layout.addWidget(self.operations_table)

        operation_buttons = QHBoxLayout()
        self.add_operation_button = QPushButton("Add operation")
        self.update_operation_button = QPushButton("Update selected")
        self.remove_operation_button = QPushButton("Remove selected")
        self.move_up_button = QPushButton("Move up")
        self.move_down_button = QPushButton("Move down")
        self.add_operation_button.clicked.connect(self.add_operation)
        self.update_operation_button.clicked.connect(self.update_selected_operation)
        self.remove_operation_button.clicked.connect(self.remove_selected_operation)
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        for button in (self.add_operation_button, self.update_operation_button, self.remove_operation_button,
                       self.move_up_button, self.move_down_button):
            operation_buttons.addWidget(button)
        operation_buttons.addStretch(1)
        layout.addLayout(operation_buttons)

        editor = QFormLayout()
        self.kind_choice = QComboBox()
        labels = {
            OperationKind.EXTRACT: "Extract image contents",
            OperationKind.EXPORT_LISTING: "Export read-only directory listing",
            OperationKind.CONVERT: "Convert image format",
            OperationKind.VERIFY: "Verify SHA-256",
            OperationKind.COMPARE: "Compare image bytes",
            OperationKind.RESIZE: "Resize image safely",
            OperationKind.INJECT: "Inject into FAT image",
            OperationKind.NTFS_INJECT: "Inject safely into new NTFS image",
            OperationKind.EXT_INJECT: "Inject safely into new EXT image",
            OperationKind.HFS_INJECT: "Inject safely into new classic HFS image",
            OperationKind.HFS_CREATE: "Create verified classic HFS image",
            OperationKind.BUNDLE: "Create secure image container",
            OperationKind.UNBUNDLE: "Extract image container",
        }
        for kind in _EDITABLE_KINDS:
            self.kind_choice.addItem(labels[kind], kind.value)
        self.kind_choice.currentIndexChanged.connect(self._update_editor_hints)
        editor.addRow("Operation", self.kind_choice)

        self.operation_name = QLineEdit()
        editor.addRow("Operation name", self.operation_name)
        self.source = QLineEdit()
        self.destination = QLineEdit()
        self.sources = QPlainTextEdit()
        self.sources.setFixedHeight(70)
        self.destination_root = self.destination  # Compatibility with the v0.5 extraction designer API.
        editor.addRow("Source image / bundle", self.source)
        editor.addRow("Destination image / folder", self.destination)
        editor.addRow("Source images or local files (one per line)", self.sources)

        sequence_layout = QHBoxLayout()
        self.prefix = QLineEdit("image-")
        self.suffix = QLineEdit()
        self.start = QSpinBox()
        self.start.setRange(0, 2_147_483_647)
        self.start.setValue(1)
        self.width = QSpinBox()
        self.width.setRange(1, 12)
        self.width.setValue(3)
        self.step = QSpinBox()
        self.step.setRange(1, 2_147_483_647)
        self.step.setValue(1)
        for title, widget in (("Prefix", self.prefix), ("Width", self.width), ("Start", self.start),
                              ("Step", self.step), ("Suffix", self.suffix)):
            sequence_layout.addWidget(QLabel(title))
            sequence_layout.addWidget(widget)
        editor.addRow("Extraction sequence", sequence_layout)

        self.paths = QLineEdit("/")
        self.target_directory = QLineEdit("/")
        self.layout_choice = QComboBox()
        self.layout_choice.addItem("Preserve image paths", ExtractionLayout.PRESERVE_PATHS)
        self.layout_choice.addItem("Extract all files into one directory", ExtractionLayout.FLATTEN)
        self.layout_choice.addItem("Ignore selected subdirectories", ExtractionLayout.IGNORE_SUBDIRECTORIES)
        self.conflict_choice = QComboBox()
        self.conflict_choice.addItem("Stop on existing file", ConflictPolicy.ERROR)
        self.conflict_choice.addItem("Overwrite existing file", ConflictPolicy.OVERWRITE)
        self.conflict_choice.addItem("Skip existing file", ConflictPolicy.SKIP)
        self.conflict_choice.addItem("Rename conflicting file", ConflictPolicy.RENAME)
        editor.addRow("Image paths to extract (one per line)", self.paths)
        editor.addRow("FAT target directory", self.target_directory)
        editor.addRow("Extraction layout", self.layout_choice)
        editor.addRow("Existing files", self.conflict_choice)

        self.format_choice = QComboBox()
        for image_format in (ImageFormat.RAW, ImageFormat.IMG, ImageFormat.IMA, ImageFormat.ISO, ImageFormat.VHD,
                             ImageFormat.VHDX, ImageFormat.VMDK, ImageFormat.QCOW2, ImageFormat.DMG):
            self.format_choice.addItem(image_format.value.upper(), image_format.value)
        self.sha256 = QLineEdit()
        self.compare_bytes = QLineEdit()
        self.size_bytes = QLineEdit()
        self.partition_index = QLineEdit()
        self.html_listing = QCheckBox("Create HTML directory report")
        self.volume_label = QLineEdit("DISKFORGE")
        self.comment = QLineEdit()
        self.description = QLineEdit()
        self.bundle_names = QLineEdit()
        self.compression_level = QSpinBox()
        self.compression_level.setRange(0, 9)
        self.compression_level.setValue(6)
        self.overwrite = QCheckBox("Allow overwrite of explicit destination")
        self.continue_on_error = QCheckBox("Continue with later operations after an error")
        editor.addRow("Target image format", self.format_choice)
        editor.addRow("Expected SHA-256", self.sha256)
        editor.addRow("Bytes to compare (optional)", self.compare_bytes)
        editor.addRow("New size in bytes", self.size_bytes)
        editor.addRow("Validated partition index (optional)", self.partition_index)
        editor.addRow("Directory report format", self.html_listing)
        editor.addRow("Volume label", self.volume_label)
        editor.addRow("Container comment", self.comment)
        editor.addRow("Container description", self.description)
        editor.addRow("Container item names (optional, comma-separated)", self.bundle_names)
        editor.addRow("Container compression level", self.compression_level)
        editor.addRow("Output policy", self.overwrite)
        editor.addRow("Failure policy", self.continue_on_error)
        layout.addLayout(editor)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        for widget in (self.source, self.destination, self.sources, self.prefix, self.suffix, self.paths,
                       self.target_directory, self.sha256, self.compare_bytes, self.size_bytes, self.partition_index, self.volume_label, self.comment,
                       self.description, self.bundle_names):
            signal = widget.textChanged if isinstance(widget, QPlainTextEdit) else widget.textChanged
            signal.connect(self.update_preview)
        for widget in (self.start, self.width, self.step, self.compression_level):
            widget.valueChanged.connect(self.update_preview)
        self.kind_choice.currentIndexChanged.connect(self.update_preview)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if recipe is not None:
            self.load_recipe(recipe)
        self._update_editor_hints()
        self.update_preview()

    @classmethod
    def from_path(cls, path: Path, parent=None) -> "BatchDesignerDialog":  # type: ignore[no-untyped-def]
        try:
            recipe = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DiskForgeError("Batch recipe is unreadable or invalid JSON.") from exc
        return cls(parent, recipe=recipe)

    def _update_editor_hints(self) -> None:
        kind = OperationKind(str(self.kind_choice.currentData()))
        hints = {
            OperationKind.EXTRACT: "For sequential extraction, enter several source images and a destination root. For one image, use Source and Destination.",
            OperationKind.EXPORT_LISTING: "Write a new text or HTML directory report from a browsable image or an explicitly selected validated partition. NTFS, EXT, HFS, and HFS+ remain read-only.",
            OperationKind.CONVERT: "Convert a source image into the chosen target format.",
            OperationKind.VERIFY: "Compare a source image against an explicit SHA-256 digest.",
            OperationKind.COMPARE: "Compare the source image with the destination image; no file is written.",
            OperationKind.RESIZE: "Create a safely resized destination image. Use an explicit byte size.",
            OperationKind.INJECT: "Inject local file paths into a writable FAT destination image.",
            OperationKind.NTFS_INJECT: "Copy a standalone NTFS image into a new output, add new root-level regular files, and verify every payload. Existing destinations and in-place changes are rejected.",
            OperationKind.EXT_INJECT: "Copy a standalone EXT image into a new output, add new root-level regular files, and verify every payload. Existing destinations and in-place changes are rejected.",
            OperationKind.HFS_INJECT: "Copy a standalone classic HFS image into a new output, add new root-level raw-data-fork files, and verify every payload. Existing destinations, in-place changes, HFS+, metadata, and resource forks are rejected.",
            OperationKind.HFS_CREATE: "Create a new standalone classic HFS output through an explicitly available hfsutils backend. Choose a new destination, at least 800 KiB in 512-byte units, and a safe volume label. HFS+, physical media, partition maps, and overwrite are rejected.",
            OperationKind.BUNDLE: "Create an unencrypted, auditable image container from selected image files.",
            OperationKind.UNBUNDLE: "Extract named or all items from an unencrypted image container.",
        }
        self.preview.setText(hints[kind])

    def _choose_sources(self) -> None:
        values, _ = QFileDialog.getOpenFileNames(
            self, "Choose source images", "",
            "Disk images (*.img *.ima *.hfs *.bin *.dd *.dmf *.iso *.vhd *.vhdx *.vmdk *.qcow2);;All files (*)",
        )
        if values:
            current = [line for line in self.sources.toPlainText().splitlines() if line.strip()]
            self.sources.setPlainText("\n".join([*current, *values]))

    def _choose_destination(self) -> None:
        value = QFileDialog.getExistingDirectory(self, "Choose batch destination root", self.destination.text())
        if value:
            self.destination.setText(value)

    def source_paths(self) -> list[Path]:
        return [Path(line.strip()) for line in self.sources.toPlainText().splitlines() if line.strip()]

    def sequence(self) -> SequencePattern:
        return SequencePattern(
            prefix=self.prefix.text(), suffix=self.suffix.text(), start=self.start.value(),
            width=self.width.value(), step=self.step.value(),
        )

    def update_preview(self) -> None:
        try:
            kind = OperationKind(str(self.kind_choice.currentData()))
            if kind == OperationKind.EXTRACT and self.source_paths():
                preview = self.sequence().preview(max(1, min(len(self.source_paths()), 8)))
                self.preview.setText("Planned destination folders: " + ", ".join(preview))
            else:
                self._update_editor_hints()
        except DiskForgeError as exc:
            self.preview.setText(f"Naming error: {exc}")

    def _current_operation(self) -> dict[str, Any]:
        kind = OperationKind(str(self.kind_choice.currentData()))
        name = self.operation_name.text().strip() or self.kind_choice.currentText()
        item: dict[str, Any] = {"name": name, "kind": kind.value}
        if self.continue_on_error.isChecked():
            item["continue_on_error"] = True
        source = self.source.text().strip()
        destination = self.destination.text().strip()
        source_paths = self.source_paths()
        if source_paths and not all(path.is_file() for path in source_paths):
            raise DiskForgeError("Every selected source image or local file must exist.")
        sources = [str(path) for path in source_paths]
        if kind == OperationKind.EXTRACT:
            paths = [value.strip() for value in self.paths.text().splitlines() if value.strip()] or ["/"]
            if len(sources) > 1:
                if not destination:
                    raise DiskForgeError("Choose a destination root directory.")
                planned_paths(destination, self.sequence(), len(sources))
                item.update({
                    "sources": sources,
                    "destination_root": destination,
                    "sequence": {
                        "prefix": self.prefix.text(), "start": self.start.value(), "width": self.width.value(),
                        "step": self.step.value(), "suffix": self.suffix.text(),
                    },
                })
            else:
                single_source = source or (sources[0] if sources else "")
                if not single_source or not destination:
                    raise DiskForgeError("Extraction requires a source image and destination directory.")
                item.update({"source": single_source, "destination": destination})
            item.update({
                "paths": paths,
                "layout": ExtractionLayout(str(self.layout_choice.currentData())).value,
                "on_conflict": ConflictPolicy(str(self.conflict_choice.currentData())).value,
            })
        elif kind == OperationKind.EXPORT_LISTING:
            if not source or not destination:
                raise DiskForgeError("Directory report export requires a source image and a new report destination.")
            item.update({"source": source, "destination": destination, "html": self.html_listing.isChecked()})
            if self.partition_index.text().strip():
                try:
                    partition = int(self.partition_index.text().strip())
                except ValueError as exc:
                    raise DiskForgeError("Directory report partition index must be a positive integer.") from exc
                if partition < 1:
                    raise DiskForgeError("Directory report partition index must be a positive integer.")
                item["partition"] = partition
        elif kind == OperationKind.CONVERT:
            if not source or not destination:
                raise DiskForgeError("Conversion requires source and destination images.")
            item.update({"source": source, "destination": destination, "format": str(self.format_choice.currentData())})
        elif kind == OperationKind.VERIFY:
            if not source or not self.sha256.text().strip():
                raise DiskForgeError("Verification requires a source image and expected SHA-256.")
            item.update({"source": source, "sha256": self.sha256.text().strip()})
        elif kind == OperationKind.COMPARE:
            if not source or not destination:
                raise DiskForgeError("Comparison requires two image paths.")
            item.update({"source": source, "destination": destination})
            if self.compare_bytes.text().strip():
                item["bytes_to_compare"] = int(self.compare_bytes.text().strip())
        elif kind == OperationKind.RESIZE:
            if not source or not destination or not self.size_bytes.text().strip():
                raise DiskForgeError("Resize requires source, destination and byte size.")
            item.update({"source": source, "destination": destination, "size_bytes": int(self.size_bytes.text().strip())})
        elif kind == OperationKind.INJECT:
            if not destination or not sources:
                raise DiskForgeError("Injection requires a FAT destination image and local file paths.")
            item.update({"destination": destination, "sources": sources, "target_directory": self.target_directory.text().strip() or "/"})
        elif kind in {OperationKind.NTFS_INJECT, OperationKind.EXT_INJECT, OperationKind.HFS_INJECT}:
            if not source or not destination or not sources:
                raise DiskForgeError("Controlled NTFS/EXT/classic HFS injection requires a source image, new destination image, and local file paths.")
            item.update({"source": source, "destination": destination, "sources": sources})
        elif kind == OperationKind.HFS_CREATE:
            if not destination or not self.size_bytes.text().strip() or not self.volume_label.text().strip():
                raise DiskForgeError("Classic HFS creation requires a new destination image, byte size, and volume label.")
            try:
                size_bytes = int(self.size_bytes.text().strip())
            except ValueError as exc:
                raise DiskForgeError("Classic HFS creation byte size must be an integer.") from exc
            item.update({"destination": destination, "size_bytes": size_bytes, "label": self.volume_label.text().strip()})
        elif kind == OperationKind.BUNDLE:
            if not destination or not sources:
                raise DiskForgeError("Container creation requires source images and destination.")
            item.update({
                "sources": sources, "destination": destination, "comment": self.comment.text(),
                "description": self.description.text(), "compression_level": self.compression_level.value(),
            })
        elif kind == OperationKind.UNBUNDLE:
            if not source or not destination:
                raise DiskForgeError("Container extraction requires source and destination.")
            item.update({"source": source, "destination": destination})
            names = [value.strip() for value in self.bundle_names.text().split(",") if value.strip()]
            if names:
                item["names"] = names
        if kind in {OperationKind.CONVERT, OperationKind.RESIZE, OperationKind.BUNDLE, OperationKind.UNBUNDLE}:
            item["overwrite"] = self.overwrite.isChecked()
        return item

    @staticmethod
    def _summary(item: dict[str, Any]) -> str:
        kind = str(item.get("kind", "operation"))
        source = "new image" if kind == OperationKind.HFS_CREATE.value else item.get("source") or f"{len(item.get('sources', []))} source(s)"
        destination = item.get("destination") or item.get("destination_root") or "read-only"
        return f"{kind}: {source} → {destination}"

    def _refresh_operation_table(self, select: int | None = None) -> None:
        self.operations_table.setRowCount(len(self._operations))
        for index, item in enumerate(self._operations):
            for column, value in enumerate((str(index + 1), str(item.get("name", item.get("kind", ""))), self._summary(item))):
                self.operations_table.setItem(index, column, QTableWidgetItem(value))
        self.operations_table.resizeColumnsToContents()
        if select is not None and 0 <= select < len(self._operations):
            self.operations_table.selectRow(select)

    def add_operation(self) -> None:
        self._operations.append(self._current_operation())
        self._editing_index = len(self._operations) - 1
        self._refresh_operation_table(self._editing_index)

    def update_selected_operation(self) -> None:
        index = self.operations_table.currentRow()
        if index < 0:
            raise DiskForgeError("Select an operation to update.")
        self._operations[index] = self._current_operation()
        self._editing_index = index
        self._refresh_operation_table(index)

    def remove_selected_operation(self) -> None:
        index = self.operations_table.currentRow()
        if index < 0:
            return
        self._operations.pop(index)
        self._editing_index = None
        self._refresh_operation_table(min(index, len(self._operations) - 1))

    def _move_selected(self, delta: int) -> None:
        index = self.operations_table.currentRow()
        target = index + delta
        if index < 0 or target < 0 or target >= len(self._operations):
            return
        self._operations[index], self._operations[target] = self._operations[target], self._operations[index]
        self._refresh_operation_table(target)

    def _load_selected_operation(self) -> None:
        index = self.operations_table.currentRow()
        if 0 <= index < len(self._operations):
            self._load_operation(self._operations[index])
            self._editing_index = index

    def _load_operation(self, item: dict[str, Any]) -> None:
        kind = OperationKind(str(item["kind"]))
        selector = self.kind_choice.findData(kind.value)
        if selector >= 0:
            self.kind_choice.setCurrentIndex(selector)
        self.operation_name.setText(str(item.get("name", "")))
        self.source.setText(str(item.get("source", "")))
        self.destination.setText(str(item.get("destination") or item.get("destination_root") or ""))
        self.sources.setPlainText("\n".join(str(value) for value in item.get("sources", [])))
        sequence = item.get("sequence", {})
        if isinstance(sequence, dict):
            self.prefix.setText(str(sequence.get("prefix", "image-")))
            self.suffix.setText(str(sequence.get("suffix", "")))
            self.start.setValue(int(sequence.get("start", 1)))
            self.width.setValue(int(sequence.get("width", 3)))
            self.step.setValue(int(sequence.get("step", 1)))
        self.paths.setText("\n".join(str(value) for value in item.get("paths", ["/"])))
        self.target_directory.setText(str(item.get("target_directory", "/")))
        self._set_combo_data(self.layout_choice, item.get("layout", ExtractionLayout.PRESERVE_PATHS.value))
        self._set_combo_data(self.conflict_choice, item.get("on_conflict", ConflictPolicy.ERROR.value))
        self._set_combo_data(self.format_choice, item.get("format", ImageFormat.IMG.value))
        self.sha256.setText(str(item.get("sha256", "")))
        self.compare_bytes.setText(str(item.get("bytes_to_compare", "")))
        self.size_bytes.setText(str(item.get("size_bytes", "")))
        self.partition_index.setText(str(item.get("partition", "")))
        self.html_listing.setChecked(bool(item.get("html", False)))
        self.volume_label.setText(str(item.get("label", "DISKFORGE")))
        self.comment.setText(str(item.get("comment", "")))
        self.description.setText(str(item.get("description", "")))
        self.bundle_names.setText(", ".join(str(value) for value in item.get("names", [])))
        self.compression_level.setValue(int(item.get("compression_level", 6)))
        self.overwrite.setChecked(bool(item.get("overwrite", False)))
        self.continue_on_error.setChecked(bool(item.get("continue_on_error", False)))
        self.update_preview()

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

    def load_recipe(self, recipe: dict[str, Any]) -> None:
        if recipe.get("schema") not in {"diskforge.batch/v1", "diskforge.batch/v2", "diskforge.batch/v3", "diskforge.batch/v4"}:
            raise DiskForgeError("Unsupported batch schema.")
        operations = recipe.get("operations")
        if not isinstance(operations, list) or not all(isinstance(item, dict) for item in operations):
            raise DiskForgeError("Batch operations must be a list.")
        rejected = [str(item.get("kind")) for item in operations if item.get("kind") in {"read_device", "write_device"}]
        if rejected:
            raise DiskForgeError("Raw device actions are not permitted in unattended batch files.")
        self._operations = [dict(item) for item in operations]
        self._refresh_operation_table(0 if self._operations else None)

    def recipe(self) -> dict[str, Any]:
        operations = self._operations or [self._current_operation()]
        return {"schema": "diskforge.batch/v4", "operations": operations}

    def write_recipe(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.recipe(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path
