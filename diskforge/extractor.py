"""Standalone verified extractor for DiskForge `.pyz` image bundles.

This module intentionally depends only on the Python standard library.  The
build script packages it as a separate native executable so a recipient need
not pre-install Python to extract a DiskForge self-extracting archive.  It does
not append data to, inspect, or mutate the primary desktop application bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from collections.abc import Iterable
from pathlib import Path


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _items(archive: zipfile.ZipFile) -> list[dict[str, object]]:
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Archive does not contain a valid DiskForge manifest.") from exc
    if not isinstance(manifest, dict):
        raise ValueError("DiskForge manifest must be an object.")
    entries = manifest.get("items") or [{
        "name": manifest.get("filename"), "sha256": manifest.get("sha256"), "size": manifest.get("size"),
    }]
    if not isinstance(entries, list) or not entries:
        raise ValueError("DiskForge manifest does not declare payload items.")
    checked: list[dict[str, object]] = []
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("DiskForge manifest contains an invalid payload entry.")
        name, digest, size = entry.get("name"), entry.get("sha256"), entry.get("size")
        if not isinstance(name, str) or not name or Path(name).name != name or name in names:
            raise ValueError("DiskForge manifest contains an unsafe or duplicate payload name.")
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
            raise ValueError(f"DiskForge manifest has an invalid SHA-256 for {name}.")
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"DiskForge manifest has an invalid size for {name}.")
        names.add(name)
        checked.append({"name": name, "sha256": digest.lower(), "size": size})
    return checked


def extract_self_extractor(package: Path | str, destination: Path | str, *, names: Iterable[str] | None = None,
                           overwrite: bool = False) -> list[Path]:
    """Extract selected image payloads with manifest, size and SHA-256 checks."""
    source, target = Path(package), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    with zipfile.ZipFile(source) as archive:
        entries = _items(archive)
        known = {str(item["name"]) for item in entries}
        selected = set(names or known)
        unknown = selected - known
        if unknown:
            raise ValueError("Unknown payload selection: " + ", ".join(sorted(unknown)))
        target.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []
        for item in entries:
            name = str(item["name"])
            if name not in selected:
                continue
            output = target / name
            if output.exists() and not overwrite:
                raise FileExistsError(output)
            temporary = output.with_name(output.name + ".partial")
            try:
                with archive.open(f"payload/{name}") as handle, temporary.open("wb") as destination_handle:
                    shutil.copyfileobj(handle, destination_handle, length=8 * 1024 * 1024)
                if temporary.stat().st_size != item["size"] or _digest(temporary) != item["sha256"]:
                    raise ValueError(f"Verification failed for {name}; extraction aborted.")
                temporary.replace(output)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            outputs.append(output)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract and verify a DiskForge self-extracting image bundle")
    parser.add_argument("package", type=Path, help="DiskForge .pyz archive")
    parser.add_argument("destination", nargs="?", default=Path("."), type=Path)
    parser.add_argument("--name", action="append", dest="names", help="Extract only this payload name; repeatable")
    parser.add_argument("--force", action="store_true", help="Allow replacing an existing destination payload")
    args = parser.parse_args(argv)
    try:
        outputs = extract_self_extractor(args.package, args.destination, names=args.names, overwrite=args.force)
    except Exception as exc:
        parser.error(str(exc))
    for output in outputs:
        print(f"Extracted and verified: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
