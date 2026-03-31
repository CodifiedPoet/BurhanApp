"""Helper utilities — page parsing, path resolution, geometry, UI scaling."""

import math
import os
import sys
import urllib.parse


# ── UI scale factor ──────────────────────────────────────────────────

_ui_scale: float | None = None


def get_ui_scale() -> float:
    """Return a scale factor (0.65–1.0) based on primary screen height.

    Baseline is 1080px (typical Windows desktop).  Smaller screens
    (e.g. 900px MacBook) get proportionally smaller UI elements.
    On macOS, an extra 10% reduction compensates for larger system
    font rendering.  Must be called *after* QApplication is created.
    """
    global _ui_scale
    if _ui_scale is not None:
        return _ui_scale
    try:
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            h = screen.availableGeometry().height()
            _ui_scale = max(0.65, min(1.0, h / 1080))
            if sys.platform == "darwin":
                _ui_scale = max(0.65, _ui_scale * 0.88)
        else:
            _ui_scale = 1.0
    except Exception:
        _ui_scale = 1.0
    return _ui_scale


def is_compact_screen() -> bool:
    """Return True if the screen is too small for a comfortable layout."""
    try:
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            return g.height() < 1000 or g.width() < 1400
    except Exception:
        pass
    return sys.platform == "darwin"


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
