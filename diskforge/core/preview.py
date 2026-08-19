"""Safe, dependency-light inspection for files extracted from disk images.

The preview service never executes a file and never extracts an embedded archive.
It returns bounded text and metadata that the Qt UI can render in an isolated dialog.
"""
from __future__ import annotations

import gzip
import struct
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


MAX_PREVIEW_BYTES = 512 * 1024
MAX_ARCHIVE_ENTRIES = 500
_TEXT_SUFFIXES = {
    ".asc", ".bat", ".c", ".cfg", ".cmd", ".conf", ".csv", ".dat", ".htm", ".html",
    ".ini", ".inf", ".json", ".log", ".md", ".nfo", ".ps1", ".rc", ".reg", ".rtf",
    ".sh", ".sys", ".text", ".txt", ".xml", ".yml", ".yaml",
}
_IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM", b"\xff\xd8\xff", b"\x00\x00\x01\x00",
)


@dataclass(frozen=True)
class PreviewDocument:
    """Bounded, read-only representation of an extracted image entry."""

    kind: str
    title: str
    summary: str
    details: tuple[str, ...] = ()
    text: str = ""
    image_path: Path | None = None


def _human_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    number = float(value)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024
    return f"{value} B"


def _read_prefix(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit)


def _looks_like_text(data: bytes) -> bool:
    if not data:
        return True
    if b"\0" in data:
        return False
    printable = sum(character in b"\t\n\r\f\b" or 32 <= character < 127 or character >= 128 for character in data)
    return printable / len(data) >= 0.88


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp437", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _bounded_text(path: Path, size: int) -> PreviewDocument:
    data = _read_prefix(path, MAX_PREVIEW_BYTES)
    suffix = path.suffix.lower()
    if suffix == ".rtf":
        mode = "Rich Text source"
    elif suffix in {".htm", ".html", ".xml"}:
        mode = "Markup source"
    else:
        mode = "Text"
    details = [f"Encoding: best-effort legacy text decoding", f"Shown: {_human_bytes(len(data))}"]
    if size > len(data):
        details.append(f"Preview is limited to the first {_human_bytes(MAX_PREVIEW_BYTES)}")
    return PreviewDocument("text", f"{mode} preview", "Read-only internal text preview", tuple(details), _decode_text(data))


def _zip_preview(path: Path) -> PreviewDocument:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [f"{'[folder] ' if item.is_dir() else ''}{item.filename}\t{_human_bytes(item.file_size)}" for item in entries[:MAX_ARCHIVE_ENTRIES]]
        details = [f"Entries: {len(entries)}", f"Uncompressed size: {_human_bytes(sum(item.file_size for item in entries))}"]
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            details.append(f"Only the first {MAX_ARCHIVE_ENTRIES} entries are shown")
        return PreviewDocument("archive", "ZIP archive contents", "Archive was inspected without extraction", tuple(details), "\n".join(names))


def _tar_preview(path: Path) -> PreviewDocument:
    with tarfile.open(path, "r:*") as archive:
        entries = archive.getmembers()
        names = [f"{'[folder] ' if item.isdir() else ''}{item.name}\t{_human_bytes(item.size)}" for item in entries[:MAX_ARCHIVE_ENTRIES]]
        details = [f"Entries: {len(entries)}", f"Payload size: {_human_bytes(sum(item.size for item in entries if item.isfile()))}"]
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            details.append(f"Only the first {MAX_ARCHIVE_ENTRIES} entries are shown")
        return PreviewDocument("archive", "TAR archive contents", "Archive was inspected without extraction", tuple(details), "\n".join(names))


def _gzip_preview(path: Path, size: int) -> PreviewDocument:
    try:
        with gzip.open(path, "rb") as archive:
            data = archive.read(MAX_PREVIEW_BYTES)
    except OSError:
        return PreviewDocument("binary", "GZip file", "Compressed data could not be read safely")
    details = [f"Compressed size: {_human_bytes(size)}", f"Shown after decompression: {_human_bytes(len(data))}"]
    if _looks_like_text(data):
        return PreviewDocument("text", "GZip text preview", "Read-only decompressed preview", tuple(details), _decode_text(data))
    return PreviewDocument("binary", "GZip file", "Compressed binary data inspected without writing output", tuple(details), _hex_preview(data))


