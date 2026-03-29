"""Rendering — PDF to images, annotation compositing, watermark, merge."""

import math
from dataclasses import replace as _dc_replace

import fitz  # PyMuPDF
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .models import Annotation, TextRun, Tool
from .utils import arrowhead, get_local_pdf_path, norm


import os as _os
import sys as _sys

# Build a lookup table: (family_lower, style_lower) -> full path
_FONT_MAP: dict[tuple[str, str], str] = {}

_STYLE_WORDS = {"Bold", "Italic", "Light", "SemiBold", "Thin",
                "Medium", "Black", "ExtraBold", "ExtraLight"}


def _parse_font_filename(display_name: str, filepath: str):
    """Parse a font display name and register it in _FONT_MAP."""
    name_part = display_name.split("(")[0].strip()
    tokens = name_part.split()
    style_start = len(tokens)
    for si in range(len(tokens) - 1, 0, -1):
        if tokens[si] in _STYLE_WORDS:
            style_start = si
        else:
            break
    family = " ".join(tokens[:style_start])
    style = " ".join(tokens[style_start:])
    if not family:
        family = name_part
        style = ""
    _FONT_MAP[(family.lower(), style.lower())] = filepath


def _build_font_map():
    """Populate _FONT_MAP from the OS font registry / directories."""
    if _FONT_MAP:
        return
    if _sys.platform == "win32":
        _build_font_map_windows()
    else:
        _build_font_map_unix()


