"""Helper utilities — page parsing, path resolution, geometry."""

import math
import os
import urllib.parse


def parse_page_ranges(text: str) -> list[int]:
    """Parse '1-5, 7, 9' into a sorted list of ints."""
    pages: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            pages.update(range(int(lo.strip()), int(hi.strip()) + 1))
        else:
            pages.add(int(part))
    return sorted(pages)


def get_local_pdf_path(pdf_path: str) -> str:
    if pdf_path.startswith("file://"):
        parsed = urllib.parse.urlparse(pdf_path)
        path = urllib.parse.unquote(parsed.path)
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return path
    return pdf_path


def ruler_step(scale: float) -> int:
    """Pick a nice tick interval (in image-pixels) based on current zoom."""
    raw = 50 / max(scale, 0.01)
    nice = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000]
    for n in nice:
        if n >= raw:
            return n
    return nice[-1]


def norm(x1, y1, x2, y2):
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def arrowhead(x1, y1, x2, y2, line_width=3):
    """Return (polygon, shaft_end) for a filled arrowhead at (x2, y2)."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1:
        return None, (x2, y2)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    head_len = max(14, line_width * 4)
    head_half_w = max(6, line_width * 2)

    bx, by = x2 - ux * head_len, y2 - uy * head_len
    polygon = [
        (x2, y2),
        (bx + px * head_half_w, by + py * head_half_w),
        (bx - px * head_half_w, by - py * head_half_w),
    ]
    shaft_end = (bx, by)
    return polygon, shaft_end