def _cab_preview(data: bytes, size: int) -> PreviewDocument:
    """List CAB file records without decompressing cabinet payloads."""
    if len(data) < 36 or not data.startswith(b"MSCF"):
        return PreviewDocument("binary", "CAB archive", "Invalid or truncated cabinet header")
    cabinet_size, files_offset = struct.unpack_from("<II", data, 8)
    folders, files, flags = struct.unpack_from("<HHH", data, 26)
    cursor = 36
    try:
        if flags & 0x0004:
            header_size = struct.unpack_from("<H", data, cursor)[0]
            cursor += 4 + header_size
        for enabled in (flags & 0x0001, flags & 0x0002):
            if enabled:
                while cursor < len(data) and data[cursor] != 0:
                    cursor += 1
                cursor += 1
                while cursor < len(data) and data[cursor] != 0:
                    cursor += 1
                cursor += 1
        cursor = files_offset
        names: list[str] = []
        for _ in range(min(files, MAX_ARCHIVE_ENTRIES)):
            if cursor + 16 > len(data):
                break
            file_size = struct.unpack_from("<I", data, cursor)[0]
            name_start = cursor + 16
            name_end = data.find(b"\0", name_start)
            if name_end < 0:
                break
            name = data[name_start:name_end].decode("cp437", errors="replace")
            names.append(f"{name}\t{_human_bytes(file_size)}")
            cursor = name_end + 1
    except struct.error:
        names = []
    details = [f"Cabinet size field: {_human_bytes(cabinet_size)}", f"Folders: {folders}", f"Files declared: {files}"]
    if size != cabinet_size:
        details.append("Cabinet header size differs from the extracted file size")
    if files > MAX_ARCHIVE_ENTRIES:
        details.append(f"Only the first {MAX_ARCHIVE_ENTRIES} entries are shown")
    return PreviewDocument("archive", "CAB archive contents", "Cabinet index inspected without extraction", tuple(details), "\n".join(names) or "No readable CAB file records in the preview prefix.")


def _installshield_preview(data: bytes, size: int) -> PreviewDocument:
    """Inspect the documented signature and bounded header of legacy InstallShield data."""
    if len(data) < 20 or not data.startswith(b"ISc("):
        return PreviewDocument("binary", "InstallShield setup data", "Invalid or truncated InstallShield header")
    version = int.from_bytes(data[4:8], "little")
    descriptor_size = int.from_bytes(data[16:20], "little")
    details = (
        f"Format signature: ISc(",
        f"Header version: 0x{version:08X}",
        f"Descriptor size: {_human_bytes(descriptor_size)}",
        f"File size: {_human_bytes(size)}",
        "Payload extraction and execution are disabled during preview",
    )
    return PreviewDocument("archive", "InstallShield setup data", "Legacy InstallShield package structure inspected without execution", details, _hex_preview(data))


def _dos_or_pe_preview(data: bytes) -> PreviewDocument | None:
    if not data.startswith(b"MZ"):
        return None
    details = ["Execution is disabled in DiskForge preview"]
    if len(data) >= 64:
        pointer = int.from_bytes(data[60:64], "little")
        if pointer + 2 <= len(data):
            signature = data[pointer:pointer + 2]
            if signature == b"NE":
                return PreviewDocument("executable", "16-bit Windows NE executable", "Read-only executable structure inspection", tuple(details + [f"NE header offset: 0x{pointer:X}"]), _hex_preview(data))
            if data[pointer:pointer + 4] == b"PE\0\0":
                machine = int.from_bytes(data[pointer + 4:pointer + 6], "little")
                sections = int.from_bytes(data[pointer + 6:pointer + 8], "little")
                return PreviewDocument("executable", "Windows PE executable", "Read-only executable structure inspection", tuple(details + [f"Machine: 0x{machine:04X}", f"Sections: {sections}"]), _hex_preview(data))
    return PreviewDocument("executable", "DOS MZ executable", "Read-only executable structure inspection", tuple(details), _hex_preview(data))


def _hex_preview(data: bytes, rows: int = 96) -> str:
    lines: list[str] = []
    for offset in range(0, min(len(data), rows * 16), 16):
        chunk = data[offset:offset + 16]
        hex_part = " ".join(f"{value:02X}" for value in chunk)
        text_part = "".join(chr(value) if 32 <= value < 127 else "." for value in chunk)
        lines.append(f"{offset:08X}  {hex_part:<47}  {text_part}")
    return "\n".join(lines)


def inspect_file_preview(path: Path | str) -> PreviewDocument:
    """Return a bounded, non-executing internal preview for one local file."""
    target = Path(path)
    size = target.stat().st_size
    data = _read_prefix(target, max(4096, min(MAX_PREVIEW_BYTES, size)))
    suffix = target.suffix.lower()
    if data.startswith(_IMAGE_SIGNATURES) or suffix in {".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".webp"}:
        return PreviewDocument("image", "Image preview", "Read-only rendered image preview", (f"File size: {_human_bytes(size)}",), image_path=target)
    if zipfile.is_zipfile(target):
        return _zip_preview(target)
    if tarfile.is_tarfile(target):
        return _tar_preview(target)
    if data.startswith(b"MSCF"):
        return _cab_preview(data, size)
    if data.startswith(b"ISc("):
        return _installshield_preview(data, size)
    if data.startswith(b"SZDD\x88\xf0\x27\x33"):
        return PreviewDocument("archive", "Microsoft SZDD compressed file", "Legacy compressed-file signature detected; the file is not executed", (f"File size: {_human_bytes(size)}",), _hex_preview(data))
    if suffix == ".gz" or data.startswith(b"\x1f\x8b"):
        return _gzip_preview(target, size)
    executable = _dos_or_pe_preview(data)
    if executable is not None:
        return executable
    if suffix in _TEXT_SUFFIXES or _looks_like_text(data):
        return _bounded_text(target, size)
    return PreviewDocument("binary", "Binary inspection", "Read-only hexadecimal preview; no system application is required", (f"File size: {_human_bytes(size)}", f"Shown: {_human_bytes(min(size, len(data)))}"), _hex_preview(data))
