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
