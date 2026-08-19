"""Qt rendering for DiskForge's non-executing file preview service."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QPlainTextEdit,
                               QVBoxLayout, QWidget)

from diskforge.core.preview import PreviewDocument


class FilePreviewDialog(QDialog):
    """Display a bounded in-process file preview without launching user content."""

    def __init__(self, document: PreviewDocument, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(document.title)
        self.resize(860, 620)
        layout = QVBoxLayout(self)
        heading = QLabel(f"<b>{document.title}</b>")
        heading.setObjectName("previewHeading")
        layout.addWidget(heading)
        summary = QLabel(document.summary)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        if document.details:
            details = QLabel("<br>".join(document.details))
            details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            details.setWordWrap(True)
            details.setObjectName("previewDetails")
            layout.addWidget(details)
        if document.kind == "image" and document.image_path is not None:
            image = QPixmap(str(document.image_path))
            if image.isNull():
                fallback = QPlainTextEdit("The image codec could not decode this file.")
                fallback.setReadOnly(True)
                layout.addWidget(fallback, 1)
            else:
                image_label = QLabel()
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                image_label.setPixmap(image.scaled(800, 480, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
                layout.addWidget(image_label, 1)
        else:
            body = QPlainTextEdit(document.text)
            body.setReadOnly(True)
            body.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            body.setObjectName("previewBody")
            layout.addWidget(body, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
