from __future__ import annotations

from diskforge.gui.settings import create_settings, portable_directory, portable_settings_path


def test_explicit_portable_directory_uses_ini_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    directory = tmp_path / "portable"
    settings = create_settings([f"--portable={directory}"])
    settings.setValue("appearance", "dark")
    settings.sync()
    assert portable_directory([f"--portable={directory}"]) == directory
    assert portable_settings_path(settings) == directory / "diskforge.ini"
    reopened = create_settings([f"--portable={directory}"])
    assert reopened.value("appearance") == "dark"


def test_portable_environment_takes_precedence(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from_environment = tmp_path / "environment"
    monkeypatch.setenv("DISKFORGE_PORTABLE_DIR", str(from_environment))
    assert portable_directory(["--portable=/ignored"]) == from_environment
