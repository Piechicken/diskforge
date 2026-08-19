from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from diskforge.core.preview import PreviewDocument
from diskforge.gui.preview import FilePreviewDialog


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_editable_text_preview_exposes_document_workflow(tmp_path: Path) -> None:
    _application()
    source = tmp_path / "notes.txt"
    source.write_text("draft", encoding="utf-8")
    dialog = FilePreviewDialog(
        PreviewDocument("text", "Text editor", "Editable text", text="draft", editable=True, encoding="utf-8"),
        source_path=source,
        save_back=lambda text, encoding: None,
    )

    assert dialog.body is not None and not dialog.body.isReadOnly()
    assert dialog.save_copy_button.isVisible() is False  # parentless widgets are not shown yet
    assert dialog.save_back_button.isHidden() is False
    assert dialog.find_text.placeholderText() == "Find in document"


def test_binary_preview_remains_read_only() -> None:
    _application()
    dialog = FilePreviewDialog(PreviewDocument("binary", "Binary inspection", "Safe inspection", text="00000000  FF", editable=False))

    assert dialog.body is not None and dialog.body.isReadOnly()
    assert dialog.save_copy_button.isHidden()
    assert dialog.save_back_button.isHidden()
