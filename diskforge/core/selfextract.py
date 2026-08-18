"""Portable self-extracting image bundles.

Instead of generating opaque executable stubs, DiskForge creates a transparent
Python zip application (``.pyz``) containing an image, a SHA-256 digest and a
small extractor.  It runs on Windows, macOS and Linux with Python 3.10+; the
release workflow can wrap the same launcher as a native Windows executable.
"""
from __future__ import annotations

import json
import os
import textwrap
import zipapp
import zipfile
from pathlib import Path

from .storage import sha256_file


_EXTRACTOR = '''\
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Extract a DiskForge image bundle")
    parser.add_argument("destination", nargs="?", default=".")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    destination = Path(args.destination).resolve()
    # In a zip application __file__ points to archive/__main__.py; argv[0] is the archive.
    with zipfile.ZipFile(Path(sys.argv[0]).resolve()) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        output = destination / manifest["filename"]
        if output.exists() and not args.force:
            raise SystemExit(f"Refusing to overwrite {output}; use --force.")
        destination.mkdir(parents=True, exist_ok=True)
        with archive.open("payload/" + manifest["filename"]) as source, output.open("wb") as target:
            shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
    if digest(output) != manifest["sha256"]:
        output.unlink(missing_ok=True)
        raise SystemExit("Digest mismatch; extraction aborted.")
    print(f"Extracted and verified: {output}")

if __name__ == "__main__":
    main()
'''


def create_self_extractor(image: Path | str, output: Path | str, *, description: str = "") -> Path:
    """Package a single image in a verifiable executable Python archive."""
    source, target = Path(image), Path(output)
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.suffix.lower() != ".pyz":
        target = target.with_suffix(".pyz")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_suffix(".stage.zip")
    manifest = {
        "format": "diskforge-self-extractor-v1",
        "filename": source.name,
        "sha256": sha256_file(source),
        "size": source.stat().st_size,
        "description": description,
    }
    with zipfile.ZipFile(stage, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        archive.writestr("__main__.py", textwrap.dedent(_EXTRACTOR))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.write(source, arcname=f"payload/{source.name}")
    # Prefix makes the archive directly executable on POSIX and Python-launchable elsewhere.
    shebang = b"#!/usr/bin/env python3\n"
    with target.open("wb") as handle, stage.open("rb") as archive:
        handle.write(shebang)
        handle.write(archive.read())
    stage.unlink(missing_ok=True)
    try:
        target.chmod(target.stat().st_mode | 0o111)
    except OSError:
        pass
    return target
