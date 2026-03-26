"""AnnotationCanvas — interactive drawing widget on a page image."""

import math
import sys
from dataclasses import replace as dc_replace
from tkinter import Canvas, Scrollbar, simpledialog

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from .models import Annotation, TextRun, Tool
from .rendering import render_annotations
from .utils import ruler_step


class AnnotationCanvas(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)

        self.base_image: Image.Image | None = None
        self.annotations: list[Annotation] = []
        self._undo_stack: list[list[Annotation]] = []
        self._redo_stack: list[list[Annotation]] = []

        self.current_effects: set[Tool] = {Tool.HIGHLIGHT}  # toggleable effects
        self.current_shape: Tool | None = None               # exclusive shape or None
        self.current_color: tuple = (255, 255, 0)
        self.current_opacity: float = 0.4
        self.current_width: int = 3
        self.current_lift_zoom: float = 1.08
        self.scale: float = 1.0

        # Image overlay state
        self.pending_image: Image.Image | None = None   # image waiting to be placed

        # Text annotation state
        self.current_font_family: str = "Arial"
        self.current_font_size: int = 24
        self.current_font_bold: bool = False
        self.current_font_italic: bool = False
        self.current_font_color: tuple = (0, 0, 0)
        self.current_text_bg: tuple | None = (255, 255, 255)  # None = transparent
        self.current_line_spacing: float = 1.2  # line-height multiplier

        # Inline text editor state
        self._text_editor = None          # the tk Text widget
        self._text_editor_win = None      # canvas window item id (solid bg mode)
        self._text_editor_border = None   # canvas rect for visible border
        self._text_editor_toplevel = None # Toplevel window (transparent mode)
        self._text_box_img_coords = None  # (x1, y1, x2, y2) in image coords
        self._editing_annotation_idx = None  # index into self.annotations being re-edited

        self._drag_start = None
        self._preview_id = None
        self._photo = None
        self._render_cache: Image.Image | None = None  # full-res rendered
        self._cache_dirty = True
        self.on_zoom_changed = None  # callback(scale) for external UI
        self.on_text_edit_start = None  # callback() when re-editing existing text

        # Right-click drag-to-move / resize state
        self._moving_annotation_idx: int | None = None
        self._move_start_img: tuple | None = None  # (ix, iy) at drag start
        self._resize_handle: str | None = None  # e.g. "nw", "ne", "se", "sw", "n", "s", "e", "w"

        # Selection state (click an image to select it)
        self._selected_annotation_idx: int | None = None
        self._march_offset: int = 0
        self._march_after_id = None

        # Measure / ruler overlay (old line-based)
        self._measure_mode = False
        self._measure_start = None      # (ix, iy) during drag
        self._measure_pts = None        # (sx, sy, ex, ey) persisted img coords
        self._measure_items: list = []  # canvas item IDs
        self.on_measure_update = None   # callback(data_dict | None)

        # Floating ruler overlay (Windows Snip & Sketch style)
        self._ruler_visible = False
        self._ruler_angle = 0.0         # degrees
        self._ruler_cx = 300.0          # center x (canvas coords)
        self._ruler_cy = 200.0          # center y (canvas coords)
        self._ruler_length = 700        # computed dynamically to fill the canvas
        self._ruler_width = 70          # total width in screen pixels
        self._ruler_dragging = False
        self._ruler_drag_offset = (0, 0)
        self._ruler_redraw_pending = False

        # Ruler dimensions
        self._ruler_size = 22

        # Rulers (Tkinter Canvases)
        self._ruler_colors = ("#2d2d2d", "#808080", "#606060")  # bg, fg text, tick
        self.h_ruler = Canvas(self, height=self._ruler_size, bg=self._ruler_colors[0],
                              highlightthickness=0, bd=0)
        self.v_ruler = Canvas(self, width=self._ruler_size, bg=self._ruler_colors[0],
                              highlightthickness=0, bd=0)
        self._ruler_corner = Canvas(self, width=self._ruler_size, height=self._ruler_size,
                                    bg=self._ruler_colors[0], highlightthickness=0, bd=0)

        # Canvas + scrollbars
        self.canvas = Canvas(self, bg="#1a1a1a", highlightthickness=0, cursor="crosshair", takefocus=True)
        self.v_scroll = Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.h_scroll = Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self._h_scroll_set, yscrollcommand=self._v_scroll_set)

        self._ruler_corner.grid(row=0, column=0, sticky="nsew")
        self.h_ruler.grid(row=0, column=1, sticky="ew")
        self.v_ruler.grid(row=1, column=0, sticky="ns")
        self.canvas.grid(row=1, column=1, sticky="nsew")
        self.v_scroll.grid(row=1, column=2, sticky="ns")
        self.h_scroll.grid(row=2, column=1, sticky="ew")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-3>", self._on_right_press)
        self.canvas.bind("<B3-Motion>", self._on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Delete>", self._on_delete_key)
        self.canvas.bind("<KeyPress-Escape>", self._on_escape_key)
        # macOS / Linux X11 scroll events
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)
        # macOS: two-finger tap = Button-2, and BackSpace = Delete key
        self.canvas.bind("<ButtonPress-2>", self._on_right_press)
        self.canvas.bind("<B2-Motion>", self._on_right_drag)
        self.canvas.bind("<ButtonRelease-2>", self._on_right_release)
        self.canvas.bind("<BackSpace>", self._on_delete_key)
        # macOS: Control+Click as right-click
        self.canvas.bind("<Control-ButtonPress-1>", self._on_right_press)
        self.canvas.bind("<Control-B1-Motion>", self._on_right_drag)
        self.canvas.bind("<Control-ButtonRelease-1>", self._on_right_release)

        self._img_offset = (0, 0)  # (ox, oy) pixel offset for centering
        self._auto_fit = True  # when True, zoom tracks window size

    # -- public API -------------------------------------------------

    def set_image(self, img: Image.Image):
        self.base_image = img
        self.annotations.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._invalidate()

    def load_state(self, img, annotations, undo, redo):
        self._commit_text_editor()
        self.base_image = img
        self.annotations = annotations
        self._undo_stack = undo
        self._redo_stack = redo
        self._invalidate()

    def set_scale(self, s: float):
        self._commit_text_editor()
        self._auto_fit = False
        self.scale = max(0.1, min(5.0, s))
        self._display()
        self._notify_zoom()

    def fit_to_frame(self):
        if not self.base_image:
            return
        self._auto_fit = True
        self._do_fit()

    def _do_fit(self):
        """Recalculate scale to fit the canvas, called on resize too."""
        if not self.base_image:
            return
        self.update_idletasks()
        cw = self.canvas.winfo_width() or 800
        ch = self.canvas.winfo_height() or 600
        iw, ih = self.base_image.size
        self.scale = max(0.05, min(cw / iw, ch / ih))
        self._display()
        self._notify_zoom()

    def _notify_zoom(self):
        if self.on_zoom_changed:
            self.on_zoom_changed(self.scale)

    def _invalidate(self):
        self._cache_dirty = True
        self._refresh()

    def undo(self):
        if self._undo_stack:
            self._redo_stack.append(list(self.annotations))
            self.annotations = self._undo_stack.pop()
            self._invalidate()

    def redo(self):
        if self._redo_stack:
            self._undo_stack.append(list(self.annotations))
            self.annotations = self._redo_stack.pop()
            self._invalidate()

    def clear_all(self):
        self._dismiss_text_editor()
        if self.annotations:
            self._undo_stack.append(list(self.annotations))
            self._redo_stack.clear()
            self.annotations.clear()
            self._invalidate()

    def get_rendered(self) -> Image.Image | None:
        if not self.base_image:
            return None
        return render_annotations(self.base_image, self.annotations).convert("RGB")

    # -- coordinate helpers -----------------------------------------

    def _to_img(self, ex, ey):
        ox, oy = self._img_offset
        cx = self.canvas.canvasx(ex) - ox
        cy = self.canvas.canvasy(ey) - oy
        return int(cx / self.scale), int(cy / self.scale)

    # -- display ----------------------------------------------------

    def _refresh(self):
        """Full re-render (annotations changed)."""
        if not self.base_image:
            self.canvas.delete("all")
            self._render_cache = None
            return
        self._render_cache = render_annotations(self.base_image, self.annotations)
        self._cache_dirty = False
        self._display()

    def _display(self):
        """Fast rescale of cached render to current zoom, centered in canvas."""
        if self._cache_dirty or self._render_cache is None:
            self._refresh()
            return
        rc = self._render_cache
        dw = max(1, int(rc.width * self.scale))
        dh = max(1, int(rc.height * self.scale))
        display = rc.convert("RGB").resize((dw, dh), Image.BILINEAR)
        self._photo = ImageTk.PhotoImage(display)

        cw = self.canvas.winfo_width() or dw
        ch = self.canvas.winfo_height() or dh
        ox = max(0, (cw - dw) // 2)
        oy = max(0, (ch - dh) // 2)
        self._img_offset = (ox, oy)

        total_w = max(cw, dw + ox * 2)
        total_h = max(ch, dh + oy * 2)

        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, anchor="nw", image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))
        self._draw_rulers()
        self._redraw_measure()
        if self._ruler_visible:
            self._draw_floating_ruler()
        self._draw_selection_border()
        # Re-place the inline text editor after canvas refresh
        self._reposition_text_editor()

    # -- ruler drawing ----------------------------------------------

    def _h_scroll_set(self, lo, hi):
        """Scroll wrapper that updates the horizontal scrollbar and redraws rulers."""
        self.h_scroll.set(lo, hi)
        self._draw_rulers()

    def _v_scroll_set(self, lo, hi):
        """Scroll wrapper that updates the vertical scrollbar and redraws rulers."""
        self.v_scroll.set(lo, hi)
        self._draw_rulers()

    def _draw_rulers(self):
        self._draw_h_ruler()
        self._draw_v_ruler()

    def _draw_h_ruler(self):
        ruler = self.h_ruler
        ruler.delete("all")
        w = ruler.winfo_width()
        if w < 2 or not self.base_image:
            return
        bg, fg, tick = self._ruler_colors
        ox, _ = self._img_offset
        x0_canvas = self.canvas.canvasx(0)
        scale = self.scale
        step = ruler_step(scale)
        img_x_start = (x0_canvas - ox) / scale
        first = int(img_x_start // step) * step
        x = first
        iw = self.base_image.width
        while True:
            cx = (x * scale + ox) - x0_canvas
            if cx > w:
                break
            if 0 <= x <= iw and cx >= 0:
                is_major = (x % (step * 5) == 0) if step else True
                h = self._ruler_size if is_major else self._ruler_size // 2
                ruler.create_line(cx, self._ruler_size, cx, self._ruler_size - h,
                                  fill=tick if not is_major else fg)
                if is_major:
                    ruler.create_text(cx + 2, 2, anchor="nw", text=str(int(x)),
                                      fill=fg, font=("Segoe UI", 7))
            x += step
            if x > iw + step:
                break

    def _draw_v_ruler(self):
        ruler = self.v_ruler
        ruler.delete("all")
        h = ruler.winfo_height()
        if h < 2 or not self.base_image:
            return
        bg, fg, tick = self._ruler_colors
        _, oy = self._img_offset
        y0_canvas = self.canvas.canvasy(0)
        scale = self.scale
        step = ruler_step(scale)
        img_y_start = (y0_canvas - oy) / scale
        first = int(img_y_start // step) * step
        y = first
        ih = self.base_image.height
        while True:
            cy = (y * scale + oy) - y0_canvas
            if cy > h:
                break
            if 0 <= y <= ih and cy >= 0:
                is_major = (y % (step * 5) == 0) if step else True
                w_tick = self._ruler_size if is_major else self._ruler_size // 2
                ruler.create_line(self._ruler_size, cy, self._ruler_size - w_tick, cy,
                                  fill=tick if not is_major else fg)
                if is_major:
                    ruler.create_text(2, cy + 2, anchor="nw", text=str(int(y)),
                                      fill=fg, font=("Segoe UI", 7))
            y += step
            if y > ih + step:
                break

    def _on_canvas_resize(self, e):
        if self._auto_fit and self.base_image:
            self._do_fit()
        if self._ruler_visible:
            cw = self.canvas.winfo_width() or 800
            ch = self.canvas.winfo_height() or 600
            self._ruler_length = max(cw, ch) + 200
            self._draw_floating_ruler()

    # -- measure overlay --------------------------------------------

    def set_measure_mode(self, active: bool):
        self._measure_mode = active
        self.canvas.configure(cursor="tcross" if active else "crosshair")
        if not active:
            self._clear_measure()

    def _clear_measure(self):
        for i in self._measure_items:
            self.canvas.delete(i)
        self._measure_items.clear()
        self._measure_pts = None
        self._measure_start = None
        if self.on_measure_update:
            self.on_measure_update(None)

    def _redraw_measure(self):
        """Redraw persisted measurement after zoom/scroll."""
        for i in self._measure_items:
            self.canvas.delete(i)
        self._measure_items.clear()
        if self._measure_pts:
            self._draw_measure_line(*self._measure_pts)

    def _draw_measure_line(self, sx, sy, ex, ey):
        """Draw measurement overlay given image coordinates."""
        ox, oy = self._img_offset
        s = self.scale
        cx1, cy1 = sx * s + ox, sy * s + oy
        cx2, cy2 = ex * s + ox, ey * s + oy
        add = self._measure_items.append

        # Dashed measurement line
        add(self.canvas.create_line(cx1, cy1, cx2, cy2,
                                    fill="#ff4444", width=2, dash=(6, 3)))
        # Endpoint markers
        r = 5
        for cx, cy in [(cx1, cy1), (cx2, cy2)]:
            add(self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        fill="#ff4444", outline="white", width=1))

        # Distance computation
        dx, dy = abs(ex - sx), abs(ey - sy)
        dist = math.hypot(dx, dy)

        # Label at midpoint with background
        mid_x, mid_y = (cx1 + cx2) / 2, (cy1 + cy2) / 2
        label = f"{dist:.1f} px"
        font = ("Segoe UI", 9, "bold")
        tmp = self.canvas.create_text(0, 0, text=label, font=font)
        bb = self.canvas.bbox(tmp)
        self.canvas.delete(tmp)
        tw = (bb[2] - bb[0]) if bb else 50
        th = (bb[3] - bb[1]) if bb else 14
        pad = 4
        add(self.canvas.create_rectangle(
            mid_x - tw // 2 - pad, mid_y - 16 - th // 2 - pad,
            mid_x + tw // 2 + pad, mid_y - 16 + th // 2 + pad,
            fill="#1e1e1e", outline="#ff4444", width=1, stipple=""))
        add(self.canvas.create_text(mid_x, mid_y - 16, text=label,
                                    fill="#ff4444", font=font))

        # Tick marks along the line
        line_len_screen = math.hypot(cx2 - cx1, cy2 - cy1)
        if line_len_screen > 20:
            tick_step = ruler_step(s)
            line_len_img = math.hypot(ex - sx, ey - sy)
            if line_len_img > 0:
                ux, uy = (ex - sx) / line_len_img, (ey - sy) / line_len_img
                px, py = -uy, ux
                t = tick_step
                while t < line_len_img:
                    frac = t / line_len_img
                    tx = cx1 + (cx2 - cx1) * frac
                    ty = cy1 + (cy2 - cy1) * frac
                    is_major = (int(t) % (tick_step * 5) == 0) if tick_step else True
                    tl = 6 if is_major else 3
                    add(self.canvas.create_line(
                        tx - px * tl, ty - py * tl,
                        tx + px * tl, ty + py * tl,
                        fill="#ff4444", width=1))
                    t += tick_step

        data = {'start': (sx, sy), 'end': (ex, ey), 'dist': dist, 'dx': dx, 'dy': dy}
        if self.on_measure_update:
            self.on_measure_update(data)

    # -- floating ruler (Snip & Sketch style) -----------------------

    def toggle_floating_ruler(self):
        """Show or hide the floating ruler overlay."""
        if self._ruler_visible:
            self._hide_floating_ruler()
        else:
            self._show_floating_ruler()

    def _show_floating_ruler(self):
        self._ruler_visible = True
        cw = self.canvas.winfo_width() or 800
        ch = self.canvas.winfo_height() or 600
        self._ruler_length = max(cw, ch) + 200  # span well beyond the window
        self._ruler_cx = self.canvas.canvasx(cw / 2)
        self._ruler_cy = self.canvas.canvasy(ch / 2)
        self._ruler_angle = 0.0
        self._draw_floating_ruler()

    def _hide_floating_ruler(self):
        self._ruler_visible = False
        self.canvas.delete("floatruler")
        self._ruler_dragging = False
        self._ruler_redraw_pending = False

    def _draw_floating_ruler(self):
        """Draw the floating ruler using canvas primitives (no PIL overhead)."""
        self.canvas.delete("floatruler")
        if not self._ruler_visible:
            return

        cx, cy = self._ruler_cx, self._ruler_cy
        a = math.radians(self._ruler_angle)
        ca, sa = math.cos(a), math.sin(a)
        L, W = self._ruler_length, self._ruler_width
        hL, hW = L / 2, W / 2

        def rot(lx, ly):
            return cx + lx * ca - ly * sa, cy + lx * sa + ly * ca

        # --- Pill-shaped body (polygon with semicircular end caps) ---
        r = hW
        n_arc = 12
        body_pts = []
        for i in range(n_arc + 1):
            theta = -math.pi / 2 + math.pi * i / n_arc
            body_pts.append(rot(hL - r + r * math.cos(theta), r * math.sin(theta)))
        for i in range(n_arc + 1):
            theta = math.pi / 2 + math.pi * i / n_arc
            body_pts.append(rot(-hL + r + r * math.cos(theta), r * math.sin(theta)))
        flat = [coord for p in body_pts for coord in p]
        self.canvas.create_polygon(flat, fill="#c8d4e4", outline="#a0afc3",
                                   width=1, stipple="gray75", tags="floatruler")

        # --- Edge line near measurement edge ---
        edge_y = -hW + 3
        self.canvas.create_line(
            *rot(-hL + r, edge_y), *rot(hL - r, edge_y),
            fill="#647c8c", width=1, tags="floatruler")

        # --- Tick marks and labels ---
        scale = max(self.scale, 0.01)
        step = ruler_step(scale)
        tick_spacing = step * scale
        if tick_spacing < 2:
            tick_spacing = 10
            step = tick_spacing / scale

        # Use smaller minor spacing: 4 minor ticks between each numbered tick
        # Each 5th tick is mid-height, each 10th is major with a number
        margin = r + 4
        x = margin
        idx = 0
        while x < L - margin:
            lx = x - hL
            major = (idx % 10 == 0)
            mid = (idx % 5 == 0) and not major

            if major:
                h = W * 0.50
                color = "#3a4e6a"
                lw = 1
            elif mid:
                h = W * 0.35
                color = "#4a6080"
                lw = 1
            else:
                h = W * 0.18
                color = "#8898b0"
                lw = 1

            self.canvas.create_line(
                *rot(lx, edge_y + 1), *rot(lx, edge_y + 1 + h),
                fill=color, width=lw, tags="floatruler")

            # Number labels at every major (10th) and mid (5th) tick
            if major and idx > 0:
                val = int(idx * step)
                self.canvas.create_text(
                    *rot(lx, edge_y + h + 10), text=str(val),
                    fill="#2c3e54", font=("Segoe UI", 9, "bold"),
                    angle=-self._ruler_angle, tags="floatruler")
            elif mid:
                val = int(idx * step)
                self.canvas.create_text(
                    *rot(lx, edge_y + h + 9), text=str(val),
                    fill="#5a6e88", font=("Segoe UI", 7),
                    angle=-self._ruler_angle, tags="floatruler")

            x += tick_spacing
            idx += 1

        # --- Angle indicator bubble at center ---
        angle_display = round(self._ruler_angle) % 360
        if angle_display > 180:
            angle_display -= 360  # show -179 to 180
        angle_text = f"{angle_display}\u00b0"
        # Rounded pill background
        bw, bh = 42, 20
        pts = []
        br = bh / 2
        for i in range(9):
            theta = -math.pi / 2 + math.pi * i / 8
            pts.append(rot(bw / 2 - br + br * math.cos(theta), br * math.sin(theta)))
        for i in range(9):
            theta = math.pi / 2 + math.pi * i / 8
            pts.append(rot(-bw / 2 + br + br * math.cos(theta), br * math.sin(theta)))
        bflat = [coord for p in pts for coord in p]
        self.canvas.create_polygon(bflat, fill="#3c5068", outline="#5a7a98",
                                   width=1, tags="floatruler")
        self.canvas.create_text(
            *rot(0, 0), text=angle_text,
            fill="white", font=("Segoe UI", 9, "bold"),
            angle=-self._ruler_angle, tags="floatruler")

    def _schedule_ruler_redraw(self):
        """Throttled redraw — max ~60 fps."""
        if self._ruler_redraw_pending:
            return
        self._ruler_redraw_pending = True
        self.canvas.after(16, self._do_ruler_redraw)

    def _do_ruler_redraw(self):
        self._ruler_redraw_pending = False
        self._draw_floating_ruler()

    def _point_on_ruler(self, cx, cy):
        """Check if a canvas point is within the ruler body."""
        dx = cx - self._ruler_cx
        dy = cy - self._ruler_cy
        angle_rad = math.radians(self._ruler_angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        along = dx * cos_a + dy * sin_a
        perp = -dx * sin_a + dy * cos_a
        return (abs(along) <= self._ruler_length / 2 and
                abs(perp) <= self._ruler_width / 2)

    def _ruler_try_press(self, e):
        """Try to start ruler drag. Returns True if click was on the ruler."""
        if not self._ruler_visible:
            return False
        cx = self.canvas.canvasx(e.x)
        cy = self.canvas.canvasy(e.y)
        if self._point_on_ruler(cx, cy):
            self._ruler_dragging = True
            self._ruler_drag_offset = (cx - self._ruler_cx, cy - self._ruler_cy)
            return True
        return False

    def _ruler_try_drag(self, e):
        """Move the ruler if dragging. Returns True if handled."""
        if not self._ruler_dragging:
            return False
        cx = self.canvas.canvasx(e.x)
        cy = self.canvas.canvasy(e.y)
        off_x, off_y = self._ruler_drag_offset
        new_cx = cx - off_x
        new_cy = cy - off_y
        dx = new_cx - self._ruler_cx
        dy = new_cy - self._ruler_cy
        self._ruler_cx = new_cx
        self._ruler_cy = new_cy
        self.canvas.move("floatruler", dx, dy)
        return True

    def _ruler_try_release(self, e):
        """End ruler drag. Returns True if was dragging."""
        if self._ruler_dragging:
            self._ruler_dragging = False
            return True
        return False

    def _ruler_try_rotate(self, e):
        """Rotate ruler with scroll wheel if cursor is over it. Returns 'break' or None."""
        if not self._ruler_visible:
            return None
        # Don't intercept Ctrl/Cmd+scroll — that's always zoom
        if e.state & 0x4 or (sys.platform == "darwin" and e.state & 0x8):
            return None
        cx = self.canvas.canvasx(e.x)
        cy = self.canvas.canvasy(e.y)
        if not self._point_on_ruler(cx, cy):
            return None
        # Normalise direction across platforms
        if hasattr(e, 'num') and e.num == 4:
            up = True
        elif hasattr(e, 'num') and e.num == 5:
            up = False
        else:
            up = e.delta > 0
        delta = 2 if up else -2
        if e.state & 0x1:  # Shift → fine rotation (0.5°)
            delta = 0.5 if up else -0.5
        self._ruler_angle = (self._ruler_angle + delta) % 360
        self._schedule_ruler_redraw()
        return "break"

    # -- selection / marching ants -----------------------------------

    def _draw_selection_border(self):
        """Draw a marching-ants dashed border around the selected annotation."""
        idx = self._selected_annotation_idx
        if idx is None or idx >= len(self.annotations):
            self._selected_annotation_idx = None
            return
        a = self.annotations[idx]
        ox, oy = self._img_offset
        s = self.scale
        x1 = min(a.x1, a.x2) * s + ox
        y1 = min(a.y1, a.y2) * s + oy
        x2 = max(a.x1, a.x2) * s + ox
        y2 = max(a.y1, a.y2) * s + oy
        d = self._march_offset
        # Draw two overlapping dashed rects (white + blue) for visibility
        self.canvas.create_rectangle(
            x1, y1, x2, y2, outline="white", width=2,
            dash=(8, 8), dashoffset=d, tags="sel_border")
        self.canvas.create_rectangle(
            x1, y1, x2, y2, outline="#00aaff", width=2,
            dash=(8, 8), dashoffset=(d + 8) % 16, tags="sel_border")

    def _march_ants(self):
        """Animate the marching-ants border."""
        self._march_after_id = None
        if self._selected_annotation_idx is None:
            return
        self._march_offset = (self._march_offset + 2) % 16
        self.canvas.delete("sel_border")
        self._draw_selection_border()
        self._march_after_id = self.after(100, self._march_ants)

    def _start_marching(self):
        """Start the marching-ants animation loop."""
        if self._march_after_id is None and self._selected_annotation_idx is not None:
            self._march_offset = 0
            self._march_ants()

    def _stop_marching(self):
        """Stop the marching-ants animation loop."""
        if self._march_after_id is not None:
            self.after_cancel(self._march_after_id)
            self._march_after_id = None
        self.canvas.delete("sel_border")

    def select_annotation(self, idx: int | None):
        """Select an annotation by index, or deselect if None."""
        if idx == self._selected_annotation_idx:
            return
        self._stop_marching()
        self._selected_annotation_idx = idx
        if idx is not None:
            self.canvas.focus_set()
            self._start_marching()

    def _on_delete_key(self, e):
        """Delete the currently selected annotation."""
        idx = self._selected_annotation_idx
        if idx is None or idx >= len(self.annotations):
            return
        self._stop_marching()
        self._undo_stack.append(list(self.annotations))
        self._redo_stack.clear()
        self.annotations.pop(idx)
        self._selected_annotation_idx = None
        self._invalidate()

    def _on_escape_key(self, e):
        """Deselect the current annotation."""
        if self._selected_annotation_idx is not None:
            self.select_annotation(None)

    def _find_image_annotation_at(self, ix, iy):
        """Return the index of the top-most IMAGE annotation at (ix, iy), or None."""
        for i in range(len(self.annotations) - 1, -1, -1):
            a = self.annotations[i]
            if Tool.IMAGE not in a.tools:
                continue
            if min(a.x1, a.x2) <= ix <= max(a.x1, a.x2) and min(a.y1, a.y2) <= iy <= max(a.y1, a.y2):
                return i
        return None

    # -- mouse interaction ------------------------------------------

    def _on_press(self, e):
        if not self.base_image:
            return
        # Floating ruler intercepts left-click if cursor is on it
        if self._ruler_try_press(e):
            return
        if self._measure_mode:
            self._measure_start = self._to_img(e.x, e.y)
            return
        # Commit any active inline text editor when clicking on the canvas
        if self._text_editor is not None:
            # Check if the click is inside the editor widget — if so, let it handle it
            try:
                ex = self._text_editor.winfo_rootx()
                ey = self._text_editor.winfo_rooty()
                ew = self._text_editor.winfo_width()
                eh = self._text_editor.winfo_height()
                rx, ry = e.x_root, e.y_root
                if ex <= rx <= ex + ew and ey <= ry <= ey + eh:
                    return  # click is inside the editor, don't commit
            except Exception:
                pass
            self._commit_text_editor()
            return
        # IMAGE tool: drag to define placement area
        if self.current_shape == Tool.IMAGE and self.pending_image is not None:
            self._drag_start = self._to_img(e.x, e.y)
            self.select_annotation(None)
            return
        # Click to select / deselect an image annotation
        click_img = self._to_img(e.x, e.y)
        img_idx = self._find_image_annotation_at(*click_img)
        if img_idx is not None and self.current_shape != Tool.TEXT:
            self.select_annotation(img_idx)
            self._drag_start = None
            return
        # Clicked elsewhere — deselect
        self.select_annotation(None)
        # TEXT tool: drag to draw a text box (like shapes)
        if self.current_shape == Tool.TEXT:
            self._drag_start = self._to_img(e.x, e.y)
            return
        self._drag_start = self._to_img(e.x, e.y)

    def _find_text_annotation_at(self, ix, iy):
        """Return the index of the top-most TEXT annotation whose box contains (ix, iy), or None."""
        for i in range(len(self.annotations) - 1, -1, -1):
            a = self.annotations[i]
            if Tool.TEXT not in a.tools:
                continue
            if min(a.x1, a.x2) <= ix <= max(a.x1, a.x2) and min(a.y1, a.y2) <= iy <= max(a.y1, a.y2):
                return i
        return None

    def _find_movable_annotation_at(self, ix, iy):
        """Return the index of the top-most TEXT or IMAGE annotation at (ix, iy), or None."""
        for i in range(len(self.annotations) - 1, -1, -1):
            a = self.annotations[i]
            if Tool.TEXT not in a.tools and Tool.IMAGE not in a.tools:
                continue
            if min(a.x1, a.x2) <= ix <= max(a.x1, a.x2) and min(a.y1, a.y2) <= iy <= max(a.y1, a.y2):
                return i
        return None

    # -- Right-click drag to move / resize annotations ----------------

    _HANDLE_CURSORS = {
        "nw": "top_left_corner", "ne": "top_right_corner",
        "sw": "bottom_left_corner", "se": "bottom_right_corner",
        "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
        "w": "sb_h_double_arrow", "e": "sb_h_double_arrow",
    }

    def _hit_test_handle(self, ann, ix, iy):
        """Return a resize handle string if (ix,iy) is near an edge/corner, else None."""
        x1, y1, x2, y2 = min(ann.x1, ann.x2), min(ann.y1, ann.y2), max(ann.x1, ann.x2), max(ann.y1, ann.y2)
        # Grab margin in image pixels (scaled so it feels the same at any zoom)
        margin = max(12, int(20 / self.scale))
        on_left = abs(ix - x1) < margin
        on_right = abs(ix - x2) < margin
        on_top = abs(iy - y1) < margin
        on_bottom = abs(iy - y2) < margin
        if on_top and on_left:
            return "nw"
        if on_top and on_right:
            return "ne"
        if on_bottom and on_left:
            return "sw"
        if on_bottom and on_right:
            return "se"
        if on_top:
            return "n"
        if on_bottom:
            return "s"
        if on_left:
            return "w"
        if on_right:
            return "e"
        return None

    def _on_mouse_move(self, e):
        """Change cursor to indicate movable / resizable annotation on hover."""
        if not self.base_image:
            return
        ix, iy = self._to_img(e.x, e.y)
        idx = self._find_movable_annotation_at(ix, iy)
        if idx is not None:
            a = self.annotations[idx]
            if Tool.IMAGE in a.tools:
                handle = self._hit_test_handle(a, ix, iy)
                if handle:
                    self.canvas.configure(cursor=self._HANDLE_CURSORS[handle])
                    return
            self.canvas.configure(cursor="fleur")
        else:
            self.canvas.configure(cursor="crosshair")

    def _on_right_press(self, e):
        """Start moving or resizing an annotation on right-click."""
        if not self.base_image:
            return
        ix, iy = self._to_img(e.x, e.y)
        idx = self._find_movable_annotation_at(ix, iy)
        if idx is not None:
            a = self.annotations[idx]
            self._moving_annotation_idx = idx
            self._move_start_img = (ix, iy)
            self._undo_stack.append(list(self.annotations))
            self._redo_stack.clear()
            # Check for resize handle (IMAGE annotations only)
            if Tool.IMAGE in a.tools:
                handle = self._hit_test_handle(a, ix, iy)
                if handle:
                    self._resize_handle = handle
                    self.canvas.configure(cursor=self._HANDLE_CURSORS[handle])
                    return
            self._resize_handle = None
            self.canvas.configure(cursor="fleur")

    def _on_right_drag(self, e):
        """Drag to move or resize an annotation."""
        if self._moving_annotation_idx is None or self._move_start_img is None:
            return
        ix, iy = self._to_img(e.x, e.y)
        sx, sy = self._move_start_img
        a = self.annotations[self._moving_annotation_idx]

        if self._resize_handle:
            # Resize: corners lock aspect ratio, edges stretch freely
            x1, y1, x2, y2 = a.x1, a.y1, a.x2, a.y2
            nx1, ny1, nx2, ny2 = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
            ow, oh = max(nx2 - nx1, 1), max(ny2 - ny1, 1)
            ar = ow / oh
            h = self._resize_handle
            if "w" in h:
                nx1 = ix
            if "e" in h:
                nx2 = ix
            if "n" in h:
                ny1 = iy
            if "s" in h:
                ny2 = iy
            # Corner handles: constrain to aspect ratio
            if len(h) == 2:
                nw, nh = max(nx2 - nx1, 1), max(ny2 - ny1, 1)
                if nw / nh > ar:
                    nw = int(nh * ar)
                else:
                    nh = int(nw / ar)
                if "w" in h:
                    nx1 = nx2 - nw
                else:
                    nx2 = nx1 + nw
                if "n" in h:
                    ny1 = ny2 - nh
                else:
                    ny2 = ny1 + nh
            self.annotations[self._moving_annotation_idx] = dc_replace(
                a, x1=nx1, y1=ny1, x2=nx2, y2=ny2,
            )
        else:
            # Move: translate
            dx, dy = ix - sx, iy - sy
            self.annotations[self._moving_annotation_idx] = dc_replace(
                a, x1=a.x1 + dx, y1=a.y1 + dy, x2=a.x2 + dx, y2=a.y2 + dy,
            )
        self._move_start_img = (ix, iy)
        self._invalidate()

    def _on_right_release(self, e):
        """Finish moving or resizing an annotation."""
        if self._moving_annotation_idx is None:
            return
        self._moving_annotation_idx = None
        self._move_start_img = None
        self._resize_handle = None
        self.canvas.configure(cursor="crosshair")

    def _active_tools(self) -> frozenset:
        """Return the frozenset of tools for the current selection."""
        if self.current_shape:
            return frozenset({self.current_shape})
        return frozenset(self.current_effects)

    def _sample_region_color(self, ix1, iy1, ix2, iy2):
        """Return a hex color string by averaging the base image in a region."""
        if self.base_image is None:
            return "#ffffff"
        img = self.base_image
        # Clamp to image bounds
        x1 = max(0, min(ix1, img.width - 1))
        y1 = max(0, min(iy1, img.height - 1))
        x2 = max(x1 + 1, min(ix2, img.width))
        y2 = max(y1 + 1, min(iy2, img.height))
        region = img.crop((x1, y1, x2, y2)).convert("RGB")
        # Resize to 1x1 to get average
        avg = region.resize((1, 1), Image.BILINEAR).getpixel((0, 0))
        return "#%02x%02x%02x" % avg[:3]

    def _open_text_annotation_for_editing(self, idx):
        """Re-open the inline text editor for an existing TEXT annotation."""
        ann = self.annotations[idx]
        # Restore format state from the annotation so the editor matches
        self.current_font_family = ann.font_family
        self.current_font_size = ann.font_size
        self.current_font_bold = ann.font_bold
        self.current_font_italic = ann.font_italic
        self.current_font_color = ann.font_color
        self.current_text_bg = ann.bg_color
        self.current_line_spacing = ann.line_spacing
        # Notify the app to update sidebar controls
        if self.on_text_edit_start:
            self.on_text_edit_start()
        if ann.text_runs:
            self._show_inline_text_editor(ann.x1, ann.y1, ann.x2, ann.y2,
                                          initial_runs=ann.text_runs)
        else:
            self._show_inline_text_editor(ann.x1, ann.y1, ann.x2, ann.y2,
                                          initial_text=ann.text)
        # Set AFTER _show_inline_text_editor, because it calls
        # _dismiss_text_editor() internally which clears _editing_annotation_idx.
        self._editing_annotation_idx = idx

    # ── Rich-text tag helpers ──────────────────────────────────────

    def _fmt_tag_name(self, family, size, bold, italic, color_tuple):
        """Return a unique tk.Text tag name for this formatting combination."""
        b = "b" if bold else ""
        i = "i" if italic else ""
        c = "%02x%02x%02x" % color_tuple
        safe_family = family.replace(" ", "+")
        return f"fmt_{safe_family}_{size}_{b}{i}_{c}"

    def _ensure_fmt_tag(self, tag, family, size, bold, italic, color_tuple):
        """Create / update a named tag on the current editor with the given style."""
        if self._text_editor is None:
            return
        s = self.scale
        display_size = max(8, int(size * s))
        weight = "bold" if bold else "normal"
        slant = "italic" if italic else "roman"
        fg = "#%02x%02x%02x" % color_tuple
        self._text_editor.tag_configure(
            tag,
            font=(family, display_size, weight, slant),
            foreground=fg,
        )

    def _current_fmt_tag(self):
        """Return (tag_name, ensure it exists) for the current toolbar formatting."""
        tag = self._fmt_tag_name(
            self.current_font_family, self.current_font_size,
            self.current_font_bold, self.current_font_italic,
            self.current_font_color)
        self._ensure_fmt_tag(
            tag, self.current_font_family, self.current_font_size,
            self.current_font_bold, self.current_font_italic,
            self.current_font_color)
        return tag

    def apply_format_to_selection(self):
        """Apply the current toolbar formatting to the selected text or future typing."""
        if self._text_editor is None:
            return
        tag = self._current_fmt_tag()
        try:
            sel_start = self._text_editor.index("sel.first")
            sel_end = self._text_editor.index("sel.last")
            # Remove all existing fmt_ tags in the selection range
            for t in self._text_editor.tag_names():
                if t.startswith("fmt_"):
                    self._text_editor.tag_remove(t, sel_start, sel_end)
            self._text_editor.tag_add(tag, sel_start, sel_end)
        except Exception:
            # No selection — set the tag for future typing at the insert cursor
            # Remove existing fmt tags at insert, add new one
            for t in self._text_editor.tag_names("insert"):
                if t.startswith("fmt_"):
                    self._text_editor.tag_remove(t, "insert")
            self._text_editor.mark_set("insert", "insert")
            # Use the tag for subsequent characters by binding KeyRelease
            self._text_editor._pending_fmt_tag = tag

    def _on_editor_key(self, event):
        """After each keypress, ensure all untagged characters get the current format tag."""
        editor = self._text_editor
        if editor is None:
            return
        tag = getattr(editor, "_pending_fmt_tag", None)
        if tag is None:
            tag = self._current_fmt_tag()
        # Scan backward from insert and tag any consecutive untagged characters.
        # This handles fast typing where KeyRelease events overlap.
        try:
            pos = editor.index("insert")
            while editor.compare(pos, ">", "1.0"):
                prev = editor.index(f"{pos} - 1 char")
                if [t for t in editor.tag_names(prev) if t.startswith("fmt_")]:
                    break
                pos = prev
            # pos is now the start of the untagged run; tag up to insert
            if editor.compare(pos, "<", "insert"):
                editor.tag_add(tag, pos, "insert")
        except Exception:
            pass

    def _extract_text_runs(self):
        """Extract a list of TextRun from the editor, grouping contiguous same-format chars."""
        if self._text_editor is None:
            return []
        editor = self._text_editor
        runs = []
        # Walk every character
        idx = "1.0"
        end = editor.index("end - 1 char")
        current_text = []
        current_fmt = None  # (family, size, bold, italic, color)

        while editor.compare(idx, "<", end):
            char = editor.get(idx, f"{idx} + 1 char")
            # Find the fmt_ tag on this character
            tags = [t for t in editor.tag_names(idx) if t.startswith("fmt_")]
            if tags:
                tag = tags[-1]  # last applied wins
                # Parse: fmt_<family>_<size>_<bi>_<color>
                parts = tag.split("_", 4)  # ['fmt', family, size, bi, color]
                if len(parts) == 5:
                    family = parts[1].replace("+", " ")
                    size = int(parts[2])
                    bi = parts[3]
                    bold = "b" in bi
                    italic = "i" in bi
                    color = tuple(int(parts[4][j:j+2], 16) for j in (0, 2, 4))
                    fmt = (family, size, bold, italic, color)
                else:
                    fmt = (self.current_font_family, self.current_font_size,
                           self.current_font_bold, self.current_font_italic,
                           self.current_font_color)
            else:
                fmt = (self.current_font_family, self.current_font_size,
                       self.current_font_bold, self.current_font_italic,
                       self.current_font_color)

            if fmt != current_fmt:
                if current_text and current_fmt:
                    runs.append(TextRun(
                        text="".join(current_text),
                        font_family=current_fmt[0], font_size=current_fmt[1],
                        font_bold=current_fmt[2], font_italic=current_fmt[3],
                        font_color=current_fmt[4]))
                current_text = [char]
                current_fmt = fmt
            else:
                current_text.append(char)
            idx = editor.index(f"{idx} + 1 char")

        if current_text and current_fmt:
            runs.append(TextRun(
                text="".join(current_text),
                font_family=current_fmt[0], font_size=current_fmt[1],
                font_bold=current_fmt[2], font_italic=current_fmt[3],
                font_color=current_fmt[4]))
        return runs

    def _insert_text_runs(self, runs):
        """Insert TextRun objects into the editor with appropriate formatting tags."""
        if self._text_editor is None or not runs:
            return
        for run in runs:
            tag = self._fmt_tag_name(run.font_family, run.font_size,
                                     run.font_bold, run.font_italic,
                                     run.font_color)
            self._ensure_fmt_tag(tag, run.font_family, run.font_size,
                                 run.font_bold, run.font_italic,
                                 run.font_color)
            start = self._text_editor.index("end - 1 char")
            self._text_editor.insert("end", run.text)
            end = self._text_editor.index("end - 1 char")
            self._text_editor.tag_add(tag, start, end)

    # ── Inline text editor ───────────────────────────────────────

    def _show_inline_text_editor(self, ix1, iy1, ix2, iy2, *, initial_text="",
                                 initial_runs=None):
        """Place an editable text widget on the canvas inside the drawn box."""
        self._dismiss_text_editor()  # clean up any previous editor

        ox, oy = self._img_offset
        s = self.scale
        cx1 = ix1 * s + ox
        cy1 = iy1 * s + oy
        cx2 = ix2 * s + ox
        cy2 = iy2 * s + oy
        # Normalise
        if cx1 > cx2:
            cx1, cx2 = cx2, cx1
        if cy1 > cy2:
            cy1, cy2 = cy2, cy1
        w = max(40, int(cx2 - cx1))
        h = max(24, int(cy2 - cy1))

        self._text_box_img_coords = (min(ix1, ix2), min(iy1, iy2),
                                     max(ix1, ix2), max(iy1, iy2))

        import tkinter as tk
        fg_hex = "#%02x%02x%02x" % self.current_font_color

        # Editor background
        if self.current_text_bg is not None:
            bg_hex = "#%02x%02x%02x" % self.current_text_bg
        else:
            bg_hex = self._sample_region_color(
                min(ix1, ix2), min(iy1, iy2),
                max(ix1, ix2), max(iy1, iy2))

        # Base font matches current format so untagged chars look correct
        display_size = max(8, int(self.current_font_size * self.scale))
        weight = "bold" if self.current_font_bold else "normal"
        slant = "italic" if self.current_font_italic else "roman"
        # Compute inter-line pixel spacing from the multiplier
        extra_px = max(0, int(display_size * (self.current_line_spacing - 1.0)))
        editor = tk.Text(
            self.canvas, wrap="word",
            font=(self.current_font_family, display_size, weight, slant),
            fg=fg_hex, bg=bg_hex,
            relief="flat", bd=0, highlightthickness=0,
            insertbackground=fg_hex, padx=4, pady=4,
            spacing1=0, spacing3=extra_px,
        )
        self._text_editor = editor
        self._text_editor_toplevel = None

        # Dashed border style: blue for solid bg, green for transparent
        border_color = "#2ecc71" if self.current_text_bg is None else "#3498db"
        self._text_editor_border = self.canvas.create_rectangle(
            cx1, cy1, cx1 + w, cy1 + h,
            outline=border_color, width=2, dash=(4, 3), tags="texteditor")
        self._text_editor_win = self.canvas.create_window(
            cx1 + 1, cy1 + 1, anchor="nw", window=editor,
            width=w - 2, height=h - 2, tags="texteditor")

        # Initial content: either rich text runs or plain text
        if initial_runs:
            self._insert_text_runs(initial_runs)
        elif initial_text:
            # Insert as a single run with current formatting
            tag = self._current_fmt_tag()
            editor.insert("1.0", initial_text, tag)
        else:
            # Set up the default format tag for new typing
            self._current_fmt_tag()

        # Set the pending tag so new keystrokes get the current format
        editor._pending_fmt_tag = self._current_fmt_tag()
        editor.bind("<KeyRelease>", self._on_editor_key)

        editor.focus_set()
        editor.bind("<Escape>", lambda e: self._commit_text_editor())
        editor.bind("<ButtonPress-1>", lambda e: "break", add=False)
        editor.bindtags((str(editor), "Text", ".", "all"))

    def _commit_text_editor(self):
        """Read text from the inline editor and create/update an annotation."""
        if self._text_editor is None:
            return
        text = self._text_editor.get("1.0", "end").strip()
        runs = self._extract_text_runs()
        coords = self._text_box_img_coords
        editing_idx = self._editing_annotation_idx
        self._dismiss_text_editor()
        if text and coords:
            x1, y1, x2, y2 = coords
            self._undo_stack.append(list(self.annotations))
            self._redo_stack.clear()
            new_ann = Annotation(
                tools=frozenset({Tool.TEXT}),
                x1=x1, y1=y1, x2=x2, y2=y2,
                color=self.current_color,
                opacity=self.current_opacity,
                text=text,
                font_family=self.current_font_family,
                font_size=self.current_font_size,
                font_bold=self.current_font_bold,
                font_italic=self.current_font_italic,
                font_color=self.current_font_color,
                bg_color=self.current_text_bg,
                line_spacing=self.current_line_spacing,
                text_runs=runs,
            )
            if editing_idx is not None and 0 <= editing_idx < len(self.annotations):
                self.annotations[editing_idx] = new_ann
            else:
                self.annotations.append(new_ann)
            self._invalidate()
        elif not text and editing_idx is not None and 0 <= editing_idx < len(self.annotations):
            # User cleared all text while re-editing — remove the annotation
            self._undo_stack.append(list(self.annotations))
            self._redo_stack.clear()
            del self.annotations[editing_idx]
            self._invalidate()

    def _dismiss_text_editor(self):
        """Remove the inline text editor without committing."""
        if self._text_editor is not None:
            self._text_editor.destroy()
            self._text_editor = None
        if self._text_editor_toplevel is not None:
            self._text_editor_toplevel.destroy()
            self._text_editor_toplevel = None
        if self._text_editor_win is not None:
            self.canvas.delete(self._text_editor_win)
            self._text_editor_win = None
        if self._text_editor_border is not None:
            self.canvas.delete(self._text_editor_border)
            self._text_editor_border = None
        self._text_box_img_coords = None
        self._editing_annotation_idx = None

    def _reposition_text_editor(self):
        """Re-create the canvas window for the text editor after a canvas refresh."""
        if self._text_editor is None or self._text_box_img_coords is None:
            return
        ix1, iy1, ix2, iy2 = self._text_box_img_coords
        ox, oy = self._img_offset
        s = self.scale
        cx1 = ix1 * s + ox
        cy1 = iy1 * s + oy
        cx2 = ix2 * s + ox
        cy2 = iy2 * s + oy
        w = max(40, int(cx2 - cx1))
        h = max(24, int(cy2 - cy1))

        # Update the widget base font for untagged characters
        s = self.scale
        base_ds = max(8, int(self.current_font_size * s))
        base_w = "bold" if self.current_font_bold else "normal"
        base_sl = "italic" if self.current_font_italic else "roman"
        self._text_editor.configure(
            font=(self.current_font_family, base_ds, base_w, base_sl))

        # Rescale line spacing for current zoom
        extra_px = max(0, int(base_ds * (self.current_line_spacing - 1.0)))
        self._text_editor.configure(spacing3=extra_px)

        # Rescale all fmt_ tags to match the current zoom level
        for tag_name in self._text_editor.tag_names():
            if not tag_name.startswith("fmt_"):
                continue
            parts = tag_name.split("_", 4)
            if len(parts) == 5:
                base_size = int(parts[2])
                display_size = max(8, int(base_size * s))
                family = parts[1].replace("+", " ")
                bi = parts[3]
                weight = "bold" if "b" in bi else "normal"
                slant = "italic" if "i" in bi else "roman"
                fg = "#" + parts[4]
                self._text_editor.tag_configure(
                    tag_name,
                    font=(family, display_size, weight, slant),
                    foreground=fg)

        border_color = "#2ecc71" if self.current_text_bg is None else "#3498db"
        self._text_editor_border = self.canvas.create_rectangle(
            cx1, cy1, cx1 + w, cy1 + h,
            outline=border_color, width=2, dash=(4, 3), tags="texteditor")
        self._text_editor_win = self.canvas.create_window(
            cx1 + 1, cy1 + 1, anchor="nw", window=self._text_editor,
            width=w - 2, height=h - 2, tags="texteditor")

    def _on_drag(self, e):
        if self._ruler_try_drag(e):
            return
        if self._measure_mode and self._measure_start:
            for i in self._measure_items:
                self.canvas.delete(i)
            self._measure_items.clear()
            sx, sy = self._measure_start
            ex, ey = self._to_img(e.x, e.y)
            self._draw_measure_line(sx, sy, ex, ey)
            return
        if not self._drag_start:
            return
        if self._preview_id:
            self.canvas.delete(self._preview_id)
        sx, sy = self._drag_start
        ix, iy = self._to_img(e.x, e.y)
        ox, oy = self._img_offset
        cx1, cy1 = sx * self.scale + ox, sy * self.scale + oy
        cx2, cy2 = ix * self.scale + ox, iy * self.scale + oy
        color_hex = "#%02x%02x%02x" % self.current_color
        shape = self.current_shape
        effects = self.current_effects

        if shape == Tool.TEXT:
            # Dashed rectangle preview for text box area
            self._preview_id = self.canvas.create_rectangle(
                cx1, cy1, cx2, cy2, outline="#3498db", width=2, dash=(4, 3)
            )
        elif shape == Tool.IMAGE:
            # Dashed rectangle preview for image placement area
            self._preview_id = self.canvas.create_rectangle(
                cx1, cy1, cx2, cy2, outline="#00ccff", width=2, dash=(6, 3)
            )
        elif shape == Tool.ARROW:
            lw = max(1, int(self.current_width * self.scale))
            head_len = max(14, self.current_width * 4) * self.scale
            head_hw = max(6, self.current_width * 2) * self.scale
            self._preview_id = self.canvas.create_line(
                cx1, cy1, cx2, cy2, fill=color_hex,
                width=lw,
                arrow="last", arrowshape=(head_len, head_len, head_hw),
            )
        elif shape == Tool.ELLIPSE:
            self._preview_id = self.canvas.create_oval(
                cx1, cy1, cx2, cy2, outline=color_hex, width=2, dash=(4, 4)
            )
        elif shape == Tool.RECTANGLE:
            self._preview_id = self.canvas.create_rectangle(
                cx1, cy1, cx2, cy2, outline=color_hex, width=2, dash=(4, 4)
            )
        elif effects:
            only_underline = effects == {Tool.UNDERLINE}
            only_border = effects <= {Tool.BORDER, Tool.UNDERLINE} and Tool.BORDER in effects and Tool.HIGHLIGHT not in effects and Tool.TEXT_LIFT not in effects
            if only_underline:
                y = max(cy1, cy2)
                self._preview_id = self.canvas.create_line(
                    cx1, y, cx2, y, fill=color_hex, width=max(1, int(self.current_width * self.scale))
                )
            elif only_border:
                self._preview_id = self.canvas.create_rectangle(
                    cx1, cy1, cx2, cy2, outline=color_hex,
                    width=max(1, int(self.current_width * self.scale))
                )
            else:
                self._preview_id = self.canvas.create_rectangle(
                    cx1, cy1, cx2, cy2, outline=color_hex, width=2, dash=(4, 4)
                )

    def _on_release(self, e):
        if self._ruler_try_release(e):
            return
        if self._measure_mode and self._measure_start:
            sx, sy = self._measure_start
            ex, ey = self._to_img(e.x, e.y)
            self._measure_start = None
            if abs(ex - sx) >= 2 or abs(ey - sy) >= 2:
                self._measure_pts = (sx, sy, ex, ey)
            return
        if not self._drag_start:
            return
        if self._preview_id:
            self.canvas.delete(self._preview_id)
            self._preview_id = None
        sx, sy = self._drag_start
        ix, iy = self._to_img(e.x, e.y)
        self._drag_start = None
        if abs(ix - sx) < 3 and abs(iy - sy) < 3:
            # Tiny drag = click.  Check for click on existing annotation.
            if self.current_shape == Tool.TEXT:
                idx = self._find_text_annotation_at(ix, iy)
                if idx is not None:
                    self._open_text_annotation_for_editing(idx)
                    return
            # Click on an image to select it
            img_idx = self._find_image_annotation_at(ix, iy)
            if img_idx is not None:
                self.select_annotation(img_idx)
            else:
                self.select_annotation(None)
            return
        active = self._active_tools()
        if not active:
            return
        # TEXT tool: open inline text editor at the drawn rectangle
        if Tool.TEXT in active:
            self._show_inline_text_editor(sx, sy, ix, iy)
            return
        # IMAGE tool: place the pending image into the drawn rectangle
        if Tool.IMAGE in active and self.pending_image is not None:
            # Fit to aspect ratio of the source image
            iw, ih = self.pending_image.size
            if iw > 0 and ih > 0:
                ar = iw / ih
                bw, bh = abs(ix - sx), abs(iy - sy)
                if bw / max(bh, 1) > ar:
                    bw = int(bh * ar)
                else:
                    bh = int(bw / ar)
                ix = sx + (bw if ix >= sx else -bw)
                iy = sy + (bh if iy >= sy else -bh)
            self._undo_stack.append(list(self.annotations))
            self._redo_stack.clear()
            self.annotations.append(Annotation(
                tools=frozenset({Tool.IMAGE}),
                x1=sx, y1=sy, x2=ix, y2=iy,
                color=self.current_color,
                opacity=self.current_opacity,
                image_data=self.pending_image.copy(),
            ))
            self.pending_image = None  # consumed — allow clicking to select
            self._invalidate()
            return
        self._undo_stack.append(list(self.annotations))
        self._redo_stack.clear()
        self.annotations.append(Annotation(
            tools=active,
            x1=sx, y1=sy, x2=ix, y2=iy,
            color=self.current_color,
            opacity=self.current_opacity,
            line_width=self.current_width,
            lift_zoom=self.current_lift_zoom,
        ))
        self._invalidate()

    def _on_wheel(self, e):
        # Normalise delta across platforms
        if e.num == 4:         # Linux/X11 scroll up
            delta = 120
        elif e.num == 5:       # Linux/X11 scroll down
            delta = -120
        elif sys.platform == "darwin":
            delta = e.delta      # macOS: small integers already
        else:
            delta = e.delta      # Windows: multiples of 120
        # Ruler rotation takes priority when cursor is over it
        result = self._ruler_try_rotate(e)
        if result == "break":
            return "break"
        if e.state & 0x4 or (sys.platform == "darwin" and e.state & 0x8):  # Ctrl or ⌘ held → zoom
            self._auto_fit = False
            factor = 1.1 if delta > 0 else 1 / 1.1
            self.scale = max(0.1, min(5.0, self.scale * factor))
            self._display()
            self._notify_zoom()
        else:
            units = -1 * (delta // 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            self.canvas.yview_scroll(units, "units")
