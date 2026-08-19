"""Readable per-operation result review for visual batch workflows."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from diskforge.core.models import BatchResult


class BatchResultDialog(QDialog):
    """Present an auditable operation-by-operation batch outcome."""

    def __init__(self, result: BatchResult, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Batch workflow results")
        self.resize(940, 440)
        layout = QVBoxLayout(self)
        summary = QLabel(f"Completed {len(result.items)} operation(s): {result.succeeded} succeeded, {result.failed} failed.")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        table = QTableWidget(len(result.items), 6)
        table.setHorizontalHeaderLabels(["#", "Operation", "Status", "Source", "Output", "Detail"])
        for index, item in enumerate(result.items):
            values = (
                str(index + 1),
                item.name or item.operation.value,
                "Succeeded" if item.success else "Failed",
                str(item.source),
                str(item.destination or ""),
                item.message,
            )
            for column, value in enumerate(values):
                table.setItem(index, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        table.setWordWrap(True)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
