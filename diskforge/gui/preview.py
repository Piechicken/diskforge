"""Document-style Qt workspace for safe, in-process file preview and text editing."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from diskforge.core.preview import PreviewDocument
from diskforge.gui.i18n import language_manager


class FilePreviewDialog(QDialog):
    """A readable document workspace that never executes the inspected file."""

    def __init__(
        self,
        document: PreviewDocument,
        *,
        source_path: Path | None = None,
        save_back: Callable[[str, str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.document = document
        self.source_path = source_path
        self.save_back = save_back
        self._dirty = False
        try:
            self._translate = language_manager().text
        except RuntimeError:
            self._translate = lambda value: value
        self.setWindowTitle(self._translate(document.title))
        self.resize(1060, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("documentPreviewHeader")
        header_layout = QVBoxLayout(header)
        title = QLabel(self._translate(document.title))
        title.setObjectName("documentPreviewTitle")
        subtitle = QLabel(self._translate(document.summary))
        subtitle.setWordWrap(True)
        subtitle.setObjectName("documentPreviewSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        controls = QHBoxLayout()
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText(self._translate("Find in document"))
        find_button = QPushButton(self._translate("Find next"))
        find_button.clicked.connect(self._find_next)
        controls.addWidget(self.find_text, 1)
        controls.addWidget(find_button)
        self.save_copy_button = QPushButton(self._translate("Save copy…"))
        self.save_copy_button.clicked.connect(self._save_copy)
        self.save_copy_button.setVisible(document.editable)
        controls.addWidget(self.save_copy_button)
        self.save_back_button = QPushButton(self._translate("Save back to image"))
        self.save_back_button.clicked.connect(self._save_back)
        self.save_back_button.setVisible(document.editable and save_back is not None)
        controls.addWidget(self.save_back_button)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body: QPlainTextEdit | None = None
        if document.kind == "image" and document.image_path is not None:
            content = QLabel()
            content.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image = QPixmap(str(document.image_path))
            if image.isNull():
                content.setText(self._translate("The image codec could not decode this file."))
            else:
                content.setPixmap(image.scaled(820, 560, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            splitter.addWidget(content)
        else:
            self.body = QPlainTextEdit(document.text)
            self.body.setReadOnly(not document.editable)
            self.body.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.body.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            self.body.setObjectName("documentPreviewBody")
            self.body.textChanged.connect(self._mark_dirty)
            splitter.addWidget(self.body)

        details = QTextBrowser()
        details.setObjectName("documentPreviewDetails")
        details.setOpenExternalLinks(False)
        metadata = "".join(f"<li>{self._translate(item)}</li>" for item in document.details) or f"<li>{self._translate('No additional metadata.')}</li>"
        editing = self._translate("Editable plain-text content" if document.editable else "Read-only safe inspection")
        details.setHtml(f"<h3>{self._translate('Document details')}</h3><p><b>{self._translate('Mode:')}</b> {editing}</p><ul>{metadata}</ul>")
        splitter.addWidget(details)
        splitter.setSizes([760, 260])
        layout.addWidget(splitter, 1)

        self.state = QLabel(self._translate("Unsaved changes" if document.editable else "Safe read-only preview"))
        self.state.setObjectName("documentPreviewState")
        layout.addWidget(self.state)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _mark_dirty(self) -> None:
        if self.body is not None and self.document.editable:
            self._dirty = True
            self.state.setText(self._translate("Unsaved changes"))

    def _find_next(self) -> None:
        if self.body is None or not self.find_text.text():
            return
        if not self.body.find(self.find_text.text()):
            cursor = self.body.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.body.setTextCursor(cursor)
            self.body.find(self.find_text.text())

    def _text_and_encoding(self) -> tuple[str, str]:
        if self.body is None:
            return "", self.document.encoding or "utf-8"
        return self.body.toPlainText(), self.document.encoding or "utf-8"

    def _save_copy(self) -> None:
        if not self.document.editable:
            return
        suggested = self.source_path.name if self.source_path else "document.txt"
        output, _ = QFileDialog.getSaveFileName(self, self._translate("Save edited copy"), suggested, "All files (*)")
        if not output:
            return
        text, encoding = self._text_and_encoding()
        try:
            Path(output).write_text(text, encoding=encoding)
        except OSError as exc:
            self.state.setText(f"Unable to save copy: {exc}")
            return
        self._dirty = False
        self.state.setText(f"Saved copy: {output}")

    def _save_back(self) -> None:
        if self.save_back is None or not self.document.editable:
            return
        text, encoding = self._text_and_encoding()
        self.save_back(text, encoding)
        self._dirty = False
        self.state.setText(self._translate("Saving edited text back to the image…"))
