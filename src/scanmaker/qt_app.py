"""BurhanApp — PySide6 (Qt6) main application window."""

import os
import sys

from PIL import Image

from PySide6.QtCore import Qt, Slot, Signal, QTimer, QRectF, QRect, QSize, QPoint
from PySide6.QtGui import (
    QAction, QIcon, QPixmap, QFont, QColor, QKeySequence,
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolButton, QLabel, QPushButton, QLineEdit, QSlider, QComboBox,
    QCheckBox, QFileDialog, QColorDialog, QMessageBox, QScrollArea, QFrame,
    QSplitter, QSizePolicy, QDialog,
    QLayout,
)

from .models import Annotation, Tool
from .qt_canvas import AnnotationCanvas, _pil_to_qpixmap
from .rendering import (
    pdf_pages_to_images, merge_images, render_annotations,
    _build_font_map, _FONT_MAP,
)
from .utils import parse_page_ranges
from .theme import get_qss, get_palette
from .updater import check_for_update

# --- Locate bundled data / assets ---
if getattr(sys, "frozen", False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ASSETS_DIR = os.path.join(_BASE_DIR, "assets")
BANNER_DARK = os.path.join(_ASSETS_DIR, "Bring_evidence2_dark.png")
BANNER_LIGHT = os.path.join(_ASSETS_DIR, "Bring_evidence2_light.png")


# ── Flow Layout ──────────────────────────────────────────────────────

class _FlowLayout(QLayout):
    """Horizontal flow layout that wraps items to new rows automatically."""

    def __init__(self, parent=None, margin=6, h_spacing=6, v_spacing=4):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, apply_geom):
        m = self.contentsMargins()
        effective = QRect(
            rect.x() + m.left(), rect.y() + m.top(),
            rect.width() - m.left() - m.right(),
            rect.height() - m.top() - m.bottom(),
        )
        x = effective.x()
        y = effective.y()
        row_height = 0

        for item in self._items:
            wid = item.widget()
            if wid and not wid.isVisible():
                continue
            sz = item.sizeHint()
            next_x = x + sz.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() + 1 and row_height > 0:
                x = effective.x()
                y += row_height + self._v_spacing
                next_x = x + sz.width() + self._h_spacing
                row_height = 0
            if apply_geom:
                item.setGeometry(QRect(QPoint(x, y), sz))
            x = next_x
            row_height = max(row_height, sz.height())

        return y + row_height - rect.y() + m.bottom()


