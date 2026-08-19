from __future__ import annotations

from datetime import datetime, timezone

import pytest

from diskforge.core.filesystems import ImageFilesystem
from diskforge.core.models import ImageEntry
from diskforge.core.storage import CancellationToken, OperationCancelled


class _PagedFilesystem(ImageFilesystem):
    def __init__(self) -> None:
        self.calls = 0

    def list_entries(self, path: str = "/") -> list[ImageEntry]:
        self.calls += 1
        return [
            ImageEntry("/zeta.txt", "zeta.txt", False, 9, datetime(2020, 1, 1, tzinfo=timezone.utc)),
            ImageEntry("/folder", "folder", True),
            ImageEntry("/alpha.txt", "alpha.txt", False, 1, datetime(2021, 1, 1, tzinfo=timezone.utc)),
        ]

    def extract(self, paths, destination, progress=None, token=None, policy=None):  # type: ignore[no-untyped-def]
        return []


def test_directory_paging_uses_sorted_cache_and_page_boundaries() -> None:
    filesystem = _PagedFilesystem()
    first = filesystem.list_entries_page("/", limit=2)
    second = filesystem.list_entries_page("/", offset=2, limit=2)

    assert [entry.name for entry in first.entries] == ["folder", "alpha.txt"]
    assert [entry.name for entry in second.entries] == ["zeta.txt"]
    assert first.total == 3 and first.has_more
    assert not second.has_more
    assert filesystem.calls == 1


def test_directory_paging_honors_cancelled_token() -> None:
    filesystem = _PagedFilesystem()
    token = CancellationToken()
    token.cancel()

    with pytest.raises(OperationCancelled):
        filesystem.list_entries_page(token=token)
