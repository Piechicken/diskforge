"""Strict read-only inspection for standard Commodore 1541 D64 images.

The D64 family has no magic header.  This module intentionally accepts only the
canonical 35-track, 174,848-byte, 256-byte-sector profile and validates the
CBM DOS directory plus ordinary SEQ/PRG/USR data chains.  It does not infer
40-track extensions, appended error maps, REL side-sector data, GEOS layouts,
GCR, copy protection, repair, conversion, or writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .storage import DiskForgeError

D64_SUFFIX = ".d64"
D64_SECTOR_SIZE = 256
D64_TRACK_COUNT = 35
D64_SECTOR_COUNT = 683
D64_SIZE_BYTES = D64_SECTOR_COUNT * D64_SECTOR_SIZE
D64_DIRECTORY_TRACK = 18
D64_DIRECTORY_SECTOR = 1
D64_BAM_TRACK = 18
D64_BAM_SECTOR = 0
_D64_ALLOWED_FILE_TYPES = {1: "SEQ", 2: "PRG", 3: "USR"}


@dataclass(frozen=True)
class D64File:
    """One validated ordinary CBM DOS file exposed through the read-only facade."""

    index: int
    path: str
    name: str
    file_type: str
    locked: bool
    closed: bool
    blocks: int
    size: int
    start_track: int
    start_sector: int
    chain: tuple[tuple[int, int], ...]

    @property
    def attributes(self) -> str:
        flags = [self.file_type]
        if self.locked:
            flags.append("locked")
        if not self.closed:
            flags.append("open")
        return ", ".join(flags)


@dataclass(frozen=True)
class D64Inspection:
    """Verified facts about a canonical D64 and its ordinary data files."""

    source: Path
    size: int
    disk_name: str
    disk_id: str
    dos_type: str
    directory_sectors: int
    free_blocks: int
    files: tuple[D64File, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)


class _D64Reader:
    """Bounds-checked sector and CBM DOS-chain reader for one canonical image."""

    def __init__(self, source: Path, data: bytes) -> None:
        self.source = source
        self.data = data

    @staticmethod
    def sectors_per_track(track: int) -> int:
        if not 1 <= track <= D64_TRACK_COUNT:
            raise DiskForgeError("D64 track number is outside the canonical 35-track range.")
        if track <= 17:
            return 21
        if track <= 24:
            return 19
        if track <= 30:
            return 18
        return 17

    @classmethod
    def sector_offset(cls, track: int, sector: int) -> int:
        sectors = cls.sectors_per_track(track)
        if not 0 <= sector < sectors:
            raise DiskForgeError("D64 sector number is outside its track range.")
        prior = sum(cls.sectors_per_track(number) for number in range(1, track))
        return (prior + sector) * D64_SECTOR_SIZE

    def sector(self, track: int, sector: int) -> bytes:
        offset = self.sector_offset(track, sector)
        value = self.data[offset:offset + D64_SECTOR_SIZE]
        if len(value) != D64_SECTOR_SIZE:
            raise DiskForgeError("D64 sector range is truncated.")
        return value

    @staticmethod
    def petscii(value: bytes) -> str:
        """Render a bounded PETSCII label without allowing path separators or controls."""
        value = value.rstrip(b"\x00\xa0")
        rendered: list[str] = []
        for byte in value:
            if byte in (0x00, 0xA0):
                rendered.append(" ")
            elif 0x20 <= byte <= 0x5E:
                rendered.append(chr(byte))
            elif 0xC1 <= byte <= 0xDA:
                rendered.append(chr(byte - 0x80))
            elif byte == 0x5F:
                rendered.append("←")
            elif byte == 0x5C:
                rendered.append("£")
            else:
                rendered.append("�")
        return "".join(rendered).strip()

    @staticmethod
    def safe_name(value: str, index: int) -> str:
        """Keep displayed entry names useful while preventing local path escapes."""
        cleaned = value.replace("/", "∕").replace("\\", "⧵").replace("\x00", "�").strip()
        if cleaned in {"", ".", ".."}:
            return f"unnamed-{index:03d}"
        return cleaned

    def read_directory(self) -> tuple[tuple[tuple[int, int], ...], tuple[D64File, ...]]:
        current = (D64_DIRECTORY_TRACK, D64_DIRECTORY_SECTOR)
        visited: set[tuple[int, int]] = set()
        directory_chain: list[tuple[int, int]] = []
        records: list[tuple[int, bytes]] = []
        while True:
            if current in visited:
                raise DiskForgeError("D64 directory chain contains a loop.")
            visited.add(current)
            directory_chain.append(current)
            block = self.sector(*current)
            for offset in range(0, D64_SECTOR_SIZE, 32):
                record = block[offset:offset + 32]
                if record[2] != 0:
                    records.append((len(records) + 1, record))
            next_track, next_sector = block[0], block[1]
            if next_track == 0:
                break
            self.sector_offset(next_track, next_sector)
            current = (next_track, next_sector)
            if len(visited) > D64_SECTOR_COUNT:
                raise DiskForgeError("D64 directory chain exceeds the canonical sector limit.")

        files: list[D64File] = []
        claimed_data: set[tuple[int, int]] = set(directory_chain)
        for index, record in records:
            kind = record[2] & 0x0F
            if kind == 0:
                continue
            if kind not in _D64_ALLOWED_FILE_TYPES:
                raise DiskForgeError("D64 contains a REL or unsupported CBM DOS directory entry type.")
            start_track, start_sector = record[3], record[4]
            blocks = int.from_bytes(record[30:32], "little")
            raw_name = self.petscii(record[5:21])
            name = self.safe_name(raw_name, index)
            chain, size = self.read_file_chain(start_track, start_sector, blocks)
            overlap = claimed_data.intersection(chain)
            if overlap:
                raise DiskForgeError("D64 directory and file chains overlap.")
            claimed_data.update(chain)
            path = f"/{index:03d}-{name}"
            files.append(D64File(
                index=index,
                path=path,
                name=name,
                file_type=_D64_ALLOWED_FILE_TYPES[kind],
                locked=bool(record[2] & 0x40),
                closed=bool(record[2] & 0x80),
                blocks=blocks,
                size=size,
                start_track=start_track,
                start_sector=start_sector,
                chain=chain,
            ))
        return tuple(directory_chain), tuple(files)

    def read_file_chain(self, start_track: int, start_sector: int, blocks: int) -> tuple[tuple[tuple[int, int], ...], int]:
        if blocks == 0:
            if (start_track, start_sector) != (0, 0):
                raise DiskForgeError("A zero-block D64 file must not have a data-chain start sector.")
            return (), 0
        self.sector_offset(start_track, start_sector)
        current = (start_track, start_sector)
        visited: set[tuple[int, int]] = set()
        chain: list[tuple[int, int]] = []
        size = 0
        while True:
            if current in visited:
                raise DiskForgeError("D64 file data chain contains a loop.")
            visited.add(current)
            chain.append(current)
            block = self.sector(*current)
            next_track, next_sector = block[0], block[1]
            if next_track == 0:
                if not 1 <= next_sector <= 255:
                    raise DiskForgeError("D64 final file sector has an invalid used-byte count.")
                size += next_sector - 1
                break
            self.sector_offset(next_track, next_sector)
            size += D64_SECTOR_SIZE - 2
            current = (next_track, next_sector)
            if len(visited) > D64_SECTOR_COUNT:
                raise DiskForgeError("D64 file data chain exceeds the canonical sector limit.")
        if len(visited) != blocks:
            raise DiskForgeError("D64 directory block count does not match the validated file chain.")
        return tuple(chain), size

    def file_bytes(self, entry: D64File) -> bytes:
        result = bytearray()
        for offset, location in enumerate(entry.chain):
            block = self.sector(*location)
            if offset + 1 == len(entry.chain):
                result.extend(block[2:block[1] + 1])
            else:
                result.extend(block[2:])
        if len(result) != entry.size:
            raise DiskForgeError("D64 file chain changed while being read.")
        return bytes(result)


def is_d64_header(path: Path | str) -> bool:
    """Return whether a regular non-symlink path can be the canonical D64 profile."""
    source = Path(path)
    return source.suffix.lower() == D64_SUFFIX and source.is_file() and not source.is_symlink() and source.stat().st_size == D64_SIZE_BYTES


def inspect_d64(path: Path | str) -> D64Inspection:
    """Strictly inspect one canonical 35-track D64 and its ordinary file chains."""
    source = Path(path)
    if source.suffix.lower() != D64_SUFFIX:
        raise DiskForgeError("D64 inspection requires a .d64 source file.")
    if not source.is_file() or source.is_symlink():
        raise DiskForgeError("D64 inspection requires a regular non-symlink source file.")
    if source.stat().st_size != D64_SIZE_BYTES:
        raise DiskForgeError("D64 inspection accepts only the canonical 35-track 174,848-byte profile without an error map.")
    data = source.read_bytes()
    reader = _D64Reader(source, data)
    bam = reader.sector(D64_BAM_TRACK, D64_BAM_SECTOR)
    if bam[2] not in {0x00, 0x41}:
        raise DiskForgeError("D64 BAM has an unsupported DOS version byte.")
    directory_chain, files = reader.read_directory()
    free_counts = tuple(bam[4 + (track - 1) * 4] for track in range(1, D64_TRACK_COUNT + 1))
    if any(count > reader.sectors_per_track(track) for track, count in enumerate(free_counts, start=1)):
        raise DiskForgeError("D64 BAM contains an impossible free-sector count.")
    free_blocks = sum(free_counts)
    return D64Inspection(
        source=source,
        size=len(data),
        disk_name=reader.petscii(bam[0x90:0xA0]),
        disk_id=reader.petscii(bam[0xA2:0xA4]),
        dos_type=reader.petscii(bam[0xA5:0xA7]),
        directory_sectors=len(directory_chain),
        free_blocks=free_blocks,
        files=files,
    )


def read_d64_file(path: Path | str, entry: D64File) -> bytes:
    """Read bytes for a file produced by :func:`inspect_d64` after revalidation."""
    inspection = inspect_d64(path)
    matching = next((candidate for candidate in inspection.files if candidate.path == entry.path), None)
    if matching is None:
        raise FileNotFoundError(entry.path)
    data = Path(path).read_bytes()
    return _D64Reader(Path(path), data).file_bytes(matching)
