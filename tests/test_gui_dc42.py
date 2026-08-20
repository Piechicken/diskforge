from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog

from diskforge.gui.main_window import IMAGE_FILTER, MainWindow


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_open_image_routes_dc42_to_read_only_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    source = tmp_path / "archive.dc42"
    source.write_bytes(b"not-opened-by-this-routing-test")
    window = MainWindow()
    calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "DC42"))
    monkeypatch.setattr(window, "inspect_dc42_image", lambda path: calls.append(path))

    window.open_image()

    assert "*.dc42" in IMAGE_FILTER
    assert window.action_dc42.text()
    assert calls == [source]
    window.close()


def test_open_image_routes_twoimg_to_read_only_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    source = tmp_path / "archive.2img"
    source.write_bytes(b"not-opened-by-this-routing-test")
    window = MainWindow()
    calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "2MG"))
    monkeypatch.setattr(window, "inspect_twoimg_image", lambda path: calls.append(path))

    window.open_image()

    assert "*.2mg" in IMAGE_FILTER and "*.2img" in IMAGE_FILTER
    assert window.action_twoimg.text()
    assert calls == [source]
    window.close()


def test_open_image_routes_apridisk_signature_to_dedicated_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    magic = b"ACT Apricot disk image\x1a\x04"
    source = tmp_path / "archive.dsk"
    source.write_bytes(magic + b"\0" * (128 - len(magic)))
    window = MainWindow()
    apridisk_calls: list[Path] = []
    cpc_calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "APRIDISK"))
    monkeypatch.setattr(window, "inspect_apridisk_image", lambda path: apridisk_calls.append(path))
    monkeypatch.setattr(window, "inspect_cpc_dsk_image", lambda path: cpc_calls.append(path))

    window.open_image()

    assert window.action_apridisk.text()
    assert apridisk_calls == [source]
    assert not cpc_calls
    window.close()


def test_open_image_routes_copyqm_to_read_only_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    source = tmp_path / "archive.qm"
    source.write_bytes(b"not-opened-by-this-routing-test")
    window = MainWindow()
    calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "CopyQM"))
    monkeypatch.setattr(window, "inspect_copyqm_image", lambda path: calls.append(path))

    window.open_image()

    assert "*.qm" in IMAGE_FILTER
    assert window.action_copyqm.text()
    assert calls == [source]
    window.close()


def test_open_image_routes_sap_to_read_only_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    source = tmp_path / "archive.sap"
    source.write_bytes(b"not-opened-by-this-routing-test")
    window = MainWindow()
    calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "SAP"))
    monkeypatch.setattr(window, "inspect_sap_image", lambda path: calls.append(path))

    window.open_image()

    assert "*.sap" in IMAGE_FILTER
    assert window.action_sap.text()
    assert calls == [source]
    window.close()


def test_open_image_routes_msa_to_read_only_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    source = tmp_path / "archive.msa"
    source.write_bytes(b"not-opened-by-this-routing-test")
    window = MainWindow()
    calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "MSA"))
    monkeypatch.setattr(window, "inspect_msa_image", lambda path: calls.append(path))

    window.open_image()

    assert "*.msa" in IMAGE_FILTER
    assert window.action_msa.text()
    assert calls == [source]
    window.close()


def test_open_image_routes_psi_to_read_only_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    source = tmp_path / "archive.psi"
    source.write_bytes(b"not-opened-by-this-routing-test")
    window = MainWindow()
    calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "PSI"))
    monkeypatch.setattr(window, "inspect_psi_image", lambda path: calls.append(path))

    window.open_image()

    assert "*.psi" in IMAGE_FILTER
    assert window.action_psi.text()
    assert calls == [source]
    window.close()


def test_open_image_routes_pri_to_read_only_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    source = tmp_path / "archive.pri"
    source.write_bytes(b"not-opened-by-this-routing-test")
    window = MainWindow()
    calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "PRI"))
    monkeypatch.setattr(window, "inspect_pri_image", lambda path: calls.append(path))

    window.open_image()

    assert "*.pri" in IMAGE_FILTER
    assert window.action_pri.text()
    assert calls == [source]
    window.close()


def test_open_image_routes_86f_to_read_only_inspector(monkeypatch, tmp_path: Path) -> None:
    _application()
    source = tmp_path / "archive.86f"
    source.write_bytes(b"not-opened-by-this-routing-test")
    window = MainWindow()
    calls: list[Path] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(source), "86F"))
    monkeypatch.setattr(window, "inspect_86f_image", lambda path: calls.append(path))

    window.open_image()

    assert "*.86f" in IMAGE_FILTER
    assert window.action_86f.text()
    assert calls == [source]
    window.close()
