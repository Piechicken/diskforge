"""Build deterministic desktop icon formats from the approved DiskForge source art."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "icons" / "diskforge-v075-source.png"
TARGET = ROOT / "assets" / "icons"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024)


def render(size: int, source: Image.Image) -> Image.Image:
    return source.resize((size, size), Image.Resampling.LANCZOS)


def _is_checker_background(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, _ = pixel
    return min(red, green, blue) >= 224 and max(red, green, blue) - min(red, green, blue) <= 12


def _remove_edge_connected_checkerboard(source: Image.Image) -> Image.Image:
    """Make only the outer light-grey checkerboard transparent.

    The approved mark is separated from the canvas edge by a generous margin, so
    four-connected flood fill preserves silver shapes inside the floppy symbol.
    """
    image = source.copy().convert("RGBA")
    width, height = image.size
    pixels = image.load()
    pending: deque[tuple[int, int]] = deque()
    visited: set[tuple[int, int]] = set()
    for x in range(width):
        pending.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        pending.extend(((0, y), (width - 1, y)))
    while pending:
        x, y = pending.popleft()
        if (x, y) in visited or not _is_checker_background(pixels[x, y]):
            continue
        visited.add((x, y))
        for neighbor_x, neighbor_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= neighbor_x < width and 0 <= neighbor_y < height:
                pending.append((neighbor_x, neighbor_y))
    for x, y in visited:
        red, green, blue, _ = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
    return image


def main() -> None:
    source = _remove_edge_connected_checkerboard(Image.open(SOURCE).convert("RGBA"))
    alpha = source.getchannel("A")
    minimum, maximum = alpha.getextrema()
    if minimum == maximum == 255:
        raise SystemExit("The icon source has no removable transparent margin.")
    TARGET.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        render(size, source).save(TARGET / f"diskforge-{size}.png", optimize=True)
    render(512, source).save(TARGET / "diskforge-icon.png", optimize=True)
    render(1024, source).save(TARGET / "diskforge-icon.icns", format="ICNS")
    render(256, source).save(
        TARGET / "diskforge-icon.ico",
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Rendered icons from {SOURCE.name}; alpha range={minimum}..{maximum}.")


if __name__ == "__main__":
    main()
