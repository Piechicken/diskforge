from __future__ import annotations

from pathlib import Path

from diskforge.core.compare import compare_streams


def test_compare_can_report_identical_after_full_zero_sector_tail(tmp_path: Path) -> None:
    left = tmp_path / "left.img"
    right = tmp_path / "right.img"
    payload = b"D" * 1024
    left.write_bytes(payload)
    right.write_bytes(payload + b"\x00" * 1024)
    strict = compare_streams(left, right)
    relaxed = compare_streams(left, right, ignore_trailing_zero_sectors=True)
    assert not strict.equal
    assert strict.reason == "endpoint sizes differ"
    assert relaxed.equal
    assert relaxed.reason == "identical after ignoring trailing zero sectors"
    assert relaxed.ignored_source_zero_tail == 0
    assert relaxed.ignored_destination_zero_tail == 1024
    assert right.read_bytes() == payload + b"\x00" * 1024


def test_compare_does_not_ignore_partial_or_nonzero_tail(tmp_path: Path) -> None:
    left = tmp_path / "left.img"
    partial = tmp_path / "partial.img"
    changed = tmp_path / "changed.img"
    payload = b"A" * 512
    left.write_bytes(payload)
    partial.write_bytes(payload + b"\x00")
    changed.write_bytes(payload + b"\x00" * 511 + b"X")
    assert not compare_streams(left, partial, ignore_trailing_zero_sectors=True).equal
    assert not compare_streams(left, changed, ignore_trailing_zero_sectors=True).equal
