"""Build a standalone DiskForge desktop package for the current platform.

Run this script on each target operating system; PyInstaller intentionally
builds native artifacts rather than cross-compiling them.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "icons"


def _platform_icon() -> Path:
    if platform.system() == "Windows":
        return ICON_DIR / "diskforge-icon.ico"
    if platform.system() == "Darwin":
        return ICON_DIR / "diskforge-icon.icns"
    return ICON_DIR / "diskforge-icon.png"


def main() -> int:
    name = "DiskForge"
    runtime_icon = ICON_DIR / "diskforge-icon.png"
    application_icon = _platform_icon()
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", name,
        "--collect-all", "pyfatfs", "--collect-all", "pycdlib", "--collect-all", "fs",
        "--add-data", f"{runtime_icon}{os.pathsep}assets/icons",
        "--paths", str(ROOT), str(ROOT / "diskforge" / "app.py"),
    ]
    if platform.system() in {"Windows", "Darwin"}:
        command.extend(["--icon", str(application_icon)])
    if platform.system() == "Darwin":
        command.extend(["--osx-bundle-identifier", "org.diskforge.app"])
    subprocess.run(command, cwd=ROOT, check=True)
    # Build a separate console extractor rather than appending data to the
    # desktop executable.  It uses only standard-library archive handling and
    # can run on a recipient system without a pre-installed Python runtime.
    extractor = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--name", "DiskForgeExtractor", "--paths", str(ROOT), str(ROOT / "diskforge" / "extractor.py"),
    ]
    if platform.system() in {"Windows", "Darwin"}:
        extractor.extend(["--icon", str(application_icon)])
    subprocess.run(extractor, cwd=ROOT, check=True)
    print(f"Built native package: {ROOT / 'dist' / (name + ('.app' if platform.system() == 'Darwin' else ''))}")
    print(f"Built verified bundle extractor: {ROOT / 'dist' / ('DiskForgeExtractor.exe' if platform.system() == 'Windows' else 'DiskForgeExtractor')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
