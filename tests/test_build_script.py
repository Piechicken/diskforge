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
    assert "setuptools" not in captured
    assert "jaraco" not in captured


def test_windows_and_macos_builds_select_native_icon(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    module = _build_module()
    for platform_name, suffix in (("Windows", ".ico"), ("Darwin", ".icns")):
        captured: list[str] = []
        monkeypatch.setattr(module.platform, "system", lambda current=platform_name: current)
        monkeypatch.setattr(module.subprocess, "run", lambda command, cwd, check: captured.extend(command))
        assert module.main() == 0
        icon = captured.index("--icon")
        assert captured[icon + 1].endswith(suffix)


def test_release_workflow_uses_immutable_tag_only_publication() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "tags: ['v*']" in workflow
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "Verify tag matches project version" in workflow
    assert "already exists; versioned release assets are immutable" in workflow
    assert "--clobber" not in workflow


def test_package_and_project_versions_match() -> None:
    import tomllib

    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    namespace: dict[str, str] = {}
    exec((root / "diskforge" / "__init__.py").read_text(encoding="utf-8"), namespace)

    assert metadata["project"]["version"] == "0.7.5"
    assert namespace["__version__"] == metadata["project"]["version"]
