from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from diskforge.cli import main


def test_cli_fat_editing_comment_and_compare(tmp_path: Path, capsys) -> None:
    image = tmp_path / "media.img"
    host = tmp_path / "payload.txt"
    host.write_text("cli data", encoding="utf-8")

    assert main(["create-fat", str(image), "--size-mib", "8", "--fat", "16"]) == 0
    assert main(["inject", str(image), str(host)]) == 0
    assert main(["rename", str(image), "/payload.txt", "renamed.txt"]) == 0
    assert main(["set-attributes", str(image), "/renamed.txt", "--hidden", "--read-only"]) == 0
    assert main(["set-label", str(image), "CLIWORK"]) == 0
    assert main(["comment", str(image), "test note"]) == 0
    capsys.readouterr()
    assert main(["--json", "list", str(image)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["name"] == "renamed.txt"
    assert listed[0]["attributes"] == "RH"
    assert main(["compare", str(host), str(host)]) == 0


def test_cli_bundle_password_stdin(tmp_path: Path, monkeypatch, capsys) -> None:
    image = tmp_path / "payload.img"
    image.write_bytes(b"bundle payload")
    bundle = tmp_path / "payload.dfb"
    original_stdin = sys.stdin
    monkeypatch.setattr(sys, "stdin", io.StringIO("passphrase\n"))
    try:
        assert main(["bundle", str(bundle), str(image), "--password-stdin"]) == 0
    finally:
        monkeypatch.setattr(sys, "stdin", original_stdin)
    assert bundle.is_file()
    capsys.readouterr()
    output = tmp_path / "unpacked"
    monkeypatch.setattr(sys, "stdin", io.StringIO("passphrase\n"))
    try:
        assert main(["unbundle", str(bundle), str(output), "--password-stdin"]) == 0
    finally:
        monkeypatch.setattr(sys, "stdin", original_stdin)
    assert (output / "payload.img").read_bytes() == image.read_bytes()



def test_cli_move_fat_emits_json_and_rejects_directory_sources(tmp_path: Path, capsys) -> None:
    image = tmp_path / "move.img"
    payload = tmp_path / "payload.txt"
    payload.write_text("CLI move payload", encoding="utf-8")
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "placeholder.txt").write_text("directory anchor", encoding="utf-8")

    assert main(["create-fat", str(image), "--size-mib", "8", "--fat", "16"]) == 0
    assert main(["inject", str(image), str(payload), str(archive)]) == 0
    capsys.readouterr()

    assert main(["--json", "move-fat", str(image), "/payload.txt", "/archive"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "source": "/payload.txt", "destination": "/archive/payload.txt",
    }
    assert main(["move-fat", str(image), "/archive", "/"]) == 2
    assert "directory moves" in capsys.readouterr().err



def test_cli_reads_zip_image_container_and_refuses_writes(tmp_path: Path, capsys) -> None:
    import zipfile

    image = tmp_path / "inside.img"
    payload = tmp_path / "payload.txt"
    payload.write_text("zip CLI payload", encoding="utf-8")
    assert main(["create-fat", str(image), "--size-mib", "8", "--fat", "16"]) == 0
    assert main(["inject", str(image), str(payload)]) == 0

    archive = tmp_path / "inside.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as container:
        container.write(image, image.name)
    capsys.readouterr()

    assert main(["--json", "list", str(archive)]) == 0
    assert [entry["name"] for entry in json.loads(capsys.readouterr().out)] == ["payload.txt"]

    output = tmp_path / "out"
    assert main(["--json", "extract", str(archive), str(output), "/payload.txt"]) == 0
    assert (output / "payload.txt").read_text(encoding="utf-8") == "zip CLI payload"

    report = tmp_path / "listing.txt"
    assert main(["--json", "export-listing", str(archive), str(report)]) == 0
    assert "/payload.txt" in report.read_text(encoding="utf-8")

    assert main(["inject", str(archive), str(payload)]) == 2
    assert "read-only" in capsys.readouterr().err



def test_cli_lists_and_recovers_conservative_deleted_fat_candidate(tmp_path: Path, capsys) -> None:
    from diskforge.core.fat_recovery import _layout
    from diskforge.core.storage import sha256_file

    image = tmp_path / "deleted.img"
    payload = tmp_path / "SHORT.TXT"
    payload.write_bytes(b"CLI deleted-file recovery payload")
    assert main(["create-fat", str(image), "--size-mib", "8", "--fat", "16"]) == 0
    assert main(["inject", str(image), str(payload)]) == 0
    root = _layout(image, 0)
    for slot in range(root.root_directory_entries):
        with image.open("r+b") as handle:
            handle.seek(root.root_directory_offset + slot * 32)
            entry = handle.read(32)
            if entry[:11] != b"SHORT   TXT":
                continue
            cluster = int.from_bytes(entry[26:28], "little")
            handle.seek(root.root_directory_offset + slot * 32)
            handle.write(b"\xe5")
            fat_copies = (root.root_directory_offset - root.first_fat_offset) // root.fat_bytes
            for copy_index in range(fat_copies):
                handle.seek(root.first_fat_offset + copy_index * root.fat_bytes + cluster * 2)
                handle.write(b"\x00\x00")
            break
    else:
        raise AssertionError("expected injected root entry")
    before = sha256_file(image)
    capsys.readouterr()

    assert main(["--json", "list-deleted-fat", str(image)]) == 0
    candidates = json.loads(capsys.readouterr().out)["candidates"]
    candidate = next(item for item in candidates if item["display_name"] == "?HORT.TXT")
    assert candidate["recoverable"] is True

    output = tmp_path / "recovered.bin"
    assert main(["--json", "recover-deleted-fat", str(image), str(candidate["slot_index"]), str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["destination"] == str(output)
    assert output.read_bytes() == payload.read_bytes()
    assert sha256_file(image) == before
    assert main(["recover-deleted-fat", str(image), str(candidate["slot_index"]), str(output)]) == 2
    assert str(output) in capsys.readouterr().err
