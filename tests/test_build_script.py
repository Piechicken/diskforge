from __future__ import annotations

import importlib.util
from pathlib import Path


def _build_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[1] / "scripts" / "build.py"
    spec = importlib.util.spec_from_file_location("diskforge_build_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_linux_build_includes_runtime_icon_without_unsupported_icon_flag(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    module = _build_module()
    captured: list[str] = []
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(module.subprocess, "run", lambda command, cwd, check: captured.extend(command))

    assert module.main() == 0
    assert "--add-data" in captured
    assert "assets/icons" in captured[captured.index("--add-data") + 1]
    assert "--icon" not in captured


def test_windows_and_macos_builds_select_native_icon(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    module = _build_module()
    for platform_name, suffix in (("Windows", ".ico"), ("Darwin", ".icns")):
        captured: list[str] = []
        monkeypatch.setattr(module.platform, "system", lambda current=platform_name: current)
        monkeypatch.setattr(module.subprocess, "run", lambda command, cwd, check: captured.extend(command))
        assert module.main() == 0
        icon = captured.index("--icon")
        assert captured[icon + 1].endswith(suffix)
