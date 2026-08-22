"""Strict read-only inspection for standard 1581 D81 images.

The D81 family has no magic header. This module accepts only the canonical
80-track, 819,200-byte, 256-byte-sector profile and validates the 1581 header,
both BAM sectors, a canonical root directory on track 40, and ordinary
SEQ/PRG/USR data chains. It deliberately excludes error maps, extended
directories, REL/GEOS, CBM partitions, GCR decoding, repair, conversion, and
writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .storage import DiskForgeError

D81_SUFFIX = ".d81"
D81_SECTOR_SIZE = 256
D81_TRACK_COUNT = 80
D81_SECTORS_PER_TRACK = 40
D81_SECTOR_COUNT = D81_TRACK_COUNT * D81_SECTORS_PER_TRACK
D81_SIZE_BYTES = D81_SECTOR_COUNT * D81_SECTOR_SIZE
D81_DIRECTORY_TRACK = 40
D81_DIRECTORY_SECTOR = 3
D81_HEADER_TRACK = 40
D81_HEADER_SECTOR = 0
D81_BAM_TRACK = 40
D81_BAM0_SECTOR = 1
D81_BAM1_SECTOR = 2
_D81_ALLOWED_FILE_TYPES = {1: "SEQ", 2: "PRG", 3: "USR"}


@dataclass(frozen=True)
class D81File:
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
class D81Inspection:
    """Verified facts about a canonical D81 and its ordinary data files."""

    source: Path
    size: int
    disk_name: str
    disk_id: str
    dos_type: str
    directory_sectors: int
    free_blocks: int
    files: tuple[D81File, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)


class _D81Reader:
    """Bounds-checked sector and CBM DOS-chain reader for one canonical image."""

    def __init__(self, source: Path, data: bytes) -> None:
        self.source = source
        self.data = data

    @staticmethod
    def sectors_per_track(track: int) -> int:
        if not 1 <= track <= D81_TRACK_COUNT:
            raise DiskForgeError("D81 track number is outside the canonical 80-track range.")
        return D81_SECTORS_PER_TRACK

    @classmethod
    def sector_offset(cls, track: int, sector: int) -> int:
        sectors = cls.sectors_per_track(track)
        if not 0 <= sector < sectors:
            raise DiskForgeError("D81 sector number is outside its track range.")
        return ((track - 1) * D81_SECTORS_PER_TRACK + sector) * D81_SECTOR_SIZE

    def sector(self, track: int, sector: int) -> bytes:
        offset = self.sector_offset(track, sector)
        value = self.data[offset:offset + D81_SECTOR_SIZE]
        if len(value) != D81_SECTOR_SIZE:
            raise DiskForgeError("D81 sector range is truncated.")
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

    def read_directory(self) -> tuple[tuple[tuple[int, int], ...], tuple[D81File, ...]]:
        current = (D81_DIRECTORY_TRACK, D81_DIRECTORY_SECTOR)
        visited: set[tuple[int, int]] = set()
        directory_chain: list[tuple[int, int]] = []
        records: list[tuple[int, bytes]] = []
        while True:
            if current in visited:
                raise DiskForgeError("D81 directory chain contains a loop.")
            visited.add(current)
            directory_chain.append(current)
            block = self.sector(*current)
            for offset in range(0, D81_SECTOR_SIZE, 32):
                record = block[offset:offset + 32]
                if record[2] != 0:
                    records.append((len(records) + 1, record))
            next_track, next_sector = block[0], block[1]
            if next_track == 0:
                break
            if next_track != D81_DIRECTORY_TRACK or next_sector != current[1] + 1 or next_sector >= D81_SECTORS_PER_TRACK:
                raise DiskForgeError("D81 directory chain is not a canonical linear track-40 directory.")
            current = (next_track, next_sector)
            if len(visited) > D81_SECTORS_PER_TRACK - D81_DIRECTORY_SECTOR:
                raise DiskForgeError("D81 directory chain exceeds the canonical track-40 limit.")

        files: list[D81File] = []
        claimed_data: set[tuple[int, int]] = {
            (D81_HEADER_TRACK, D81_HEADER_SECTOR),
            (D81_BAM_TRACK, D81_BAM0_SECTOR),
            (D81_BAM_TRACK, D81_BAM1_SECTOR),
            *directory_chain,
        }
        for index, record in records:
            kind = record[2] & 0x0F
            if kind == 0:
                continue
            if kind not in _D81_ALLOWED_FILE_TYPES:
                raise DiskForgeError("D81 contains a REL or unsupported CBM DOS directory entry type.")
            start_track, start_sector = record[3], record[4]
            blocks = int.from_bytes(record[30:32], "little")
            raw_name = self.petscii(record[5:21])
            name = self.safe_name(raw_name, index)
            chain, size = self.read_file_chain(start_track, start_sector, blocks)
            overlap = claimed_data.intersection(chain)
            if overlap:
                raise DiskForgeError("D81 directory and file chains overlap.")
            claimed_data.update(chain)
            path = f"/{index:03d}-{name}"
            files.append(D81File(
                index=index,
                path=path,
                name=name,
                file_type=_D81_ALLOWED_FILE_TYPES[kind],
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
                raise DiskForgeError("A zero-block D81 file must not have a data-chain start sector.")
            return (), 0
        self.sector_offset(start_track, start_sector)
        current = (start_track, start_sector)
        visited: set[tuple[int, int]] = set()
        chain: list[tuple[int, int]] = []
        size = 0
        while True:
            if current in visited:
                raise DiskForgeError("D81 file data chain contains a loop.")
            visited.add(current)
            chain.append(current)
            block = self.sector(*current)
            next_track, next_sector = block[0], block[1]
            if next_track == 0:
                if not 1 <= next_sector <= 255:
                    raise DiskForgeError("D81 final file sector has an invalid used-byte count.")
                size += next_sector - 1
                break
            self.sector_offset(next_track, next_sector)
            size += D81_SECTOR_SIZE - 2
            current = (next_track, next_sector)
            if len(visited) > D81_SECTOR_COUNT:
                raise DiskForgeError("D81 file data chain exceeds the canonical sector limit.")
        if len(visited) != blocks:
            raise DiskForgeError("D81 directory block count does not match the validated file chain.")
        return tuple(chain), size

    def file_bytes(self, entry: D81File) -> bytes:
        result = bytearray()
        for offset, location in enumerate(entry.chain):
            block = self.sector(*location)
            if offset + 1 == len(entry.chain):
                result.extend(block[2:block[1] + 1])
            else:
                result.extend(block[2:])
        if len(result) != entry.size:
            raise DiskForgeError("D81 file chain changed while being read.")
        return bytes(result)


def is_d81_header(path: Path | str) -> bool:
    """Return whether a regular non-symlink path can be the canonical D81 profile."""
    source = Path(path)
    return source.suffix.lower() == D81_SUFFIX and source.is_file() and not source.is_symlink() and source.stat().st_size == D81_SIZE_BYTES


def inspect_d81(path: Path | str) -> D81Inspection:
    """Strictly inspect one canonical 80-track D81 and its ordinary file chains."""
    source = Path(path)
    if source.suffix.lower() != D81_SUFFIX:
        raise DiskForgeError("D81 inspection requires a .d81 source file.")
    if not source.is_file() or source.is_symlink():
        raise DiskForgeError("D81 inspection requires a regular non-symlink source file.")
    if source.stat().st_size != D81_SIZE_BYTES:
        raise DiskForgeError("D81 inspection accepts only the canonical 80-track 819,200-byte profile without an error map.")
    data = source.read_bytes()
    reader = _D81Reader(source, data)
    header = reader.sector(D81_HEADER_TRACK, D81_HEADER_SECTOR)
    bam0 = reader.sector(D81_BAM_TRACK, D81_BAM0_SECTOR)
    bam1 = reader.sector(D81_BAM_TRACK, D81_BAM1_SECTOR)
    if header[2] != 0x44 or header[3] != 0:
        raise DiskForgeError("D81 header does not declare the canonical 1581 DOS type.")
    if bam0[:4] != bytes((D81_BAM_TRACK, D81_BAM1_SECTOR, 0x44, 0xBB)):
        raise DiskForgeError("D81 side-0 BAM has an invalid canonical link or DOS version.")
    if bam1[:4] != bytes((0, 0xFF, 0x44, 0xBB)):
        raise DiskForgeError("D81 side-1 BAM has an invalid canonical terminal link or DOS version.")
    if bam0[4:6] != header[0x16:0x18] or bam1[4:6] != header[0x16:0x18]:
        raise DiskForgeError("D81 header and BAM disk IDs do not match.")

    free_blocks = 0
    free_locations: set[tuple[int, int]] = set()
    for track in range(1, D81_TRACK_COUNT + 1):
        bam = bam0 if track <= 40 else bam1
        offset = 0x10 + ((track - 1) % 40) * 6
        count = bam[offset]
        bitmap = bam[offset + 1:offset + 6]
        actual = sum(byte.bit_count() for byte in bitmap)
        if count != actual:
            raise DiskForgeError("D81 BAM free-sector count does not match its bitmap.")
        free_blocks += count
        for sector in range(D81_SECTORS_PER_TRACK):
            if bitmap[sector // 8] & (1 << (sector % 8)):
                free_locations.add((track, sector))

    directory_chain, files = reader.read_directory()
    claimed = {
        (D81_HEADER_TRACK, D81_HEADER_SECTOR),
        (D81_BAM_TRACK, D81_BAM0_SECTOR),
        (D81_BAM_TRACK, D81_BAM1_SECTOR),
        *directory_chain,
        *(location for item in files for location in item.chain),
    }
    if claimed.intersection(free_locations):
        raise DiskForgeError("D81 BAM marks a required system, directory, or file sector as free.")
    return D81Inspection(
        source=source,
        size=len(data),
        disk_name=reader.petscii(header[4:20]),
        disk_id=reader.petscii(header[0x16:0x18]),
        dos_type=reader.petscii(header[0x19:0x1B]),
        directory_sectors=len(directory_chain),
        free_blocks=free_blocks,
        files=files,
    )


def read_d81_file(path: Path | str, entry: D81File) -> bytes:
    """Read bytes for a file produced by :func:`inspect_d81` after revalidation."""
    inspection = inspect_d81(path)
    matching = next((candidate for candidate in inspection.files if candidate.path == entry.path), None)
    if matching is None:
        raise FileNotFoundError(entry.path)
    data = Path(path).read_bytes()
    return _D81Reader(Path(path), data).file_bytes(matching)
