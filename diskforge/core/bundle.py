"""Versioned, authenticated multi-image bundles.

The on-disk DFB1 container is original to DiskForge.  It intentionally does not
attempt to parse or generate third-party encrypted image formats.  A cleartext,
versioned header conveys only the KDF and archive metadata.  The payload is a
ZIP archive and may be protected by AES-256-GCM with a per-file scrypt key.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .storage import DiskForgeError


_MAGIC = b"DFB1"
_HEADER_LENGTH = struct.Struct(">I")
_TAG_SIZE = 16
_CHUNK_SIZE = 1024 * 1024
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1


@dataclass(frozen=True)
class BundleItem:
    """A payload item stored in a DiskForge bundle."""

    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class BundleInfo:
    """Public metadata available without decrypting the payload."""

    path: Path
    encrypted: bool
    comment: str
    description: str
    compression: str
    items: tuple[BundleItem, ...]
    created_at: datetime | None = None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_CHUNK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def _safe_archive_name(path: Path, occupied: set[str]) -> str:
    """Return a flat unique archive filename with no traversal semantics."""
    name = path.name.replace("\\", "_").replace("/", "_") or "image.bin"
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, index = name, 2
    while candidate.casefold() in occupied:
        candidate = f"{stem}-{index}{suffix}"
        index += 1
    occupied.add(candidate.casefold())
    return candidate


def _derive_key(password: str, salt: bytes, *, n: int, r: int, p: int) -> bytes:
    if not isinstance(password, str) or not password:
        raise DiskForgeError("A non-empty password is required for an encrypted bundle.")
    try:
        return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise DiskForgeError("The bundle KDF parameters are not supported.") from exc


def _build_archive(images: Sequence[Path], stage: Path, comment: str, description: str,
                   compression_level: int) -> list[BundleItem]:
    if not 0 <= compression_level <= 9:
        raise ValueError("compression_level must be between 0 and 9.")
    if not images:
        raise DiskForgeError("A bundle must contain at least one image.")
    items: list[BundleItem] = []
    occupied: set[str] = set()
    compression = zipfile.ZIP_STORED if compression_level == 0 else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(stage, "w", compression=compression, compresslevel=compression_level,
                         allowZip64=True) as archive:
        for image in images:
            if not image.is_file():
                raise FileNotFoundError(image)
            name = _safe_archive_name(image, occupied)
            item = BundleItem(name, image.stat().st_size, _sha256_file(image))
            items.append(item)
            archive.write(image, arcname=f"payload/{name}")
        manifest = {
            "schema": "diskforge.bundle/v1",
            "comment": comment,
            "description": description,
            "items": [item.__dict__ for item in items],
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False,
                                                       sort_keys=True, separators=(",", ":")))
    return items


def _write_header(handle, header: dict[str, object]) -> bytes:
    raw = json.dumps(header, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > 1024 * 1024:
        raise DiskForgeError("Bundle header is unexpectedly large.")
    handle.write(_MAGIC)
    handle.write(_HEADER_LENGTH.pack(len(raw)))
    handle.write(raw)
    return raw


def create_bundle(images: Iterable[Path | str], output: Path | str, *, password: str | None = None,
                  comment: str = "", description: str = "", compression_level: int = 6,
                  overwrite: bool = False) -> BundleInfo:
    """Create a `.dfb` bundle containing one or more images.

    The archive is built in a private temporary file first.  Output is atomically
    replaced only after all payload bytes and authentication data are flushed.
    """
    source_paths = [Path(item) for item in images]
    destination = Path(output)
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix="diskforge-bundle-", dir=destination.parent))
    archive_path = stage_dir / "payload.zip"
    output_stage = stage_dir / destination.name
    try:
        items = _build_archive(source_paths, archive_path, comment, description, compression_level)
        header: dict[str, object] = {
            "schema": "diskforge.bundle-envelope/v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "compression": "store" if compression_level == 0 else "deflate",
            "comment": comment,
            "description": description,
            "items": [item.__dict__ for item in items],
            "payload_size": archive_path.stat().st_size,
            "encrypted": password is not None,
        }
        with output_stage.open("wb") as target:
            if password is None:
                _write_header(target, header)
                with archive_path.open("rb") as source:
                    shutil.copyfileobj(source, target, length=_CHUNK_SIZE)
            else:
                salt, nonce = os.urandom(16), os.urandom(12)
                header["kdf"] = {"name": "scrypt", "n": _SCRYPT_N, "r": _SCRYPT_R,
                                 "p": _SCRYPT_P, "salt": salt.hex()}
                header["cipher"] = {"name": "AES-256-GCM", "nonce": nonce.hex(),
                                    "tag_size": _TAG_SIZE}
                raw_header = _write_header(target, header)
                encryptor = Cipher(algorithms.AES(_derive_key(password, salt, n=_SCRYPT_N,
                                                               r=_SCRYPT_R, p=_SCRYPT_P)),
                                   modes.GCM(nonce)).encryptor()
                encryptor.authenticate_additional_data(raw_header)
                with archive_path.open("rb") as source:
                    while block := source.read(_CHUNK_SIZE):
                        target.write(encryptor.update(block))
                target.write(encryptor.finalize())
                target.write(encryptor.tag)
            target.flush()
            os.fsync(target.fileno())
        os.replace(output_stage, destination)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    return inspect_bundle(destination)


def _read_header(path: Path) -> tuple[dict[str, object], int, bytes]:
    with path.open("rb") as handle:
        if handle.read(len(_MAGIC)) != _MAGIC:
            raise DiskForgeError("Not a DiskForge DFB1 bundle.")
        raw_length = handle.read(_HEADER_LENGTH.size)
        if len(raw_length) != _HEADER_LENGTH.size:
            raise DiskForgeError("Bundle header is truncated.")
        length = _HEADER_LENGTH.unpack(raw_length)[0]
        if not 2 <= length <= 1024 * 1024:
            raise DiskForgeError("Bundle header length is invalid.")
        raw_header = handle.read(length)
    if len(raw_header) != length:
        raise DiskForgeError("Bundle header is truncated.")
    try:
        header = json.loads(raw_header.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiskForgeError("Bundle header is not valid JSON.") from exc
    if not isinstance(header, dict) or header.get("schema") != "diskforge.bundle-envelope/v1":
        raise DiskForgeError("Bundle header schema is not supported.")
    return header, len(_MAGIC) + _HEADER_LENGTH.size + length, raw_header


def _items_from_header(header: dict[str, object]) -> tuple[BundleItem, ...]:
    raw_items = header.get("items")
    if not isinstance(raw_items, list):
        raise DiskForgeError("Bundle item list is invalid.")
    items: list[BundleItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise DiskForgeError("Bundle item metadata is invalid.")
        try:
            name, size, digest = str(raw["name"]), int(raw["size"]), str(raw["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DiskForgeError("Bundle item metadata is invalid.") from exc
        if Path(name).name != name or not name or len(digest) != 64 or size < 0:
            raise DiskForgeError("Bundle item metadata is unsafe or invalid.")
        items.append(BundleItem(name, size, digest))
    return tuple(items)


def inspect_bundle(path: Path | str) -> BundleInfo:
    """Read safe public metadata without accessing an encrypted payload."""
    target = Path(path)
    header, _, _ = _read_header(target)
    created_raw = header.get("created_at")
    try:
        created = datetime.fromisoformat(str(created_raw)) if created_raw else None
    except ValueError:
        created = None
    return BundleInfo(
        target, bool(header.get("encrypted")), str(header.get("comment", "")),
        str(header.get("description", "")), str(header.get("compression", "unknown")),
        _items_from_header(header), created,
    )


def _payload_to_archive(path: Path, header: dict[str, object], payload_offset: int,
                        raw_header: bytes, stage: Path, password: str | None) -> Path:
    payload_size = header.get("payload_size")
    if not isinstance(payload_size, int) or payload_size < 0:
        raise DiskForgeError("Bundle payload size is invalid.")
    expected_minimum = payload_offset + payload_size + (_TAG_SIZE if header.get("encrypted") else 0)
    if path.stat().st_size != expected_minimum:
        raise DiskForgeError("Bundle payload length does not match its header.")
    if not header.get("encrypted"):
        with path.open("rb") as source, stage.open("wb") as destination:
            source.seek(payload_offset)
            remaining = payload_size
            while remaining:
                block = source.read(min(_CHUNK_SIZE, remaining))
                if not block:
                    raise DiskForgeError("Bundle payload is truncated.")
                destination.write(block)
                remaining -= len(block)
        return stage
    if password is None:
        raise DiskForgeError("This bundle is password-protected.")
    kdf, cipher = header.get("kdf"), header.get("cipher")
    if not isinstance(kdf, dict) or not isinstance(cipher, dict) or kdf.get("name") != "scrypt" or cipher.get("name") != "AES-256-GCM":
        raise DiskForgeError("Bundle cryptography parameters are not supported.")
    try:
        salt = bytes.fromhex(str(kdf["salt"]))
        nonce = bytes.fromhex(str(cipher["nonce"]))
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
        if len(salt) != 16 or len(nonce) != 12 or n < 2**14 or n > 2**20 or r < 1 or r > 32 or p < 1 or p > 16:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise DiskForgeError("Bundle KDF parameters are invalid.") from exc
    with path.open("rb") as source:
        source.seek(payload_offset + payload_size)
        tag = source.read(_TAG_SIZE)
        if len(tag) != _TAG_SIZE:
            raise DiskForgeError("Bundle authentication tag is missing.")
        decryptor = Cipher(algorithms.AES(_derive_key(password, salt, n=n, r=r, p=p)),
                           modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(raw_header)
        source.seek(payload_offset)
        remaining = payload_size
        try:
            with stage.open("wb") as destination:
                while remaining:
                    block = source.read(min(_CHUNK_SIZE, remaining))
                    if not block:
                        raise DiskForgeError("Bundle payload is truncated.")
                    destination.write(decryptor.update(block))
                    remaining -= len(block)
                destination.write(decryptor.finalize())
        except InvalidTag as exc:
            stage.unlink(missing_ok=True)
            raise DiskForgeError("The password is incorrect or the bundle was modified.") from exc
    return stage


def _validate_member_name(name: str) -> None:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts or name.startswith(("/", "\\")):
        raise DiskForgeError("Bundle archive contains an unsafe member path.")


def extract_bundle(path: Path | str, destination: Path | str, *, password: str | None = None,
                   names: Sequence[str] | None = None, overwrite: bool = False) -> list[Path]:
    """Extract verified payloads from a bundle into `destination`.

    Hashes in both the outer header and embedded manifest must agree before a
    payload becomes visible at its final destination.
    """
    source, output = Path(path), Path(destination)
    header, payload_offset, raw_header = _read_header(source)
    expected_items = _items_from_header(header)
    requested = {str(name) for name in names} if names is not None else None
    if requested is not None and not requested.issubset({item.name for item in expected_items}):
        raise FileNotFoundError("Requested bundle item is not present.")
    output.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix="diskforge-unbundle-", dir=output))
    archive_path = stage_dir / "payload.zip"
    extracted: list[Path] = []
    try:
        _payload_to_archive(source, header, payload_offset, raw_header, archive_path, password)
        try:
            archive = zipfile.ZipFile(archive_path, "r")
        except zipfile.BadZipFile as exc:
            raise DiskForgeError("Bundle payload is not a valid ZIP archive.") from exc
        with archive:
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DiskForgeError("Bundle manifest is missing or invalid.") from exc
            if not isinstance(manifest, dict) or manifest.get("schema") != "diskforge.bundle/v1":
                raise DiskForgeError("Bundle manifest schema is not supported.")
            embedded = _items_from_header({"items": manifest.get("items")})
            if embedded != expected_items:
                raise DiskForgeError("Bundle manifest does not match envelope metadata.")
            for item in expected_items:
                if requested is not None and item.name not in requested:
                    continue
                member = f"payload/{item.name}"
                _validate_member_name(member)
                try:
                    info = archive.getinfo(member)
                except KeyError as exc:
                    raise DiskForgeError("Bundle payload item is missing.") from exc
                if info.is_dir() or info.file_size != item.size:
                    raise DiskForgeError("Bundle payload item metadata is inconsistent.")
                stage_item = stage_dir / item.name
                with archive.open(info, "r") as src, stage_item.open("wb") as dst:
                    digest = hashlib.sha256()
                    while block := src.read(_CHUNK_SIZE):
                        digest.update(block)
                        dst.write(block)
                if digest.hexdigest() != item.sha256:
                    raise DiskForgeError("Bundle payload hash verification failed.")
                final_path = output / item.name
                if final_path.exists() and not overwrite:
                    raise FileExistsError(final_path)
                os.replace(stage_item, final_path)
                extracted.append(final_path)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    return extracted
