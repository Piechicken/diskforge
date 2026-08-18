"""Deterministic, auditable numbering patterns for batch file workflows."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .storage import DiskForgeError


@dataclass(frozen=True)
class SequencePattern:
    """Render safe, predictable sequential names without mutating the filesystem."""

    prefix: str = "image-"
    start: int = 1
    width: int = 3
    step: int = 1
    suffix: str = ""

    def __post_init__(self) -> None:
        if self.start < 0:
            raise DiskForgeError("Sequence start must be zero or greater.")
        if not 1 <= self.width <= 12:
            raise DiskForgeError("Sequence width must be between 1 and 12 digits.")
        if self.step <= 0:
            raise DiskForgeError("Sequence step must be greater than zero.")
        if any(part in self.prefix or part in self.suffix for part in ("/", "\\", "\x00")):
            raise DiskForgeError("Sequence prefix and suffix must not contain path separators or NUL.")

    def value_at(self, index: int) -> int:
        if index < 0:
            raise DiskForgeError("Sequence index must be zero or greater.")
        return self.start + index * self.step

    def render(self, index: int) -> str:
        return f"{self.prefix}{self.value_at(index):0{self.width}d}{self.suffix}"

    def preview(self, count: int) -> tuple[str, ...]:
        if count < 0:
            raise DiskForgeError("Preview count must be zero or greater.")
        return tuple(self.render(index) for index in range(count))

    @classmethod
    def from_mapping(cls, value: object) -> "SequencePattern":
        if not isinstance(value, dict):
            raise DiskForgeError("Sequence pattern must be an object.")
        allowed = {"prefix", "start", "width", "step", "suffix"}
        unknown = set(value) - allowed
        if unknown:
            raise DiskForgeError(f"Unsupported sequence pattern keys: {', '.join(sorted(unknown))}")
        try:
            return cls(
                prefix=str(value.get("prefix", "image-")),
                start=int(value.get("start", 1)),
                width=int(value.get("width", 3)),
                step=int(value.get("step", 1)),
                suffix=str(value.get("suffix", "")),
            )
        except (TypeError, ValueError) as exc:
            raise DiskForgeError("Sequence pattern values are invalid.") from exc


def planned_paths(root: Path | str, pattern: SequencePattern, count: int) -> tuple[Path, ...]:
    """Return uncreated, normalized destination paths for a planned sequence."""
    base = Path(root)
    names = pattern.preview(count)
    if len({name.casefold() for name in names}) != len(names):
        raise DiskForgeError("Sequence pattern produces duplicate destination names.")
    return tuple(base / name for name in names)
