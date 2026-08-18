from __future__ import annotations

from pathlib import Path

from diskforge.core.browse_session import materialize_browsable_image
from diskforge.core.formats import create_fixed_vhd


def test_fixed_vhd_materializes_temporary_raw_without_footer(tmp_path: Path) -> None:
    raw = tmp_path / "source.img"
    raw_bytes = b"DiskForge" * 512
    raw.write_bytes(raw_bytes)
    vhd = tmp_path / "source.vhd"
    create_fixed_vhd(raw, vhd)
    session = materialize_browsable_image(vhd)
    try:
        assert session.temporary
        assert session.image.read_bytes() == raw_bytes
        temporary = session.temporary_directory
    finally:
        session.close()
    assert temporary is not None and not temporary.exists()


def test_raw_browse_session_returns_original_path(tmp_path: Path) -> None:
    raw = tmp_path / "source.img"
    raw.write_bytes(b"raw")
    session = materialize_browsable_image(raw)
    assert not session.temporary
    assert session.image == raw
