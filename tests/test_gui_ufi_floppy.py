from __future__ import annotations

from PySide6.QtWidgets import QApplication

from diskforge.core.models import DeviceInfo, DeviceKind
from diskforge.gui.main_window import DeviceDialog


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _device() -> DeviceInfo:
    return DeviceInfo("/dev/sg4", "USB floppy — generic SCSI UFI probe", 1_474_560,
                      DeviceKind.REMOVABLE, removable=True, mounted=False, system_disk=False)


def test_ufi_usb_floppy_gui_requires_phrase_then_explicit_discovered_capacity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import diskforge.gui.main_window as main_window

    _application()
    monkeypatch.setattr(main_window, "list_devices", lambda: [_device()])
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda parent, title, text: warnings.append((title, text)))
    dialog = DeviceDialog(None)
    assert any(button.text() == "Format UFI USB floppy" for button in dialog.findChildren(main_window.QPushButton))

    dialog._format_ufi_floppy()
    assert dialog.property("operation") is None
    assert warnings and warnings[-1][0] == "Confirmation required"

    class Formatter:
        def discover_usb(self, device):  # type: ignore[no-untyped-def]
            assert device.identifier == "/dev/sg4"
            return type("Discovery", (), {"supported_capacities": (737280, 1474560)})()

    monkeypatch.setattr(main_window, "FloppyControllerFormatter", Formatter)
    monkeypatch.setattr(main_window.QInputDialog, "getItem", lambda *args, **kwargs: ("1474560", True))
    dialog.floppy_phrase.setText("FORMAT_FLOPPY")
    dialog._format_ufi_floppy()
    assert dialog.property("operation") == ("format_ufi_floppy", _device(), 1474560, "FORMAT_FLOPPY")
