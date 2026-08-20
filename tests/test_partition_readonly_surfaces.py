from __future__ import annotations

import json
from pathlib import Path

import pytest

from diskforge import api
from diskforge import cli
from diskforge.core.models import ImageEntry


class _StubReadOnlyFilesystem:
    def __init__(self) -> None:
        self.closed = False

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        assert path == "/"
        return [ImageEntry("/README.TXT", "README.TXT", False, 12)]

    def walk_entries(self, path: str = "/", *, token=None):  # type: ignore[no-untyped-def]
        assert path == "/"
        yield from self.list_entries(path)

    def close(self) -> None:
        self.closed = True


def _image(path: Path) -> Path:
    data = bytearray(1024)
    data[446 + 4] = 0x83
    data[510:512] = b"\x55\xaa"
    path.write_bytes(data)
    return path


def test_cli_lists_explicit_non_fat_partition_through_read_only_router(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _image(tmp_path / "partitioned.img")
    filesystem = _StubReadOnlyFilesystem()
    received: dict[str, object] = {}

    def open_router(source: Path, index: int, *, writable: bool = False):  # type: ignore[no-untyped-def]
        received.update({"source": source, "index": index, "writable": writable})
        return filesystem

    monkeypatch.setattr(cli, "open_partition_filesystem", open_router)

    assert cli.main(["--json", "list", str(image), "--partition", "1"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["path"] == "/README.TXT"
    assert received == {"source": image, "index": 1, "writable": False}
    assert filesystem.closed


def test_cli_exports_explicit_non_fat_partition_listing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _image(tmp_path / "partitioned.img")
    output = tmp_path / "partition.html"
    filesystem = _StubReadOnlyFilesystem()

    monkeypatch.setattr(cli, "open_partition_filesystem", lambda *_args, **_kwargs: filesystem)

    assert cli.main(["--json", "export-listing", str(image), str(output), "--html", "--partition", "1"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record == {"path": str(output), "format": "html"}
    assert "README.TXT" in output.read_text(encoding="utf-8")
    assert filesystem.closed


def test_sdk_opens_explicit_non_fat_partition_read_only_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _image(tmp_path / "partitioned.img")
    filesystem = _StubReadOnlyFilesystem()
    received: dict[str, object] = {}

    def open_router(source: Path, index: int, *, writable: bool = False):  # type: ignore[no-untyped-def]
        received.update({"source": source, "index": index, "writable": writable})
        return filesystem

    monkeypatch.setattr(api, "open_partition_filesystem", open_router)
    client = api.DiskForgeClient()

    with client.filesystem(image, partition_index=1) as opened:
        assert opened is filesystem
    assert received == {"source": image, "index": 1, "writable": False}
    assert filesystem.closed
