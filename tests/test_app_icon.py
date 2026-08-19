from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from diskforge.app import _resource_path


def test_runtime_application_icon_resources_are_present_and_loadable() -> None:
    QApplication.instance() or QApplication([])
    png = _resource_path("assets/icons/diskforge-icon.png")
    assert png.is_file()
    assert not QIcon(str(png)).isNull()
    assert _resource_path("assets/icons/diskforge-icon.ico").is_file()
    assert _resource_path("assets/icons/diskforge-icon.icns").is_file()
