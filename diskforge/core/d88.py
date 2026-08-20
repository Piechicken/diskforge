"""Restricted read-only D88 inspection and strict RAW export."""
from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .storage import CancellationToken, DiskForgeError

_HEADER_SIZES = {0x2A0, 0x2B0}
_MAX_SOURCE = 16 * 1024 * 1024 * 1024
_MAX_TRACKS = 164
_MAX_SECTORS = 64
_MAX_N = 7
_MAX_RAW = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class D88Sector:
    track_slot: int
    c: int
    h: int
    r: int
    n: int
    sectors_in_track: int
    density: int
    deleted: int
    status: int
    actual_bytes: int
    data_offset: int


@dataclass(frozen=True)
class D88Track:
    slot: int
    offset: int
    sectors: tuple[D88Sector, ...]


@dataclass(frozen=True)
class D88Inspection:
    source: Path
    name: str
    write_protected: bool
    media_type: int
    tracks: tuple[D88Track, ...]
    source_bytes: int
    exportable: bool
    export_reason: str
    cylinders: int | None
    sides: int | None
    sectors_per_track: int | None
    bytes_per_sector: int | None
    raw_bytes: int | None


def _exact(handle: BinaryIO, size: int, message: str) -> bytes:
    value = handle.read(size)
    if len(value) != size:
        raise DiskForgeError(message)
    return value


