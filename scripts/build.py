"""Build a standalone DiskForge desktop package for the current platform.

Run this script on each target operating system; PyInstaller intentionally
builds native artifacts rather than cross-compiling them.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    name = "DiskForge"
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", name,
        "--collect-all", "pyfatfs", "--collect-all", "pycdlib", "--collect-all", "fs",
        "--collect-all", "setuptools", "--collect-all", "jaraco",
        "--paths", str(ROOT), str(ROOT / "diskforge" / "app.py"),
    ]
    if platform.system() == "Darwin":
        command.extend(["--osx-bundle-identifier", "org.diskforge.app"])
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"Built native package: {ROOT / 'dist' / (name + ('.app' if platform.system() == 'Darwin' else ''))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
