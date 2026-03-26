"""Rendering — PDF to images, annotation compositing, watermark, merge."""

import math

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
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    images: list[Image.Image] = []
    for page_num in pages:
        idx = page_num - 1
        if idx < 0 or idx >= len(doc):
            continue
        pix = doc[idx].get_pixmap(matrix=mat, alpha=False)
        images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    doc.close()
    return images


def render_annotations(base: Image.Image, annotations: list[Annotation]) -> Image.Image:
    result = base.convert("RGBA")
    for ann in annotations:
        x1, y1, x2, y2 = norm(ann.x1, ann.y1, ann.x2, ann.y2)
        tools = ann.tools

        # --- Standalone shapes (Arrow / Rectangle / Ellipse) ---
        if Tool.ARROW in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov)
            alpha = int(255 * ann.opacity)
            c = ann.color + (alpha,)
            head_pts, shaft_end = arrowhead(ann.x1, ann.y1, ann.x2, ann.y2, ann.line_width)
            draw.line([(ann.x1, ann.y1), shaft_end], fill=c, width=ann.line_width)
            if head_pts:
                draw.polygon(head_pts, fill=c)
            result = Image.alpha_composite(result, ov)
            continue

        if Tool.RECTANGLE in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            ImageDraw.Draw(ov).rectangle(
                [x1, y1, x2, y2],
                fill=ann.color + (int(255 * ann.opacity),),
                outline=ann.color + (255,),
                width=ann.line_width,
            )
            result = Image.alpha_composite(result, ov)
            continue

        if Tool.ELLIPSE in tools:
            ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
            ImageDraw.Draw(ov).ellipse(
                [x1, y1, x2, y2],
                fill=ann.color + (int(255 * ann.opacity),),
                outline=ann.color + (255,),
                width=ann.line_width,
            )
            result = Image.alpha_composite(result, ov)
            continue

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
                result = Image.alpha_composite(result, ov)
            continue

        # --- Text annotation ---
        if Tool.TEXT in tools:
            if ann.text:
                ov = Image.new("RGBA", result.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(ov)
                alpha = int(255 * ann.opacity)
                # Text always renders at full opacity; alpha only applies to background
                text_alpha = 255 if ann.bg_color is None else alpha
                # Draw background rectangle if bg_color is set
                if ann.bg_color is not None:
                    bg_fill = ann.bg_color + (alpha,)
                    draw.rectangle([x1, y1, x2, y2], fill=bg_fill)
                # Rich text: render each run with its own font
                if ann.text_runs:
                    _render_text_runs(draw, ann.text_runs, x1, y1, x2, text_alpha, ann.color,
                                      line_spacing=ann.line_spacing)
                else:
                    # Fallback: single-format rendering
                    font = _resolve_font(ann.font_family, ann.font_size,
                                         ann.font_bold, ann.font_italic)
                    fc = ann.font_color if ann.font_color else ann.color
                    fill = fc + (text_alpha,)
                    draw.multiline_text((x1, y1), ann.text, font=font, fill=fill)
                result = Image.alpha_composite(result, ov)
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


def apply_watermark(img: Image.Image, text: str, color: tuple, opacity: float = 0.6) -> Image.Image:
    if not text:
        return img
    w, h = img.size
    diag = math.hypot(w, h)
    size = max(12, int(diag * 0.25))
    try:
        font = ImageFont.truetype("arial.ttf", size)
    except IOError:
        font = ImageFont.load_default()

    tmp_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = tmp_draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    txt_img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(txt_img).text((-bbox[0], -bbox[1]), text, font=font, fill=color + (int(255 * opacity),))
    rot = txt_img.rotate(45, expand=True)
    rw, rh = rot.size
    scale = min(w / rw, h / rh) * 0.9
    if scale < 1:
        final = max(10, int(size * scale))
        try:
            font = ImageFont.truetype("arial.ttf", final)
        except IOError:
            font = ImageFont.load_default()
        bbox = tmp_draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        txt_img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ImageDraw.Draw(txt_img).text((-bbox[0], -bbox[1]), text, font=font, fill=color + (int(255 * opacity),))
        rot = txt_img.rotate(45, expand=True)
        rw, rh = rot.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    overlay.paste(rot, ((w - rw) // 2, (h - rh) // 2), rot)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def merge_images(images: list[Image.Image], lang: str, wm_on: bool, wm_text: str, wm_color: tuple) -> Image.Image:
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
        merged = apply_watermark(merged, wm_text, wm_color)
    return merged
