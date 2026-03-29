"""AnnotationCanvas — QGraphicsView-based interactive annotation editor.

Provides the main drawing surface for BurhanApp's PySide6/Qt6 interface.
Handles page display, zoom/pan, mouse-driven annotation creation (effects,
shapes, text boxes, image stamps), selection with marching-ants, right-click
move/resize, and undo/redo.

The rendering pipeline delegates to ``rendering.render_annotations()``
(PIL-based) and converts the result to a QPixmap for display via a
QGraphicsPixmapItem.
"""

from __future__ import annotations

import math
from dataclasses import replace as dc_replace

from PIL import Image
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QBrush, QPolygonF, QFont,
    QWheelEvent, QMouseEvent, QKeyEvent, QTransform, QCursor,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsProxyWidget,
    QWidget, QMessageBox, QVBoxLayout, QFrame, QTextEdit,
)

from .models import Annotation, TextRun, Tool
from .rendering import render_annotations
from .utils import ruler_step


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
    """Convert a PIL Image (any mode) to a QPixmap without an intermediate file.

    Converts to RGBA, builds a QImage from the raw buffer, and copies it
    so the Python bytes object can be safely garbage-collected.
    """
    img = pil_image.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, 4 * img.width,
                  QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


# Cursor shapes for each resize handle direction
_HANDLE_CURSORS: dict[str, Qt.CursorShape] = {
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
    "n":  Qt.CursorShape.SizeVerCursor,
    "s":  Qt.CursorShape.SizeVerCursor,
    "w":  Qt.CursorShape.SizeHorCursor,
    "e":  Qt.CursorShape.SizeHorCursor,
}


