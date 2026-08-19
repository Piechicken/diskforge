from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.filesystems import create_fat_image
from diskforge.core.formats import QemuImgConverter, create_dynamic_vhd_from_raw, parse_vhd_footer
from diskforge.core.models import FileSystemType
from diskforge.core.storage import DiskForgeError


def _dynamic_footer(size: int) -> bytes:
    from diskforge.core.formats import VHD_FOOTER_SIZE, _checksum

    footer = bytearray(VHD_FOOTER_SIZE)
    footer[:8] = b"conectix"
    footer[8:12] = (2).to_bytes(4, "big")
    footer[12:16] = (0x00010000).to_bytes(4, "big")
    footer[16:24] = (512).to_bytes(8, "big")
    footer[40:48] = size.to_bytes(8, "big")
    footer[48:56] = size.to_bytes(8, "big")
    footer[60:64] = (3).to_bytes(4, "big")
    footer[64:68] = _checksum(footer).to_bytes(4, "big")
    return bytes(footer)


def test_create_dynamic_vhd_from_raw_uses_safe_subformat_and_validates_output(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source.img"
    create_fat_image(source, 8 * 1024 * 1024, FileSystemType.FAT16, "DYNAMIC")
    destination = tmp_path / "dynamic.vhd"
    converter = QemuImgConverter("mock-qemu-img")
    monkeypatch.setattr(QemuImgConverter, "available", property(lambda self: True))
    calls: list[list[str]] = []

    def run(args: list[str], token=None):  # type: ignore[no-untyped-def]
        calls.append(args)
        target = Path(args[-1])
        target.write_bytes(source.read_bytes() + _dynamic_footer(source.stat().st_size))

    monkeypatch.setattr(converter, "_run", run)
    result = create_dynamic_vhd_from_raw(source, destination, converter)

    assert result.destination == destination
    assert result.virtual_size == source.stat().st_size
    assert calls[0][:6] == ["convert", "-p", "-O", "vpc", "-o", "subformat=dynamic,block_state_zero=on"]
    footer = parse_vhd_footer(destination)
    assert footer is not None and footer.disk_type == 3


def test_dynamic_vhd_export_rejects_overwrite_invalid_source_and_invalid_output(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source.img"
    create_fat_image(source, 8 * 1024 * 1024, FileSystemType.FAT16, "DYNAMIC")
    destination = tmp_path / "dynamic.vhd"
    destination.write_bytes(b"existing")
    converter = QemuImgConverter("mock-qemu-img")
    monkeypatch.setattr(QemuImgConverter, "available", property(lambda self: True))

    with pytest.raises(FileExistsError):
        create_dynamic_vhd_from_raw(source, destination, converter)

    destination.unlink()
    monkeypatch.setattr(converter, "_run", lambda args, token=None: Path(args[-1]).write_bytes(b"invalid"))
    with pytest.raises(DiskForgeError, match="dynamic VHD"):
        create_dynamic_vhd_from_raw(source, destination, converter)
    assert not destination.exists()
    assert not list(tmp_path.glob(".dynamic.vhd.*.tmp"))

    raw = tmp_path / "not-fat.img"
    raw.write_bytes(b"\0" * 4096)
    with pytest.raises(DiskForgeError):
        create_dynamic_vhd_from_raw(raw, tmp_path / "other.vhd", converter)
