"""Transparent, verifiable cross-platform self-extracting image archives.

A ``.pyz`` is intentionally used instead of an opaque native stub.  Its manifest
is inspectable, payload paths are flat and validated, and every extracted image
is checked before it is reported as available.
"""
from __future__ import annotations

import json
import os
import shutil
import textwrap
import zipfile
from collections.abc import Iterable
from pathlib import Path

from .storage import DiskForgeError, sha256_file


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
    parser.add_argument("--name", action="append", dest="names", help="Extract only this payload name; repeatable")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    destination = Path(args.destination).resolve()
    with zipfile.ZipFile(Path(sys.argv[0]).resolve()) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        # v1 archives remain readable by normalizing their one payload.
        items = manifest.get("items") or [{
            "name": manifest["filename"], "sha256": manifest["sha256"], "size": manifest["size"],
        }]
        known = {item["name"] for item in items}
        selected = set(args.names or known)
        unknown = selected - known
        if unknown:
            raise SystemExit("Unknown payload selection: " + ", ".join(sorted(unknown)))
        destination.mkdir(parents=True, exist_ok=True)
        for item in items:
            name = item["name"]
            if name not in selected:
                continue
            if Path(name).name != name or not name:
                raise SystemExit("Unsafe payload name in manifest.")
            output = destination / name
            if output.exists() and not args.force:
                raise SystemExit(f"Refusing to overwrite {output}; use --force.")
            with archive.open("payload/" + name) as source, output.open("wb") as target:
                shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
            if digest(output) != item["sha256"] or output.stat().st_size != item["size"]:
                output.unlink(missing_ok=True)
                raise SystemExit(f"Verification failed for {name}; extraction aborted.")
            print(f"Extracted and verified: {output}")

if __name__ == "__main__":
    main()
'''


def _normalise_sources(images: Path | str | Iterable[Path | str]) -> tuple[Path, ...]:
    if isinstance(images, (Path, str)):
        values = (Path(images),)
    else:
        values = tuple(Path(value) for value in images)
    if not values:
        raise DiskForgeError("A self-extracting bundle requires at least one image.")
    names = [value.name for value in values]
    if len(set(names)) != len(names):
        raise DiskForgeError("Self-extracting bundle payload names must be unique.")
    for source in values:
        if not source.is_file():
            raise FileNotFoundError(source)
    return values


def create_self_extractor(images: Path | str | Iterable[Path | str], output: Path | str, *,
                          description: str = "", overwrite: bool = False) -> Path:
    """Package one or more images in a verifiable Python zip application."""
    sources, target = _normalise_sources(images), Path(output)
    if target.suffix.lower() != ".pyz":
        target = target.with_suffix(".pyz")
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_suffix(target.suffix + ".stage.zip")
    manifest = {
        "format": "diskforge-self-extractor-v2",
        "description": description,
        "items": [
            {"name": source.name, "sha256": sha256_file(source), "size": source.stat().st_size}
            for source in sources
        ],
    }
    try:
        with zipfile.ZipFile(stage, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("__main__.py", textwrap.dedent(_EXTRACTOR))
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            for source in sources:
                archive.write(source, arcname=f"payload/{source.name}")
        # Prefix makes the archive directly executable on POSIX and Python-launchable elsewhere.
        with target.open("wb") as handle, stage.open("rb") as archive:
            handle.write(b"#!/usr/bin/env python3\n")
            shutil.copyfileobj(archive, handle, length=8 * 1024 * 1024)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        stage.unlink(missing_ok=True)
    try:
        target.chmod(target.stat().st_mode | 0o111)
    except OSError:
        pass
    return target
