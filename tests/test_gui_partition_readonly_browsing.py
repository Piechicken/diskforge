from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from diskforge.core.filesystems import FatImageFilesystem, create_fat_image
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


def test_gui_move_action_requires_one_selected_entry_in_writable_fat(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    image = create_fat_image(tmp_path / "move.img", 8 * 1024 * 1024, FileSystemType.FAT16, "MOVEGUI")
    writable = FatImageFilesystem(image)
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    window.current_fs = writable
    window.current_entries = [
        ImageEntry("/payload.txt", "payload.txt", False, 7),
        ImageEntry("/archive", "archive", True),
    ]
    try:
        monkeypatch.setattr(window, "_selected_paths", lambda: ["/payload.txt"])
        window._update_action_state()
        assert window.action_move.isEnabled()

        monkeypatch.setattr(window, "_selected_paths", lambda: ["/archive"])
        window._update_action_state()
        assert window.action_move.isEnabled()

        monkeypatch.setattr(window, "_selected_paths", lambda: ["/payload.txt", "/archive"])
        window._update_action_state()
        assert not window.action_move.isEnabled()
    finally:
        writable.close()

    read_only = FatImageFilesystem(image, read_only=True)
    window.current_fs = read_only
    try:
        monkeypatch.setattr(window, "_selected_paths", lambda: ["/payload.txt"])
        window._update_action_state()
        assert not window.action_move.isEnabled()
    finally:
        read_only.close()



def test_gui_move_worker_preserves_explicit_fat_partition_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "partitioned.img"
    source.write_bytes(b"image")
    received: dict[str, object] = {}

    class _StubFatFilesystem:
        def __init__(self, image: Path, *, partition_index: int | None = None) -> None:
            received.update({"image": image, "partition_index": partition_index})

        def move(self, item_path: str, target_directory: str, progress=None, token=None) -> str:
            received.update({"item_path": item_path, "target_directory": target_directory, "progress": progress, "token": token})
            return "/archive/source-tree"

        def close(self) -> None:
            received["closed"] = True

    monkeypatch.setattr(window_module, "FatImageFilesystem", _StubFatFilesystem)

    progress, token = object(), object()
    assert MainWindow._move_in_image(source, "/source-tree", "/archive", 2, progress, token) == "/archive/source-tree"
    assert received == {
        "image": source, "partition_index": 2, "item_path": "/source-tree",
        "target_directory": "/archive", "progress": progress, "token": token, "closed": True,
    }



def test_gui_deleted_fat_recovery_action_requires_direct_fat_session(
    qtbot, tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    image = create_fat_image(tmp_path / "recover.img", 8 * 1024 * 1024, FileSystemType.FAT16, "RECOVERGUI")
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    direct = FatImageFilesystem(image, read_only=True)
    window.current_fs = direct
    try:
        window._update_action_state()
        assert window.action_recover_deleted.isEnabled()
        window.current_browse_session = object()  # Container/virtual view: not a direct recovery source.
        window._update_action_state()
        assert not window.action_recover_deleted.isEnabled()
    finally:
        window.current_browse_session = None
        direct.close()


def test_gui_deleted_fat_recovery_worker_preserves_read_only_partition_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "partitioned.img"
    destination = tmp_path / "recovered.bin"
    source.write_bytes(b"image")
    received: dict[str, object] = {}

    class _StubFatFilesystem:
        def __init__(self, image: Path, *, read_only: bool = False, partition_index: int | None = None) -> None:
            received.update({"image": image, "read_only": read_only, "partition_index": partition_index})

        def recover_deleted_root_file(self, slot_index: int, output: Path, token=None) -> Path:  # type: ignore[no-untyped-def]
            received.update({"slot_index": slot_index, "destination": output, "token": token})
            return output

        def close(self) -> None:
            received["closed"] = True

    monkeypatch.setattr(window_module, "FatImageFilesystem", _StubFatFilesystem)

    assert MainWindow._recover_deleted_fat_file(source, 17, destination, 2, "token") == destination
    assert received == {
        "image": source, "read_only": True, "partition_index": 2, "slot_index": 17,
        "destination": destination, "token": "token", "closed": True,
    }



def test_gui_imd_inspection_action_is_available_without_a_writable_image(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow()
    qtbot.addWidget(window)
    window._update_action_state()
    assert window.action_imd.isEnabled()


def test_gui_image_inventory_action_is_available_without_an_open_image(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow()
    qtbot.addWidget(window)
    window._update_action_state()
    assert window.current_path is None
    assert window.action_inventory.isEnabled()


def test_gui_open_routes_imd_to_read_only_inspector(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "legacy.imd"
    source.write_bytes(b"IMD x\x1a")
    window = MainWindow()
    qtbot.addWidget(window)
    received: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), "Disk images (*.imd)"))
    monkeypatch.setattr(window, "inspect_imd_image", lambda path=None: received.append(path))
    monkeypatch.setattr(window, "_open_path", lambda *args, **kwargs: pytest.fail("IMD must not enter normal open routing"))
    window.open_image()
    assert received == [source]


def test_gui_td0_inspection_action_is_available_without_a_writable_image(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = MainWindow()
    qtbot.addWidget(window)
    window._update_action_state()
    assert window.action_td0.isEnabled()


def test_gui_open_routes_td0_to_read_only_inspector(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "legacy.td0"
    source.write_bytes(b"TD")
    window = MainWindow()
    qtbot.addWidget(window)
    received: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), "Disk images (*.td0)"))
    monkeypatch.setattr(window, "inspect_td0_image", lambda path=None: received.append(path))
    monkeypatch.setattr(window, "_open_path", lambda *args, **kwargs: pytest.fail("TD0 must not enter normal open routing"))
    window.open_image()
    assert received == [source]


def test_gui_dos_attribute_action_allows_multiple_entries_only_in_writable_fat(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    image = create_fat_image(tmp_path / "metadata-gui.img", 8 * 1024 * 1024, FileSystemType.FAT16, "METAGUI")
    writable = FatImageFilesystem(image)
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    window.current_fs = writable
    try:
        monkeypatch.setattr(window, "_selected_paths", lambda: ["/first.txt", "/second.txt"])
        window._update_action_state()
        assert window.action_attributes.isEnabled()
    finally:
        writable.close()

    read_only = FatImageFilesystem(image, read_only=True)
    window.current_fs = read_only
    try:
        window._update_action_state()
        assert not window.action_attributes.isEnabled()
    finally:
        read_only.close()


def test_gui_directory_creation_action_requires_writable_fat(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    image = create_fat_image(tmp_path / "directory.img", 8 * 1024 * 1024, FileSystemType.FAT16, "DIRGUI")
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    writable = FatImageFilesystem(image)
    window.current_fs = writable
    try:
        window._update_action_state()
        assert window.action_new_directory.isEnabled()
    finally:
        writable.close()

    read_only = FatImageFilesystem(image, read_only=True)
    window.current_fs = read_only
    try:
        window._update_action_state()
        assert not window.action_new_directory.isEnabled()
    finally:
        read_only.close()


def test_gui_directory_worker_preserves_explicit_fat_partition_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "partitioned.img"
    source.write_bytes(b"image")
    received: dict[str, object] = {}

    class _StubFatFilesystem:
        def __init__(self, image: Path, *, partition_index: int | None = None) -> None:
            received.update({"image": image, "partition_index": partition_index})

        def create_directory(self, directory: str, token=None) -> str:
            received.update({"directory": directory, "token": token})
            return directory

        def close(self) -> None:
            received["closed"] = True

    monkeypatch.setattr(window_module, "FatImageFilesystem", _StubFatFilesystem)
    token = object()

    assert MainWindow._create_directory_in_image(source, "/DOCS", 2, token) == "/DOCS"
    assert received == {
        "image": source, "partition_index": 2, "directory": "/DOCS", "token": token, "closed": True,
    }


def test_gui_copy_action_requires_one_selected_entry_in_writable_fat(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    image = create_fat_image(tmp_path / "copy.img", 8 * 1024 * 1024, FileSystemType.FAT16, "COPYGUI")
    writable = FatImageFilesystem(image)
    window = MainWindow()
    qtbot.addWidget(window)
    window.current_path = image
    window.current_fs = writable
    window.current_entries = [
        ImageEntry("/payload.txt", "payload.txt", False, 7),
        ImageEntry("/archive", "archive", True),
    ]
    try:
        monkeypatch.setattr(window, "_selected_paths", lambda: ["/payload.txt"])
        window._update_action_state()
        assert window.action_copy.isEnabled()

        monkeypatch.setattr(window, "_selected_paths", lambda: ["/archive"])
        window._update_action_state()
        assert window.action_copy.isEnabled()

        monkeypatch.setattr(window, "_selected_paths", lambda: ["/payload.txt", "/archive"])
        window._update_action_state()
        assert not window.action_copy.isEnabled()
    finally:
        writable.close()


def test_gui_copy_worker_preserves_explicit_fat_partition_and_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "partitioned.img"
    source.write_bytes(b"image")
    received: dict[str, object] = {}

    class _StubFatFilesystem:
        def __init__(self, image: Path, *, partition_index: int | None = None) -> None:
            received.update({"image": image, "partition_index": partition_index})

        def copy(self, item_path: str, target_directory: str, progress=None, token=None) -> str:
            received.update({"item_path": item_path, "target_directory": target_directory, "progress": progress, "token": token})
            return "/archive/payload.txt"

        def close(self) -> None:
            received["closed"] = True

    monkeypatch.setattr(window_module, "FatImageFilesystem", _StubFatFilesystem)
    progress, token = object(), object()

    assert MainWindow._copy_in_image(source, "/source-tree", "/archive", 2, progress, token) == "/archive/payload.txt"
    assert received == {
        "image": source, "partition_index": 2, "item_path": "/source-tree", "target_directory": "/archive",
        "progress": progress, "token": token, "closed": True,
    }