def _parse(path: Path, token: CancellationToken | None = None) -> tuple[str, bool, int, tuple[D88Track, ...], int]:
    try:
        mode = path.lstat().st_mode
        size = path.stat().st_size
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DiskForgeError("D88 inspection accepts regular non-symbolic-link source files only.")
    if size > _MAX_SOURCE or size < min(_HEADER_SIZES):
        raise DiskForgeError("The D88 source size is outside the supported safety range.")
    with path.open("rb") as handle:
        prefix = _exact(handle, min(_HEADER_SIZES), "The D88 header is truncated.")
        first_offset = int.from_bytes(prefix[0x20:0x24], "little")
        if first_offset not in _HEADER_SIZES:
            raise DiskForgeError("The D88 first track offset does not identify a supported header layout.")
        header = prefix if first_offset == len(prefix) else prefix + _exact(handle, first_offset - len(prefix), "The D88 header is truncated.")
        disk_bytes = int.from_bytes(header[0x1C:0x20], "little")
        if disk_bytes != size:
            raise DiskForgeError("The D88 disk size does not exactly match the source file; multi-disk or trailing data is rejected.")
        offsets = [int.from_bytes(header[0x20 + 4*i:0x24 + 4*i], "little") for i in range((first_offset - 0x20)//4)]
        active = [(i, offset) for i, offset in enumerate(offsets) if offset]
        if not active or active[0][1] != first_offset or any(offset < first_offset or offset >= size for _, offset in active):
            raise DiskForgeError("The D88 track offsets are invalid.")
        if any(right <= left for (_, left), (_, right) in zip(active, active[1:])):
            raise DiskForgeError("The D88 track offsets are not strictly increasing.")
        tracks: list[D88Track] = []
        for pos, (slot, offset) in enumerate(active):
            if token: token.raise_if_cancelled()
            end = active[pos + 1][1] if pos + 1 < len(active) else size
            handle.seek(offset)
            sectors: list[D88Sector] = []
            while handle.tell() < end:
                if token: token.raise_if_cancelled()
                header_bytes = _exact(handle, 16, "The D88 file ends inside a sector header.")
                c,h,r,n = header_bytes[:4]
                count = int.from_bytes(header_bytes[4:6], "little")
                actual = int.from_bytes(header_bytes[14:16], "little")
                if not count or count > _MAX_SECTORS or n > _MAX_N or not actual or handle.tell() + actual > end:
                    raise DiskForgeError("The D88 sector header or payload extent is invalid.")
                data_offset = handle.tell()
                _exact(handle, actual, "The D88 file ends inside sector data.")
                sectors.append(D88Sector(slot,c,h,r,n,count,header_bytes[6],header_bytes[7],header_bytes[8],actual,data_offset))
                if len(sectors) > count:
                    raise DiskForgeError("The D88 track contains more sectors than it declares.")
            if not sectors or len(sectors) != sectors[0].sectors_in_track or any(s.sectors_in_track != len(sectors) for s in sectors):
                raise DiskForgeError("The D88 track sector count is inconsistent.")
            tracks.append(D88Track(slot, offset, tuple(sectors)))
    return header[:16].rstrip(b"\0 ").decode("ascii", errors="replace"), bool(header[0x1A]), header[0x1B], tuple(tracks), size


def _proof(tracks: tuple[D88Track, ...]) -> tuple[bool,str,int|None,int|None,int|None,int|None,int|None]:
    if not tracks: return False,"The D88 contains no tracks.",None,None,None,None,None
    first = tracks[0].sectors[0]; spt=len(tracks[0].sectors); bps=128<<first.n
    coordinates={(track.sectors[0].c, track.sectors[0].h) for track in tracks}
    cylinders=max(c for c,_ in coordinates)+1; sides=max(h for _,h in coordinates)+1
    if coordinates != {(c,h) for c in range(cylinders) for h in range(sides)}: return False,"The D88 tracks do not form a complete rectangular CHS layout.",None,None,None,None,None
    for track in tracks:
        expected=tuple(range(1,spt+1))
        if len(track.sectors)!=spt or tuple(s.r for s in track.sectors)!=expected: return False,"The D88 sector identifiers are not consecutive 1..N.",None,None,None,None,None
        for s in track.sectors:
            if s.n!=first.n or s.actual_bytes!=bps or s.deleted or s.status or (s.c,s.h)!=(track.sectors[0].c,track.sectors[0].h): return False,"The D88 contains non-normal, variable, or coordinate-mismatched sector data.",None,None,None,None,None
    raw=cylinders*sides*spt*bps
    return (True,"The D88 has a complete normal-data rectangular CHS layout.",cylinders,sides,spt,bps,raw) if raw <= _MAX_RAW else (False,"The D88 RAW output exceeds the 2-GiB safety limit.",None,None,None,None,None)


def inspect_d88(source: Path | str, token: CancellationToken | None = None) -> D88Inspection:
    path=Path(source); name, protected, media, tracks, size=_parse(path,token); proof=_proof(tracks)
    return D88Inspection(path,name,protected,media,tracks,size,*proof)


def export_d88_to_raw(source: Path | str, destination: Path | str, token: CancellationToken | None = None) -> Path:
    source_path=Path(source); target=Path(destination); inspection=inspect_d88(source_path,token)
    if not inspection.exportable: raise DiskForgeError(f"The D88 cannot be safely exported to RAW: {inspection.export_reason}")
    if source_path.resolve()==target.resolve(): raise DiskForgeError("The D88 RAW export destination must differ from the source file.")
    if target.exists() or target.is_symlink(): raise FileExistsError(target)
    if not target.parent.is_dir(): raise DiskForgeError("The D88 RAW export destination directory does not exist.")
    temp: Path|None=None
    try:
        fd,name=tempfile.mkstemp(prefix=f".{target.name}.diskforge-d88-",suffix=".tmp",dir=target.parent); temp=Path(name)
        with source_path.open("rb") as inp, os.fdopen(fd,"wb") as out:
            for track in inspection.tracks:
                for sector in track.sectors:
                    if token: token.raise_if_cancelled()
                    inp.seek(sector.data_offset); out.write(_exact(inp,sector.actual_bytes,"The D88 sector payload is truncated."))
        if temp.stat().st_size != inspection.raw_bytes: raise DiskForgeError("The D88 RAW export produced an unexpected byte count.")
        os.link(temp,target); temp.unlink(); temp=None; return target
    finally:
        if temp is not None: temp.unlink(missing_ok=True)
