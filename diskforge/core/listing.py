"""Read-only, deterministic directory-listing reports for image filesystems."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Iterable, Protocol

from .models import ImageEntry
from .storage import CancellationToken


class DirectoryWalker(Protocol):
    """Minimal protocol shared by every browsable image filesystem facade."""

    def walk_entries(self, path: str = "/", *, token: CancellationToken | None = None) -> Iterable[ImageEntry]:
        """Yield the complete directory subtree without mutating the image."""


def collect_directory_listing(
    filesystem: DirectoryWalker,
    *,
    token: CancellationToken | None = None,
) -> list[ImageEntry]:
    """Collect one complete, stable read-only listing from the filesystem root."""
    if token:
        token.raise_if_cancelled()
    entries = list(filesystem.walk_entries("/", token=token))
    if token:
        token.raise_if_cancelled()
    return sorted(entries, key=lambda entry: (entry.path.casefold(), entry.path))


def directory_listing_html(entries: Iterable[ImageEntry], source: Path | str) -> str:
    """Render a self-contained, escaped HTML report without executable content."""
    rows = "".join(
        f"<tr><td>{escape(entry.path)}</td><td>{'Directory' if entry.is_dir else 'File'}</td>"
        f"<td>{entry.size}</td><td>{escape(entry.modified.isoformat() if entry.modified else '')}</td></tr>"
        for entry in entries
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>DiskForge directory listing</title></head><body>"
        f"<h2>DiskForge directory listing</h2><p>{escape(str(source))}</p>"
        "<table border='1' cellspacing='0' cellpadding='4'><thead><tr>"
        "<th>Path</th><th>Type</th><th>Bytes</th><th>Modified</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></body></html>"
    )


def directory_listing_text(entries: Iterable[ImageEntry], source: Path | str) -> str:
    """Render a tab-separated UTF-8 report whose paths remain unambiguous."""
    lines = [f"DiskForge directory listing: {source}", "Path\tType\tBytes\tModified"]
    lines.extend(
        f"{entry.path}\t{'Directory' if entry.is_dir else 'File'}\t{entry.size}\t"
        f"{entry.modified.isoformat() if entry.modified else ''}"
        for entry in entries
    )
    return "\n".join(lines) + "\n"


def export_directory_listing(
    filesystem: DirectoryWalker,
    source: Path | str,
    output: Path | str,
    *,
    html: bool = False,
    token: CancellationToken | None = None,
) -> Path:
    """Write a new local report for any browsable filesystem; never modify its source."""
    entries = collect_directory_listing(filesystem, token=token)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = directory_listing_html(entries, source) if html else directory_listing_text(entries, source)
    if token:
        token.raise_if_cancelled()
    target.write_text(content, encoding="utf-8")
    return target
