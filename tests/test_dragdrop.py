from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from diskforge.gui.dragdrop import ImageEntryTable


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _table() -> ImageEntryTable:
    _application()
    table = ImageEntryTable(1, 2)
    table.resize(420, 120)
    name = QTableWidgetItem("FOLDER")
    name.setData(Qt.ItemDataRole.UserRole, "/FOLDER")
    table.setItem(0, 0, name)
    table.setItem(0, 1, QTableWidgetItem("Folder"))
    table.show()
    QApplication.processEvents()
    return table


def test_drop_local_paths_emits_destination_directory(tmp_path: Path) -> None:
    table = _table()
    table.set_local_path_drop_enabled(True)
    source = tmp_path / "payload.txt"
    source.write_text("payload", encoding="utf-8")
    received: list[tuple[list[Path], str]] = []
    table.local_paths_dropped.connect(lambda paths, target: received.append((paths, target)))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    table.dropEvent(event)
    assert received == [([source], "/FOLDER")]


def test_drop_is_ignored_when_injection_is_disabled(tmp_path: Path) -> None:
    table = _table()
    source = tmp_path / "payload.txt"
    source.write_text("payload", encoding="utf-8")
    received: list[tuple[list[Path], str]] = []
    table.local_paths_dropped.connect(lambda paths, target: received.append((paths, target)))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    table.dropEvent(event)
    assert received == []
    assert not event.isAccepted()


def test_start_drag_requests_selected_entry_export() -> None:
    table = _table()
    table.set_entry_drag_enabled(True)
    requests: list[bool] = []
    table.entry_drag_requested.connect(lambda: requests.append(True))
    table.startDrag(Qt.DropAction.CopyAction)
    assert requests == [True]
