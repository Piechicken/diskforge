from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from diskforge.core.models import DiskPartition, FileSystemType, ImageEntry
from diskforge.gui import main_window as window_module
from diskforge.gui.main_window import MainWindow


class _StubReadOnlyFilesystem:
    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        return []

    def close(self) -> None:
        pass


def _image(path: Path) -> Path:
    data = bytearray(1024)
    data[446 + 4] = 0x83
    data[510:512] = b"\x55\xaa"
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("filesystem", [
    FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS, FileSystemType.HFS_PLUS,
])
def test_gui_opens_supported_non_fat_partition_as_read_only(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filesystem: FileSystemType,
) -> None:  # type: ignore[no-untyped-def]
    image = _image(tmp_path / "partitioned.img")
    window = MainWindow()
    qtbot.addWidget(window)
    received: dict[str, object] = {}
    readonly = _StubReadOnlyFilesystem()

    def open_router(source: Path, index: int, *, writable: bool = False):  # type: ignore[no-untyped-def]
        received.update({"source": source, "index": index, "writable": writable})
        return readonly

    monkeypatch.setattr(window_module, "open_partition_filesystem", open_router)
    monkeypatch.setattr(window, "_populate_tree", lambda: None)
    monkeypatch.setattr(window, "_populate_table", lambda _path: None)
    monkeypatch.setattr(window, "_show_info", lambda: None)

    window._open_path(image, partition_index=1)

    assert window.current_fs is readonly
    assert received == {"source": image, "index": 1, "writable": False}
    assert window.action_export.isEnabled()
    assert window.action_print.isEnabled()
    assert not window.action_inject.isEnabled()
    assert not window.action_delete.isEnabled()
    assert not window.action_rename.isEnabled()
    assert not window.action_controlled_inject.isEnabled()


def test_gui_partition_chooser_routes_supported_non_fat_index(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    image = _image(tmp_path / "partitioned.img")
    partition = DiskPartition(1, 64, 32, "Linux", filesystem=FileSystemType.EXT)
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    opened: list[tuple[Path, int | None]] = []

    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(window_module, "list_partitions", lambda _path: [partition])
    monkeypatch.setattr(QInputDialog, "getItem", lambda *_args, **_kwargs: (_args[3][0], True))
    monkeypatch.setattr(window, "_open_path", lambda path, *, partition_index=None: opened.append((path, partition_index)))
    monkeypatch.setattr(QMessageBox, "critical", lambda _parent, title, text: errors.append((title, text)))

    window.show_partitions()

    assert errors == []
    assert opened == [(image, 1)]
