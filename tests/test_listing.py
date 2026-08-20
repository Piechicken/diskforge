from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from diskforge.core.listing import (collect_directory_listing, directory_listing_html,
                                    directory_listing_text, export_directory_listing)
from diskforge.core.models import ImageEntry
from diskforge.core.storage import CancellationToken, DiskForgeError


class _Filesystem:
    def walk_entries(self, path: str = "/", *, token: CancellationToken | None = None):
        assert path == "/"
        yield ImageEntry("/zeta.txt", "zeta.txt", False, 1)
        yield ImageEntry("/Alpha & <beta>.txt", "Alpha & <beta>.txt", False, 2,
                         modified=datetime(2026, 1, 2, tzinfo=timezone.utc))


def test_generic_listing_is_stable_and_escapes_html(tmp_path: Path) -> None:
    filesystem = _Filesystem()
    entries = collect_directory_listing(filesystem)

    assert [entry.path for entry in entries] == ["/Alpha & <beta>.txt", "/zeta.txt"]
    html = directory_listing_html(entries, tmp_path / "source.img")
    text = directory_listing_text(entries, tmp_path / "source.img")
    output = export_directory_listing(filesystem, tmp_path / "source.img", tmp_path / "report.html", html=True)

    assert "Alpha &amp; &lt;beta&gt;.txt" in html
    assert text.startswith("DiskForge directory listing:")
    assert "Path\tType\tBytes\tModified" in text
    assert output.read_text(encoding="utf-8") == html


def test_cancelled_listing_does_not_write_output(tmp_path: Path) -> None:
    token = CancellationToken()
    token.cancel()
    output = tmp_path / "report.txt"

    with pytest.raises(DiskForgeError, match="cancel"):
        export_directory_listing(_Filesystem(), tmp_path / "source.img", output, token=token)
    assert not output.exists()