class AnnotationCanvas(QFrame):
    """Main editor widget wrapping a QGraphicsView and QGraphicsScene.

    Signals
    -------
    zoom_changed : Signal(float)
        Emitted when the zoom scale changes (for toolbar sync).
    text_edit_requested : Signal(int)
        Emitted when a text annotation needs to be opened for editing.
    """

    zoom_changed = Signal(float)
    text_edit_requested = Signal(int)

    # ==================================================================
    # Construction
    # ==================================================================

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # --- Annotation / page data ---
        self.base_image: Image.Image | None = None
        self.annotations: list[Annotation] = []
        self._undo_stack: list[list[Annotation]] = []
        self._redo_stack: list[list[Annotation]] = []
        self._MAX_UNDO: int = 50

        # --- Active tool state ---
        self.current_effects: set[Tool] = {Tool.HIGHLIGHT}
        self.current_shape: Tool | None = None
        self.current_color: tuple[int, int, int] = (255, 255, 0)
        self.current_opacity: float = 0.4
        self.current_width: int = 3
        self.current_lift_zoom: float = 1.08
        self.current_line_style: str = "solid"      # "solid", "dashed", "dotted"
        self.current_arrow_head: str = "filled"      # "filled", "open", "diamond", "double", "none"
        self.current_curve_offset: float = 0.25       # Bezier bow amount
        self.current_polygon_sides: int = 5           # star/polygon point count
        self.current_star_inner_ratio: float = 0.45   # star inner radius ratio
        self.current_connector_style: str = "straight" # "straight" or "elbow"
        self.current_bracket_style: str = "curly"      # "curly" or "square"
        self.current_gradient_type: str = "none"       # "none", "linear", "radial"
        self.current_gradient_color2: tuple[int, int, int] = (255, 255, 255)
        self.scale: float = 1.0

        # Image overlay waiting to be placed
        self.pending_image: Image.Image | None = None

        # --- Text formatting state ---
        self.current_font_family: str = "Arial"
        self.current_font_size: int = 24
        self.current_font_bold: bool = False
        self.current_font_italic: bool = False
        self.current_font_color: tuple[int, int, int] = (0, 0, 0)
        self.current_text_bg: tuple[int, int, int] | None = (255, 255, 255)
        self.current_line_spacing: float = 1.2

        # --- Interaction state ---
        self._drag_start: tuple[int, int] | None = None
        self._render_cache: Image.Image | None = None
        self._cache_dirty: bool = True
        self._auto_fit: bool = True

        # Right-click move / resize tracking
        self._moving_ann_idx: int | None = None
        self._move_start_img: tuple[int, int] | None = None
        self._resize_handle: str | None = None
        self._drag_overlay: QGraphicsPixmapItem | None = None  # lightweight drag preview

        # Selection (marching-ants)
        self._selected_ann_idx: int | None = None
        self._march_timer: QTimer | None = None
        self._march_offset: int = 0

        # External callback (set by qt_app.py when re-editing text)
        self.on_text_edit_start: callable = None  # type: ignore[assignment]

        # Inline text editor state
        self._text_editor: QTextEdit | None = None
        self._text_proxy: QGraphicsProxyWidget | None = None
        self._text_box_img_coords: tuple[int, int, int, int] | None = None
        self._editing_annotation_idx: int | None = None

        # Measurement mode state
        self._measure_mode: bool = False
        self._measure_start: tuple[int, int] | None = None
        self._measure_pts: tuple[int, int, int, int] | None = None

        # Freehand pen tracking
        self._freehand_points: list[tuple[int, int]] = []
        self._measure_items: list = []
        self.on_measure_update: callable = None  # type: ignore[assignment]

        # Floating ruler state
        self._ruler_visible: bool = False
        self._ruler_cx: float = 0.0
        self._ruler_cy: float = 0.0
        self._ruler_angle: float = 0.0
        self._ruler_length: float = 1000.0
        self._ruler_width: float = 40.0
        self._ruler_dragging: bool = False
        self._ruler_drag_offset: tuple[float, float] = (0.0, 0.0)
        self._ruler_items: list = []
        self._ruler_redraw_pending: bool = False

        # --- QGraphicsView / Scene ---
        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene, self)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self._view.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate
        )
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setBackgroundBrush(QColor("#1a1a1a"))
        self._view.viewport().setCursor(Qt.CursorShape.CrossCursor)

        # Rendered page pixmap as a scene item
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        # Transient rubber-band preview items (created/destroyed per drag)
        self._preview_items: list = []
        # Marching-ants selection border items
        self._sel_items: list = []

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        # Intercept mouse + wheel on the viewport
        self._view.viewport().installEventFilter(self)

    # ==================================================================
    # Public API
    # ==================================================================

    def set_page(
        self,
        pil_image: Image.Image | None,
        annotations: list[Annotation] | None = None,
    ) -> None:
        """Load a new page image with optional annotations."""
        self._commit_text_editor()
        self.base_image = pil_image
        self.annotations = annotations if annotations is not None else []
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._cache_dirty = True
        self._deselect()
        self._refresh()
        if self._auto_fit and pil_image is not None:
            QTimer.singleShot(0, self.fit_to_frame)

    def load_state(
        self,
        img: Image.Image | None,
        annotations: list[Annotation],
        undo: list[list[Annotation]],
        redo: list[list[Annotation]],
    ) -> None:
        """Restore full page state (used when switching pages)."""
        self._commit_text_editor()
        self.base_image = img
        self.annotations = annotations
        self._undo_stack = undo
        self._redo_stack = redo
        self._cache_dirty = True
        self._deselect()
        self._refresh()
        if self._auto_fit and img is not None:
            QTimer.singleShot(0, self.fit_to_frame)

    def set_scale(self, s: float) -> None:
        """Set an explicit zoom level (clamped to 0.1–5.0)."""
        self._commit_text_editor()
        self._auto_fit = False
        self.scale = max(0.1, min(5.0, s))
        self._apply_zoom()
        self.zoom_changed.emit(self.scale)

    def fit_to_frame(self) -> None:
        """Fit the page image to the current view size."""
        if not self.base_image:
            return
        self._auto_fit = True
        self._view.fitInView(
            self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio
        )
        t = self._view.transform()
        self.scale = t.m11()
        self.zoom_changed.emit(self.scale)

    def get_rendered(self) -> Image.Image | None:
        """Return the current page with annotations composited (RGB)."""
        if not self.base_image:
            return None
        return render_annotations(self.base_image, self.annotations).convert("RGB")

    # --- Undo / Redo / Clear ---

    def undo(self) -> None:
        """Revert to the previous annotation state."""
        if not self._undo_stack:
            return
        self._redo_stack.append(list(self.annotations))
        if len(self._redo_stack) > self._MAX_UNDO:
            self._redo_stack.pop(0)
        self.annotations = self._undo_stack.pop()
        self._cache_dirty = True
        self._deselect()
        self._refresh()

    def redo(self) -> None:
        """Re-apply the last undone change."""
        if not self._redo_stack:
            return
        self._undo_stack.append(list(self.annotations))
        if len(self._undo_stack) > self._MAX_UNDO:
            self._undo_stack.pop(0)
        self.annotations = self._redo_stack.pop()
        self._cache_dirty = True
        self._deselect()
        self._refresh()

    def clear_all(self) -> None:
        """Remove all annotations on the current page."""
        if not self.annotations:
            return
        self._push_undo()
        self.annotations.clear()
        self._cache_dirty = True
        self._deselect()
        self._refresh()

    # ==================================================================
    # Internal — undo helpers
    # ==================================================================

    def _push_undo(self) -> None:
        """Snapshot current annotations onto the undo stack."""
        self._undo_stack.append(list(self.annotations))
        if len(self._undo_stack) > self._MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    # ==================================================================
    # Internal — display pipeline
    # ==================================================================

    def _refresh(self) -> None:
        """Re-render annotations via PIL and update the displayed pixmap."""
        if not self.base_image:
            self._pixmap_item.setPixmap(QPixmap())
            self._scene.setSceneRect(QRectF())
            return
        self._render_cache = render_annotations(self.base_image, self.annotations)
        self._cache_dirty = False
        pixmap = _pil_to_qpixmap(self._render_cache)
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._draw_selection_border()

    def _apply_zoom(self) -> None:
        """Apply ``self.scale`` to the view's transform matrix."""
        self._view.setTransform(QTransform.fromScale(self.scale, self.scale))

    # ==================================================================
    # Internal — coordinate mapping
    # ==================================================================

    def _view_to_image(self, view_pos: QPointF) -> tuple[int, int]:
        """Map a viewport-local position to image-pixel coordinates.

        Accounts for the current zoom/pan transform so the returned
        (x, y) corresponds to the pixel in ``self.base_image``.
        """
        scene_pos = self._view.mapToScene(view_pos.toPoint())
        return int(scene_pos.x()), int(scene_pos.y())

    # ==================================================================
    # Internal — active tool helpers
    # ==================================================================

    def _active_tools(self) -> frozenset[Tool]:
        """Return the tool(s) that will be applied on the next drag."""
        if self.current_shape:
            return frozenset({self.current_shape})
        return frozenset(self.current_effects)

    # ==================================================================
    # Internal — hit testing
    # ==================================================================

    def _find_movable_at(self, ix: int, iy: int) -> int | None:
        """Return the index of the top-most TEXT or IMAGE annotation at *(ix, iy)*.

        Searches back-to-front so the visually top-most annotation wins.
        """
        for i in range(len(self.annotations) - 1, -1, -1):
            a = self.annotations[i]
            if Tool.TEXT not in a.tools and Tool.IMAGE not in a.tools:
                continue
            if (min(a.x1, a.x2) <= ix <= max(a.x1, a.x2)
                    and min(a.y1, a.y2) <= iy <= max(a.y1, a.y2)):
                return i
        return None

    def _find_text_at(self, ix: int, iy: int) -> int | None:
        """Return the index of the top-most TEXT annotation at *(ix, iy)*."""
        for i in range(len(self.annotations) - 1, -1, -1):
            a = self.annotations[i]
            if Tool.TEXT not in a.tools:
                continue
            if (min(a.x1, a.x2) <= ix <= max(a.x1, a.x2)
                    and min(a.y1, a.y2) <= iy <= max(a.y1, a.y2)):
                return i
        return None

    def _hit_test_handle(self, ann: Annotation, ix: int, iy: int) -> str | None:
        """Return a resize-handle name if *(ix, iy)* is near an edge/corner.

        The grab margin scales inversely with zoom so it feels consistent.
        Returns one of "nw", "n", "ne", "e", "se", "s", "sw", "w", or None.
        """
        x1, y1 = min(ann.x1, ann.x2), min(ann.y1, ann.y2)
        x2, y2 = max(ann.x1, ann.x2), max(ann.y1, ann.y2)
        margin = max(12, int(20 / max(self.scale, 0.01)))
        on_l = abs(ix - x1) < margin
        on_r = abs(ix - x2) < margin
        on_t = abs(iy - y1) < margin
        on_b = abs(iy - y2) < margin
        if on_t and on_l: return "nw"
        if on_t and on_r: return "ne"
        if on_b and on_l: return "sw"
        if on_b and on_r: return "se"
        if on_t: return "n"
        if on_b: return "s"
        if on_l: return "w"
        if on_r: return "e"
        return None

    # ==================================================================
    # Internal — selection (marching-ants)
    # ==================================================================

    def select_annotation(self, idx: int | None) -> None:
        """Select an annotation by index, or deselect with ``None``."""
        if idx == self._selected_ann_idx:
            return
        self._stop_marching()
        self._selected_ann_idx = idx
        if idx is not None:
            self._start_marching()
        self._draw_selection_border()

    def _deselect(self) -> None:
        """Convenience wrapper to deselect without redundant redraws."""
        self._stop_marching()
        self._clear_sel_items()
        self._selected_ann_idx = None

    def _draw_selection_border(self) -> None:
        """Draw two overlapping dashed rects (white + blue) for visibility."""
        self._clear_sel_items()
        idx = self._selected_ann_idx
        if idx is None or idx >= len(self.annotations):
            self._selected_ann_idx = None
            return
        a = self.annotations[idx]
        x1 = min(a.x1, a.x2)
        y1 = min(a.y1, a.y2)
        x2 = max(a.x1, a.x2)
        y2 = max(a.y1, a.y2)
        d = self._march_offset

        pen_w = QPen(QColor("white"), 2, Qt.PenStyle.DashLine)
        pen_w.setDashOffset(d)
        r1 = self._scene.addRect(QRectF(x1, y1, x2 - x1, y2 - y1), pen_w)
        self._sel_items.append(r1)

        pen_b = QPen(QColor("#00aaff"), 2, Qt.PenStyle.DashLine)
        pen_b.setDashOffset(d + 8)
        r2 = self._scene.addRect(QRectF(x1, y1, x2 - x1, y2 - y1), pen_b)
        self._sel_items.append(r2)

    def _clear_sel_items(self) -> None:
        """Remove selection border items from the scene."""
        for item in self._sel_items:
            self._scene.removeItem(item)
        self._sel_items.clear()

    def _start_marching(self) -> None:
        """Start the marching-ants animation timer."""
        if self._march_timer is None:
            self._march_timer = QTimer(self)
            self._march_timer.setInterval(100)
            self._march_timer.timeout.connect(self._march_tick)
        self._march_offset = 0
        self._march_timer.start()

    def _stop_marching(self) -> None:
        """Stop the marching-ants animation timer."""
        if self._march_timer is not None:
            self._march_timer.stop()
        self._clear_sel_items()

    def _march_tick(self) -> None:
        """Advance dash offset and redraw the selection border."""
        if self._selected_ann_idx is None:
            self._stop_marching()
            return
        self._march_offset = (self._march_offset + 2) % 16
        self._draw_selection_border()

    # ==================================================================
    # Internal — rubber-band preview
    # ==================================================================

    def _clear_preview(self) -> None:
        """Remove any rubber-band preview items from the scene."""
        for item in self._preview_items:
            self._scene.removeItem(item)
        self._preview_items.clear()

    def _draw_preview(self, sx: int, sy: int, ix: int, iy: int) -> None:
        """Draw a live rubber-band preview between drag start and current pos.

        Parameters are in *image* coordinates.  The preview style depends
        on the currently active tool.
        """
        self._clear_preview()
        color_hex = "#%02x%02x%02x" % self.current_color
        qcolor = QColor(color_hex)
        shape = self.current_shape
        effects = self.current_effects

        if shape == Tool.TEXT:
            pen = QPen(QColor("#3498db"), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)  # constant screen-space width
            r = self._scene.addRect(QRectF(QPointF(sx, sy), QPointF(ix, iy)), pen)
            self._preview_items.append(r)

        elif shape == Tool.IMAGE:
            pen = QPen(QColor("#00ccff"), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            r = self._scene.addRect(QRectF(QPointF(sx, sy), QPointF(ix, iy)), pen)
            self._preview_items.append(r)

        elif shape == Tool.ARROW:
            pen = QPen(qcolor, max(1, self.current_width))
            line = self._scene.addLine(sx, sy, ix, iy, pen)
            self._preview_items.append(line)
            self._draw_arrowhead_preview(sx, sy, ix, iy, qcolor)

        elif shape == Tool.CURVED_ARROW:
            from .rendering import _bezier_points
            curve_pts = _bezier_points(sx, sy, ix, iy, self.current_curve_offset)
            if len(curve_pts) >= 2:
                pen = QPen(qcolor, max(1, self.current_width))
                path = QPainterPath()
                path.moveTo(QPointF(*curve_pts[0]))
                for pt in curve_pts[1:]:
                    path.lineTo(QPointF(*pt))
                item = self._scene.addPath(path, pen)
                self._preview_items.append(item)
                # Arrowhead at the tip
                tx1, ty1 = curve_pts[-2]
                tx2, ty2 = curve_pts[-1]
                self._draw_arrowhead_preview(tx1, ty1, tx2, ty2, qcolor)

        elif shape == Tool.LINE:
            pen = QPen(qcolor, max(1, self.current_width))
            line = self._scene.addLine(sx, sy, ix, iy, pen)
            self._preview_items.append(line)

        elif shape == Tool.RECTANGLE:
            pen = QPen(qcolor, 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            r = self._scene.addRect(QRectF(QPointF(sx, sy), QPointF(ix, iy)), pen)
            self._preview_items.append(r)

        elif shape == Tool.ELLIPSE:
            pen = QPen(qcolor, 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            rect = QRectF(QPointF(min(sx, ix), min(sy, iy)),
                          QPointF(max(sx, ix), max(sy, iy)))
            e = self._scene.addEllipse(rect, pen)
            self._preview_items.append(e)

        elif shape == Tool.ROUNDED_RECT:
            pen = QPen(qcolor, 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            rect = QRectF(QPointF(min(sx, ix), min(sy, iy)),
                          QPointF(max(sx, ix), max(sy, iy)))
            w = rect.width()
            h = rect.height()
            radius = max(10, min(w, h) / 4)
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            item = self._scene.addPath(path, pen)
            self._preview_items.append(item)

        elif shape == Tool.FREEHAND:
            if self._freehand_points:
                pen = QPen(qcolor, max(1, self.current_width))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                path = QPainterPath()
                path.moveTo(QPointF(*self._freehand_points[0]))
                for pt in self._freehand_points[1:]:
                    path.lineTo(QPointF(*pt))
                item = self._scene.addPath(path, pen)
                self._preview_items.append(item)

        elif shape == Tool.CALLOUT:
            pen = QPen(qcolor, 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            rect = QRectF(QPointF(min(sx, ix), min(sy, iy)),
                          QPointF(max(sx, ix), max(sy, iy)))
            w, h = rect.width(), rect.height()
            radius = max(8, min(w, h) / 8)
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            item = self._scene.addPath(path, pen)
            self._preview_items.append(item)
            # Tail preview
            cx = rect.center().x()
            by = rect.bottom()
            tail_hw = max(8, w / 8)
            tail_y = by + h / 3
            tail = QPolygonF([
                QPointF(cx - tail_hw, by),
                QPointF(cx, tail_y),
                QPointF(cx + tail_hw, by),
            ])
            ti = self._scene.addPolygon(tail, pen)
            self._preview_items.append(ti)

        elif shape == Tool.BRACKET:
            pen = QPen(qcolor, max(1, self.current_width))
            bw, bh = abs(ix - sx), abs(iy - sy)
            lx, ly = min(sx, ix), min(sy, iy)
            rx, ry = max(sx, ix), max(sy, iy)
            vertical = bh >= bw
            if vertical:
                # } shape preview using cubic beziers
                mid_y = (ly + ry) / 2
                bow = max(12, bw / 2, 18)
                path = QPainterPath()
                path.moveTo(QPointF(lx, ly))
                qtr = (ry - ly) / 4
                # Top hook → straight to near mid
                path.cubicTo(QPointF(lx + bow * 0.5, ly),
                             QPointF(lx + bow * 0.1, ly + qtr),
                             QPointF(lx, mid_y - 1))
                # Mid tip juts right
                path.cubicTo(QPointF(lx + bow * 0.3, mid_y - 0.5),
                             QPointF(lx + bow, mid_y),
                             QPointF(lx + bow, mid_y))
                path.cubicTo(QPointF(lx + bow, mid_y),
                             QPointF(lx + bow * 0.3, mid_y + 0.5),
                             QPointF(lx, mid_y + 1))
                # Straight to near bottom → bottom hook
                path.cubicTo(QPointF(lx + bow * 0.1, ry - qtr),
                             QPointF(lx + bow * 0.5, ry),
                             QPointF(lx, ry))
                item = self._scene.addPath(path, pen)
                self._preview_items.append(item)
            else:
                mid_x = (lx + rx) / 2
                bow = max(12, bh / 2, 18)
                path = QPainterPath()
                path.moveTo(QPointF(lx, ly))
                qtr = (rx - lx) / 4
                path.cubicTo(QPointF(lx, ly + bow * 0.5),
                             QPointF(lx + qtr, ly + bow * 0.1),
                             QPointF(mid_x - 1, ly))
                path.cubicTo(QPointF(mid_x - 0.5, ly + bow * 0.3),
                             QPointF(mid_x, ly + bow),
                             QPointF(mid_x, ly + bow))
                path.cubicTo(QPointF(mid_x, ly + bow),
                             QPointF(mid_x + 0.5, ly + bow * 0.3),
                             QPointF(mid_x + 1, ly))
                path.cubicTo(QPointF(rx - qtr, ly + bow * 0.1),
                             QPointF(rx, ly + bow * 0.5),
                             QPointF(rx, ly))
                item = self._scene.addPath(path, pen)
                self._preview_items.append(item)

        elif shape == Tool.STAR:
            pen = QPen(qcolor, 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            import math as _m
            rect = QRectF(QPointF(min(sx, ix), min(sy, iy)),
                          QPointF(max(sx, ix), max(sy, iy)))
            cx, cy = rect.center().x(), rect.center().y()
            rx_r, ry_r = rect.width() / 2, rect.height() / 2
            n = self.current_polygon_sides
            ir = self.current_star_inner_ratio
            poly = QPolygonF()
            for i in range(n * 2):
                angle = _m.pi * i / n - _m.pi / 2
                r_frac = 1.0 if i % 2 == 0 else ir
                poly.append(QPointF(cx + rx_r * r_frac * _m.cos(angle),
                                    cy + ry_r * r_frac * _m.sin(angle)))
            item = self._scene.addPolygon(poly, pen)
            self._preview_items.append(item)

        elif shape == Tool.DIAMOND:
            pen = QPen(qcolor, max(1, self.current_width))
            pen.setStyle(Qt.DashLine)
            pen.setCosmetic(True)
            cx = (sx + ix) / 2
            cy = (sy + iy) / 2
            poly = QPolygonF([
                QPointF(cx, sy),   # top
                QPointF(ix, cy),   # right
                QPointF(cx, iy),   # bottom
                QPointF(sx, cy),   # left
            ])
            item = self._scene.addPolygon(poly, pen)
            self._preview_items.append(item)

        elif shape == Tool.CONNECTOR:
            pen = QPen(qcolor, max(1, self.current_width))
            if self.current_connector_style == "elbow":
                path = QPainterPath()
                path.moveTo(QPointF(sx, sy))
                path.lineTo(QPointF(ix, sy))
                path.lineTo(QPointF(ix, iy))
                item = self._scene.addPath(path, pen)
                self._preview_items.append(item)
            else:
                line = self._scene.addLine(sx, sy, ix, iy, pen)
                self._preview_items.append(line)
            # Endpoint dots
            dot_r = max(3, self.current_width)
            brush = QBrush(qcolor)
            for dx, dy in [(sx, sy), (ix, iy)]:
                e = self._scene.addEllipse(dx - dot_r, dy - dot_r,
                                           dot_r * 2, dot_r * 2, pen, brush)
                self._preview_items.append(e)

        elif effects:
            # Determine preview shape from the active effect combination
            only_underline = effects == {Tool.UNDERLINE}
            has_border = Tool.BORDER in effects
            no_fill = (Tool.HIGHLIGHT not in effects
                       and Tool.TEXT_LIFT not in effects)

            if only_underline:
                y = max(sy, iy)
                pen = QPen(qcolor, max(1, self.current_width))
                line = self._scene.addLine(sx, y, ix, y, pen)
                self._preview_items.append(line)
            elif has_border and no_fill:
                pen = QPen(qcolor, max(1, self.current_width))
                r = self._scene.addRect(
                    QRectF(QPointF(sx, sy), QPointF(ix, iy)), pen)
                self._preview_items.append(r)
            else:
                pen = QPen(qcolor, 2, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                r = self._scene.addRect(
                    QRectF(QPointF(sx, sy), QPointF(ix, iy)), pen)
                self._preview_items.append(r)

    def _draw_arrowhead_preview(
        self, sx: int, sy: int, ex: int, ey: int, qcolor: QColor,
    ) -> None:
        """Draw a triangular arrowhead at the end of a line preview."""
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        head_len = max(14, self.current_width * 4)
        head_hw = max(6, self.current_width * 2)
        bx, by = ex - ux * head_len, ey - uy * head_len
        px, py = -uy * head_hw, ux * head_hw
        tri = QPolygonF([
            QPointF(ex, ey),
            QPointF(bx + px, by + py),
            QPointF(bx - px, by - py),
        ])
        item = self._scene.addPolygon(tri, QPen(Qt.PenStyle.NoPen), QBrush(qcolor))
        self._preview_items.append(item)

    # ==================================================================
    # Internal — inline text editor
    # ==================================================================

    def _sample_region_color(self, x1: int, y1: int, x2: int, y2: int) -> str:
        """Sample the average color from the base image in the given region.

        Used to approximate a background color when transparent text bg
        is selected, so the editor blends visually with the page.
        """
        if not self.base_image:
            return "#ffffff"
        crop = self.base_image.crop((
            max(0, x1), max(0, y1),
            min(self.base_image.width, x2),
            min(self.base_image.height, y2),
        ))
        if crop.width < 1 or crop.height < 1:
            return "#ffffff"
        avg = crop.resize((1, 1), Image.BILINEAR).getpixel((0, 0))
        if isinstance(avg, int):
            return f"#{avg:02x}{avg:02x}{avg:02x}"
        return "#%02x%02x%02x" % avg[:3]

    def show_inline_text_editor(
        self,
        ix1: int, iy1: int, ix2: int, iy2: int,
        *,
        initial_text: str = "",
        initial_runs: list | None = None,
        editing_idx: int | None = None,
    ) -> None:
        """Place an editable QTextEdit on the canvas inside the drawn box.

        Parameters
        ----------
        ix1, iy1, ix2, iy2 : int
            Bounding box in *image* coordinates.
        initial_text : str
            Plain text to pre-populate (used for new annotations).
        initial_runs : list[TextRun] | None
            Rich text runs to pre-populate (used when re-editing).
        editing_idx : int | None
            Index of the annotation being re-edited (``None`` for new).
        """
        self._dismiss_text_editor()

        x1, y1 = min(ix1, ix2), min(iy1, iy2)
        x2, y2 = max(ix1, ix2), max(iy1, iy2)
        w = max(60, x2 - x1)
        h = max(30, y2 - y1)
        self._text_box_img_coords = (x1, y1, x1 + w, y1 + h)

        # Build editor background color
        if self.current_text_bg is not None:
            bg_hex = "#%02x%02x%02x" % self.current_text_bg
        else:
            bg_hex = self._sample_region_color(x1, y1, x2, y2)
        fg_hex = "#%02x%02x%02x" % self.current_font_color

        editor = QTextEdit()
        editor.setStyleSheet(
            f"QTextEdit {{ background-color: {bg_hex}; color: {fg_hex}; "
            f"border: 2px dashed #3498db; padding: 2px; }}"
        )
        editor.setFixedSize(w, h)
        editor.setAcceptRichText(True)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Set default font
        font = QFont(self.current_font_family, self.current_font_size)
        font.setBold(self.current_font_bold)
        font.setItalic(self.current_font_italic)
        editor.setFont(font)
        editor.setTextColor(QColor(*self.current_font_color))

        # Populate content
        if initial_runs:
            self._insert_text_runs_to_editor(editor, initial_runs)
        elif initial_text:
            editor.setText(initial_text)

        # Add as a proxy widget in the scene
        proxy = self._scene.addWidget(editor)
        proxy.setPos(x1, y1)
        proxy.setZValue(1000)
        self._text_editor = editor
        self._text_proxy = proxy
        self._editing_annotation_idx = editing_idx

        editor.setFocus()

    def _insert_text_runs_to_editor(
        self, editor: QTextEdit, runs: list
    ) -> None:
        """Insert TextRun objects into a QTextEdit with per-run formatting."""
        from PySide6.QtGui import QTextCursor, QTextCharFormat
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for run in runs:
            fmt = QTextCharFormat()
            font = QFont(run.font_family, max(1, run.font_size))
            font.setBold(run.font_bold)
            font.setItalic(run.font_italic)
            fmt.setFont(font)
            fmt.setForeground(QColor(*run.font_color))
            cursor.insertText(run.text, fmt)
        editor.setTextCursor(cursor)

    def _extract_text_runs(self) -> list:
        """Extract a list of TextRun from the current text editor.

        Walks the QTextEdit's document character-by-character, grouping
        contiguous characters with the same formatting into TextRun objects.
        """
        if self._text_editor is None:
            return []
        doc = self._text_editor.document()
        runs: list[TextRun] = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    font = fmt.font()
                    color = fmt.foreground().color()
                    runs.append(TextRun(
                        text=fragment.text(),
                        font_family=font.family(),
                        font_size=max(1, font.pointSize()),
                        font_bold=font.bold(),
                        font_italic=font.italic(),
                        font_color=(color.red(), color.green(), color.blue()),
                    ))
                it += 1
            # Add newline between blocks (paragraphs) except the last
            next_block = block.next()
            if next_block.isValid():
                if runs:
                    runs.append(TextRun(
                        text="\n",
                        font_family=runs[-1].font_family,
                        font_size=runs[-1].font_size,
                        font_bold=runs[-1].font_bold,
                        font_italic=runs[-1].font_italic,
                        font_color=runs[-1].font_color,
                    ))
            block = next_block
        return runs

    def _commit_text_editor(self) -> None:
        """Read text from the inline editor and create/update an annotation."""
        if self._text_editor is None:
            return
        text = self._text_editor.toPlainText().strip()
        runs = self._extract_text_runs()
        coords = self._text_box_img_coords
        editing_idx = self._editing_annotation_idx
        self._dismiss_text_editor()
        if text and coords:
            x1, y1, x2, y2 = coords
            self._push_undo()
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
            self._cache_dirty = True
            self._refresh()
        elif not text and editing_idx is not None and 0 <= editing_idx < len(self.annotations):
            # User cleared all text — remove the annotation
            self._push_undo()
            del self.annotations[editing_idx]
            self._cache_dirty = True
            self._refresh()

    def _dismiss_text_editor(self) -> None:
        """Remove the inline text editor without committing."""
        # Clear Python references first so state is consistent even if
        # removal triggers re-entrant events.
        editor = self._text_editor
        proxy = self._text_proxy
        self._text_editor = None
        self._text_proxy = None
        self._text_box_img_coords = None
        self._editing_annotation_idx = None
        if proxy is not None:
            self._scene.removeItem(proxy)
            # proxy owns the QTextEdit; removing it is enough.
            proxy.deleteLater()

    def apply_format_to_selection(self) -> None:
        """Apply the current toolbar formatting to selected text in the editor."""
        if self._text_editor is None:
            return
        from PySide6.QtGui import QTextCharFormat

        # Update the editor background live when transparency changes
        if self.current_text_bg is not None:
            bg_hex = "#%02x%02x%02x" % self.current_text_bg
        else:
            coords = self._text_box_img_coords
            if coords:
                bg_hex = self._sample_region_color(*coords)
            else:
                bg_hex = "transparent"
        fg_hex = "#%02x%02x%02x" % self.current_font_color
        self._text_editor.setStyleSheet(
            f"QTextEdit {{ background-color: {bg_hex}; color: {fg_hex}; "
            f"border: 2px dashed #3498db; padding: 2px; }}"
        )

        cursor = self._text_editor.textCursor()
        if not cursor.hasSelection():
            # Set format for future typing
            fmt = QTextCharFormat()
            font = QFont(self.current_font_family, self.current_font_size)
            font.setBold(self.current_font_bold)
            font.setItalic(self.current_font_italic)
            fmt.setFont(font)
            fmt.setForeground(QColor(*self.current_font_color))
            cursor.setCharFormat(fmt)
            self._text_editor.setCurrentCharFormat(fmt)
            return
        fmt = QTextCharFormat()
        font = QFont(self.current_font_family, self.current_font_size)
        font.setBold(self.current_font_bold)
        font.setItalic(self.current_font_italic)
        fmt.setFont(font)
        fmt.setForeground(QColor(*self.current_font_color))
        cursor.mergeCharFormat(fmt)
        self._text_editor.mergeCurrentCharFormat(fmt)

    # ==================================================================
    # Measurement system
    # ==================================================================

    def set_measure_mode(self, active: bool) -> None:
        """Enable or disable point-to-point measurement mode.

        When active, the cursor changes to a crosshair and clicks define
        start/end points. A dashed line with tick marks and a distance
        label is drawn between them.
        """
        self._measure_mode = active
        if active:
            self._view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._view.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self._clear_measure()

    def _clear_measure(self) -> None:
        """Remove measurement overlay items and reset state."""
        for item in self._measure_items:
            self._scene.removeItem(item)
        self._measure_items.clear()
        self._measure_pts = None
        self._measure_start = None
        if self.on_measure_update:
            self.on_measure_update(None)

    def _redraw_measure(self) -> None:
        """Redraw persisted measurement after zoom/scroll."""
        for item in self._measure_items:
            self._scene.removeItem(item)
        self._measure_items.clear()
        if self._measure_pts:
            self._draw_measure_line(*self._measure_pts)

    def _draw_measure_line(self, sx: int, sy: int, ex: int, ey: int) -> None:
        """Draw measurement overlay between two image-coordinate points.

        Draws a dashed red line with endpoint markers, tick marks along
        the line, and a distance label at the midpoint.
        """
        add = self._measure_items.append

        # Dashed measurement line
        pen = QPen(QColor("#ff4444"), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        line = self._scene.addLine(sx, sy, ex, ey, pen)
        line.setZValue(900)
        add(line)

        # Endpoint markers (small circles)
        r = max(3, int(5 / max(self.scale, 0.01)))
        marker_pen = QPen(QColor("white"), 1)
        marker_pen.setCosmetic(True)
        marker_brush = QBrush(QColor("#ff4444"))
        for mx, my in [(sx, sy), (ex, ey)]:
            ell = self._scene.addEllipse(mx - r, my - r, 2 * r, 2 * r,
                                         marker_pen, marker_brush)
            ell.setZValue(901)
            add(ell)

        # Distance computation
        dx_px, dy_px = abs(ex - sx), abs(ey - sy)
        dist = math.hypot(dx_px, dy_px)

        # Label at midpoint
        mid_x = (sx + ex) / 2
        mid_y = (sy + ey) / 2
        label = f"{dist:.1f} px"
        inv = 1.0 / max(self.scale, 0.01)
        font_size = max(1, int(9 * inv))
        font = QFont("Segoe UI", font_size, QFont.Weight.Bold)

        # Background rectangle for the label
        lbl_offset = 16 * inv
        tw, th = 60 * inv, 16 * inv
        pad = 4 * inv
        bg_rect = self._scene.addRect(
            QRectF(mid_x - tw / 2 - pad, mid_y - lbl_offset - th / 2 - pad,
                   tw + 2 * pad, th + 2 * pad),
            QPen(QColor("#ff4444"), 1),
            QBrush(QColor("#1e1e1e")),
        )
        bg_rect.setZValue(902)
        add(bg_rect)

        text_item = self._scene.addText(label, font)
        text_item.setDefaultTextColor(QColor("#ff4444"))
        text_item.setPos(mid_x - tw / 2, mid_y - lbl_offset - th / 2 - 2)
        text_item.setZValue(903)
        add(text_item)

        # Tick marks along the measurement line
        line_len_img = math.hypot(ex - sx, ey - sy)
        if line_len_img > 20:
            scale = max(self.scale, 0.01)
            tick_step = ruler_step(scale)
            if line_len_img > 0 and tick_step > 0:
                ux = (ex - sx) / line_len_img
                uy = (ey - sy) / line_len_img
                px, py = -uy, ux  # perpendicular
                t = tick_step
                while t < line_len_img:
                    frac = t / line_len_img
                    tx = sx + (ex - sx) * frac
                    ty = sy + (ey - sy) * frac
                    is_major = (int(t) % (tick_step * 5) == 0) if tick_step else True
                    tl = max(4, int(6 / max(scale, 0.01))) if is_major else max(2, int(3 / max(scale, 0.01)))
                    tick_pen = QPen(QColor("#ff4444"), 1)
                    tick_pen.setCosmetic(True)
                    tick_line = self._scene.addLine(
                        tx - px * tl, ty - py * tl,
                        tx + px * tl, ty + py * tl,
                        tick_pen,
                    )
                    tick_line.setZValue(901)
                    add(tick_line)
                    t += tick_step

        data = {"start": (sx, sy), "end": (ex, ey), "dist": dist,
                "dx": dx_px, "dy": dy_px}
        if self.on_measure_update:
            self.on_measure_update(data)

    # ==================================================================
    # Floating ruler (Snip & Sketch style)
    # ==================================================================

    def toggle_floating_ruler(self) -> None:
        """Show or hide the floating ruler overlay."""
        if self._ruler_visible:
            self._hide_floating_ruler()
        else:
            self._show_floating_ruler()

    def _show_floating_ruler(self) -> None:
        """Position the ruler spanning the full viewport width."""
        self._ruler_visible = True
        scale = max(self.scale, 0.01)
        vw = self._view.viewport().width() or 800
        vh = self._view.viewport().height() or 600
        center_scene = self._view.mapToScene(vw // 2, vh // 2)
        self._ruler_cx = center_scene.x()
        self._ruler_cy = center_scene.y()
        # Span well beyond the viewport so it always covers the full width
        self._ruler_length = (max(vw, vh) + 400) / scale
        self._ruler_width = 54 / scale
        self._ruler_angle = 0.0
        self._draw_floating_ruler()

    def _hide_floating_ruler(self) -> None:
        """Remove all ruler items from the scene."""
        self._ruler_visible = False
        for item in self._ruler_items:
            self._scene.removeItem(item)
        self._ruler_items.clear()
        self._ruler_dragging = False
        self._ruler_redraw_pending = False

    def _draw_floating_ruler(self) -> None:
        """Draw the floating ruler using scene items (no PIL overhead).

        Creates a pill-shaped semi-transparent body with tick marks,
        numeric labels, and an angle bubble at the center.  All geometry
        is built axis-aligned then rotated via a parent group item so
        text and ticks stay crisp at any angle.
        """
        # Clear previous items
        for item in self._ruler_items:
            self._scene.removeItem(item)
        self._ruler_items.clear()
        if not self._ruler_visible:
            return

        scale = max(self.scale, 0.01)
        inv = 1.0 / scale  # scene-units-per-screen-pixel

        cx, cy = self._ruler_cx, self._ruler_cy
        angle = self._ruler_angle
        L, W = self._ruler_length, self._ruler_width
        hL, hW = L / 2, W / 2

        # Helper: rotate point around (cx, cy)
        a = math.radians(angle)
        ca, sa = math.cos(a), math.sin(a)

        def rot(lx: float, ly: float) -> tuple[float, float]:
            return cx + lx * ca - ly * sa, cy + lx * sa + ly * ca

        # --- Pill-shaped body ---
        r = hW
        n_arc = 12
        body_pts: list[QPointF] = []
        for i in range(n_arc + 1):
            theta = -math.pi / 2 + math.pi * i / n_arc
            rx, ry = rot(hL - r + r * math.cos(theta), r * math.sin(theta))
            body_pts.append(QPointF(rx, ry))
        for i in range(n_arc + 1):
            theta = math.pi / 2 + math.pi * i / n_arc
            rx, ry = rot(-hL + r + r * math.cos(theta), r * math.sin(theta))
            body_pts.append(QPointF(rx, ry))
        poly = QPolygonF(body_pts)
        body_brush = QBrush(QColor(200, 212, 228, 180))
        body_pen = QPen(QColor("#a0afc3"), 1)
        body_pen.setCosmetic(True)
        body_item = self._scene.addPolygon(poly, body_pen, body_brush)
        body_item.setZValue(800)
        self._ruler_items.append(body_item)

        # --- Edge line near measurement edge ---
        edge_y = -hW + 3 * inv
        ex1, ey1 = rot(-hL + r, edge_y)
        ex2, ey2 = rot(hL - r, edge_y)
        edge_pen = QPen(QColor("#647c8c"), 1)
        edge_pen.setCosmetic(True)
        edge_line = self._scene.addLine(ex1, ey1, ex2, ey2, edge_pen)
        edge_line.setZValue(801)
        self._ruler_items.append(edge_line)

        # --- Tick marks and labels ---
        step = ruler_step(scale)
        tick_spacing = step * scale  # screen pixels between ticks
        if tick_spacing < 2:
            tick_spacing = 10
            step = tick_spacing / scale
        tick_spacing_scene = tick_spacing * inv

        # Double the subdivisions: insert a minor tick between each step
        sub_step_scene = tick_spacing_scene / 2
        margin = r + 4 * inv
        x = margin
        sub_idx = 0  # counts sub-ticks (even = original, odd = new sub-division)
        while x < L - margin:
            lx = x - hL
            tick_idx = sub_idx // 2  # original tick index
            is_sub = (sub_idx % 2 == 1)

            if is_sub:
                h = W * 0.12
                color = QColor("#a0b0c4")
            elif tick_idx % 10 == 0:
                # Major
                h = W * 0.50
                color = QColor("#3a4e6a")
            elif tick_idx % 5 == 0:
                # Mid
                h = W * 0.35
                color = QColor("#4a6080")
            else:
                # Minor
                h = W * 0.18
                color = QColor("#8898b0")

            t1x, t1y = rot(lx, edge_y + inv)
            t2x, t2y = rot(lx, edge_y + inv + h)
            tick_pen = QPen(color, 1)
            tick_pen.setCosmetic(True)
            tick = self._scene.addLine(t1x, t1y, t2x, t2y, tick_pen)
            tick.setZValue(802)
            self._ruler_items.append(tick)

            # Number labels at major and mid ticks (not sub-ticks)
            if not is_sub and tick_idx > 0:
                is_major = (tick_idx % 10 == 0)
                is_mid = (tick_idx % 5 == 0) and not is_major
                if is_major or is_mid:
                    val = int(tick_idx * step)
                    if is_major:
                        font_size = max(1, int(9 * inv))
                        font = QFont("Segoe UI", font_size, QFont.Weight.Bold)
                        txt_color = QColor("#2c3e54")
                    else:
                        font_size = max(1, int(7 * inv))
                        font = QFont("Segoe UI", font_size)
                        txt_color = QColor("#5a6e88")

                    lbl = self._scene.addText(str(val), font)
                    lbl.setDefaultTextColor(txt_color)
                    # Position label along the ruler, offset from edge
                    label_y = edge_y + h + 4 * inv
                    lx2, ly2 = rot(lx, label_y)
                    lbl.setPos(lx2, ly2)
                    # Rotate around its own top-left so text follows the ruler
                    lbl.setRotation(angle)
                    # Shift so the label is centered on the tick
                    br = lbl.boundingRect()
                    lbl.setTransformOriginPoint(0, 0)
                    # Adjust position to center the text on the tick mark
                    offset_along = -br.width() / 2
                    offset_perp = 0
                    dx_off = offset_along * ca - offset_perp * sa
                    dy_off = offset_along * sa + offset_perp * ca
                    lbl.setPos(lx2 + dx_off, ly2 + dy_off)
                    lbl.setZValue(803)
                    self._ruler_items.append(lbl)

            x += sub_step_scene
            sub_idx += 1

        # --- Angle indicator bubble at center ---
        angle_display = round(self._ruler_angle) % 360
        if angle_display > 180:
            angle_display -= 360
        angle_text = f"{angle_display}\u00b0"

        bw, bh = 42 * inv, 20 * inv
        br = bh / 2
        bubble_pts: list[QPointF] = []
        for i in range(9):
            theta = -math.pi / 2 + math.pi * i / 8
            bx, by = rot(bw / 2 - br + br * math.cos(theta), br * math.sin(theta))
            bubble_pts.append(QPointF(bx, by))
        for i in range(9):
            theta = math.pi / 2 + math.pi * i / 8
            bx, by = rot(-bw / 2 + br + br * math.cos(theta), br * math.sin(theta))
            bubble_pts.append(QPointF(bx, by))
        bubble = self._scene.addPolygon(
            QPolygonF(bubble_pts),
            QPen(QColor("#5a7a98"), 1),
            QBrush(QColor("#3c5068")),
        )
        bubble.setZValue(804)
        self._ruler_items.append(bubble)

        font_size = max(1, int(9 * inv))
        angle_lbl = self._scene.addText(
            angle_text, QFont("Segoe UI", font_size, QFont.Weight.Bold))
        angle_lbl.setDefaultTextColor(QColor("white"))
        # Center the angle label on the ruler center
        angle_lbl.setRotation(angle)
        abr = angle_lbl.boundingRect()
        offset_along = -abr.width() / 2
        offset_perp = -abr.height() / 2
        dx_off = offset_along * ca - offset_perp * sa
        dy_off = offset_along * sa + offset_perp * ca
        angle_lbl.setPos(cx + dx_off, cy + dy_off)
        angle_lbl.setZValue(805)
        self._ruler_items.append(angle_lbl)

    def _schedule_ruler_redraw(self) -> None:
        """Throttled redraw — max ~60 fps to avoid excessive redraws."""
        if self._ruler_redraw_pending:
            return
        self._ruler_redraw_pending = True
        QTimer.singleShot(16, self._do_ruler_redraw)

    def _do_ruler_redraw(self) -> None:
        """Execute the pending ruler redraw."""
        self._ruler_redraw_pending = False
        self._draw_floating_ruler()

    def _point_on_ruler(self, scene_x: float, scene_y: float) -> bool:
        """Check if a scene point is within the ruler body."""
        dx = scene_x - self._ruler_cx
        dy = scene_y - self._ruler_cy
        angle_rad = math.radians(self._ruler_angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        along = dx * cos_a + dy * sin_a
        perp = -dx * sin_a + dy * cos_a
        return (abs(along) <= self._ruler_length / 2
                and abs(perp) <= self._ruler_width / 2)

    # ==================================================================
    # Events — main event filter
    # ==================================================================

    def eventFilter(self, obj, event) -> bool:
        """Central event dispatcher for the viewport.

        Intercepts mouse and wheel events on the viewport widget rather
        than subclassing QGraphicsView, keeping interaction logic in one
        place.
        """
        if obj is not self._view.viewport():
            return super().eventFilter(obj, event)

        etype = event.type()

        # Ctrl+Wheel → zoom
        if isinstance(event, QWheelEvent):
            return self._handle_wheel(event)

        if isinstance(event, QMouseEvent):
            if etype == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    return self._handle_left_press(event)
                if event.button() == Qt.MouseButton.RightButton:
                    return self._handle_right_press(event)

            if etype == event.Type.MouseMove:
                return self._handle_mouse_move(event)

            if etype == event.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    return self._handle_left_release(event)
                if event.button() == Qt.MouseButton.RightButton:
                    return self._handle_right_release(event)

            if etype == event.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.LeftButton:
                    return self._handle_double_click(event)

        return super().eventFilter(obj, event)

    # ==================================================================
    # Events — wheel (zoom / scroll)
    # ==================================================================

    def _handle_wheel(self, event: QWheelEvent) -> bool:
        """Ctrl+wheel zooms; plain wheel rotates ruler if cursor is on it."""
        # Ctrl+Scroll is always zoom, never ruler rotation
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._auto_fit = False
            delta = event.angleDelta().y()
            factor = 1.1 if delta > 0 else 1 / 1.1
            self.scale = max(0.1, min(5.0, self.scale * factor))
            self._apply_zoom()
            self.zoom_changed.emit(self.scale)
            self._redraw_measure()
            # Keep ruler visually the same screen size after zoom
            if self._ruler_visible:
                scale = max(self.scale, 0.01)
                self._ruler_width = 54 / scale
                self._schedule_ruler_redraw()
            event.accept()
            return True

        # Plain scroll over the ruler → rotate it
        if self._ruler_visible:
            scene_pos = self._view.mapToScene(event.position().toPoint())
            if self._point_on_ruler(scene_pos.x(), scene_pos.y()):
                up = event.angleDelta().y() > 0
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    delta_deg = 0.5 if up else -0.5  # fine rotation
                else:
                    delta_deg = 2 if up else -2
                self._ruler_angle = (self._ruler_angle + delta_deg) % 360
                self._schedule_ruler_redraw()
                event.accept()
                return True

        return False  # let QGraphicsView handle normal scrolling

    # ==================================================================
    # Events — left mouse button (draw / select)
    # ==================================================================

    def _handle_left_press(self, event: QMouseEvent) -> bool:
        """Start a new annotation drag, or click-select a movable annotation."""
        if not self.base_image:
            return False
        ix, iy = self._view_to_image(event.position())

        # Floating ruler intercepts left-click if cursor is on it
        if self._ruler_visible:
            scene_pos = self._view.mapToScene(event.position().toPoint())
            if self._point_on_ruler(scene_pos.x(), scene_pos.y()):
                self._ruler_dragging = True
                self._ruler_drag_offset = (
                    scene_pos.x() - self._ruler_cx,
                    scene_pos.y() - self._ruler_cy,
                )
                return True

        # Measurement mode: record start point
        if self._measure_mode:
            self._measure_start = (ix, iy)
            return True

        # If text editor is open, commit it first (clicking outside)
        if self._text_editor is not None:
            self._commit_text_editor()
            return True

        # IMAGE tool with pending image → start placement drag
        if self.current_shape == Tool.IMAGE and self.pending_image is not None:
            self._drag_start = (ix, iy)
            self._deselect()
            return True

        # Click on a movable annotation (TEXT / IMAGE) → select it
        ann_idx = self._find_movable_at(ix, iy)
        if ann_idx is not None:
            self.select_annotation(ann_idx)
            self._drag_start = None
            return True

        # Click elsewhere → deselect and start drag for current tool
        self._deselect()
        self._drag_start = (ix, iy)

        # Freehand: begin collecting points
        if self.current_shape == Tool.FREEHAND:
            self._freehand_points = [(ix, iy)]

        return True

    def _handle_left_release(self, event: QMouseEvent) -> bool:
        """Finish the annotation drag and commit the new annotation."""
        # Ruler drag release
        if self._ruler_dragging:
            self._ruler_dragging = False
            return True

        # Measurement mode: draw measurement between start and end
        if self._measure_mode and self._measure_start is not None:
            ix, iy = self._view_to_image(event.position())
            sx, sy = self._measure_start
            self._measure_start = None
            if abs(ix - sx) > 3 or abs(iy - sy) > 3:
                self._clear_measure()
                self._measure_pts = (sx, sy, ix, iy)
                self._draw_measure_line(sx, sy, ix, iy)
            return True

        if self._drag_start is None:
            return False
        self._clear_preview()
        sx, sy = self._drag_start
        ix, iy = self._view_to_image(event.position())
        self._drag_start = None

        # Tiny drag ≈ click — try to select instead
        if abs(ix - sx) < 3 and abs(iy - sy) < 3:
            ann_idx = self._find_movable_at(ix, iy)
            self.select_annotation(ann_idx)
            return True

        active = self._active_tools()
        if not active:
            return True

        # TEXT tool → open inline editor directly on the canvas
        if Tool.TEXT in active:
            self._push_undo()
            self.show_inline_text_editor(sx, sy, ix, iy)
            self.text_edit_requested.emit(-1)  # signal with -1 = new text box
            return True

        # IMAGE tool → place pending image fitted to aspect ratio
        if Tool.IMAGE in active and self.pending_image is not None:
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
            self._push_undo()
            self.annotations.append(Annotation(
                tools=frozenset({Tool.IMAGE}),
                x1=sx, y1=sy, x2=ix, y2=iy,
                color=self.current_color,
                opacity=self.current_opacity,
                image_data=self.pending_image.copy(),
            ))
            self.pending_image = None
            self._cache_dirty = True
            self._refresh()
            return True

        # FREEHAND tool → commit polyline annotation
        if Tool.FREEHAND in active and len(self._freehand_points) >= 2:
            self._push_undo()
            pts = self._freehand_points
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            self.annotations.append(Annotation(
                tools=active,
                x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys),
                color=self.current_color,
                opacity=self.current_opacity,
                line_width=self.current_width,
                line_style=self.current_line_style,
                points=list(pts),
            ))
            self._freehand_points = []
            self._cache_dirty = True
            self._refresh()
            return True
        self._freehand_points = []

        # Effects / shapes → create the annotation
        self._push_undo()
        self.annotations.append(Annotation(
            tools=active,
            x1=sx, y1=sy, x2=ix, y2=iy,
            color=self.current_color,
            opacity=self.current_opacity,
            line_width=self.current_width,
            lift_zoom=self.current_lift_zoom,
            line_style=self.current_line_style,
            arrow_head=self.current_arrow_head,
            curve_offset=self.current_curve_offset,
            bracket_style=self.current_bracket_style,
            polygon_sides=self.current_polygon_sides,
            star_inner_ratio=self.current_star_inner_ratio,
            connector_style=self.current_connector_style,
            gradient_type=self.current_gradient_type,
            gradient_color2=self.current_gradient_color2,
        ))
        self._cache_dirty = True
        self._refresh()
        return True

    def _handle_double_click(self, event: QMouseEvent) -> bool:
        """Double-click on a TEXT annotation to open it for editing."""
        if not self.base_image:
            return False
        ix, iy = self._view_to_image(event.position())
        idx = self._find_text_at(ix, iy)
        if idx is not None:
            self._deselect()
            # Restore formatting state from the annotation
            ann = self.annotations[idx]
            self.current_font_family = ann.font_family
            self.current_font_size = ann.font_size
            self.current_font_bold = ann.font_bold
            self.current_font_italic = ann.font_italic
            self.current_font_color = ann.font_color
            self.current_text_bg = ann.bg_color
            self.current_line_spacing = ann.line_spacing
            if self.on_text_edit_start:
                self.on_text_edit_start()
            # Re-open inline editor with existing content
            if ann.text_runs:
                self.show_inline_text_editor(
                    ann.x1, ann.y1, ann.x2, ann.y2,
                    initial_runs=ann.text_runs, editing_idx=idx)
            else:
                self.show_inline_text_editor(
                    ann.x1, ann.y1, ann.x2, ann.y2,
                    initial_text=ann.text, editing_idx=idx)
            self.text_edit_requested.emit(idx)
            return True
        return False

    # ==================================================================
    # Events — right mouse button (move / resize)
    # ==================================================================

    def _handle_right_press(self, event: QMouseEvent) -> bool:
        """Right-click on a movable annotation to begin move/resize."""
        if not self.base_image:
            return False
        ix, iy = self._view_to_image(event.position())
        idx = self._find_movable_at(ix, iy)
        if idx is None:
            return False
        a = self.annotations[idx]
        self._moving_ann_idx = idx
        self._move_start_img = (ix, iy)
        self._push_undo()

        # Resize handle check (IMAGE annotations only)
        if Tool.IMAGE in a.tools:
            handle = self._hit_test_handle(a, ix, iy)
            if handle:
                self._resize_handle = handle
                self._view.viewport().setCursor(_HANDLE_CURSORS[handle])
                return True

        self._resize_handle = None
        self._view.viewport().setCursor(Qt.CursorShape.SizeAllCursor)

        # --- Lightweight drag preview ---
        # Render the annotation region into a small QPixmap overlay so that
        # mouse-move only repositions a Qt item instead of re-running the
        # full PIL pipeline on every pixel.
        ann = self.annotations[idx]
        ax1, ay1 = min(ann.x1, ann.x2), min(ann.y1, ann.y2)
        ax2, ay2 = max(ann.x1, ann.x2), max(ann.y1, ann.y2)
        rw, rh = max(ax2 - ax1, 1), max(ay2 - ay1, 1)

        # Render just this one annotation onto a transparent base
        single_base = Image.new("RGBA", (ax2, ay2), (0, 0, 0, 0))
        single_rendered = render_annotations(single_base, [ann])
        cropped = single_rendered.crop((ax1, ay1, ax2, ay2))
        single_rendered.close()
        single_base.close()
        overlay_pixmap = _pil_to_qpixmap(cropped)
        cropped.close()

        self._drag_overlay = QGraphicsPixmapItem(overlay_pixmap)
        self._drag_overlay.setPos(ax1, ay1)
        self._drag_overlay.setZValue(1000)
        self._scene.addItem(self._drag_overlay)

        # Re-render the page *without* the dragged annotation so the
        # background stays correct while dragging.
        saved = self.annotations[idx]
        self.annotations.pop(idx)
        self._refresh()
        self.annotations.insert(idx, saved)

        return True

    def _handle_right_release(self, event: QMouseEvent) -> bool:
        """Finish move/resize and restore the crosshair cursor."""
        if self._moving_ann_idx is None:
            return False
        # Remove lightweight drag overlay
        if self._drag_overlay is not None:
            self._scene.removeItem(self._drag_overlay)
            self._drag_overlay = None
        self._moving_ann_idx = None
        self._move_start_img = None
        self._resize_handle = None
        self._view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        # Commit: single full refresh at final position
        self._cache_dirty = True
        self._refresh()
        return True

    # ==================================================================
    # Events — mouse move (drag / hover cursor)
    # ==================================================================

    def _handle_mouse_move(self, event: QMouseEvent) -> bool:
        """Route mouse-move to drag handlers or update the hover cursor."""
        if not self.base_image:
            return False
        ix, iy = self._view_to_image(event.position())

        # Ruler dragging
        if self._ruler_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            scene_pos = self._view.mapToScene(event.position().toPoint())
            off_x, off_y = self._ruler_drag_offset
            self._ruler_cx = scene_pos.x() - off_x
            self._ruler_cy = scene_pos.y() - off_y
            self._schedule_ruler_redraw()
            return True

        # Measurement mode: draw preview line while dragging
        if self._measure_mode and self._measure_start is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                sx, sy = self._measure_start
                # Draw temporary preview line
                self._clear_measure()
                self._draw_measure_line(sx, sy, ix, iy)
                return True

        # Left-button drag → rubber-band preview
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start:
            sx, sy = self._drag_start
            # Freehand: accumulate points
            if self.current_shape == Tool.FREEHAND:
                self._freehand_points.append((ix, iy))
            self._draw_preview(sx, sy, ix, iy)
            return True

        # Right-button drag → move or resize annotation
        if event.buttons() & Qt.MouseButton.RightButton:
            return self._handle_right_drag(ix, iy)

        # No buttons → update hover cursor
        self._update_hover_cursor(ix, iy)
        return False

    def _handle_right_drag(self, ix: int, iy: int) -> bool:
        """Move or resize the annotation being right-dragged."""
        if self._moving_ann_idx is None or self._move_start_img is None:
            return False
        sx, sy = self._move_start_img
        a = self.annotations[self._moving_ann_idx]

        if self._resize_handle:
            # Resize: edges stretch freely, corners lock aspect ratio
            x1, y1 = min(a.x1, a.x2), min(a.y1, a.y2)
            x2, y2 = max(a.x1, a.x2), max(a.y1, a.y2)
            ow, oh = max(x2 - x1, 1), max(y2 - y1, 1)
            ar = ow / oh
            h = self._resize_handle
            if "w" in h: x1 = ix
            if "e" in h: x2 = ix
            if "n" in h: y1 = iy
            if "s" in h: y2 = iy
            # Corner handles: constrain to original aspect ratio
            if len(h) == 2:
                nw, nh = max(x2 - x1, 1), max(y2 - y1, 1)
                if nw / nh > ar:
                    nw = int(nh * ar)
                else:
                    nh = int(nw / ar)
                if "w" in h: x1 = x2 - nw
                else:        x2 = x1 + nw
                if "n" in h: y1 = y2 - nh
                else:        y2 = y1 + nh
            self.annotations[self._moving_ann_idx] = dc_replace(
                a, x1=x1, y1=y1, x2=x2, y2=y2)
            # Resize still needs full refresh (changing size)
            self._move_start_img = (ix, iy)
            self._cache_dirty = True
            self._refresh()
        else:
            # Move: translate, clamped to image bounds
            dx, dy = ix - sx, iy - sy
            nx1, ny1, nx2, ny2 = a.x1 + dx, a.y1 + dy, a.x2 + dx, a.y2 + dy
            if self.base_image is not None:
                iw, ih = self.base_image.size
                if nx1 < 0: nx2 -= nx1; nx1 = 0
                if ny1 < 0: ny2 -= ny1; ny1 = 0
                if nx2 > iw: nx1 -= (nx2 - iw); nx2 = iw
                if ny2 > ih: ny1 -= (ny2 - ih); ny2 = ih
            self.annotations[self._moving_ann_idx] = dc_replace(
                a, x1=nx1, y1=ny1, x2=nx2, y2=ny2)

            # Lightweight move: just reposition the Qt overlay item
            if self._drag_overlay is not None:
                self._drag_overlay.setPos(min(nx1, nx2), min(ny1, ny2))
            self._move_start_img = (ix, iy)
            self._cache_dirty = True

        return True

    def _update_hover_cursor(self, ix: int, iy: int) -> None:
        """Set the viewport cursor based on what's under the mouse."""
        # Ruler pointer
        if self._ruler_visible:
            scene_pos = self._view.mapToScene(
                self._view.mapFromGlobal(QCursor.pos()))
            if self._point_on_ruler(scene_pos.x(), scene_pos.y()):
                self._view.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
                return

        idx = self._find_movable_at(ix, iy)
        if idx is not None:
            a = self.annotations[idx]
            if Tool.IMAGE in a.tools:
                handle = self._hit_test_handle(a, ix, iy)
                if handle:
                    self._view.viewport().setCursor(_HANDLE_CURSORS[handle])
                    return
            self._view.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self._view.viewport().setCursor(Qt.CursorShape.CrossCursor)

    # ==================================================================
    # Key events
    # ==================================================================

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Delete and Escape keys for annotation management."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._text_editor is not None:
                return  # let the text editor handle Delete/Backspace
            self._delete_selected()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._text_editor is not None:
                self._commit_text_editor()
                return
            self._deselect()
            return
        super().keyPressEvent(event)

    def _delete_selected(self) -> None:
        """Delete the currently selected annotation after confirmation."""
        idx = self._selected_ann_idx
        if idx is None or idx >= len(self.annotations):
            return
        ann = self.annotations[idx]
        kind = ("text box" if Tool.TEXT in ann.tools
                else "image" if Tool.IMAGE in ann.tools
                else "annotation")
        reply = QMessageBox.question(
            self, "Delete", f"Delete this {kind}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._view.viewport().setFocus()
            return
        self._deselect()
        self._push_undo()
        self.annotations.pop(idx)
        self._cache_dirty = True
        self._refresh()
        # Restore viewport focus so subsequent clicks work immediately
        self._view.viewport().setFocus()

    # ==================================================================
    # Resize event — auto-fit
    # ==================================================================

    def resizeEvent(self, event) -> None:
        """Re-fit the image when the widget is resized (if auto-fit is on)."""
        super().resizeEvent(event)
        if self._auto_fit and self.base_image is not None:
            QTimer.singleShot(0, self.fit_to_frame)
