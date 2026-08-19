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
    assert "DiskForgeExtractor" in captured
    assert "--onefile" in captured


def test_windows_and_macos_builds_select_native_icon(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    module = _build_module()
    for platform_name, suffix in (("Windows", ".ico"), ("Darwin", ".icns")):
        captured: list[str] = []
        monkeypatch.setattr(module.platform, "system", lambda current=platform_name: current)
        monkeypatch.setattr(module.subprocess, "run", lambda command, cwd, check: captured.extend(command))
        assert module.main() == 0
        icon = captured.index("--icon")
        assert captured[icon + 1].endswith(suffix)
        assert "DiskForgeExtractor" in captured
        assert "--onefile" in captured


def test_release_workflow_uses_immutable_tag_only_publication() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "tags: ['v*']" in workflow
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "Verify tag matches project version" in workflow
    assert "already exists; versioned release assets are immutable" in workflow
    assert "--clobber" not in workflow
    assert "apt-get update" not in workflow
    assert "apt-get install -y --no-install-recommends libegl1" in workflow
    assert "DiskForgeExtractor.exe" in workflow
    assert "cp dist/DiskForgeExtractor dist/DiskForge/DiskForgeExtractor" in workflow
    assert "DiskForge.app/Contents/MacOS/DiskForgeExtractor" in workflow


def test_package_and_project_versions_match() -> None:
    root = Path(__file__).resolve().parents[1]
    project_text = (root / "pyproject.toml").read_text(encoding="utf-8")
    namespace: dict[str, str] = {}
    exec((root / "diskforge" / "__init__.py").read_text(encoding="utf-8"), namespace)

    project_version = next(
        line.split('"', 2)[1] for line in project_text.splitlines()
        if line.startswith("version = ")
    )
    assert project_version == "0.9.0"
    assert namespace["__version__"] == project_version
