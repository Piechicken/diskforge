"""Settings factories for normal and explicitly portable DiskForge sessions."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QSettings

_PORTABLE_ENV = "DISKFORGE_PORTABLE_DIR"


def portable_directory(arguments: Sequence[str] | None = None) -> Path | None:
    """Resolve an explicitly requested portable directory without side effects."""
    values = list(arguments if arguments is not None else sys.argv[1:])
    configured = os.environ.get(_PORTABLE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    for index, value in enumerate(values):
        if value == "--portable":
            return Path.cwd() / "DiskForgeData"
        if value.startswith("--portable="):
            location = value.partition("=")[2].strip()
            if not location:
                raise ValueError("--portable requires a directory when an equals sign is used.")
            return Path(location).expanduser().resolve()
        if value == "--portable-directory":
            if index + 1 >= len(values):
                raise ValueError("--portable-directory requires a directory.")
            return Path(values[index + 1]).expanduser().resolve()
    return None


def create_settings(arguments: Sequence[str] | None = None) -> QSettings:
    """Return ordinary organization settings or an explicitly portable INI file."""
    directory = portable_directory(arguments)
    if directory is None:
        return QSettings("DiskForge", "DiskForge")
    directory.mkdir(parents=True, exist_ok=True)
    return QSettings(str(directory / "diskforge.ini"), QSettings.Format.IniFormat)


def portable_settings_path(settings: QSettings) -> Path | None:
    """Return the INI path for a portable settings instance, else ``None``."""
    if settings.format() != QSettings.Format.IniFormat:
        return None
    name = settings.fileName()
    return Path(name) if name else None
