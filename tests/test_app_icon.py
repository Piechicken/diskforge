from __future__ import annotations

from types import SimpleNamespace

from PIL import Image
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from diskforge import app
from diskforge.app import _resource_path


def test_runtime_application_icon_resources_are_present_and_loadable() -> None:
    QApplication.instance() or QApplication([])
    png = _resource_path("assets/icons/diskforge-icon.png")
    source = _resource_path("assets/icons/diskforge-v075-source.png")
    assert source.is_file() and Image.open(source).getchannel("A").getextrema()[0] == 0
    assert png.is_file() and Image.open(png).getchannel("A").getextrema()[0] == 0
    assert not QIcon(str(png)).isNull()
    assert _resource_path("assets/icons/diskforge-icon.ico").is_file()
    assert _resource_path("assets/icons/diskforge-icon.icns").is_file()


def test_offscreen_qt_size_hint_notice_is_silenced_without_hiding_other_messages(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    context = SimpleNamespace(category="qt.qpa.plugin")
    monkeypatch.setattr(app, "_is_offscreen_platform", lambda: True)

    app._qt_message_handler(None, context, "This plugin does not support propagateSizeHints()")
    assert capsys.readouterr().err == ""

    app._qt_message_handler(None, context, "A distinct Qt diagnostic")
    assert "qt.qpa.plugin: A distinct Qt diagnostic" in capsys.readouterr().err