class BurhanApp(QMainWindow):

    _update_available = Signal(str, str)  # tag, url

    def __init__(self):
        super().__init__()
        self._theme_name = "dark"

        self.setWindowTitle("BurhanApp  \u2014  \u0642\u064f\u0644\u0652 \u0647\u064e\u0627\u062a\u064f\u0648\u0652 \u0628\u064f\u0631\u0652\u0647\u064e\u0627\u0646\u064e\u0643\u064f\u0645\u0652")
        self.resize(1280, 860)
        self.setMinimumSize(1000, 700)
        self._set_icon()

        # Page data
        self.pages = []                          # list[PIL.Image]
        self.page_annotations: dict[int, list[Annotation]] = {}
        self.page_undo: dict[int, list] = {}
        self.page_redo: dict[int, list] = {}
        self.current_page_idx: int = -1

        self._build_ui()
        self._apply_theme()
        self._bind_shortcuts()
        self._update_available.connect(self._show_update_dialog)
        check_for_update(self._on_update_result)

    # ------------------------------------------------------------------
    # Icon
    # ------------------------------------------------------------------

    def _set_icon(self):
        icon_path = os.path.join(_ASSETS_DIR, "BurhanApp.ico")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self):
        self.setStyleSheet(get_qss(self._theme_name))
        pal = get_palette(self._theme_name)
        self.editor.setStyleSheet(f"background-color: {pal['editor_bg']};")

    def _on_update_result(self, tag, url):
        """Called from background thread; emit signal to main thread."""
        if tag and url:
            self._update_available.emit(tag, url)

    @Slot(str, str)
    def _show_update_dialog(self, tag, url):
        import webbrowser
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setText(f"A new version <b>{tag}</b> is available!")
        msg.setInformativeText("Would you like to open the download page?")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        if msg.exec() == QMessageBox.StandardButton.Yes:
            webbrowser.open(url)

    @Slot()
    def _toggle_theme(self):
        self._theme_name = "light" if self._theme_name == "dark" else "dark"
        self._apply_theme()
        self._load_banner()
        # Update toggle icon and checkbox state
        self._theme_icon.setText("\u2600\ufe0f" if self._theme_name == "light" else "\U0001f319")
        self._theme_toggle.blockSignals(True)
        self._theme_toggle.setChecked(self._theme_name == "light")
        self._theme_toggle.blockSignals(False)
        # Re-apply thumbnail highlight for new theme
        if self.pages and self.thumb_widgets:
            self._select_page(self.current_page_idx)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # === HEADER ===
        header = QFrame()
        header.setObjectName("panel")
        header.setFixedHeight(90)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.addStretch()
        self._banner_label = QLabel()
        self._banner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self._banner_label)
        self._load_banner()
        header_layout.addStretch()

        # Theme toggle
        self._theme_toggle = QCheckBox()
        self._theme_toggle.setObjectName("theme_toggle")
        self._theme_toggle.setChecked(self._theme_name == "light")
        self._theme_toggle.setToolTip("Toggle light / dark theme")
        self._theme_toggle.setFixedSize(56, 30)
        self._theme_toggle.toggled.connect(self._toggle_theme)

        theme_box = QHBoxLayout()
        theme_box.setContentsMargins(0, 0, 12, 0)
        theme_box.setSpacing(8)
        self._theme_icon = QLabel("\U0001f319" if self._theme_name == "dark" else "\u2600\ufe0f")
        self._theme_icon.setStyleSheet("font-size: 16px; background: transparent;")
        theme_box.addWidget(self._theme_icon)
        theme_box.addWidget(self._theme_toggle)
        header_layout.addLayout(theme_box)
        main_layout.addWidget(header)

        # === INPUT BAR ===
        input_bar = QFrame()
        input_bar.setObjectName("panel")
        ib_layout = _FlowLayout(input_bar, margin=8, h_spacing=8, v_spacing=8)

        def _ib_group():
            f = QFrame()
            f.setObjectName("tool_group")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(8)
            return f, lay

        # ── PDF file group ──
        g_pdf, l_pdf = _ib_group()
        l_pdf.addWidget(QLabel("\U0001f4c4 PDF:"))
        self.pdf_entry = QLineEdit()
        self.pdf_entry.setPlaceholderText("Select a PDF file...")
        self.pdf_entry.setMinimumWidth(150)
        l_pdf.addWidget(self.pdf_entry)
        browse_pdf_btn = QPushButton("Browse")
        browse_pdf_btn.clicked.connect(self._browse_pdf)
        l_pdf.addWidget(browse_pdf_btn)
        l_pdf.addWidget(QLabel("Pages:"))
        self.pages_entry = QLineEdit()
        self.pages_entry.setPlaceholderText("e.g. 1-3, 5, 8")
        self.pages_entry.setFixedWidth(120)
        l_pdf.addWidget(self.pages_entry)
        l_pdf.addWidget(QLabel("DPI:"))
        self.dpi_entry = QLineEdit("300")
        self.dpi_entry.setFixedWidth(50)
        l_pdf.addWidget(self.dpi_entry)
        load_pdf_btn = QPushButton("\u25b6  Load Pages")
        load_pdf_btn.setObjectName("green")
        load_pdf_btn.clicked.connect(self._load_pages)
        l_pdf.addWidget(load_pdf_btn)
        ib_layout.addWidget(g_pdf)

        # ── Images group ──
        g_img, l_img = _ib_group()
        l_img.addWidget(QLabel("\U0001f5bc Images:"))
        self._img_label = QLabel("No images selected")
        self._img_label.setMinimumWidth(120)
        l_img.addWidget(self._img_label)
        browse_img_btn = QPushButton("Browse")
        browse_img_btn.clicked.connect(self._browse_images)
        l_img.addWidget(browse_img_btn)
        load_img_btn = QPushButton("\u25b6  Load Images")
        load_img_btn.setObjectName("green")
        load_img_btn.clicked.connect(self._load_images)
        l_img.addWidget(load_img_btn)
        ib_layout.addWidget(g_img)

        # ── Reset group ──
        g_act, l_act = _ib_group()
        reset_btn = QPushButton("\u21ba  Reset")
        reset_btn.setObjectName("red")
        reset_btn.clicked.connect(self._reset)
        l_act.addWidget(reset_btn)
        ib_layout.addWidget(g_act)
        main_layout.addWidget(input_bar)

        # === CONTENT AREA ===
        content = QSplitter(Qt.Orientation.Horizontal)
        content.setContentsMargins(0, 0, 0, 0)
        content.setHandleWidth(12)

        # -- Sidebar (page thumbnails) --
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("panel")
        sidebar_frame.setFixedWidth(160)
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)
        lbl = QLabel("\U0001F4D1  Pages")
        lbl.setObjectName("gold")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(lbl)
        _sidebar_sep = QFrame()
        _sidebar_sep.setObjectName("sidebar_sep")
        _sidebar_sep.setFixedHeight(1)
        sidebar_layout.addWidget(_sidebar_sep)

        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sidebar_container = QWidget()
        self._sidebar_layout = QVBoxLayout(self._sidebar_container)
        self._sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._sidebar_layout.setSpacing(8)
        self._sidebar_layout.setContentsMargins(4, 8, 4, 8)
        sidebar_scroll.setWidget(self._sidebar_container)
        sidebar_layout.addWidget(sidebar_scroll)
        self.thumb_widgets: list[QPushButton] = []
        self._selected_image_paths: list[str] = []

        content.addWidget(sidebar_frame)

        # -- Center (toolbar + editor) --
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        # Editor (annotation canvas) — created before toolbar so toolbar can reference it
        self.editor = AnnotationCanvas()
        self.editor.zoom_changed.connect(self._on_zoom_changed)
        self.editor.text_edit_requested.connect(self._on_text_edit_requested)
        self.editor.on_text_edit_start = self._on_text_edit_start

        # Toolbar (two rows + optional text format row)
        self._build_toolbar()
        self._refresh_tool_buttons()  # set initial control visibility
        center_layout.addWidget(self._toolbar)
        center_layout.addWidget(self._text_toolbar)
        center_layout.addWidget(self.editor, stretch=1)

        # Page nav bar
        nav_bar = QFrame()
        nav_bar.setObjectName("panel")
        nav_bar.setFixedHeight(42)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(12, 4, 12, 4)
        self._prev_btn = QPushButton("\u25C0  Prev")
        self._prev_btn.clicked.connect(self._prev_page)
        nav_layout.addWidget(self._prev_btn)
        self._page_label = QLabel("No pages loaded")
        self._page_label.setObjectName("dim")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self._page_label, stretch=1)
        self._next_btn = QPushButton("Next  \u25B6")
        self._next_btn.clicked.connect(self._next_page)
        nav_layout.addWidget(self._next_btn)
        center_layout.addWidget(nav_bar)

        content.addWidget(center)

        # -- Hints panel (inside splitter, right side) --
        self._hints_panel = QFrame()
        self._hints_panel.setObjectName("panel")
        self._hints_panel.setMinimumWidth(280)
        hints_panel_layout = QVBoxLayout(self._hints_panel)
        hints_panel_layout.setContentsMargins(0, 0, 0, 0)
        hints_panel_layout.setSpacing(0)

        # Title bar
        _hints_title_bar = QFrame()
        _hints_title_bar.setObjectName("tool_group")
        _hints_title_bar.setFixedHeight(42)
        _htb_layout = QHBoxLayout(_hints_title_bar)
        _htb_layout.setContentsMargins(12, 0, 8, 0)
        _htb_layout.setSpacing(8)
        _hints_lbl = QLabel("Quick Guide")
        _hints_lbl.setObjectName("gold")
        _hints_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        _hints_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        _htb_layout.addWidget(_hints_lbl)
        _htb_layout.addStretch()
        _hints_close = QPushButton("✕")
        _hints_close.setFixedSize(24, 24)
        _hints_close.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #e2e4e9;"
            " font-size: 16px; padding: 0; line-height: 24px; }"
            "QPushButton:hover { color: #f87171; }"
        )
        _hints_close.clicked.connect(lambda: self._toggle_hints())
        _htb_layout.addWidget(_hints_close, alignment=Qt.AlignmentFlag.AlignVCenter)
        hints_panel_layout.addWidget(_hints_title_bar)

        # Scrollable content
        hints_content = QScrollArea()
        hints_content.setWidgetResizable(True)
        hints_widget = QWidget()
        hints_layout = QVBoxLayout(hints_widget)
        hints_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        hints_layout.setSpacing(8)
        hints_layout.setContentsMargins(8, 8, 8, 8)
        hints = [
            # --- Drawing ---
            ("\U0001F58C Left-click + drag",
             "Draw the selected effect or shape in a rectangular region. "
             "Multiple effects (Highlight, Underline, Border, Lift) can be combined on one drag."),
            ("\U0001F5BC Image tool",
             "Click Image, pick a file, then right-click drag to move it. "
             "Drag corner handles to resize (aspect ratio locked). Edge handles stretch freely."),
            ("\U0001F4DD Text tool",
             "Click Text, drag a box, then type inside it. "
             "Use the formatting bar to set font, size, bold, italic, color, and background. "
             "Double-click an existing text box to re-edit it."),
            # --- Selection & editing ---
            ("\u2195 Right-click drag",
             "Right-click on a text box or image to move it. "
             "On images, drag edge or corner handles to resize."),
            ("\U0001F5D1 Delete / Backspace",
             "Click an annotation to select it (marching-ants border), "
             "then press Delete or Backspace to remove it."),
            ("\u2716 Clear",
             "Remove all annotations from this page."),
            # --- Keyboard shortcuts ---
            ("\u2328 Keyboard shortcuts",
             "Ctrl+Z  Undo  \u2022  Ctrl+Y  Redo  \u2022  Ctrl+Shift+Z  Undo\n"
             "\u2190 / \u2192  Previous / Next page\n"
             "PgUp / PgDn  Previous / Next page\n"
             "Escape  Finish text editing or deselect"),
            # --- Zoom & navigation ---
            ("\U0001F50D Ctrl + Scroll",
             "Zoom into the canvas (10% \u2013 500%). "
             "Use Fit / 1\u00d7 / 2\u00d7 buttons or the zoom slider for precise control."),
            # --- Ruler ---
            ("\U0001F4CF Ruler",
             "Toggle the floating ruler overlay. "
             "Scroll over it to rotate (\u00b12\u00b0). "
             "Hold Shift + Scroll for fine rotation (\u00b10.5\u00b0). "
             "Left-click drag the ruler to reposition it."),
            # --- Color & sliders ---
            ("\U0001F3A8 Color & sliders",
             "Pick a preset color or press + for a custom color.\n"
             "Opacity  5\u2013100%  \u2022  Width  1\u201325 px  \u2022  Lift zoom  100\u2013150%"),
            # --- Export ---
            ("\U0001F4E5 Export",
             "Set output path, choose language direction (RTL/LTR), "
             "optionally add a watermark, then click Export. "
             "Use Preview to check the merged result first."),
        ]
        for title, desc in hints:
            card = QFrame()
            card.setObjectName("hint_card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(4)
            t = QLabel(title)
            t.setObjectName("gold")
            t.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            t.setWordWrap(True)
            card_layout.addWidget(t)
            d = QLabel(desc)
            d.setObjectName("dim")
            d.setWordWrap(True)
            d.setFont(QFont("Segoe UI", 14))
            card_layout.addWidget(d)
            hints_layout.addWidget(card)
        hints_content.setWidget(hints_widget)
        hints_panel_layout.addWidget(hints_content)

        content.addWidget(self._hints_panel)
        content.setStretchFactor(0, 0)   # sidebar: fixed
        content.setStretchFactor(1, 1)   # center: stretch
        content.setStretchFactor(2, 0)   # hints: fixed
        content.setSizes([140, 9999, 280])

        main_layout.addWidget(content, stretch=1)

        # === EXPORT BAR ===
        export_bar = QFrame()
        export_bar.setObjectName("panel")
        eb_layout = _FlowLayout(export_bar, margin=8, h_spacing=8, v_spacing=8)

        def _eb_group():
            """Create a grouped container for export bar controls."""
            f = QFrame()
            f.setObjectName("tool_group")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(8)
            return f, lay

        # ── Language group ──
        g_lang, l_lang = _eb_group()
        l_lang.addWidget(QLabel("Language:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Arabic (RTL)", "English (LTR)"])
        self._lang_combo.setFixedWidth(150)
        l_lang.addWidget(self._lang_combo)
        eb_layout.addWidget(g_lang)

        # ── Watermark group ──
        g_wm, l_wm = _eb_group()
        self._wm_enabled = QCheckBox("Watermark")
        l_wm.addWidget(self._wm_enabled)
        self._wm_entry = QLineEdit()
        self._wm_entry.setPlaceholderText("watermark text")
        self._wm_entry.setFixedWidth(120)
        l_wm.addWidget(self._wm_entry)
        self._wm_color: tuple[int, int, int] = (0, 255, 0)
        self._wm_color_btn = QPushButton("\u25cf")
        self._wm_color_btn.setFixedSize(32, 32)
        self._wm_color_btn.setStyleSheet(
            "background-color: #00ff00; border-radius: 16px; font-size: 16px;"
        )
        self._wm_color_btn.clicked.connect(self._choose_wm_color)
        l_wm.addWidget(self._wm_color_btn)
        self._wm_pos_combo = QComboBox()
        self._wm_pos_combo.addItems([
            "Center", "Top-Left", "Top-Center", "Top-Right",
            "Left-Center", "Right-Center",
            "Bottom-Left", "Bottom-Center", "Bottom-Right", "Tiled",
        ])
        self._wm_pos_combo.setFixedWidth(120)
        self._wm_pos_combo.setToolTip("Watermark position on the merged image")
        l_wm.addWidget(self._wm_pos_combo)
        self._wm_orient_combo = QComboBox()
        self._wm_orient_combo.addItems(["Diagonal", "Horizontal", "Vertical"])
        self._wm_orient_combo.setFixedWidth(90)
        self._wm_orient_combo.setToolTip("Watermark text orientation")
        l_wm.addWidget(self._wm_orient_combo)
        l_wm.addWidget(QLabel("Opacity:"))
        self._wm_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._wm_opacity_slider.setRange(5, 100)
        self._wm_opacity_slider.setValue(60)
        self._wm_opacity_slider.setFixedWidth(60)
        self._wm_opacity_slider.setToolTip("Watermark opacity")
        l_wm.addWidget(self._wm_opacity_slider)
        l_wm.addWidget(QLabel("Size:"))
        self._wm_size_slider = QSlider(Qt.Orientation.Horizontal)
        self._wm_size_slider.setRange(10, 200)
        self._wm_size_slider.setValue(100)
        self._wm_size_slider.setFixedWidth(60)
        self._wm_size_slider.setToolTip("Watermark size (10\u2013200%)")
        l_wm.addWidget(self._wm_size_slider)
        eb_layout.addWidget(g_wm)

        # ── Output group ──
        g_out, l_out = _eb_group()
        l_out.addWidget(QLabel("Output:"))
        self._out_entry = QLineEdit()
        self._out_entry.setPlaceholderText("output file path...")
        self._out_entry.setMinimumWidth(150)
        l_out.addWidget(self._out_entry)
        browse_out = QPushButton("Browse")
        browse_out.clicked.connect(self._browse_output)
        l_out.addWidget(browse_out)
        preview_btn = QPushButton("\U0001f50d  Preview")
        preview_btn.setObjectName("preview_btn")
        preview_btn.clicked.connect(self._preview)
        l_out.addWidget(preview_btn)
        export_btn = QPushButton("\u2b07  Export Merged")
        export_btn.setObjectName("export_btn")
        export_btn.clicked.connect(self._export)
        l_out.addWidget(export_btn)
        eb_layout.addWidget(g_out)

        main_layout.addWidget(export_bar)

    def _build_toolbar(self):
        """Build the main toolbar with two wrapping rows."""

        def _group(label=None):
            f = QFrame()
            f.setObjectName("tool_group")
            lay = QHBoxLayout(f)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(8)
            if label:
                lbl = QLabel(label)
                lbl.setObjectName("group_label")
                lay.addWidget(lbl)
            return f, lay

        # ── Container for both rows ──
        self._toolbar = QWidget()
        self._toolbar.setObjectName("toolbar_area")
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self._toolbar.setSizePolicy(policy)
        outer = QVBoxLayout(self._toolbar)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(4)

        # ═══ ROW 1: Drawing tools │ Actions │ Tools (wrapping) ═══
        row1_w = QWidget()
        row1_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row1_policy.setHeightForWidth(True)
        row1_w.setSizePolicy(row1_policy)
        row1 = _FlowLayout(row1_w, margin=0, h_spacing=8, v_spacing=8)

        # --- Effects ---
        ef, el = _group("Effects")
        self.effect_buttons: dict[Tool, QToolButton] = {}
        for tool, label, tip in [
            (Tool.HIGHLIGHT, "Highlight", "Semi-transparent highlight"),
            (Tool.UNDERLINE, "Underline", "Draw an underline beneath text"),
            (Tool.BORDER, "Border", "Draw a border around area"),
            (Tool.TEXT_LIFT, "Lift", "Enlarge text in selected region"),
        ]:
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setChecked(tool in self.editor.current_effects)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda checked, t=tool: self._toggle_effect(t))
            el.addWidget(btn)
            self.effect_buttons[tool] = btn
        row1.addWidget(ef)

        # --- Shapes ---
        sf, sl = _group("Shapes")
        self.shape_buttons: dict[Tool, QToolButton] = {}
        for tool, label, tip in [
            (Tool.ARROW, "Arrow", "Draw an arrow"),
            (Tool.CURVED_ARROW, "Curve", "Draw a curved arrow"),
            (Tool.LINE, "Line", "Draw a straight line"),
            (Tool.RECTANGLE, "Rect", "Draw a rectangle"),
            (Tool.ROUNDED_RECT, "Rounded", "Draw a rounded rectangle"),
            (Tool.ELLIPSE, "Ellipse", "Draw an ellipse"),
            (Tool.CALLOUT, "Callout", "Draw a speech-bubble callout"),
            (Tool.BRACKET, "Bracket", "Draw a curly/square bracket"),
            (Tool.STAR, "Star", "Draw a star or polygon"),
            (Tool.DIAMOND, "Diamond", "Draw a diamond shape"),
            (Tool.CONNECTOR, "Connect", "Draw a connector line"),
            (Tool.FREEHAND, "Pen", "Freehand drawing"),
        ]:
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda checked, t=tool: self._select_shape(t))
            sl.addWidget(btn)
            self.shape_buttons[tool] = btn
        row1.addWidget(sf)

        # --- Insert ---
        ins_f, ins_l = _group("Insert")
        img_btn = QToolButton()
        img_btn.setText("Image")
        img_btn.setCheckable(True)
        img_btn.setToolTip("Place an image on the canvas")
        img_btn.clicked.connect(lambda checked: self._activate_image_tool())
        ins_l.addWidget(img_btn)
        self.shape_buttons[Tool.IMAGE] = img_btn
        txt_btn = QToolButton()
        txt_btn.setText("Text")
        txt_btn.setCheckable(True)
        txt_btn.setToolTip("Draw a text box, then type inside")
        txt_btn.clicked.connect(lambda checked: self._select_shape(Tool.TEXT))
        ins_l.addWidget(txt_btn)
        self.shape_buttons[Tool.TEXT] = txt_btn
        row1.addWidget(ins_f)

        # --- Tools ---
        tl_f, tl_l = _group("Tools")
        self._ruler_btn = QToolButton()
        self._ruler_btn.setText("Ruler")
        self._ruler_btn.setCheckable(True)
        self._ruler_btn.setToolTip("Toggle floating ruler")
        self._ruler_btn.clicked.connect(self._toggle_ruler)
        tl_l.addWidget(self._ruler_btn)
        self._hints_btn = QToolButton()
        self._hints_btn.setText("Guide")
        self._hints_btn.setCheckable(True)
        self._hints_btn.setChecked(True)
        self._hints_btn.setToolTip("Show / hide Quick Guide")
        self._hints_btn.clicked.connect(self._toggle_hints)
        tl_l.addWidget(self._hints_btn)
        row1.addWidget(tl_f)

        # --- Actions ---
        act_f, act_l = _group("Actions")
        for label, tip, slot, obj_name in [
            ("Undo", "Undo (Ctrl+Z)", self.editor.undo, "action_btn"),
            ("Redo", "Redo (Ctrl+Y)", self.editor.redo, "action_btn"),
            ("Clear", "Clear all annotations", self.editor.clear_all, "red"),
            ("Delete", "Delete selected", self._delete_selected, "action_btn"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName(obj_name)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            act_l.addWidget(btn)
        row1.addWidget(act_f)

        outer.addWidget(row1_w)

        # ═══ ROW 2: Color │ Sliders │ Zoom (wrapping) ═══
        self._row2_widget = row2_w = QWidget()
        row2_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row2_policy.setHeightForWidth(True)
        row2_w.setSizePolicy(row2_policy)
        row2 = _FlowLayout(row2_w, margin=0, h_spacing=8, v_spacing=6)

        # --- Color presets ---
        clr_f, clr_l = _group("Color")
        self._color_presets: list[tuple[int, int, int]] = [
            (231, 76, 60), (241, 196, 15), (46, 204, 113), (52, 152, 219),
            (155, 89, 182), (236, 240, 241), (26, 188, 156), (230, 126, 34),
        ]
        self._color_preset_btns: list[QPushButton] = []
        for rgb in self._color_presets:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            hex_col = "#%02x%02x%02x" % rgb
            btn.setToolTip(hex_col)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_col}; "
                f"border: 2px solid transparent; border-radius: 11px; "
                f"min-width: 22px; min-height: 22px; "
                f"max-width: 22px; max-height: 22px; padding: 0; }}"
            )
            btn.clicked.connect(lambda checked, c=rgb: self._set_color(c))
            clr_l.addWidget(btn)
            self._color_preset_btns.append(btn)
        custom_btn = QPushButton("+")
        custom_btn.setFixedSize(22, 22)
        custom_btn.setToolTip("Custom color")
        custom_btn.setStyleSheet(
            "QPushButton { border-radius: 11px; font-size: 13px; "
            "font-weight: bold; min-width: 22px; min-height: 22px; "
            "max-width: 22px; max-height: 22px; padding: 0; }"
        )
        custom_btn.clicked.connect(self._pick_custom_color)
        clr_l.addWidget(custom_btn)
        self._color_indicator = QPushButton()
        self._color_indicator.setFixedSize(26, 26)
        self._color_indicator.setEnabled(False)
        self._color_indicator.setToolTip("Active color")
        self._update_color_indicator()
        clr_l.addWidget(self._color_indicator)
        row2.addWidget(clr_f)

        # --- Zoom ---
        zm_f, zm_l = _group("Zoom")
        for label, tip, slot in [
            ("Fit", "Fit page in view", lambda: self.editor.fit_to_frame()),
            ("1\u00d7", "Zoom 100%", lambda: self.editor.set_scale(1.0)),
            ("2\u00d7", "Zoom 200%", lambda: self.editor.set_scale(2.0)),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("action_btn")
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            zm_l.addWidget(btn)
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(10, 300)
        self._zoom_slider.setValue(100)
        self._zoom_slider.setFixedWidth(80)
        self._zoom_slider.setToolTip("Zoom level")
        self._zoom_slider.valueChanged.connect(
            lambda v: self.editor.set_scale(v / 100.0)
        )
        zm_l.addWidget(self._zoom_slider)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setObjectName("value_blue")
        self._zoom_label.setFixedWidth(40)
        zm_l.addWidget(self._zoom_label)
        row2.addWidget(zm_f)

        # --- Opacity ---
        op_f, op_l = _group("Opacity")
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(5, 100)
        self._opacity_slider.setValue(int(self.editor.current_opacity * 100))
        self._opacity_slider.setFixedWidth(90)
        self._opacity_slider.setToolTip("Annotation opacity")
        self._opacity_slider.valueChanged.connect(self._sync_editor)
        op_l.addWidget(self._opacity_slider)
        self._opacity_label = QLabel(f"{int(self.editor.current_opacity * 100)}%")
        self._opacity_label.setObjectName("value_gold")
        self._opacity_label.setFixedWidth(34)
        op_l.addWidget(self._opacity_label)
        row2.addWidget(op_f)

        # --- Width ---
        wd_f, wd_l = _group("Width")
        self._width_slider = QSlider(Qt.Orientation.Horizontal)
        self._width_slider.setRange(1, 25)
        self._width_slider.setValue(self.editor.current_width)
        self._width_slider.setFixedWidth(90)
        self._width_slider.setToolTip("Stroke width")
        self._width_slider.valueChanged.connect(self._sync_editor)
        wd_l.addWidget(self._width_slider)
        self._width_label = QLabel(f"{self.editor.current_width}px")
        self._width_label.setObjectName("value_blue")
        self._width_label.setFixedWidth(34)
        wd_l.addWidget(self._width_label)
        row2.addWidget(wd_f)

        # --- Line Style ---
        self._stroke_frame, ls_l = _group("Stroke")
        ls_f = self._stroke_frame
        self._line_style_combo = QComboBox()
        self._line_style_combo.addItems(["solid", "dashed", "dotted"])
        self._line_style_combo.setFixedWidth(85)
        self._line_style_combo.setToolTip("Line/stroke style")
        self._line_style_combo.currentTextChanged.connect(self._sync_editor)
        ls_l.addWidget(self._line_style_combo)
        row2.addWidget(ls_f)

        # --- Arrow Head ---
        self._arrow_head_frame, ah_l = _group("Arrow Head")
        ah_f = self._arrow_head_frame
        self._arrow_head_combo = QComboBox()
        self._arrow_head_combo.addItems(["filled", "open", "diamond", "double", "none"])
        self._arrow_head_combo.setFixedWidth(90)
        self._arrow_head_combo.setToolTip("Arrow head style")
        self._arrow_head_combo.currentTextChanged.connect(self._sync_editor)
        ah_l.addWidget(self._arrow_head_combo)
        row2.addWidget(ah_f)

        # --- Curve ---
        self._curve_frame, cv_l = _group("Curve")
        cv_f = self._curve_frame
        self._curve_slider = QSlider(Qt.Orientation.Horizontal)
        self._curve_slider.setRange(-50, 50)
        self._curve_slider.setValue(25)
        self._curve_slider.setFixedWidth(80)
        self._curve_slider.setToolTip("Curved arrow bend amount (0 = straight)")
        self._curve_slider.valueChanged.connect(self._sync_editor)
        cv_l.addWidget(self._curve_slider)
        self._curve_label = QLabel("25%")
        self._curve_label.setObjectName("value_gold")
        self._curve_label.setFixedWidth(34)
        cv_l.addWidget(self._curve_label)
        row2.addWidget(cv_f)

        # --- Bracket Style ---
        self._bracket_frame, bk_l = _group("Bracket")
        bk_f = self._bracket_frame
        self._bracket_combo = QComboBox()
        self._bracket_combo.addItems(["curly", "square"])
        self._bracket_combo.setFixedWidth(75)
        self._bracket_combo.setToolTip("Bracket style")
        self._bracket_combo.currentTextChanged.connect(self._sync_editor)
        bk_l.addWidget(self._bracket_combo)
        row2.addWidget(bk_f)

        # --- Star / Polygon ---
        self._star_frame, st_l = _group("Star")
        st_f = self._star_frame
        st_l.addWidget(QLabel("Pts"))
        self._star_points_slider = QSlider(Qt.Orientation.Horizontal)
        self._star_points_slider.setRange(3, 12)
        self._star_points_slider.setValue(5)
        self._star_points_slider.setFixedWidth(60)
        self._star_points_slider.setToolTip("Number of star/polygon points")
        self._star_points_slider.valueChanged.connect(self._sync_editor)
        st_l.addWidget(self._star_points_slider)
        self._star_pts_label = QLabel("5")
        self._star_pts_label.setObjectName("value_blue")
        self._star_pts_label.setFixedWidth(20)
        st_l.addWidget(self._star_pts_label)
        st_l.addWidget(QLabel("In"))
        self._star_inner_slider = QSlider(Qt.Orientation.Horizontal)
        self._star_inner_slider.setRange(10, 95)
        self._star_inner_slider.setValue(45)
        self._star_inner_slider.setFixedWidth(60)
        self._star_inner_slider.setToolTip("Star inner radius ratio (higher = less pointy)")
        self._star_inner_slider.valueChanged.connect(self._sync_editor)
        st_l.addWidget(self._star_inner_slider)
        self._star_inner_label = QLabel("45%")
        self._star_inner_label.setObjectName("value_gold")
        self._star_inner_label.setFixedWidth(30)
        st_l.addWidget(self._star_inner_label)
        row2.addWidget(st_f)

        # --- Connector Style ---
        self._connector_frame, cn_l = _group("Connector")
        cn_f = self._connector_frame
        self._connector_combo = QComboBox()
        self._connector_combo.addItems(["straight", "elbow"])
        self._connector_combo.setFixedWidth(80)
        self._connector_combo.setToolTip("Connector line routing")
        self._connector_combo.currentTextChanged.connect(self._sync_editor)
        cn_l.addWidget(self._connector_combo)
        row2.addWidget(cn_f)

        # --- Gradient ---
        self._gradient_frame, gd_l = _group("Gradient")
        gd_f = self._gradient_frame
        self._gradient_combo = QComboBox()
        self._gradient_combo.addItems(["none", "linear", "radial"])
        self._gradient_combo.setFixedWidth(75)
        self._gradient_combo.setToolTip("Fill gradient for shapes")
        self._gradient_combo.currentTextChanged.connect(self._sync_editor)
        gd_l.addWidget(self._gradient_combo)
        self._gradient_color2_btn = QPushButton()
        self._gradient_color2_btn.setFixedSize(22, 22)
        self._gradient_color2_btn.setToolTip("2nd gradient color")
        self._gradient_color2_btn.setStyleSheet(
            "QPushButton { background-color: #ffffff; border: 2px solid #888; "
            "border-radius: 11px; min-width: 22px; min-height: 22px; "
            "max-width: 22px; max-height: 22px; padding: 0; }"
        )
        self._gradient_color2_btn.clicked.connect(self._pick_gradient_color2)
        gd_l.addWidget(self._gradient_color2_btn)
        row2.addWidget(gd_f)

        # --- Lift ---
        self._lift_frame, lf_l = _group("Lift")
        lf_f = self._lift_frame
        self._lift_slider = QSlider(Qt.Orientation.Horizontal)
        self._lift_slider.setRange(100, 150)
        self._lift_slider.setValue(int(self.editor.current_lift_zoom * 100))
        self._lift_slider.setFixedWidth(90)
        self._lift_slider.setToolTip("Text lift zoom factor")
        self._lift_slider.valueChanged.connect(self._sync_editor)
        lf_l.addWidget(self._lift_slider)
        self._lift_label = QLabel(
            f"+{int((self.editor.current_lift_zoom - 1) * 100)}%"
        )
        self._lift_label.setObjectName("value_gold")
        self._lift_label.setFixedWidth(34)
        lf_l.addWidget(self._lift_label)
        row2.addWidget(lf_f)

        outer.addWidget(row2_w)

        # ── Text formatting toolbar (shown only when Text tool active) ──
        self._text_toolbar = QFrame()
        self._text_toolbar.setObjectName("toolbar_row")
        row3 = QHBoxLayout(self._text_toolbar)
        row3.setContentsMargins(8, 8, 8, 8)
        row3.setSpacing(8)

        fn_f, fn_l = _group("Font")
        self._font_combo = QComboBox()
        self._font_combo.addItems(self._get_installed_fonts())
        self._font_combo.setFixedWidth(160)
        self._font_combo.setCurrentText("Arial")
        self._font_combo.setToolTip("Font family")
        self._font_combo.currentTextChanged.connect(lambda v: self._sync_text_format())
        fn_l.addWidget(self._font_combo)
        row3.addWidget(fn_f)

        sz_f, sz_l = _group("Size")
        self._font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self._font_size_slider.setRange(8, 120)
        self._font_size_slider.setValue(24)
        self._font_size_slider.setFixedWidth(80)
        self._font_size_slider.setToolTip("Font size")
        self._font_size_slider.valueChanged.connect(lambda v: self._sync_text_format())
        sz_l.addWidget(self._font_size_slider)
        self._font_size_label = QLabel("24pt")
        self._font_size_label.setObjectName("value_blue")
        self._font_size_label.setFixedWidth(36)
        sz_l.addWidget(self._font_size_label)
        row3.addWidget(sz_f)

        bi_f, bi_l = _group("Style")
        self._bold_btn = QToolButton()
        self._bold_btn.setText("B")
        self._bold_btn.setCheckable(True)
        self._bold_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._bold_btn.setToolTip("Bold")
        self._bold_btn.clicked.connect(self._toggle_bold)
        bi_l.addWidget(self._bold_btn)
        self._italic_btn = QToolButton()
        self._italic_btn.setText("I")
        self._italic_btn.setCheckable(True)
        self._italic_btn.setFont(
            QFont("Segoe UI", 11, weight=QFont.Weight.Normal, italic=True)
        )
        self._italic_btn.setToolTip("Italic")
        self._italic_btn.clicked.connect(self._toggle_italic)
        bi_l.addWidget(self._italic_btn)
        row3.addWidget(bi_f)

        fc_f, fc_l = _group("Colors")
        self._font_color: tuple[int, int, int] = (0, 0, 0)
        self._font_color_btn = QPushButton("A")
        self._font_color_btn.setFixedSize(28, 28)
        self._font_color_btn.setToolTip("Font color")
        self._font_color_btn.setStyleSheet(
            "QPushButton { background-color: #000; color: white; "
            "font-weight: bold; border-radius: 4px; padding: 0; }"
        )
        self._font_color_btn.clicked.connect(self._pick_font_color)
        fc_l.addWidget(self._font_color_btn)
        self._text_bg_color: tuple[int, int, int] | None = (255, 255, 255)
        self._text_bg_btn = QPushButton()
        self._text_bg_btn.setFixedSize(28, 28)
        self._text_bg_btn.setToolTip("Text background")
        self._text_bg_btn.setStyleSheet(
            "QPushButton { background-color: #fff; border: 1px solid #888; "
            "border-radius: 4px; padding: 0; }"
        )
        self._text_bg_btn.clicked.connect(self._pick_text_bg_color)
        fc_l.addWidget(self._text_bg_btn)
        self._text_bg_transparent = QCheckBox("Transparent")
        self._text_bg_transparent.setToolTip("Remove text background")
        self._text_bg_transparent.stateChanged.connect(
            lambda: self._sync_text_format()
        )
        fc_l.addWidget(self._text_bg_transparent)
        row3.addWidget(fc_f)

        sp_f, sp_l = _group("Spacing")
        self._line_spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self._line_spacing_slider.setRange(10, 30)
        self._line_spacing_slider.setValue(12)
        self._line_spacing_slider.setFixedWidth(60)
        self._line_spacing_slider.setToolTip("Line spacing")
        self._line_spacing_slider.valueChanged.connect(
            lambda v: self._sync_text_format()
        )
        sp_l.addWidget(self._line_spacing_slider)
        self._line_spacing_label = QLabel("1.2x")
        self._line_spacing_label.setObjectName("value_gold")
        self._line_spacing_label.setFixedWidth(30)
        sp_l.addWidget(self._line_spacing_label)
        row3.addWidget(sp_f)
        row3.addStretch()

        self._text_toolbar.setVisible(False)

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def _bind_shortcuts(self):
        """Bind keyboard shortcuts for common actions."""
        shortcuts = [
            (QKeySequence.StandardKey.Undo, self.editor.undo),
            (QKeySequence.StandardKey.Redo, self.editor.redo),
            (QKeySequence("Ctrl+Shift+Z"), self.editor.undo),
            (QKeySequence("Left"), self._prev_page),
            (QKeySequence("Right"), self._next_page),
            (QKeySequence("PgUp"), self._prev_page),
            (QKeySequence("PgDown"), self._next_page),
        ]
        for keys, slot in shortcuts:
            action = QAction(self)
            action.setShortcut(keys)
            action.triggered.connect(slot)
            self.addAction(action)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @Slot(float)
    def _on_zoom_changed(self, scale):
        pct = int(scale * 100)
        self._zoom_label.setText(f"{pct}%")
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(pct)
        self._zoom_slider.blockSignals(False)

    @Slot()
    def _toggle_effect(self, tool: Tool):
        self.editor.current_shape = None
        self.editor.pending_image = None
        effects = self.editor.current_effects
        if tool in effects:
            effects.discard(tool)
        else:
            effects.add(tool)
        self._refresh_tool_buttons()

    @Slot()
    def _select_shape(self, tool: Tool):
        if tool != Tool.IMAGE:
            self.editor.pending_image = None
        if self.editor.current_shape == tool:
            self.editor.current_shape = None
        else:
            self.editor.current_shape = tool
        self._refresh_tool_buttons()

    def _refresh_tool_buttons(self):
        """Sync effect/shape button checked state with the editor."""
        for tool, btn in self.effect_buttons.items():
            btn.setChecked(tool in self.editor.current_effects
                           and self.editor.current_shape is None)
        for tool, btn in self.shape_buttons.items():
            btn.setChecked(self.editor.current_shape == tool)
        # Show/hide text formatting toolbar
        self._text_toolbar.setVisible(self.editor.current_shape == Tool.TEXT)
        # Show/hide shape-specific control groups
        shape = self.editor.current_shape
        _stroke_tools = {Tool.ARROW, Tool.CURVED_ARROW, Tool.LINE,
                         Tool.FREEHAND, Tool.CONNECTOR}
        _arrow_tools = {Tool.ARROW, Tool.CURVED_ARROW}
        _fill_tools = {Tool.RECTANGLE, Tool.ELLIPSE, Tool.ROUNDED_RECT,
                       Tool.CALLOUT, Tool.STAR, Tool.DIAMOND}
        self._stroke_frame.setVisible(shape in _stroke_tools)
        self._arrow_head_frame.setVisible(shape in _arrow_tools)
        self._curve_frame.setVisible(shape == Tool.CURVED_ARROW)
        self._bracket_frame.setVisible(shape == Tool.BRACKET)
        self._star_frame.setVisible(shape == Tool.STAR)
        self._connector_frame.setVisible(shape == Tool.CONNECTOR)
        self._gradient_frame.setVisible(shape in _fill_tools)
        self._lift_frame.setVisible(shape is None)
        # Force the flow layout to recalculate after visibility changes
        if self._row2_widget.layout():
            self._row2_widget.layout().invalidate()
            self._row2_widget.updateGeometry()

    # ------------------------------------------------------------------
    # Image tool
    # ------------------------------------------------------------------

    def _activate_image_tool(self) -> None:
        """Open a file dialog to pick an image, then place it on the canvas."""
        if not self.editor.base_image:
            QMessageBox.warning(self, "No Page", "Load a PDF page first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "",
            "Image files (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff)")
        if not path:
            return
        try:
            from PIL import Image
            img = Image.open(path)
            # Place image at center of the page, sized to ~30% of page width
            page_w, page_h = self.editor.base_image.size
            iw, ih = img.size
            ar = iw / ih if ih > 0 else 1.0
            target_w = int(page_w * 0.3)
            target_h = int(target_w / ar) if ar > 0 else target_w
            if target_h > int(page_h * 0.6):
                target_h = int(page_h * 0.6)
                target_w = int(target_h * ar)
            cx, cy = page_w // 2, page_h // 2
            x1, y1 = cx - target_w // 2, cy - target_h // 2
            x2, y2 = x1 + target_w, y1 + target_h
            self.editor._push_undo()
            ann = Annotation(
                tools=frozenset({Tool.IMAGE}),
                x1=x1, y1=y1, x2=x2, y2=y2,
                color=(0, 0, 0), opacity=1.0,
                image_data=img.copy(),
            )
            self.editor.annotations.append(ann)
            self.editor.pending_image = None
            self.editor.current_shape = Tool.IMAGE
            self._opacity_slider.setValue(100)
            self._sync_editor()
            self._refresh_tool_buttons()
            self.editor._cache_dirty = True
            self.editor._refresh()
            self.editor.select_annotation(len(self.editor.annotations) - 1)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load image:\n{e}")

    def _delete_selected(self) -> None:
        """Delete the currently selected annotation via the toolbar button."""
        self.editor._delete_selected()

    # ------------------------------------------------------------------
    # Text formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _get_installed_fonts() -> list[str]:
        """Return a list of installed font families, filtered to common ones."""
        _build_font_map()
        if sys.platform == "darwin":
            preferred = [
                "Helvetica", "Arial", "Times New Roman", "SF Pro Text",
                "Courier New", "Georgia", "Verdana", "Menlo",
                "Geeza Pro", "Baghdad",
            ]
        else:
            preferred = [
                "Arial", "Times New Roman", "Segoe UI", "Tahoma",
                "Calibri", "Courier New", "Georgia", "Verdana",
                "Trebuchet MS", "Consolas", "Comic Sans MS", "Impact",
                "Traditional Arabic", "Simplified Arabic",
                "Arabic Typesetting", "Sakkal Majalla",
            ]
        installed = set(k[0] for k in _FONT_MAP)
        result = [f for f in preferred if f.lower() in installed]
        if not result:
            result = ["Arial"]
        return result

    def _toggle_bold(self) -> None:
        # clicked signal already toggles the checkable button state
        self._sync_text_format()

    def _toggle_italic(self) -> None:
        # clicked signal already toggles the checkable button state
        self._sync_text_format()

    def _pick_font_color(self) -> None:
        color = QColorDialog.getColor(QColor(*self._font_color), self, "Font Color")
        if color.isValid():
            self._font_color = (color.red(), color.green(), color.blue())
            hex_c = "#%02x%02x%02x" % self._font_color
            self._font_color_btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_c}; color: white; "
                f"font-weight: bold; border-radius: 4px; padding: 0; }}"
            )
            self._sync_text_format()

    def _pick_text_bg_color(self) -> None:
        init = QColor(*(self._text_bg_color or (255, 255, 255)))
        color = QColorDialog.getColor(init, self, "Text Background Color")
        if color.isValid():
            self._text_bg_color = (color.red(), color.green(), color.blue())
            self._text_bg_transparent.setChecked(False)
            hex_c = "#%02x%02x%02x" % self._text_bg_color
            self._text_bg_btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_c}; border: 1px solid #888; "
                f"border-radius: 4px; padding: 0; }}"
            )
            self._sync_text_format()

    def _on_text_edit_start(self) -> None:
        """Sync sidebar controls from the editor state when re-editing text."""
        ed = self.editor
        self._font_combo.setCurrentText(ed.current_font_family)
        self._font_size_slider.setValue(ed.current_font_size)
        self._bold_btn.setChecked(ed.current_font_bold)
        self._italic_btn.setChecked(ed.current_font_italic)
        self._font_color = ed.current_font_color
        fg_hex = "#%02x%02x%02x" % self._font_color
        self._font_color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {fg_hex}; color: white; "
            f"font-weight: bold; border-radius: 4px; padding: 0; }}"
        )
        if ed.current_text_bg is None:
            self._text_bg_transparent.setChecked(True)
        else:
            self._text_bg_transparent.setChecked(False)
            self._text_bg_color = ed.current_text_bg
            bg_hex = "#%02x%02x%02x" % self._text_bg_color
            self._text_bg_btn.setStyleSheet(
                f"QPushButton {{ background-color: {bg_hex}; border: 1px solid #888; "
                f"border-radius: 4px; padding: 0; }}"
            )
        self._font_size_label.setText(f"{ed.current_font_size}pt")
        self._line_spacing_slider.setValue(int(ed.current_line_spacing * 10))
        self._line_spacing_label.setText(f"{round(ed.current_line_spacing, 1)}x")
        # Make text toolbar visible when editing
        self._text_toolbar.setVisible(True)

    @Slot(int)
    def _on_text_edit_requested(self, idx: int) -> None:
        """Handle text edit request from the canvas — show text toolbar."""
        self._text_toolbar.setVisible(True)

    def _sync_text_format(self) -> None:
        """Push text formatting state to the editor and apply to selection."""
        ed = self.editor
        ed.current_font_family = self._font_combo.currentText()
        size = self._font_size_slider.value()
        ed.current_font_size = size
        ed.current_font_bold = self._bold_btn.isChecked()
        ed.current_font_italic = self._italic_btn.isChecked()
        ed.current_font_color = self._font_color
        if self._text_bg_transparent.isChecked():
            ed.current_text_bg = None
        else:
            ed.current_text_bg = self._text_bg_color
        ls = round(self._line_spacing_slider.value() / 10.0, 1)
        ed.current_line_spacing = ls
        self._font_size_label.setText(f"{size}pt")
        self._line_spacing_label.setText(f"{ls}x")
        # Apply to selected text in the editor
        ed.apply_format_to_selection()

    # ------------------------------------------------------------------
    # Color / Opacity / Width
    # ------------------------------------------------------------------

    def _set_color(self, rgb: tuple[int, int, int]) -> None:
        """Set the active annotation color and update the indicator."""
        self.editor.current_color = rgb
        self._update_color_indicator()
        for btn, preset_rgb in zip(self._color_preset_btns, self._color_presets):
            hex_p = "#%02x%02x%02x" % preset_rgb
            border = "#3b82f6" if preset_rgb == rgb else "transparent"
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_p}; "
                f"border: 2px solid {border}; border-radius: 11px; "
                f"min-width: 22px; min-height: 22px; "
                f"max-width: 22px; max-height: 22px; padding: 0; }}"
            )

    @Slot()
    def _pick_custom_color(self) -> None:
        """Open the system color dialog and apply the chosen color."""
        current = QColor(*self.editor.current_color)
        color = QColorDialog.getColor(current, self, "Choose Color")
        if color.isValid():
            self._set_color((color.red(), color.green(), color.blue()))

    def _pick_gradient_color2(self) -> None:
        """Open color dialog for the second gradient stop color."""
        current = QColor(*self.editor.current_gradient_color2)
        color = QColorDialog.getColor(current, self, "Gradient End Color")
        if color.isValid():
            rgb = (color.red(), color.green(), color.blue())
            self.editor.current_gradient_color2 = rgb
            hex_col = "#%02x%02x%02x" % rgb
            self._gradient_color2_btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_col}; border: 2px solid #888; "
                f"border-radius: 11px; min-width: 22px; min-height: 22px; "
                f"max-width: 22px; max-height: 22px; padding: 0; }}"
            )

    def _update_color_indicator(self) -> None:
        """Update the circular indicator that shows the active color."""
        hex_col = "#%02x%02x%02x" % self.editor.current_color
        self._color_indicator.setStyleSheet(
            f"QPushButton {{ background-color: {hex_col}; border: 2px solid #888; "
            f"border-radius: 13px; min-width: 26px; min-height: 26px; "
            f"max-width: 26px; max-height: 26px; padding: 0; }}"
        )

    @Slot()
    def _sync_editor(self) -> None:
        """Push all tool property values to the editor canvas."""
        opacity = self._opacity_slider.value() / 100.0
        width = self._width_slider.value()
        lift = self._lift_slider.value() / 100.0
        curve = self._curve_slider.value() / 100.0
        star_pts = self._star_points_slider.value()
        star_inner = self._star_inner_slider.value() / 100.0
        self.editor.current_opacity = opacity
        self.editor.current_width = width
        self.editor.current_lift_zoom = lift
        self.editor.current_line_style = self._line_style_combo.currentText()
        self.editor.current_arrow_head = self._arrow_head_combo.currentText()
        self.editor.current_curve_offset = curve
        self.editor.current_bracket_style = self._bracket_combo.currentText()
        self.editor.current_polygon_sides = star_pts
        self.editor.current_star_inner_ratio = star_inner
        self.editor.current_connector_style = self._connector_combo.currentText()
        self.editor.current_gradient_type = self._gradient_combo.currentText()
        self._opacity_label.setText(f"{int(opacity * 100)}%")
        self._width_label.setText(f"{width}px")
        self._lift_label.setText(f"+{int((lift - 1) * 100)}%")
        self._curve_label.setText(f"{self._curve_slider.value()}%")
        self._star_pts_label.setText(str(star_pts))
        self._star_inner_label.setText(f"{self._star_inner_slider.value()}%")

    # ------------------------------------------------------------------
    # Ruler / Hints
    # ------------------------------------------------------------------

    @Slot()
    def _toggle_ruler(self) -> None:
        """Toggle the floating ruler overlay on the canvas."""
        self.editor.toggle_floating_ruler()
        self._ruler_btn.setChecked(self.editor._ruler_visible)

    @Slot()
    def _toggle_hints(self) -> None:
        """Toggle the quick-guide hints panel visibility."""
        vis = not self._hints_panel.isVisible()
        self._hints_panel.setVisible(vis)
        self._hints_btn.setChecked(vis)

    # ------------------------------------------------------------------
    # Banner
    # ------------------------------------------------------------------

    def _load_banner(self):
        path = BANNER_DARK if self._theme_name == "dark" else BANNER_LIGHT
        if os.path.isfile(path):
            pm = QPixmap(path)
            self._banner_label.setPixmap(
                pm.scaledToHeight(80, Qt.TransformationMode.SmoothTransformation)
            )

    # ------------------------------------------------------------------
    # PDF Loading
    # ------------------------------------------------------------------

    @Slot()
    def _browse_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Files (*.pdf)")
        if path:
            self.pdf_entry.setText(path)

    @Slot()
    def _load_pages(self):
        pdf_path = self.pdf_entry.text().strip()
        if not pdf_path or not os.path.isfile(pdf_path):
            QMessageBox.warning(self, "Error", "Please select a valid PDF file.")
            return
        page_text = self.pages_entry.text().strip()
        try:
            dpi = int(self.dpi_entry.text().strip() or "300")
        except ValueError:
            dpi = 300
        page_indices = parse_page_ranges(page_text) if page_text else None
        try:
            images = pdf_pages_to_images(pdf_path, page_indices, dpi=dpi)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Error", str(exc))
            return
        if not images:
            QMessageBox.warning(self, "No Pages", "No pages were rendered.")
            return
        self._set_pages(images)

    # ------------------------------------------------------------------
    # Image Loading
    # ------------------------------------------------------------------

    @Slot()
    def _browse_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.webp);;All Files (*)",
        )
        if paths:
            self._selected_image_paths = paths
            self._img_label.setText(f"{len(paths)} image(s) selected")

    @Slot()
    def _load_images(self):
        if not self._selected_image_paths:
            QMessageBox.warning(self, "Error", "Please select image files first.")
            return
        images: list[Image.Image] = []
        for p in self._selected_image_paths:
            try:
                img = Image.open(p).convert("RGB")
                images.append(img)
            except Exception as exc:
                QMessageBox.critical(self, "Image Error", f"Failed to load {os.path.basename(p)}:\n{exc}")
                return
        if not images:
            QMessageBox.warning(self, "No Images", "No images were loaded.")
            return
        self._set_pages(images)

    # ------------------------------------------------------------------
    # Common page setup
    # ------------------------------------------------------------------

    def _set_pages(self, images: list):
        self.pages = images
        self.page_annotations = {i: [] for i in range(len(images))}
        self.page_undo = {i: [] for i in range(len(images))}
        self.page_redo = {i: [] for i in range(len(images))}
        self._rebuild_thumbnails()
        self._select_page(0)

    @Slot()
    def _reset(self):
        self.pages.clear()
        self.page_annotations.clear()
        self.page_undo.clear()
        self.page_redo.clear()
        self.current_page_idx = -1
        self.editor.set_page(None)
        self._page_label.setText("No pages loaded")
        self._selected_image_paths.clear()
        self._img_label.setText("No images selected")
        # Clear thumbnail sidebar
        for btn in self.thumb_widgets:
            btn.deleteLater()
        self.thumb_widgets.clear()

    # ------------------------------------------------------------------
    # Page Navigation
    # ------------------------------------------------------------------

    def _save_current_page_state(self):
        idx = self.current_page_idx
        if idx < 0:
            return
        self.page_annotations[idx] = list(self.editor.annotations)
        self.page_undo[idx] = list(self.editor._undo_stack)
        self.page_redo[idx] = list(self.editor._redo_stack)

    def _select_page(self, idx):
        if idx < 0 or idx >= len(self.pages):
            return
        self._save_current_page_state()
        self.current_page_idx = idx
        annots = self.page_annotations.get(idx, [])
        self.editor.set_page(self.pages[idx], list(annots))
        self.editor._undo_stack = list(self.page_undo.get(idx, []))
        self.editor._redo_stack = list(self.page_redo.get(idx, []))
        n = len(self.pages)
        cnt = len(annots)
        self._page_label.setText(f"Page {idx + 1} / {n}    ({cnt} annotations)")
        # Highlight active thumbnail
        pal = get_palette(self._theme_name)
        for i, btn in enumerate(self.thumb_widgets):
            if i == idx:
                btn.setStyleSheet(
                    f"QPushButton#thumb_btn {{ border: 2px solid {pal['thumb_active_border']};"
                    f" background-color: {pal['thumb_active_bg']}; }}"
                )
            else:
                btn.setStyleSheet("")

    @Slot()
    def _prev_page(self):
        if self.current_page_idx > 0:
            self._select_page(self.current_page_idx - 1)

    @Slot()
    def _next_page(self):
        if self.current_page_idx < len(self.pages) - 1:
            self._select_page(self.current_page_idx + 1)

    # ------------------------------------------------------------------
    # Thumbnails
    # ------------------------------------------------------------------

    def _rebuild_thumbnails(self):
        for btn in self.thumb_widgets:
            btn.deleteLater()
        self.thumb_widgets.clear()
        for i, img in enumerate(self.pages):
            thumb = img.copy()
            thumb.thumbnail((100, 140))
            pm = _pil_to_qpixmap(thumb)
            btn = QPushButton()
            btn.setObjectName("thumb_btn")
            btn.setIcon(QIcon(pm))
            btn.setIconSize(pm.size())
            btn.setFixedHeight(min(140, pm.height() + 10))
            btn.clicked.connect(lambda checked, idx=i: self._select_page(idx))
            self._sidebar_layout.addWidget(btn)
            self.thumb_widgets.append(btn)

    # ------------------------------------------------------------------
    # Export / Preview / Watermark
    # ------------------------------------------------------------------

    def _browse_output(self) -> None:
        """Open a save-file dialog for the output path."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Output", "",
            "PNG Files (*.png);;JPEG Files (*.jpg)")
        if path:
            self._out_entry.setText(path)

    def _choose_wm_color(self) -> None:
        """Pick the watermark text color."""
        color = QColorDialog.getColor(QColor(*self._wm_color), self, "Watermark Color")
        if color.isValid():
            self._wm_color = (color.red(), color.green(), color.blue())
            hex_c = "#%02x%02x%02x" % self._wm_color
            self._wm_color_btn.setStyleSheet(
                f"background-color: {hex_c}; border-radius: 16px; font-size: 16px;"
            )

    def _build_merged(self):
        """Render all pages with annotations and merge into one image."""
        if not self.pages:
            return None
        self._save_current_page_state()
        rendered = []
        for i, page_img in enumerate(self.pages):
            anns = self.page_annotations.get(i, [])
            if anns:
                rendered.append(render_annotations(page_img, anns).convert("RGB"))
            else:
                rendered.append(page_img.copy())
        lang = "ar" if "Arabic" in self._lang_combo.currentText() else "en"
        wm_on = self._wm_enabled.isChecked()
        wm_text = self._wm_entry.text().strip()
        wm_opacity = self._wm_opacity_slider.value() / 100.0
        wm_position = self._wm_pos_combo.currentText().lower()
        wm_orientation = self._wm_orient_combo.currentText().lower()
        wm_scale = self._wm_size_slider.value()
        return merge_images(
            rendered, lang, wm_on, wm_text, self._wm_color,
            wm_opacity=wm_opacity, wm_position=wm_position,
            wm_orientation=wm_orientation, wm_scale=float(wm_scale),
        )

    @Slot()
    def _export(self) -> None:
        """Export the merged image to disk."""
        out_path = self._out_entry.text().strip()
        if not out_path:
            QMessageBox.warning(self, "Error", "Specify an output file path.")
            return
        merged = self._build_merged()
        if merged is None:
            QMessageBox.warning(self, "Error", "No pages loaded.")
            return
        base, ext = os.path.splitext(out_path)
        if ext.lower() not in (".png", ".jpg", ".jpeg"):
            out_path = base + ".png"
        try:
            merged.save(out_path)
            QMessageBox.information(self, "Done", f"Saved to:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    @Slot()
    def _preview(self) -> None:
        """Open a preview window showing the final merged result."""
        merged = self._build_merged()
        if merged is None:
            QMessageBox.warning(self, "Preview", "No pages loaded.")
            return

        from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
        from PySide6.QtGui import QPainter as _QPainter

        dialog = QDialog(self)
        dialog.setWindowTitle("Scan Preview")
        dialog.resize(900, 700)
        dialog.setModal(True)
        # Inherit theme from parent
        dialog.setStyleSheet(self.styleSheet())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top bar
        bar = QFrame()
        bar.setObjectName("panel")
        bar.setFixedHeight(44)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 4, 12, 4)
        title_lbl = QLabel("\U0001F50D  Scan Preview")
        title_lbl.setObjectName("gold")
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        bar_layout.addWidget(title_lbl)

        pv_zoom = [1.0]
        auto_fit = [True]
        scene = QGraphicsScene()
        view = QGraphicsView(scene)
        view.setRenderHint(_QPainter.RenderHint.Antialiasing)
        view.setRenderHint(_QPainter.RenderHint.SmoothPixmapTransform)
        view.setBackgroundBrush(QColor("#1a1a1a"))
        pix_item = QGraphicsPixmapItem()
        scene.addItem(pix_item)

        pv_label = QLabel("100%")
        pv_label.setFixedWidth(50)
        pv_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        def _show(scale: float | None = None):
            if scale is not None:
                pv_zoom[0] = max(0.05, min(5.0, scale))
            s = pv_zoom[0]
            from PIL import Image as PILImage
            w = max(1, int(merged.width * s))
            h = max(1, int(merged.height * s))
            resized = merged.resize((w, h), PILImage.BILINEAR)
            pm = _pil_to_qpixmap(resized)
            pix_item.setPixmap(pm)
            scene.setSceneRect(QRectF(0, 0, pm.width(), pm.height()))
            pv_label.setText(f"{int(s * 100)}%")

        def _fit():
            vw = view.viewport().width() or 800
            vh = view.viewport().height() or 600
            s = min(vw / merged.width, vh / merged.height, 3.0)
            _show(max(0.05, s))

        def _wheel(event):
            """Mouse wheel zooms the preview."""
            auto_fit[0] = False
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            _show(max(0.05, min(5.0, pv_zoom[0] * factor)))
            event.accept()

        view.wheelEvent = _wheel

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(lambda: (auto_fit.__setitem__(0, True), _fit()))
        bar_layout.addWidget(fit_btn)
        btn_1x = QPushButton("1x")
        btn_1x.clicked.connect(lambda: _show(1.0))
        bar_layout.addWidget(btn_1x)
        btn_50 = QPushButton("50%")
        btn_50.clicked.connect(lambda: _show(0.5))
        bar_layout.addWidget(btn_50)
        bar_layout.addWidget(pv_label)
        bar_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setObjectName("red")
        close_btn.clicked.connect(dialog.close)
        bar_layout.addWidget(close_btn)

        layout.addWidget(bar)
        layout.addWidget(view, stretch=1)

        # Auto-fit on first show
        QTimer.singleShot(100, _fit)
        dialog.exec()
