from __future__ import annotations

from pathlib import Path

import pytest

from diskforge.core.bundle import create_bundle, extract_bundle, inspect_bundle
from diskforge.core.storage import DiskForgeError


def test_unencrypted_bundle_round_trip_with_metadata(tmp_path: Path) -> None:
    first = tmp_path / "first.img"
    second = tmp_path / "second.iso"
    first.write_bytes(b"A" * 2500)
    second.write_bytes(b"DiskForge bundle payload\x00" * 100)
    bundle = tmp_path / "archive.dfb"

    info = create_bundle([first, second], bundle, comment="release media", description="two files")

    assert info.encrypted is False
    assert info.comment == "release media"
    assert [item.name for item in info.items] == ["first.img", "second.iso"]
    extracted = extract_bundle(bundle, tmp_path / "output")
    assert [path.name for path in extracted] == ["first.img", "second.iso"]
    assert (tmp_path / "output" / "first.img").read_bytes() == first.read_bytes()
    assert (tmp_path / "output" / "second.iso").read_bytes() == second.read_bytes()


def test_encrypted_bundle_rejects_wrong_password_and_tampering(tmp_path: Path) -> None:
    payload = tmp_path / "private.img"
    payload.write_bytes(b"classified bytes" * 1024)
    bundle = tmp_path / "protected.dfb"

    create_bundle([payload], bundle, password="correct horse battery staple")
    assert inspect_bundle(bundle).encrypted is True

    with pytest.raises(DiskForgeError, match="password-protected"):
        extract_bundle(bundle, tmp_path / "missing-password")
    with pytest.raises(DiskForgeError, match="incorrect or.*modified"):
        extract_bundle(bundle, tmp_path / "wrong-password", password="wrong")

    restored = extract_bundle(bundle, tmp_path / "restored", password="correct horse battery staple")
    assert restored == [tmp_path / "restored" / "private.img"]
    assert restored[0].read_bytes() == payload.read_bytes()

    tampered = tmp_path / "tampered.dfb"
    data = bytearray(bundle.read_bytes())
    data[-1] ^= 0x01
    tampered.write_bytes(data)
    with pytest.raises(DiskForgeError, match="incorrect or.*modified"):
        extract_bundle(tampered, tmp_path / "tampered-output", password="correct horse battery staple")


def test_bundle_rejects_duplicate_destination_without_overwrite(tmp_path: Path) -> None:
    image = tmp_path / "image.img"
    image.write_bytes(b"image")
    bundle = tmp_path / "single.dfb"
    create_bundle([image], bundle)
    destination = tmp_path / "output"
    extract_bundle(bundle, destination)

    with pytest.raises(FileExistsError):
        extract_bundle(bundle, destination)

    assert extract_bundle(bundle, destination, overwrite=True) == [destination / "image.img"]
