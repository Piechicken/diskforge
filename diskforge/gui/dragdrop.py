"""Native drag-and-drop controls for DiskForge image workspaces.

The control deliberately accepts only local file URLs.  It never consumes arbitrary
MIME payloads or remote URLs, so a drop has the same explicit local-file semantics
as the regular injection workflow.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QListWidget, QTableWidget


class ImageEntryTable(QTableWidget):
    """Directory table with safe local-file injection and entry drag-out signals."""

    local_paths_dropped = Signal(list, str)
    entry_drag_requested = Signal()

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._accept_local_paths = False
        self._allow_entry_drag = False
        self.setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DragDropMode.NoDragDrop)

    def set_local_path_drop_enabled(self, enabled: bool) -> None:
        self._accept_local_paths = enabled
        self._refresh_drag_mode()

    def set_entry_drag_enabled(self, enabled: bool) -> None:
        self._allow_entry_drag = enabled
        self._refresh_drag_mode()

    def _refresh_drag_mode(self) -> None:
        self.setDragEnabled(self._allow_entry_drag)
        self.setDragDropMode(
            QTableWidget.DragDropMode.DragDrop if self._accept_local_paths or self._allow_entry_drag
            else QTableWidget.DragDropMode.NoDragDrop
        )

    @staticmethod
    def _local_paths(event: QDragEnterEvent | QDragMoveEvent | QDropEvent) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        paths: list[Path] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            candidate = Path(url.toLocalFile())
            if candidate.exists() and (candidate.is_file() or candidate.is_dir()):
                paths.append(candidate)
        return paths

    def _target_directory(self, position: QPoint) -> str:
        item = self.itemAt(position)
        if item is None:
            return "/"
        path_item = self.item(item.row(), 0)
        if path_item is None:
            return "/"
        image_path = str(path_item.data(Qt.ItemDataRole.UserRole) or "/")
        type_item = self.item(item.row(), 1)
        if type_item is not None and type_item.text() == "Folder":
            return image_path
        return "/"

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if self._accept_local_paths and self._local_paths(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # type: ignore[override]
        if self._accept_local_paths and self._local_paths(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        paths = self._local_paths(event)
        if not self._accept_local_paths or not paths:
            event.ignore()
            return
        self.local_paths_dropped.emit(paths, self._target_directory(event.position().toPoint()))
        event.acceptProposedAction()

    def startDrag(self, supported_actions: Qt.DropAction) -> None:  # type: ignore[override]
        if self._allow_entry_drag:
            self.entry_drag_requested.emit()


class ImageEntryList(QListWidget):
    """Icon/list representation with the same safe local URL drag-and-drop contract."""

    local_paths_dropped = Signal(list, str)
    entry_drag_requested = Signal()

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._accept_local_paths = False
        self._allow_entry_drag = False
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)

    def set_local_path_drop_enabled(self, enabled: bool) -> None:
        self._accept_local_paths = enabled
        self._refresh_drag_mode()

    def set_entry_drag_enabled(self, enabled: bool) -> None:
        self._allow_entry_drag = enabled
        self._refresh_drag_mode()

    def _refresh_drag_mode(self) -> None:
        self.setDragEnabled(self._allow_entry_drag)
        self.setDragDropMode(
            QListWidget.DragDropMode.DragDrop if self._accept_local_paths or self._allow_entry_drag
            else QListWidget.DragDropMode.NoDragDrop
        )

    @staticmethod
    def _local_paths(event: QDragEnterEvent | QDragMoveEvent | QDropEvent) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        paths: list[Path] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            candidate = Path(url.toLocalFile())
            if candidate.exists() and (candidate.is_file() or candidate.is_dir()):
                paths.append(candidate)
        return paths

    def _target_directory(self, position: QPoint) -> str:
        item = self.itemAt(position)
        if item is None:
            return "/"
        if bool(item.data(Qt.ItemDataRole.UserRole + 1)):
            return str(item.data(Qt.ItemDataRole.UserRole) or "/")
        return "/"

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if self._accept_local_paths and self._local_paths(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # type: ignore[override]
        if self._accept_local_paths and self._local_paths(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        paths = self._local_paths(event)
        if not self._accept_local_paths or not paths:
            event.ignore()
            return
        self.local_paths_dropped.emit(paths, self._target_directory(event.position().toPoint()))
        event.acceptProposedAction()

    def startDrag(self, supported_actions: Qt.DropAction) -> None:  # type: ignore[override]
        if self._allow_entry_drag:
            self.entry_drag_requested.emit()