def _build_font_map_windows():
    """Parse the Windows font registry."""
    import winreg as _winreg
    fonts_dir = _os.path.join(_os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    try:
        key = _winreg.OpenKey(
            _winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
    except OSError:
        return
    try:
        i = 0
        while True:
            try:
                display_name, filename, _ = _winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if not filename.lower().endswith((".ttf", ".otf")):
                continue
            path = filename if _os.path.isabs(filename) else _os.path.join(fonts_dir, filename)
            _parse_font_filename(display_name, path)
    finally:
        _winreg.CloseKey(key)


def _build_font_map_unix():
    """Scan macOS / Linux font directories."""
    from pathlib import Path
    dirs = []
    if _sys.platform == "darwin":
        dirs = [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
        ]
    else:
        dirs = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local" / "share" / "fonts",
            Path.home() / ".fonts",
        ]
    for d in dirs:
        if not d.is_dir():
            continue
        for fp in d.rglob("*"):
            if fp.suffix.lower() not in (".ttf", ".otf"):
                continue
            # Derive a display name from the filename: "ArialBoldItalic.ttf" -> "Arial Bold Italic"
            stem = fp.stem
            # Insert spaces before uppercase runs: "ArialBold" -> "Arial Bold"
            import re
            spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', stem)
            spaced = spaced.replace("-", " ").replace("_", " ")
            _parse_font_filename(spaced, str(fp))


def _resolve_font(family: str, size: int, bold: bool, italic: bool):
    """Resolve a PIL ImageFont for the given family/size/style."""
    _build_font_map()

    # Determine the desired style string
    if bold and italic:
        style = "bold italic"
    elif bold:
        style = "bold"
    elif italic:
        style = "italic"
    else:
        style = ""

    # Try the requested family, then fallbacks
    _fallbacks = ("Arial", "Helvetica", "Segoe UI", "Tahoma") if _sys.platform == "win32" \
        else ("Arial", "Helvetica", "Helvetica Neue", "SF Pro Text")
    for name in (family, *_fallbacks):
        key = (name.lower(), style)
        if key in _FONT_MAP:
            try:
                return ImageFont.truetype(_FONT_MAP[key], size)
            except IOError:
                pass
        # Fall back to regular style of this family
        reg_key = (name.lower(), "")
        if reg_key in _FONT_MAP:
            try:
                return ImageFont.truetype(_FONT_MAP[reg_key], size)
            except IOError:
                pass
    return ImageFont.load_default()


def _render_text_runs(draw, runs, x, y, x2, alpha, fallback_color,
                      line_spacing=1.2):
    """Render a list of TextRun objects, wrapping at x2, advancing y per line."""
    cursor_x = x
    cursor_y = y
    line_height = 0

    for run in runs:
        font = _resolve_font(run.font_family, run.font_size,
                              run.font_bold, run.font_italic)
        fc = run.font_color if run.font_color else fallback_color
        fill = fc + (alpha,)

        # Split by newlines first
        segments = run.text.split("\n")
        for seg_idx, segment in enumerate(segments):
            if seg_idx > 0:
                # Explicit newline: move to next line
                cursor_x = x
                cursor_y += int((line_height or run.font_size) * line_spacing)
                line_height = 0

            # Word-wrap within segment
            words = segment.split(" ")
            for w_idx, word in enumerate(words):
                piece = word if w_idx == 0 else " " + word
                bbox = font.getbbox(piece)
                pw = bbox[2] - bbox[0]
                ph = bbox[3] - bbox[1]
                # Wrap if exceeding right edge (but always draw at least one word per line)
                if cursor_x + pw > x2 and cursor_x > x:
                    cursor_x = x
                    cursor_y += int((line_height or ph) * line_spacing)
                    line_height = 0
                    piece = word  # drop leading space after wrap

                draw.text((cursor_x, cursor_y), piece, font=font, fill=fill)
                bbox2 = font.getbbox(piece)
                cursor_x += bbox2[2] - bbox2[0]
                line_height = max(line_height, ph)


def pdf_pages_to_images(pdf_path: str, pages: list[int], dpi: int = 300) -> list[Image.Image]:
    local = get_local_pdf_path(pdf_path)
    doc = fitz.open(local)
    try:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        images: list[Image.Image] = []
        for page_num in pages:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                continue
            pix = doc[idx].get_pixmap(matrix=mat, alpha=False)
            images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return images
    finally:
        doc.close()


def _bezier_points(x1, y1, x2, y2, offset_frac: float, n_segs: int = 40):
    """Return list of (x, y) points along a quadratic Bezier curve.

    The control point is placed perpendicular to the midpoint of (x1,y1)-(x2,y2)
    at a distance of *offset_frac* × line_length.
    """
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1:
        return [(x1, y1), (x2, y2)]
    px, py = -dy / length, dx / length  # perpendicular unit
    off = length * offset_frac
    cx, cy = mx + px * off, my + py * off
    pts = []
    for i in range(n_segs + 1):
        t = i / n_segs
        u = 1 - t
        bx = u * u * x1 + 2 * u * t * cx + t * t * x2
        by = u * u * y1 + 2 * u * t * cy + t * t * y2
        pts.append((bx, by))
    return pts


def _make_gradient(w: int, h: int, color1: tuple, color2: tuple,
                   gtype: str, alpha: int) -> Image.Image:
    """Create a w×h RGBA gradient image between two RGB colors (pure PIL)."""
    if w < 1 or h < 1:
        return Image.new("RGBA", (max(1, w), max(1, h)), color1 + (alpha,))
    if gtype == "radial":
        grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cx, cy = w / 2, h / 2
        max_r = math.hypot(cx, cy)
        if max_r < 1:
            max_r = 1
        # Draw concentric ellipses from outside in
        draw = ImageDraw.Draw(grad)
        steps = max(w, h) // 2
        for i in range(steps, -1, -1):
            t = i / max(steps, 1)
            r = int(color1[0] * (1 - t) + color2[0] * t)
            g = int(color1[1] * (1 - t) + color2[1] * t)
            b = int(color1[2] * (1 - t) + color2[2] * t)
            rx = cx * t
            ry = cy * t
            if rx < 1 and ry < 1:
                continue
            draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                         fill=(r, g, b, alpha))
        return grad
    else:  # linear (top-to-bottom)
        grad = Image.new("RGBA", (1, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(grad)
        for y in range(h):
            t = y / max(h - 1, 1)
            r = int(color1[0] * (1 - t) + color2[0] * t)
            g = int(color1[1] * (1 - t) + color2[1] * t)
            b = int(color1[2] * (1 - t) + color2[2] * t)
            draw.point((0, y), fill=(r, g, b, alpha))
        return grad.resize((w, h), Image.NEAREST)


def _draw_dashed_line(draw: ImageDraw.Draw, pts: list[tuple], fill, width: int,
                      style: str = "dashed") -> None:
    """Draw a dashed or dotted line along a list of (x, y) points."""
    if style == "solid":
        draw.line(pts, fill=fill, width=width)
        return
    dash = max(8, width * 3) if style == "dashed" else max(2, width)
    gap = max(6, width * 2)
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        dx, dy = x1 - x0, y1 - y0
        seg_len = math.hypot(dx, dy)
        if seg_len < 1:
            continue
        ux, uy = dx / seg_len, dy / seg_len
        t = 0.0
        drawing = True
        while t < seg_len:
            step = dash if drawing else gap
            end_t = min(t + step, seg_len)
            if drawing:
                draw.line(
                    [(x0 + ux * t, y0 + uy * t), (x0 + ux * end_t, y0 + uy * end_t)],
                    fill=fill, width=width,
                )
            t = end_t
            drawing = not drawing


def _draw_diamond_head(draw: ImageDraw.Draw, x1, y1, x2, y2, line_width, fill):
    """Draw a diamond arrowhead at (x2, y2)."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1:
        return (x2, y2)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    head_len = max(14, line_width * 4)
    head_hw = max(6, line_width * 2)
    mid_x, mid_y = x2 - ux * head_len, y2 - uy * head_len
    back_x, back_y = x2 - ux * head_len * 2, y2 - uy * head_len * 2
    polygon = [
        (x2, y2),
        (mid_x + px * head_hw, mid_y + py * head_hw),
        (back_x, back_y),
        (mid_x - px * head_hw, mid_y - py * head_hw),
    ]
    draw.polygon(polygon, fill=fill)
    return (back_x, back_y)


def render_annotations(base: Image.Image, annotations: list[Annotation]) -> Image.Image:
    result = base.convert("RGBA")
    for ann in annotations:
        x1, y1, x2, y2 = norm(ann.x1, ann.y1, ann.x2, ann.y2)
        tools = ann.tools

        # --- Standalone shapes ---
        if Tool.ARROW in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            c = ann.color + (alpha,)
            head_style = getattr(ann, "arrow_head", "filled")
            line_style = getattr(ann, "line_style", "solid")

            if head_style == "none":
                # Plain line with arrowhead style = none
                _draw_dashed_line(draw, [(ann.x1, ann.y1), (ann.x2, ann.y2)],
                                  fill=c, width=ann.line_width, style=line_style)
            elif head_style == "open":
                head_pts, shaft_end = arrowhead(ann.x1, ann.y1, ann.x2, ann.y2, ann.line_width)
                _draw_dashed_line(draw, [(ann.x1, ann.y1), shaft_end],
                                  fill=c, width=ann.line_width, style=line_style)
                if head_pts:
                    draw.line(head_pts + [head_pts[0]], fill=c, width=max(2, ann.line_width // 2))
            elif head_style == "diamond":
                shaft_end = _draw_diamond_head(draw, ann.x1, ann.y1, ann.x2, ann.y2,
                                               ann.line_width, c)
                _draw_dashed_line(draw, [(ann.x1, ann.y1), shaft_end],
                                  fill=c, width=ann.line_width, style=line_style)
            elif head_style == "double":
                head_pts, shaft_end = arrowhead(ann.x1, ann.y1, ann.x2, ann.y2, ann.line_width)
                tail_pts, tail_end = arrowhead(ann.x2, ann.y2, ann.x1, ann.y1, ann.line_width)
                _draw_dashed_line(draw, [tail_end, shaft_end],
                                  fill=c, width=ann.line_width, style=line_style)
                if head_pts:
                    draw.polygon(head_pts, fill=c)
                if tail_pts:
                    draw.polygon(tail_pts, fill=c)
            else:  # "filled" (default)
                head_pts, shaft_end = arrowhead(ann.x1, ann.y1, ann.x2, ann.y2, ann.line_width)
                _draw_dashed_line(draw, [(ann.x1, ann.y1), shaft_end],
                                  fill=c, width=ann.line_width, style=line_style)
                if head_pts:
                    draw.polygon(head_pts, fill=c)

            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.CURVED_ARROW in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            c = ann.color + (alpha,)
            head_style = getattr(ann, "arrow_head", "filled")
            line_style = getattr(ann, "line_style", "solid")
            offset_frac = getattr(ann, "curve_offset", 0.25)
            curve_pts = _bezier_points(ann.x1, ann.y1, ann.x2, ann.y2, offset_frac)

            # Arrowhead at the tip — tangent from the last two curve points
            if head_style != "none" and len(curve_pts) >= 2:
                tx1, ty1 = curve_pts[-2]
                tx2, ty2 = curve_pts[-1]
                head_pts, shaft_end = arrowhead(tx1, ty1, tx2, ty2, ann.line_width)
                # Trim the curve so it doesn't go through the arrowhead
                curve_pts[-1] = shaft_end
            else:
                head_pts = None

            # Draw curve body
            _draw_dashed_line(draw, curve_pts, fill=c, width=ann.line_width,
                              style=line_style)

            # Draw arrowhead
            if head_pts:
                if head_style == "open":
                    draw.line(head_pts + [head_pts[0]], fill=c,
                              width=max(2, ann.line_width // 2))
                elif head_style == "diamond":
                    tx1, ty1 = curve_pts[-2] if len(curve_pts) >= 2 else (ann.x1, ann.y1)
                    _draw_diamond_head(draw, tx1, ty1, ann.x2, ann.y2,
                                       ann.line_width, c)
                else:  # "filled" or "double"
                    draw.polygon(head_pts, fill=c)

            # Double: arrowhead at tail too
            if head_style == "double" and len(curve_pts) >= 2:
                tail_pts, _ = arrowhead(curve_pts[1][0], curve_pts[1][1],
                                        curve_pts[0][0], curve_pts[0][1],
                                        ann.line_width)
                if tail_pts:
                    draw.polygon(tail_pts, fill=c)

            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.LINE in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            c = ann.color + (alpha,)
            line_style = getattr(ann, "line_style", "solid")
            _draw_dashed_line(draw, [(ann.x1, ann.y1), (ann.x2, ann.y2)],
                              fill=c, width=ann.line_width, style=line_style)
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.FREEHAND in tools:
            pts = getattr(ann, "points", [])
            if len(pts) >= 2:
                ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(ov)
                alpha = int(255 * ann.opacity)
                c = ann.color + (alpha,)
                line_style = getattr(ann, "line_style", "solid")
                if line_style == "solid":
                    draw.line(pts, fill=c, width=ann.line_width, joint="curve")
                else:
                    _draw_dashed_line(draw, pts, fill=c, width=ann.line_width,
                                      style=line_style)
                old = result
                result = Image.alpha_composite(result, ov)
                ov.close()
                if old is not result:
                    old.close()
            continue

        if Tool.RECTANGLE in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            alpha = int(255 * ann.opacity)
            gt = getattr(ann, "gradient_type", "none")
            if gt in ("linear", "radial"):
                grad = _make_gradient(x2 - x1, y2 - y1, ann.color,
                                      getattr(ann, "gradient_color2", (255, 255, 255)),
                                      gt, alpha)
                ov.paste(grad, (x1, y1))
                grad.close()
            else:
                ImageDraw.Draw(ov).rectangle(
                    [x1, y1, x2, y2],
                    fill=ann.color + (alpha,),
                )
            ImageDraw.Draw(ov).rectangle(
                [x1, y1, x2, y2], fill=None,
                outline=ann.color + (255,), width=ann.line_width,
            )
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.ELLIPSE in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            alpha = int(255 * ann.opacity)
            gt = getattr(ann, "gradient_type", "none")
            if gt in ("linear", "radial"):
                bw, bh = x2 - x1, y2 - y1
                grad = _make_gradient(bw, bh, ann.color,
                                      getattr(ann, "gradient_color2", (255, 255, 255)),
                                      gt, alpha)
                mask = Image.new("L", (bw, bh), 0)
                ImageDraw.Draw(mask).ellipse([0, 0, bw, bh], fill=255)
                ov.paste(grad, (x1, y1), mask)
                grad.close()
                mask.close()
            else:
                ImageDraw.Draw(ov).ellipse(
                    [x1, y1, x2, y2],
                    fill=ann.color + (alpha,),
                )
            ImageDraw.Draw(ov).ellipse(
                [x1, y1, x2, y2], fill=None,
                outline=ann.color + (255,), width=ann.line_width,
            )
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.ROUNDED_RECT in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            radius = max(10, min(x2 - x1, y2 - y1) // 4)
            alpha = int(255 * ann.opacity)
            gt = getattr(ann, "gradient_type", "none")
            if gt in ("linear", "radial"):
                bw, bh = x2 - x1, y2 - y1
                grad = _make_gradient(bw, bh, ann.color,
                                      getattr(ann, "gradient_color2", (255, 255, 255)),
                                      gt, alpha)
                mask = Image.new("L", (bw, bh), 0)
                ImageDraw.Draw(mask).rounded_rectangle([0, 0, bw, bh],
                                                       radius=radius, fill=255)
                ov.paste(grad, (x1, y1), mask)
                grad.close()
                mask.close()
            else:
                ImageDraw.Draw(ov).rounded_rectangle(
                    [x1, y1, x2, y2], radius=radius,
                    fill=ann.color + (alpha,),
                )
            ImageDraw.Draw(ov).rounded_rectangle(
                [x1, y1, x2, y2], radius=radius, fill=None,
                outline=ann.color + (255,), width=ann.line_width,
            )
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.CALLOUT in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            fill_c = ann.color + (alpha,)
            outline_c = ann.color + (255,)
            # Box body
            draw.rounded_rectangle(
                [x1, y1, x2, y2], radius=max(8, min(x2 - x1, y2 - y1) // 8),
                fill=fill_c, outline=outline_c, width=ann.line_width,
            )
            # Triangular tail
            tx, ty = getattr(ann, "tail_x", 0), getattr(ann, "tail_y", 0)
            if tx == 0 and ty == 0:
                # Default: tail hanging below center
                tx = (x1 + x2) // 2
                ty = y2 + (y2 - y1) // 3
            cx = (x1 + x2) // 2
            tail_hw = max(8, (x2 - x1) // 8)
            # Tail base points on the box edge
            b1 = (max(x1, cx - tail_hw), y2)
            b2 = (min(x2, cx + tail_hw), y2)
            draw.polygon([b1, (tx, ty), b2], fill=fill_c, outline=outline_c,
                         width=ann.line_width)
            # Cover the seam between box and tail
            draw.rectangle([b1[0] + 1, y2 - ann.line_width, b2[0] - 1, y2 + 1],
                           fill=fill_c)
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.BRACKET in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            c = ann.color + (alpha,)
            style = getattr(ann, "bracket_style", "curly")
            lw = ann.line_width
            h = y2 - y1
            w = x2 - x1
            vertical = abs(h) >= abs(w)  # orientation heuristic
            if style == "square":
                if vertical:
                    # Square bracket facing right: top hook, vertical bar, bottom hook
                    hook = max(8, abs(w) // 2, 12)
                    draw.line([(x1 + hook, y1), (x1, y1), (x1, y2), (x1 + hook, y2)],
                              fill=c, width=lw, joint="miter")
                else:
                    hook = max(8, abs(h) // 2, 12)
                    draw.line([(x1, y1 + hook), (x1, y1), (x2, y1), (x2, y1 + hook)],
                              fill=c, width=lw, joint="miter")
            else:  # curly brace — draw a proper } shape
                if vertical:
                    mid_y = (y1 + y2) // 2
                    bow = max(12, abs(w) // 2, 18)
                    # } shape: top hook → mid tip → bottom hook
                    # Use 4 cubic beziers for smooth brace
                    qtr = (y2 - y1) // 4
                    pts = []
                    # Top hook: from (x1, y1) curve right then down
                    for t_i in range(21):
                        t = t_i / 20
                        u = 1 - t
                        px = u**3*x1 + 3*u**2*t*(x1+bow*0.5) + 3*u*t**2*(x1+bow*0.1) + t**3*x1
                        py = u**3*y1 + 3*u**2*t*y1 + 3*u*t**2*(y1+qtr) + t**3*(mid_y-lw)
                        pts.append((int(px), int(py)))
                    # Mid tip: jut out to the right
                    for t_i in range(21):
                        t = t_i / 20
                        u = 1 - t
                        px = u**3*x1 + 3*u**2*t*(x1+bow*0.3) + 3*u*t**2*(x1+bow) + t**3*(x1+bow)
                        py = u**3*(mid_y-lw) + 3*u**2*t*(mid_y-lw*0.5) + 3*u*t**2*(mid_y) + t**3*mid_y
                        pts.append((int(px), int(py)))
                    for t_i in range(21):
                        t = t_i / 20
                        u = 1 - t
                        px = u**3*(x1+bow) + 3*u**2*t*(x1+bow) + 3*u*t**2*(x1+bow*0.3) + t**3*x1
                        py = u**3*mid_y + 3*u**2*t*(mid_y) + 3*u*t**2*(mid_y+lw*0.5) + t**3*(mid_y+lw)
                        pts.append((int(px), int(py)))
                    # Bottom hook: from mid down then curve right
                    for t_i in range(21):
                        t = t_i / 20
                        u = 1 - t
                        px = u**3*x1 + 3*u**2*t*(x1+bow*0.1) + 3*u*t**2*(x1+bow*0.5) + t**3*x1
                        py = u**3*(mid_y+lw) + 3*u**2*t*(y2-qtr) + 3*u*t**2*y2 + t**3*y2
                        pts.append((int(px), int(py)))
                    _draw_dashed_line(draw, pts, fill=c, width=lw, style="solid")
                else:
                    mid_x = (x1 + x2) // 2
                    bow = max(12, abs(h) // 2, 18)
                    qtr = (x2 - x1) // 4
                    pts = []
                    # Left hook
                    for t_i in range(21):
                        t = t_i / 20
                        u = 1 - t
                        px = u**3*x1 + 3*u**2*t*x1 + 3*u*t**2*(x1+qtr) + t**3*(mid_x-lw)
                        py = u**3*y1 + 3*u**2*t*(y1+bow*0.5) + 3*u*t**2*(y1+bow*0.1) + t**3*y1
                        pts.append((int(px), int(py)))
                    # Mid tip downward
                    for t_i in range(21):
                        t = t_i / 20
                        u = 1 - t
                        px = u**3*(mid_x-lw) + 3*u**2*t*(mid_x-lw*0.5) + 3*u*t**2*mid_x + t**3*mid_x
                        py = u**3*y1 + 3*u**2*t*(y1+bow*0.3) + 3*u*t**2*(y1+bow) + t**3*(y1+bow)
                        pts.append((int(px), int(py)))
                    for t_i in range(21):
                        t = t_i / 20
                        u = 1 - t
                        px = u**3*mid_x + 3*u**2*t*(mid_x) + 3*u*t**2*(mid_x+lw*0.5) + t**3*(mid_x+lw)
                        py = u**3*(y1+bow) + 3*u**2*t*(y1+bow) + 3*u*t**2*(y1+bow*0.3) + t**3*y1
                        pts.append((int(px), int(py)))
                    # Right hook
                    for t_i in range(21):
                        t = t_i / 20
                        u = 1 - t
                        px = u**3*(mid_x+lw) + 3*u**2*t*(x2-qtr) + 3*u*t**2*x2 + t**3*x2
                        py = u**3*y1 + 3*u**2*t*(y1+bow*0.1) + 3*u*t**2*(y1+bow*0.5) + t**3*y1
                        pts.append((int(px), int(py)))
                    _draw_dashed_line(draw, pts, fill=c, width=lw, style="solid")
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.STAR in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            fill_c = ann.color + (alpha,)
            outline_c = ann.color + (255,)
            n = max(3, getattr(ann, "polygon_sides", 5))
            inner_ratio = max(0.1, min(0.95, getattr(ann, "star_inner_ratio", 0.45)))
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            rx, ry = (x2 - x1) / 2, (y2 - y1) / 2
            pts = []
            for i in range(n * 2):
                angle = math.pi * i / n - math.pi / 2
                r_frac = 1.0 if i % 2 == 0 else inner_ratio
                pts.append((cx + rx * r_frac * math.cos(angle),
                            cy + ry * r_frac * math.sin(angle)))
            draw.polygon(pts, fill=fill_c, outline=outline_c, width=ann.line_width)
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.DIAMOND in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            fill_c = ann.color + (alpha,)
            outline_c = ann.color + (255,)
            gt = getattr(ann, "gradient_type", "none")
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            diamond_pts = [(cx, y1), (x2, cy), (cx, y2), (x1, cy)]
            if gt in ("linear", "radial"):
                bw, bh = x2 - x1, y2 - y1
                grad = _make_gradient(bw, bh, ann.color,
                                      getattr(ann, "gradient_color2", (255, 255, 255)),
                                      gt, alpha)
                mask = Image.new("L", (bw, bh), 0)
                ImageDraw.Draw(mask).polygon(
                    [(cx - x1, 0), (bw, cy - y1), (cx - x1, bh), (0, cy - y1)],
                    fill=255)
                ov.paste(grad, (x1, y1), mask)
                grad.close()
                mask.close()
            else:
                draw.polygon(diamond_pts, fill=fill_c)
            draw.polygon(diamond_pts, fill=None, outline=outline_c,
                         width=ann.line_width)
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        if Tool.CONNECTOR in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            c = ann.color + (alpha,)
            line_style = getattr(ann, "line_style", "solid")
            cstyle = getattr(ann, "connector_style", "straight")
            if cstyle == "elbow":
                mid_x = ann.x2
                pts = [(ann.x1, ann.y1), (mid_x, ann.y1), (mid_x, ann.y2)]
                _draw_dashed_line(draw, pts, fill=c, width=ann.line_width,
                                  style=line_style)
            else:
                _draw_dashed_line(draw, [(ann.x1, ann.y1), (ann.x2, ann.y2)],
                                  fill=c, width=ann.line_width, style=line_style)
            # Small dots at endpoints
            dot_r = max(3, ann.line_width)
            for dx, dy in [(ann.x1, ann.y1), (ann.x2, ann.y2)]:
                draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r],
                             fill=c)
            old = result
            result = Image.alpha_composite(result, ov)
            ov.close()
            if old is not result:
                old.close()
            continue

        # --- Gradient fill support for RECTANGLE / ELLIPSE / ROUNDED_RECT ---
        # (handled above with plain fill; gradient is applied via
        #  a separate post-process if gradient_type != "none")

        # --- Image overlay ---
        if Tool.IMAGE in tools:
            if ann.image_data is not None:
                img_overlay = ann.image_data.convert("RGBA")
                bw = max(1, x2 - x1)
                bh = max(1, y2 - y1)
                img_overlay = img_overlay.resize((bw, bh), Image.LANCZOS)
                # Apply opacity
                alpha = int(255 * ann.opacity)
                if alpha < 255:
                    r, g, b, a = img_overlay.split()
                    a = a.point(lambda p: int(p * ann.opacity))
                    img_overlay = Image.merge("RGBA", (r, g, b, a))
                ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
                ov.paste(img_overlay, (x1, y1), img_overlay)
                img_overlay.close()
                old = result
                result = Image.alpha_composite(result, ov)
                ov.close()
                if old is not result:
                    old.close()
            continue

        # --- Text annotation (2x supersampled for crisp text) ---
        if Tool.TEXT in tools:
            if ann.text:
                SS = 2  # supersample factor
                region_w = max(1, x2 - x1)
                region_h = max(1, y2 - y1)
                ss_w, ss_h = region_w * SS, region_h * SS

                # Create supersampled region overlay
                ss_img = Image.new("RGBA", (ss_w, ss_h), (0, 0, 0, 0))
                ss_draw = ImageDraw.Draw(ss_img)
                alpha = int(255 * ann.opacity)
                text_alpha = 255  # text is always fully opaque

                # Draw background rectangle at supersampled size
                if ann.bg_color is not None:
                    bg_fill = ann.bg_color + (alpha,)
                    ss_draw.rectangle([0, 0, ss_w, ss_h], fill=bg_fill)

                # Render text at 2x scale
                if ann.text_runs:
                    scaled_runs = [
                        _dc_replace(run, font_size=run.font_size * SS)
                        for run in ann.text_runs
                    ]
                    _render_text_runs(ss_draw, scaled_runs, 0, 0, ss_w,
                                      text_alpha, ann.color,
                                      line_spacing=ann.line_spacing)
                else:
                    font = _resolve_font(ann.font_family, ann.font_size * SS,
                                         ann.font_bold, ann.font_italic)
                    fc = ann.font_color if ann.font_color else ann.color
                    fill = fc + (text_alpha,)
                    ss_draw.multiline_text((0, 0), ann.text, font=font, fill=fill)

                # Downscale with LANCZOS for smooth antialiasing
                downscaled = ss_img.resize((region_w, region_h), Image.LANCZOS)
                ss_img.close()

                # Place into full-size overlay and composite
                ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
                ov.paste(downscaled, (x1, y1), downscaled)
                downscaled.close()
                old = result
                result = Image.alpha_composite(result, ov)
                ov.close()
                if old is not result:
                    old.close()
            continue

        # --- Composable region effects (Lift / Highlight / Underline / Border) ---
        has_lift = Tool.TEXT_LIFT in tools
        has_highlight = Tool.HIGHLIGHT in tools
        has_underline = Tool.UNDERLINE in tools
        has_border = Tool.BORDER in tools

        # 1) Lift: shadow + zoom + backing + paste content
        if has_lift:
            cx1 = max(0, x1)
            cy1 = max(0, y1)
            cx2 = min(result.width, x2)
            cy2 = min(result.height, y2)
            if cx2 <= cx1 or cy2 <= cy1:
                continue
            content = result.crop((cx1, cy1, cx2, cy2))
            zf = ann.lift_zoom
            if zf > 1.0:
                zw, zh = int(content.width * zf), int(content.height * zf)
                zoomed = content.resize((zw, zh), Image.LANCZOS)
                dx, dy = (zw - content.width) // 2, (zh - content.height) // 2
                content = zoomed.crop((dx, dy, dx + (cx2 - cx1), dy + (cy2 - cy1)))
            off = 8
            shadow = Image.new("RGBA", result.size, (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rectangle(
                [cx1 + off, cy1 + off, cx2 + off, cy2 + off], fill=(0, 0, 0, 100)
            )
            shadow = shadow.filter(ImageFilter.GaussianBlur(6))
            result = Image.alpha_composite(result, shadow)

            if has_highlight:
                backing = Image.new("RGBA", result.size, (0, 0, 0, 0))
                tint = ann.color + (int(255 * ann.opacity),)
                ImageDraw.Draw(backing).rectangle([cx1, cy1, cx2, cy2], fill=tint)
                result = Image.alpha_composite(result, backing)
                content_rgba = content.convert("RGBA")
                tint_layer = Image.new("RGBA", content_rgba.size, ann.color + (255,))
                blended = Image.blend(
                    Image.new("RGBA", content_rgba.size, (255, 255, 255, 255)),
                    tint_layer, ann.opacity)
                content = ImageChops.multiply(content_rgba, blended)
            else:
                backing = Image.new("RGBA", result.size, (0, 0, 0, 0))
                ImageDraw.Draw(backing).rectangle([cx1, cy1, cx2, cy2], fill=(255, 255, 255, 255))
                result = Image.alpha_composite(result, backing)

            result.paste(content, (cx1, cy1))
            border_ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            ImageDraw.Draw(border_ov).rectangle(
                [cx1, cy1, cx2, cy2], outline=ann.color + (180,), width=2
            )
            result = Image.alpha_composite(result, border_ov)

        else:
            # 2) Highlight (without lift): multiply blend
            if has_highlight:
                highlight = Image.new("RGBA", result.size, (255, 255, 255, 255))
                ImageDraw.Draw(highlight).rectangle(
                    [x1, y1, x2, y2], fill=ann.color + (255,)
                )
                blended = Image.blend(
                    Image.new("RGBA", result.size, (255, 255, 255, 255)),
                    highlight,
                    ann.opacity,
                )
                result = ImageChops.multiply(result, blended)

        # 3) Underline
        if has_underline:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            y = max(y1, y2)
            alpha = int(255 * ann.opacity)
            ImageDraw.Draw(ov).line(
                [(x1, y), (x2, y)], fill=ann.color + (alpha,), width=ann.line_width
            )
            result = Image.alpha_composite(result, ov)

        # 4) Border
        if has_border and not has_lift:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            alpha = int(255 * ann.opacity)
            ImageDraw.Draw(ov).rectangle(
                [x1, y1, x2, y2], outline=ann.color + (alpha,), width=ann.line_width
            )
            result = Image.alpha_composite(result, ov)
        elif has_border and has_lift:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            alpha = int(255 * ann.opacity)
            ImageDraw.Draw(ov).rectangle(
                [x1, y1, x2, y2], outline=ann.color + (alpha,), width=ann.line_width
            )
            result = Image.alpha_composite(result, ov)

    return result


def apply_watermark(
    img: Image.Image,
    text: str,
    color: tuple,
    opacity: float = 0.6,
    position: str = "center",
    orientation: str = "diagonal",
    scale_pct: float = 100.0,
) -> Image.Image:
    if not text:
        return img
    w, h = img.size
    angle = {"diagonal": 45, "horizontal": 0, "vertical": 90}.get(orientation.lower(), 45)
    diag = math.hypot(w, h)
    size = max(12, int(diag * 0.25 * (scale_pct / 100.0)))
    try:
        font = _resolve_font("Arial", size, False, False)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except IOError:
            font = ImageFont.load_default()

    fill = color + (int(255 * opacity),)
    tmp_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def _make_stamp(fnt):
        bbox = tmp_draw.textbbox((0, 0), text, font=fnt)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        stamp = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ImageDraw.Draw(stamp).text((-bbox[0], -bbox[1]), text, font=fnt, fill=fill)
        return stamp.rotate(angle, expand=True) if angle else stamp

    rot = _make_stamp(font)
    rw, rh = rot.size
    fit_scale = min(w / rw, h / rh) * 0.9
    if fit_scale < 1:
        final = max(10, int(size * fit_scale))
        try:
            font = ImageFont.truetype("arial.ttf", final)
        except IOError:
            font = ImageFont.load_default()
        rot = _make_stamp(font)
        rw, rh = rot.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pos = position.lower()
    margin = int(min(w, h) * 0.02)
    if pos == "tiled":
        gap_x, gap_y = rw + margin * 4, rh + margin * 4
        for ty in range(-rh, h + rh, gap_y):
            for tx in range(-rw, w + rw, gap_x):
                overlay.paste(rot, (tx, ty), rot)
    else:
        coords = {
            "center": ((w - rw) // 2, (h - rh) // 2),
            "top-left": (margin, margin),
            "top-center": ((w - rw) // 2, margin),
            "top-right": (w - rw - margin, margin),
            "left-center": (margin, (h - rh) // 2),
            "right-center": (w - rw - margin, (h - rh) // 2),
            "bottom-left": (margin, h - rh - margin),
            "bottom-center": ((w - rw) // 2, h - rh - margin),
            "bottom-right": (w - rw - margin, h - rh - margin),
        }
        cx, cy = coords.get(pos, coords["center"])
        overlay.paste(rot, (cx, cy), rot)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def merge_images(
    images: list[Image.Image],
    lang: str,
    wm_on: bool,
    wm_text: str,
    wm_color: tuple,
    wm_opacity: float = 0.6,
    wm_position: str = "center",
    wm_orientation: str = "diagonal",
    wm_scale: float = 100.0,
) -> Image.Image:
    if lang.lower() == "ar":
        images = list(reversed(images))
    total_w = sum(im.width for im in images)
    max_h = max(im.height for im in images)
    merged = Image.new("RGB", (total_w, max_h), "white")
    x = 0
    for im in images:
        merged.paste(im, (x, 0))
        x += im.width
    if wm_on and wm_text:
        merged = apply_watermark(
            merged, wm_text, wm_color,
            opacity=wm_opacity, position=wm_position,
            orientation=wm_orientation, scale_pct=wm_scale,
        )
    return merged
