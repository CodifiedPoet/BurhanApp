"""BurhanApp — main application window."""

import os
import sys
from tkinter import Canvas, Scrollbar, colorchooser, filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from .canvas import AnnotationCanvas
from .models import Annotation, Tool
from .rendering import merge_images, pdf_pages_to_images, render_annotations
from .utils import parse_page_ranges


class _Tooltip:
    """Lightweight hover tooltip for any widget."""

    def __init__(self, widget, text, delay=400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip = None
        self._after_id = None
        self._check_id = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, _e):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _on_leave(self, _e):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._check_id:
            self.widget.after_cancel(self._check_id)
            self._check_id = None

    def _show(self):
        if self._tip:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tw = ctk.CTkToplevel(self.widget)
        tw.withdraw()
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        frame = ctk.CTkFrame(tw, fg_color="#1e293b", corner_radius=8,
                             border_width=1, border_color="#475569")
        frame.pack()
        ctk.CTkLabel(frame, text=self.text, text_color="#e2e8f0",
                     font=ctk.CTkFont(size=12), wraplength=280,
                     justify="left").pack(padx=10, pady=6)
        tw.update_idletasks()
        tw.geometry(f"+{x}+{y}")
        tw.deiconify()
        # Periodic check: hide if mouse leaves the widget area
        self._poll_mouse()

    def _poll_mouse(self):
        """Hide the tooltip if the pointer is no longer over the widget."""
        if not self._tip:
            return
        try:
            mx, my = self.widget.winfo_pointerxy()
            wx = self.widget.winfo_rootx()
            wy = self.widget.winfo_rooty()
            ww = self.widget.winfo_width()
            wh = self.widget.winfo_height()
            if not (wx <= mx <= wx + ww and wy <= my <= wy + wh):
                self._hide()
                return
        except Exception:
            self._hide()
            return
        self._check_id = self.widget.after(200, self._poll_mouse)

    def _hide(self):
        if self._check_id:
            self.widget.after_cancel(self._check_id)
            self._check_id = None
        if self._tip:
            self._tip.destroy()
            self._tip = None


# --- Locate bundled data / assets ---
if getattr(sys, "frozen", False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ASSETS_DIR = os.path.join(_BASE_DIR, "assets")
BANNER_DARK = os.path.join(_ASSETS_DIR, "Bring_evidence2_dark.png")
BANNER_LIGHT = os.path.join(_ASSETS_DIR, "Bring_evidence2_light.png")


class ScanGeneratorApp(ctk.CTk):

    THEMES = {
        "dark": {
            "mode": "dark",
            "bg": "#1e1e1e", "panel": "#2d2d2d",
            "accent": "#3c3c3c", "accent_hover": "#505050",
            "gold": "#e2b714", "gold_hover": "#f1c40f",
            "green": "#27ae60", "green_hover": "#2ecc71",
            "red": "#c0392b", "red_hover": "#e74c3c",
            "text": "#e0e0e0", "text_dim": "#808080", "text_label": "#b0b0b0",
            "entry_bg": "#383838", "entry_text": "#e0e0e0", "entry_placeholder": "#808080",
            "btn": "#3c3c3c", "btn_hover": "#505050",
            "sep": "#505050",
            "tool_bg": "#383838", "tool_hover": "#4a4a4a", "tool_text": "#e0e0e0",
            "slider_bg": "#383838",
            "blue": "#3498db", "blue_light": "#5dade2", "blue_bright": "#85c1e9",
            "sel_border": "#3498db", "tool_sel": "#00cc66",
            "indicator_border": "#e0e0e0",
            "canvas_bg": "#1a1a1a",
            "scroll_bg": "#3c3c3c", "scroll_trough": "#2d2d2d",
            "thumb_bg": "#383838", "thumb_text": "#b0b0b0",
            "gold_text": "#1e1e1e",
            "plus_btn": "#505050", "plus_btn_hover": "#606060",
            "ruler_bg": "#2d2d2d", "ruler_fg": "#808080", "ruler_tick": "#606060",
            "banner": BANNER_DARK,
            "switch_fg": "#3c3c3c", "switch_progress": "#e2b714", "switch_btn": "#e0e0e0",
        },
        "light": {
            "mode": "light",
            "bg": "#eef1f6", "panel": "#ffffff",
            "accent": "#d0d9e8", "accent_hover": "#b8c5d9",
            "gold": "#c49a0a", "gold_hover": "#d4ad12",
            "green": "#1e8449", "green_hover": "#27ae60",
            "red": "#b03a2e", "red_hover": "#c0392b",
            "text": "#1a202c", "text_dim": "#4a5568", "text_label": "#2d3748",
            "entry_bg": "#e8ecf1", "entry_text": "#1a202c", "entry_placeholder": "#8899aa",
            "btn": "#cbd5e1", "btn_hover": "#b0bec5",
            "sep": "#b0bec5",
            "tool_bg": "#d6dce5", "tool_hover": "#c2cad6", "tool_text": "#1a202c",
            "slider_bg": "#cbd5e1",
            "blue": "#1d4ed8", "blue_light": "#2563eb", "blue_bright": "#3b82f6",
            "sel_border": "#1d4ed8", "tool_sel": "#15803d",
            "indicator_border": "#1a202c",
            "canvas_bg": "#d4d4d4",
            "scroll_bg": "#b0bec5", "scroll_trough": "#e8ecf1",
            "thumb_bg": "#d6dce5", "thumb_text": "#2d3748",
            "gold_text": "#1a202c",
            "plus_btn": "#94a3b8", "plus_btn_hover": "#7c8fa3",
            "ruler_bg": "#e8ecf1", "ruler_fg": "#4a5568", "ruler_tick": "#b0bec5",
            "banner": BANNER_LIGHT,
            "switch_fg": "#cbd5e1", "switch_progress": "#1d4ed8", "switch_btn": "#ffffff",
        },
    }

    def __init__(self):
        super().__init__()
        self._theme_name = "dark"
        self.c = dict(self.THEMES["dark"])
        self._themed_widgets: list[tuple] = []

        self.title("BurhanApp  \u2014  \u0642\u064f\u0644\u0652 \u0647\u064e\u0627\u062a\u064f\u0648\u0652 \u0628\u064f\u0631\u0652\u0647\u064e\u0627\u0646\u064e\u0643\u064f\u0645\u0652")
        self.geometry("1280x860")
        self.minsize(1000, 700)
        self._set_icon()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=self.c["bg"])

        self.pages: list[Image.Image] = []
        self.page_annotations: dict[int, list[Annotation]] = {}
        self.page_undo: dict[int, list] = {}
        self.page_redo: dict[int, list] = {}
        self.current_page_idx: int = -1
        self.wm_color: tuple = (0, 255, 0)

        self._build_ui()
        self._bind_shortcuts()

    def _set_icon(self):
        """Set the window/taskbar icon from assets."""
        try:
            base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            if hasattr(sys, '_MEIPASS'):
                icon_path = os.path.join(base, 'assets', 'BurhanApp.ico')
            else:
                icon_path = os.path.join(base, '..', '..', 'assets', 'BurhanApp.ico')
            icon_path = os.path.normpath(icon_path)
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
                ico_img = Image.open(icon_path)
                self._icon_photo = ImageTk.PhotoImage(ico_img.resize((32, 32), Image.LANCZOS))
                self.iconphoto(False, self._icon_photo)
        except Exception:
            pass

    def _tw(self, widget, **mapping):
        """Register *widget* for automatic theme recoloring."""
        self._themed_widgets.append((widget, mapping))
        return widget

    # ---------------------------------------------------------------
    # UI construction
    # ---------------------------------------------------------------

    def _build_ui(self):
        c = self.c

        # === HEADER ===
        header = self._tw(ctk.CTkFrame(self, fg_color=c["panel"], corner_radius=0, height=90), fg_color="panel")
        header.pack(fill="x")
        header.pack_propagate(False)
        self._banner_parent = header
        self._load_banner(header)

        # Theme toggle switch
        toggle_frame = ctk.CTkFrame(header, fg_color="transparent")
        toggle_frame.place(relx=1.0, x=-80, rely=0.5, anchor="center")
        self._theme_sun = self._tw(
            ctk.CTkLabel(toggle_frame, text="\u2600\ufe0f", font=ctk.CTkFont(size=16), text_color=c["gold"]),
            text_color="gold")
        self._theme_sun.pack(side="left", padx=(0, 4))
        self._theme_switch_var = ctk.BooleanVar(value=False)  # False = dark
        self._theme_switch = self._tw(
            ctk.CTkSwitch(toggle_frame, text="", variable=self._theme_switch_var,
                          width=48, height=24, switch_width=44, switch_height=22,
                          fg_color=c["switch_fg"], progress_color=c["switch_progress"],
                          button_color=c["switch_btn"], button_hover_color=c["switch_btn"],
                          command=self._toggle_theme),
            fg_color="switch_fg", progress_color="switch_progress",
            button_color="switch_btn", button_hover_color="switch_btn")
        self._theme_switch.pack(side="left")
        self._theme_moon = self._tw(
            ctk.CTkLabel(toggle_frame, text="\U0001f319", font=ctk.CTkFont(size=16), text_color=c["text_dim"]),
            text_color="text_dim")
        self._theme_moon.pack(side="left", padx=(4, 0))

        # === INPUT BAR ===
        input_bar = self._tw(ctk.CTkFrame(self, fg_color=c["accent"], corner_radius=8, height=50), fg_color="accent")
        input_bar.pack(fill="x", padx=12, pady=(8, 4))
        input_bar.pack_propagate(False)

        lbl_font = ctk.CTkFont(size=12, weight="bold")
        entry_kw = dict(height=32, corner_radius=6, border_width=0)
        btn_kw = dict(height=32, corner_radius=6, font=ctk.CTkFont(size=12, weight="bold"))

        self._tw(ctk.CTkLabel(input_bar, text="\U0001F4C4  PDF:", font=lbl_font, text_color=c["text_label"]),
                 text_color="text_label").pack(side="left", padx=(10, 4))
        self.pdf_var = ctk.StringVar()
        self.pdf_entry = self._tw(ctk.CTkEntry(input_bar, width=260,
                              placeholder_text="Select a PDF file...",
                              placeholder_text_color=c["entry_placeholder"],
                              fg_color=c["entry_bg"], text_color=c["entry_text"], **entry_kw),
                 fg_color="entry_bg", text_color="entry_text")
        self.pdf_entry.pack(side="left", padx=2)
        _Tooltip(self.pdf_entry, "Path to a PDF file.\nUse Browse or paste a full path.")
        _browse_btn = self._tw(ctk.CTkButton(input_bar, text="Browse", width=70,
                               fg_color=c["btn"], hover_color=c["btn_hover"],
                               command=self._browse_pdf, **btn_kw),
                 fg_color="btn", hover_color="btn_hover")
        _browse_btn.pack(side="left", padx=(2, 10))
        _Tooltip(_browse_btn, "Open a file dialog to select a PDF.")

        self._tw(ctk.CTkLabel(input_bar, text="Pages:", font=lbl_font, text_color=c["text_label"]),
                 text_color="text_label").pack(side="left", padx=(0, 4))
        self.pages_var = ctk.StringVar()
        self.pages_entry = self._tw(ctk.CTkEntry(input_bar, width=120,
                              placeholder_text="e.g. 1-3, 5, 8",
                              placeholder_text_color=c["entry_placeholder"],
                              fg_color=c["entry_bg"], text_color=c["entry_text"], **entry_kw),
                 fg_color="entry_bg", text_color="entry_text")
        self.pages_entry.pack(side="left", padx=2)
        _Tooltip(self.pages_entry, "Which pages to load.\nExamples: 1-5  or  1,3,7  or  2-4, 8")

        self._tw(ctk.CTkLabel(input_bar, text="DPI:", font=lbl_font, text_color=c["text_label"]),
                 text_color="text_label").pack(side="left", padx=(10, 4))
        self.dpi_var = ctk.IntVar(value=300)
        self.dpi_entry = self._tw(ctk.CTkEntry(input_bar, width=50,
                              placeholder_text="300",
                              placeholder_text_color=c["entry_placeholder"],
                              fg_color=c["entry_bg"], text_color=c["entry_text"], **entry_kw),
                 fg_color="entry_bg", text_color="entry_text")
        self.dpi_entry.insert(0, "300")
        self.dpi_entry.pack(side="left", padx=2)
        _Tooltip(self.dpi_entry, "Resolution for rendering pages.\n150 = fast, 300 = print quality, 600 = high-res.")

        _load_btn = self._tw(ctk.CTkButton(input_bar, text="\u25B6  Load Pages", width=120,
                      fg_color=c["green"], hover_color=c["green_hover"],
                      text_color="white", command=self._load_pages, **btn_kw),
                 fg_color="green", hover_color="green_hover")
        _load_btn.pack(side="left", padx=(15, 5))
        _Tooltip(_load_btn, "Render the selected pages from the PDF.\nThis may take a moment at high DPI.")
        _reset_btn = self._tw(ctk.CTkButton(input_bar, text="\u21BA  Reset", width=70,
                      fg_color=c["red"], hover_color=c["red_hover"],
                      text_color="white", command=self._reset, **btn_kw),
                 fg_color="red", hover_color="red_hover")
        _reset_btn.pack(side="right", padx=10)
        _Tooltip(_reset_btn, "Clear all loaded pages and annotations.")

        # === MAIN CONTENT ===
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=4)

        # -- LEFT: Page thumbnails --
        sidebar_frame = self._tw(ctk.CTkFrame(content, fg_color=c["panel"], corner_radius=10, width=140), fg_color="panel")
        sidebar_frame.pack(side="left", fill="y", padx=(0, 6))
        sidebar_frame.pack_propagate(False)
        self._tw(ctk.CTkLabel(sidebar_frame, text="\U0001F4D1  Pages",
                              font=ctk.CTkFont(size=13, weight="bold"), text_color=c["gold"]),
                 text_color="gold").pack(pady=(10, 5))
        self._tw(ctk.CTkFrame(sidebar_frame, height=1, fg_color=c["accent"]), fg_color="accent").pack(fill="x", padx=10, pady=(0, 5))
        self.sidebar = self._tw(
            ctk.CTkScrollableFrame(sidebar_frame, fg_color=c["panel"], label_text="",
                                   scrollbar_button_color=c["scroll_bg"],
                                   scrollbar_button_hover_color=c["btn_hover"]),
            fg_color="panel", scrollbar_button_color="scroll_bg",
            scrollbar_button_hover_color="btn_hover")
        self.sidebar.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.thumb_widgets: list = []

        # -- RIGHT: Toolbar + Editor --
        right = ctk.CTkFrame(content, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # -- FAR RIGHT: Interaction Hints --
        self._hints_frame = self._tw(
            ctk.CTkFrame(content, fg_color=c["panel"], corner_radius=10, width=260),
            fg_color="panel")
        self._hints_frame.pack(side="right", fill="y", padx=(6, 0))
        self._hints_frame.pack_propagate(False)
        self._build_hints_panel(self._hints_frame)

        toolbar_frame = self._tw(ctk.CTkFrame(right, fg_color=c["panel"], corner_radius=10), fg_color="panel")
        toolbar_frame.pack(fill="x", pady=(0, 4))

        self.editor = self._tw(AnnotationCanvas(right, fg_color=c["panel"], corner_radius=10), fg_color="panel")
        self.editor.canvas.configure(bg=c["canvas_bg"])
        self._build_toolbar(toolbar_frame)
        self.editor.on_zoom_changed = self._on_zoom_changed
        self.editor.on_text_edit_start = self._on_text_edit_start
        self.editor.pack(fill="both", expand=True)

        # === PAGINATION BAR ===
        page_bar = self._tw(ctk.CTkFrame(right, fg_color=c["panel"], corner_radius=8, height=36), fg_color="panel")
        page_bar.pack(fill="x", pady=(4, 0))
        page_bar.pack_propagate(False)

        nav_kw = dict(height=28, corner_radius=6, font=ctk.CTkFont(size=12, weight="bold"), width=80)
        self._prev_btn = self._tw(
            ctk.CTkButton(page_bar, text="\u25C0  Prev", command=self._prev_page,
                          fg_color=c["btn"], hover_color=c["btn_hover"],
                          text_color=c["text"], **nav_kw),
            fg_color="btn", hover_color="btn_hover", text_color="text")
        self._prev_btn.pack(side="left", padx=(10, 4))

        self._page_label = self._tw(
            ctk.CTkLabel(page_bar, text="No pages loaded",
                         font=ctk.CTkFont(size=12, weight="bold"), text_color=c["text_dim"]),
            text_color="text_dim")
        self._page_label.pack(side="left", expand=True)

        self._next_btn = self._tw(
            ctk.CTkButton(page_bar, text="Next  \u25B6", command=self._next_page,
                          fg_color=c["btn"], hover_color=c["btn_hover"],
                          text_color=c["text"], **nav_kw),
            fg_color="btn", hover_color="btn_hover", text_color="text")
        self._next_btn.pack(side="right", padx=(4, 10))

        self._ann_count_label = self._tw(
            ctk.CTkLabel(page_bar, text="",
                         font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
            text_color="text_dim")
        self._ann_count_label.pack(side="right", padx=(0, 8))

        # === EXPORT BAR ===
        export_bar = self._tw(ctk.CTkFrame(self, fg_color=c["panel"], corner_radius=8, height=50), fg_color="panel")
        export_bar.pack(fill="x", padx=12, pady=(4, 10))
        export_bar.pack_propagate(False)

        self._tw(ctk.CTkLabel(export_bar, text="Language:", font=lbl_font, text_color=c["text_label"]),
                 text_color="text_label").pack(side="left", padx=(10, 4))
        self.lang_var = ctk.StringVar(value="Arabic (RTL)")
        self._tw(ctk.CTkOptionMenu(export_bar, variable=self.lang_var,
                                   values=["Arabic (RTL)", "English (LTR)"],
                                   width=150, height=32,
                                   fg_color=c["entry_bg"], button_color=c["btn"],
                                   button_hover_color=c["btn_hover"],
                                   dropdown_fg_color=c["entry_bg"],
                                   text_color=c["entry_text"]),
                 fg_color="entry_bg", button_color="btn",
                 button_hover_color="btn_hover", dropdown_fg_color="entry_bg",
                 text_color="entry_text").pack(side="left", padx=2)

        self._tw(ctk.CTkFrame(export_bar, width=1, height=30, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=10)

        self.wm_enabled = ctk.BooleanVar(value=False)
        self._tw(ctk.CTkCheckBox(export_bar, text="Watermark", variable=self.wm_enabled,
                                 font=ctk.CTkFont(size=12), text_color=c["text_label"],
                                 fg_color=c["accent"], hover_color=c["accent_hover"],
                                 checkmark_color=c["gold"]),
                 text_color="text_label", fg_color="accent", hover_color="accent_hover",
                 checkmark_color="gold").pack(side="left", padx=(0, 4))
        self.wm_text_var = ctk.StringVar()
        self.wm_entry = self._tw(ctk.CTkEntry(export_bar, width=120,
                              placeholder_text="watermark text",
                              placeholder_text_color=c["entry_placeholder"],
                              fg_color=c["entry_bg"], text_color=c["entry_text"], **entry_kw),
                 fg_color="entry_bg", text_color="entry_text")
        self.wm_entry.pack(side="left", padx=2)
        _Tooltip(self.wm_entry, "Text to overlay as a watermark.\nEnable the checkbox first, then type here.")
        self.wm_color_btn = ctk.CTkButton(export_bar, text="\u25CF", width=32, height=32,
                                           fg_color="#2ecc71", hover_color="#27ae60",
                                           corner_radius=16, command=self._choose_wm_color,
                                           font=ctk.CTkFont(size=16))
        self.wm_color_btn.pack(side="left", padx=4)
        _Tooltip(self.wm_color_btn, "Pick the watermark text color.")

        self._tw(ctk.CTkFrame(export_bar, width=1, height=30, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=10)

        self._tw(ctk.CTkLabel(export_bar, text="Output:", font=lbl_font, text_color=c["text_label"]),
                 text_color="text_label").pack(side="left", padx=(0, 4))
        self.out_var = ctk.StringVar()
        self.out_entry = self._tw(ctk.CTkEntry(export_bar, width=220,
                              placeholder_text="output file path...",
                              placeholder_text_color=c["entry_placeholder"],
                              fg_color=c["entry_bg"], text_color=c["entry_text"], **entry_kw),
                 fg_color="entry_bg", text_color="entry_text")
        self.out_entry.pack(side="left", padx=2, fill="x", expand=True)
        _Tooltip(self.out_entry, "Where to save the exported image.\nUse Browse or type a .png / .jpg path.")
        _browse_out = self._tw(ctk.CTkButton(export_bar, text="Browse", width=70,
                               fg_color=c["btn"], hover_color=c["btn_hover"],
                               command=self._browse_output, **btn_kw),
                 fg_color="btn", hover_color="btn_hover")
        _browse_out.pack(side="left", padx=2)
        _Tooltip(_browse_out, "Choose where to save the output file.")
        _export_btn = self._tw(ctk.CTkButton(export_bar, text="\u2B07  Export Merged", width=140,
                               fg_color=c["gold"], hover_color=c["gold_hover"], text_color=c["gold_text"],
                               command=self._export,
                               font=ctk.CTkFont(size=13, weight="bold"), height=34, corner_radius=6),
                 fg_color="gold", hover_color="gold_hover", text_color="gold_text")
        _export_btn.pack(side="right", padx=10)
        _Tooltip(_export_btn, "Merge all annotated pages into\na single image and save to disk.")
        _preview_btn = self._tw(ctk.CTkButton(export_bar, text="\U0001F50D  Preview", width=110,
                               fg_color=c["blue"], hover_color=c["blue_light"], text_color="white",
                               command=self._preview,
                               font=ctk.CTkFont(size=13, weight="bold"), height=34, corner_radius=6),
                 fg_color="blue", hover_color="blue_light")
        _preview_btn.pack(side="right", padx=(0, 6))
        _Tooltip(_preview_btn, "Open a preview window showing\nthe final merged result.")

    def _build_hints_panel(self, parent):
        """Build the interaction hints info panel on the right side."""
        c = self.c

        self._tw(ctk.CTkLabel(parent, text="\u2139\uFE0F  Quick Guide",
                              font=ctk.CTkFont(size=16, weight="bold"), text_color=c["gold"]),
                 text_color="gold").pack(pady=(10, 4))
        self._tw(ctk.CTkFrame(parent, height=1, fg_color=c["accent"]),
                 fg_color="accent").pack(fill="x", padx=10, pady=(0, 4))

        scroll = self._tw(
            ctk.CTkScrollableFrame(parent, fg_color=c["panel"], label_text="",
                                   scrollbar_button_color=c["scroll_bg"],
                                   scrollbar_button_hover_color=c["btn_hover"]),
            fg_color="panel", scrollbar_button_color="scroll_bg",
            scrollbar_button_hover_color="btn_hover")
        scroll.pack(fill="both", expand=True, padx=2, pady=(0, 4))

        hints = [
            ("\U0001F5B1  Select",
             "Click any text box or image\nto select it (marching border).\nClick empty area to deselect."),
            ("\u270F\uFE0F  Create Text",
             "Choose the Text tool, then\ndrag on the canvas to draw a\ntext box. Type and click outside."),
            ("\U0001F4DD  Edit Text",
             "Double-click a text box to\nre-open the editor. Change\nfont, size, color, bold/italic."),
            ("\U0001F5BC  Insert Image",
             "Click Insert Image \u2014 the image\nis placed at center instantly.\nNo need to draw a box."),
            ("\u2B05\uFE0F  Move",
             "Right-click & drag any text\nbox or image to reposition it\nanywhere on the page."),
            ("\U0001F504  Resize Image",
             "Right-click drag a handle:\n\u2022 Corners = keep aspect ratio\n\u2022 Edges = stretch freely"),
            ("\U0001F5D1  Delete",
             "Select an item, then press\nDelete key or click the \U0001F5D1\nbutton. Confirms before deleting."),
            ("\U0001F3A8  Effects",
             "Toggle Highlight, Underline,\nBorder, or Text Lift. Then drag\non the page to apply."),
            ("\u25B3  Shapes",
             "Choose Arrow, Rectangle, or\nEllipse. Drag on the canvas to\ndraw the shape."),
            ("\U0001F50D  Zoom",
             "Ctrl + Scroll wheel to zoom.\nUse Fit / 1x / 2x buttons or\nthe zoom slider. Plain scroll\nmoves the page up/down."),
            ("\U0001F4CF  Ruler",
             "Toggle the ruler to measure\ndistances. Drag on canvas to\ndraw a measurement line.\nScroll wheel on ruler to rotate."),
            ("\u2328\uFE0F  Shortcuts",
             "Ctrl+Z \u2192 Undo\nCtrl+Y \u2192 Redo\nEsc      \u2192 Deselect\nDel      \u2192 Delete selected"),
        ]

        for title, desc in hints:
            frame = self._tw(ctk.CTkFrame(scroll, fg_color=c["accent"], corner_radius=8),
                             fg_color="accent")
            frame.pack(fill="x", padx=4, pady=3)
            self._tw(ctk.CTkLabel(frame, text=title,
                                  font=ctk.CTkFont(size=15, weight="bold"),
                                  text_color=c["text"], anchor="w"),
                     text_color="text").pack(anchor="w", padx=8, pady=(6, 0))
            self._tw(ctk.CTkLabel(frame, text=desc,
                                  font=ctk.CTkFont(size=14),
                                  text_color=c["text_dim"], anchor="w",
                                  justify="left"),
                     text_color="text_dim").pack(anchor="w", padx=8, pady=(2, 6))

    def _build_toolbar(self, parent):
        c = self.c
        # --- Row 1: Effect toggles + Shape radios + actions + zoom ---
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=(8, 2))

        tool_kw = dict(height=30, corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"))

        # -- Effect toggles (multi-select) --
        self._tw(ctk.CTkLabel(row1, text="Effects", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))
        self.effect_buttons: dict[Tool, ctk.CTkButton] = {}
        effects_list = [
            (Tool.HIGHLIGHT, "\U0001F7E8 Highlight"),
            (Tool.UNDERLINE, "\u2581 Underline"),
            (Tool.BORDER, "\u25A1 Border"),
            (Tool.TEXT_LIFT, "\u2B06 Lift"),
        ]
        _effect_tips = {
            Tool.HIGHLIGHT: "Semi-transparent highlight over selected area.",
            Tool.UNDERLINE: "Draw a colored underline beneath text.",
            Tool.BORDER: "Draw a colored border around selected area.",
            Tool.TEXT_LIFT: "Slightly enlarge text in the selected region.",
        }
        for tool, label in effects_list:
            btn = self._tw(ctk.CTkButton(row1, text=label, width=90,
                                         fg_color=c["tool_bg"], hover_color=c["tool_hover"],
                                         text_color=c["tool_text"],
                                         command=lambda t=tool: self._toggle_effect(t), **tool_kw),
                           fg_color="tool_bg", hover_color="tool_hover", text_color="tool_text")
            btn.pack(side="left", padx=2)
            self.effect_buttons[tool] = btn
            _Tooltip(btn, _effect_tips[tool])

        self._tw(ctk.CTkFrame(row1, width=1, height=26, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=6)

        # -- Shape radios (exclusive) --
        self._tw(ctk.CTkLabel(row1, text="Shapes", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))
        self.shape_buttons: dict[Tool, ctk.CTkButton] = {}
        shapes_list = [
            (Tool.ARROW, "\u2197 Arrow"),
            (Tool.RECTANGLE, "\u25A0 Rect"),
            (Tool.ELLIPSE, "\u2B2C Ellipse"),
        ]
        _shape_tips = {
            Tool.ARROW: "Draw an arrow pointing to something.",
            Tool.RECTANGLE: "Draw a rectangle outline.",
            Tool.ELLIPSE: "Draw an ellipse/circle outline.",
        }
        for tool, label in shapes_list:
            btn = self._tw(ctk.CTkButton(row1, text=label, width=80,
                                         fg_color=c["tool_bg"], hover_color=c["tool_hover"],
                                         text_color=c["tool_text"],
                                         command=lambda t=tool: self._select_shape(t), **tool_kw),
                           fg_color="tool_bg", hover_color="tool_hover", text_color="tool_text")
            btn.pack(side="left", padx=2)
            self.shape_buttons[tool] = btn
            _Tooltip(btn, _shape_tips[tool])

        self._tw(ctk.CTkFrame(row1, width=1, height=26, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=6)

        # -- Overlay tools (Image / Text) --
        self._tw(ctk.CTkLabel(row1, text="Insert", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))

        img_btn = self._tw(ctk.CTkButton(row1, text="\U0001F5BC Image", width=80,
                                         fg_color=c["tool_bg"], hover_color=c["tool_hover"],
                                         text_color=c["tool_text"],
                                         command=self._activate_image_tool, **tool_kw),
                           fg_color="tool_bg", hover_color="tool_hover", text_color="tool_text")
        img_btn.pack(side="left", padx=2)
        self.shape_buttons[Tool.IMAGE] = img_btn
        _Tooltip(img_btn, "Upload an image and drag to place it.\nRight-click drag to move it.")

        txt_btn = self._tw(ctk.CTkButton(row1, text="\U0001F524 Text", width=80,
                                         fg_color=c["tool_bg"], hover_color=c["tool_hover"],
                                         text_color=c["tool_text"],
                                         command=lambda: self._select_shape(Tool.TEXT), **tool_kw),
                           fg_color="tool_bg", hover_color="tool_hover", text_color="tool_text")
        txt_btn.pack(side="left", padx=2)
        self.shape_buttons[Tool.TEXT] = txt_btn
        _Tooltip(txt_btn, "Drag to draw a text box, click to re-edit.\nRight-click drag to move a text box.")

        self._tw(ctk.CTkFrame(row1, width=1, height=26, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=6)

        # -- Actions --
        action_kw = dict(height=30, corner_radius=6, font=ctk.CTkFont(size=11), width=55)
        _undo = self._tw(ctk.CTkButton(row1, text="\u21B6 Undo", fg_color=c["btn"], hover_color=c["btn_hover"],
                               command=lambda: self.editor.undo(), **action_kw),
                 fg_color="btn", hover_color="btn_hover")
        _undo.pack(side="left", padx=2)
        _Tooltip(_undo, "Undo the last annotation.")
        _redo = self._tw(ctk.CTkButton(row1, text="\u21B7 Redo", fg_color=c["btn"], hover_color=c["btn_hover"],
                               command=lambda: self.editor.redo(), **action_kw),
                 fg_color="btn", hover_color="btn_hover")
        _redo.pack(side="left", padx=2)
        _Tooltip(_redo, "Redo a previously undone annotation.")
        _clear = self._tw(ctk.CTkButton(row1, text="\u2715 Clear", fg_color=c["red"], hover_color=c["red_hover"],
                      text_color="white", command=lambda: self.editor.clear_all(), **action_kw),
                 fg_color="red", hover_color="red_hover")
        _clear.pack(side="left", padx=2)
        _Tooltip(_clear, "Remove all annotations from this page.")
        _del = self._tw(ctk.CTkButton(row1, text="\U0001F5D1 Delete", fg_color=c["btn"], hover_color=c["btn_hover"],
                              command=self._delete_selected, **action_kw),
                fg_color="btn", hover_color="btn_hover")
        _del.pack(side="left", padx=2)
        _Tooltip(_del, "Delete the selected image (click an image first).")

        self._tw(ctk.CTkFrame(row1, width=1, height=26, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=6)

        # -- Zoom --
        zoom_kw = dict(height=30, corner_radius=6, font=ctk.CTkFont(size=11), width=40)
        _fit = self._tw(ctk.CTkButton(row1, text="Fit", command=self._zoom_fit,
                               fg_color=c["btn"], hover_color=c["btn_hover"], **zoom_kw),
                 fg_color="btn", hover_color="btn_hover")
        _fit.pack(side="left", padx=1)
        _Tooltip(_fit, "Zoom to fit the page in the canvas.")
        _1x = self._tw(ctk.CTkButton(row1, text="1x", command=lambda: self._set_zoom(1.0),
                               fg_color=c["btn"], hover_color=c["btn_hover"], **zoom_kw),
                 fg_color="btn", hover_color="btn_hover")
        _1x.pack(side="left", padx=1)
        _Tooltip(_1x, "Zoom to 100% (actual pixels).")
        _2x = self._tw(ctk.CTkButton(row1, text="2x", command=lambda: self._set_zoom(2.0),
                               fg_color=c["btn"], hover_color=c["btn_hover"], **zoom_kw),
                 fg_color="btn", hover_color="btn_hover")
        _2x.pack(side="left", padx=1)
        _Tooltip(_2x, "Zoom to 200%.")

        self.zoom_var = ctk.DoubleVar(value=1.0)
        self._tw(ctk.CTkSlider(row1, from_=0.1, to=3.0, variable=self.zoom_var, width=120,
                               fg_color=c["slider_bg"], progress_color=c["blue_light"],
                               button_color=c["blue"], button_hover_color=c["blue_bright"],
                               command=self._on_zoom_slider),
                 fg_color="slider_bg", progress_color="blue_light",
                 button_color="blue", button_hover_color="blue_bright").pack(side="left", padx=(6, 2))
        self.zoom_label = self._tw(ctk.CTkLabel(row1, text="100%", width=45,
                                                font=ctk.CTkFont(size=11, weight="bold"), text_color=c["blue_light"]),
                                   text_color="blue_light")
        self.zoom_label.pack(side="left")

        self._tw(ctk.CTkFrame(row1, width=1, height=26, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=6)

        # -- Ruler / Measure button --
        self.ruler_btn = self._tw(
            ctk.CTkButton(row1, text="\U0001F4CF Ruler", width=80,
                          fg_color=c["tool_bg"], hover_color=c["tool_hover"],
                          text_color=c["tool_text"],
                          command=self._toggle_ruler, **tool_kw),
            fg_color="tool_bg", hover_color="tool_hover", text_color="tool_text")
        self.ruler_btn.pack(side="left", padx=2)
        _Tooltip(self.ruler_btn, "Toggle a floating ruler overlay.\nDrag to move, scroll to rotate.")

        # --- Row 2: Color, Opacity, Width, Lift Zoom ---
        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(2, 8))

        self._tw(ctk.CTkLabel(row2, text="Color", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 6))

        presets = [
            ("#e74c3c", (231, 76, 60)),
            ("#f1c40f", (241, 196, 15)),
            ("#2ecc71", (46, 204, 113)),
            ("#3498db", (52, 152, 219)),
            ("#9b59b6", (155, 89, 182)),
            ("#ecf0f1", (236, 240, 241)),
            ("#1abc9c", (26, 188, 156)),
            ("#e67e22", (230, 126, 34)),
        ]
        self._color_preset_btns: list[ctk.CTkButton] = []
        for hex_c, rgb in presets:
            tc = "white" if sum(rgb) < 400 else "black"
            btn = ctk.CTkButton(row2, text="", width=24, height=24, corner_radius=12,
                          fg_color=hex_c, hover_color=hex_c, text_color=tc,
                          border_width=0, border_color="white",
                          command=lambda c_=rgb: self._set_color(c_))
            btn._preset_rgb = rgb
            btn.pack(side="left", padx=1)
            self._color_preset_btns.append(btn)
        self._tw(ctk.CTkButton(row2, text="+", width=24, height=24, corner_radius=12,
                      fg_color=c["plus_btn"], hover_color=c["plus_btn_hover"],
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._pick_custom_color),
                 fg_color="plus_btn", hover_color="plus_btn_hover").pack(side="left", padx=(1, 4))
        _Tooltip(self._color_preset_btns[-1] if self._color_preset_btns else row2,
                 "Pick from a preset color.")

        # Active color indicator — use CTkButton so it always renders at fixed size
        self.color_indicator = ctk.CTkButton(
            row2, text="", width=28, height=28, corner_radius=14,
            fg_color="#f1c40f", hover_color="#f1c40f",
            border_width=2, border_color=c["indicator_border"],
            state="disabled", command=lambda: None)
        self.color_indicator.pack(side="left", padx=(2, 4))
        _Tooltip(self.color_indicator, "Currently selected annotation color.")

        self._tw(ctk.CTkFrame(row2, width=1, height=24, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=8)

        self._tw(ctk.CTkLabel(row2, text="Opacity", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))
        self.opacity_var = ctk.DoubleVar(value=0.4)
        self._tw(ctk.CTkSlider(row2, from_=0.05, to=1.0, variable=self.opacity_var, width=100,
                               fg_color=c["slider_bg"], progress_color=c["gold"],
                               button_color=c["gold"], button_hover_color=c["gold_hover"],
                               command=lambda v: self._sync_editor()),
                 fg_color="slider_bg", progress_color="gold",
                 button_color="gold", button_hover_color="gold_hover").pack(side="left")
        self.opacity_label = self._tw(ctk.CTkLabel(row2, text="40%", width=38,
                                                   font=ctk.CTkFont(size=11, weight="bold"), text_color=c["gold"]),
                                      text_color="gold")
        self.opacity_label.pack(side="left", padx=(2, 0))

        self._tw(ctk.CTkFrame(row2, width=1, height=24, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=8)

        self._tw(ctk.CTkLabel(row2, text="Width", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))
        self.width_var = ctk.IntVar(value=3)
        self._tw(ctk.CTkSlider(row2, from_=1, to=25, variable=self.width_var, width=100,
                               fg_color=c["slider_bg"], progress_color=c["blue"],
                               button_color=c["blue"], button_hover_color=c["blue_light"],
                               command=lambda v: self._sync_editor()),
                 fg_color="slider_bg", progress_color="blue",
                 button_color="blue", button_hover_color="blue_light").pack(side="left")
        self.width_label = self._tw(ctk.CTkLabel(row2, text="3px", width=38,
                                                 font=ctk.CTkFont(size=11, weight="bold"), text_color=c["blue"]),
                                    text_color="blue")
        self.width_label.pack(side="left", padx=(2, 0))

        self._tw(ctk.CTkFrame(row2, width=1, height=24, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=8)

        # -- Lift Zoom slider --
        self._tw(ctk.CTkLabel(row2, text="Lift Zoom", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))
        self.lift_zoom_var = ctk.DoubleVar(value=1.08)
        self._tw(ctk.CTkSlider(row2, from_=1.0, to=1.5, variable=self.lift_zoom_var, width=100,
                               fg_color=c["slider_bg"], progress_color=c["gold"],
                               button_color=c["gold"], button_hover_color=c["gold_hover"],
                               command=lambda v: self._sync_editor()),
                 fg_color="slider_bg", progress_color="gold",
                 button_color="gold", button_hover_color="gold_hover").pack(side="left")
        self.lift_zoom_label = self._tw(ctk.CTkLabel(row2, text="8%", width=38,
                                                     font=ctk.CTkFont(size=11, weight="bold"), text_color=c["gold"]),
                                        text_color="gold")
        self.lift_zoom_label.pack(side="left", padx=(2, 0))

        # --- Row 3: Text formatting controls (visible when Text tool active) ---
        self._text_row = ctk.CTkFrame(parent, fg_color="transparent")
        # Not packed by default — shown only when Text tool is selected

        self._tw(ctk.CTkLabel(self._text_row, text="\U0001F524 Text Format",
                              font=ctk.CTkFont(size=10, weight="bold"), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 8))

        self._tw(ctk.CTkLabel(self._text_row, text="Font", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))
        self._font_var = ctk.StringVar(value="Arial")
        self._font_menu = self._tw(
            ctk.CTkOptionMenu(self._text_row, variable=self._font_var,
                              values=self._get_installed_fonts(),
                              width=150, height=28,
                              fg_color=c["entry_bg"], button_color=c["btn"],
                              button_hover_color=c["btn_hover"],
                              dropdown_fg_color=c["entry_bg"],
                              text_color=c["entry_text"],
                              command=lambda v: self._sync_text_format()),
            fg_color="entry_bg", button_color="btn",
            button_hover_color="btn_hover", dropdown_fg_color="entry_bg",
            text_color="entry_text")
        self._font_menu.pack(side="left", padx=(0, 8))
        _Tooltip(self._font_menu, "Font family for text annotations.")

        self._tw(ctk.CTkLabel(self._text_row, text="Size", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))
        self._font_size_var = ctk.IntVar(value=24)
        self._tw(ctk.CTkSlider(self._text_row, from_=8, to=120, variable=self._font_size_var, width=100,
                               fg_color=c["slider_bg"], progress_color=c["blue"],
                               button_color=c["blue"], button_hover_color=c["blue_light"],
                               command=lambda v: self._sync_text_format()),
                 fg_color="slider_bg", progress_color="blue",
                 button_color="blue", button_hover_color="blue_light").pack(side="left")
        self._font_size_label = self._tw(
            ctk.CTkLabel(self._text_row, text="24pt", width=42,
                         font=ctk.CTkFont(size=11, weight="bold"), text_color=c["blue"]),
            text_color="blue")
        self._font_size_label.pack(side="left", padx=(2, 8))

        self._tw(ctk.CTkFrame(self._text_row, width=1, height=24, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=4)

        self._bold_var = ctk.BooleanVar(value=False)
        self._bold_btn = self._tw(
            ctk.CTkButton(self._text_row, text="B", width=30, height=28, corner_radius=6,
                          fg_color=c["tool_bg"], hover_color=c["tool_hover"],
                          text_color=c["tool_text"],
                          font=ctk.CTkFont(size=13, weight="bold"),
                          command=self._toggle_bold),
            fg_color="tool_bg", hover_color="tool_hover", text_color="tool_text")
        self._bold_btn.pack(side="left", padx=2)
        _Tooltip(self._bold_btn, "Toggle bold text.")

        self._italic_var = ctk.BooleanVar(value=False)
        self._italic_btn = self._tw(
            ctk.CTkButton(self._text_row, text="I", width=30, height=28, corner_radius=6,
                          fg_color=c["tool_bg"], hover_color=c["tool_hover"],
                          text_color=c["tool_text"],
                          font=ctk.CTkFont(size=13),
                          command=self._toggle_italic),
            fg_color="tool_bg", hover_color="tool_hover", text_color="tool_text")
        self._italic_btn.pack(side="left", padx=2)
        _Tooltip(self._italic_btn, "Toggle italic text.")

        self._tw(ctk.CTkFrame(self._text_row, width=1, height=24, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=6)

        # -- Font color --
        self._tw(ctk.CTkLabel(self._text_row, text="Font", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 3))
        self._font_color = (0, 0, 0)
        self._font_color_btn = ctk.CTkButton(
            self._text_row, text="A", width=28, height=28, corner_radius=6,
            fg_color="#000000", hover_color="#333333",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._pick_font_color)
        self._font_color_btn.pack(side="left", padx=(0, 6))
        _Tooltip(self._font_color_btn, "Pick the text font color.")

        # -- Background color --
        self._tw(ctk.CTkLabel(self._text_row, text="Bg", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 3))
        self._text_bg_color: tuple | None = (255, 255, 255)
        self._text_bg_btn = ctk.CTkButton(
            self._text_row, text="", width=28, height=28, corner_radius=6,
            fg_color="#ffffff", hover_color="#e0e0e0",
            command=self._pick_text_bg_color)
        self._text_bg_btn.pack(side="left", padx=(0, 4))
        _Tooltip(self._text_bg_btn, "Pick the text box background color.")

        self._text_bg_transparent_var = ctk.BooleanVar(value=False)
        self._text_bg_transparent_cb = self._tw(
            ctk.CTkCheckBox(self._text_row, text="Transparent", variable=self._text_bg_transparent_var,
                            font=ctk.CTkFont(size=10), text_color=c["text_dim"],
                            fg_color=c["accent"], hover_color=c["accent_hover"],
                            checkmark_color=c["gold"],
                            command=self._sync_text_format),
            text_color="text_dim", fg_color="accent", hover_color="accent_hover",
            checkmark_color="gold")
        self._text_bg_transparent_cb.pack(side="left", padx=(0, 4))
        _Tooltip(self._text_bg_transparent_cb, "Make the text box background transparent.")

        self._tw(ctk.CTkFrame(self._text_row, width=1, height=24, fg_color=c["sep"]), fg_color="sep").pack(side="left", padx=4)

        # -- Line spacing --
        self._tw(ctk.CTkLabel(self._text_row, text="Spacing", font=ctk.CTkFont(size=10), text_color=c["text_dim"]),
                 text_color="text_dim").pack(side="left", padx=(0, 4))
        self._line_spacing_var = ctk.DoubleVar(value=1.2)
        self._tw(ctk.CTkSlider(self._text_row, from_=1.0, to=3.0, variable=self._line_spacing_var, width=80,
                               fg_color=c["slider_bg"], progress_color=c["blue"],
                               button_color=c["blue"], button_hover_color=c["blue_light"],
                               command=lambda v: self._sync_text_format()),
                 fg_color="slider_bg", progress_color="blue",
                 button_color="blue", button_hover_color="blue_light").pack(side="left")
        self._line_spacing_label = self._tw(
            ctk.CTkLabel(self._text_row, text="1.2x", width=36,
                         font=ctk.CTkFont(size=11, weight="bold"), text_color=c["blue"]),
            text_color="blue")
        self._line_spacing_label.pack(side="left", padx=(2, 0))
        _Tooltip(self._line_spacing_label, "Line spacing multiplier.")

        # Apply initial button highlights
        self._refresh_tool_buttons()

    def _load_banner(self, parent):
        banner_path = self.c["banner"]
        try:
            img = Image.open(banner_path)
            img.thumbnail((700, 80), Image.LANCZOS)
            self._banner_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
            self._banner_label = ctk.CTkLabel(parent, image=self._banner_img, text="", fg_color="transparent")
            self._banner_label.pack(expand=True)
        except Exception:
            self._banner_label = ctk.CTkLabel(parent, text="BurhanApp",
                        font=ctk.CTkFont(size=24, weight="bold"), text_color=self.c["gold"])
            self._banner_label.pack(expand=True)

    # ---------------------------------------------------------------
    # Toolbar callbacks
    # ---------------------------------------------------------------

    def _toggle_effect(self, tool: Tool):
        """Toggle an effect on/off. Multiple effects can be active. Deselects any shape."""
        self._exit_measure_mode()
        self.editor.current_shape = None
        self.editor.pending_image = None
        if tool in self.editor.current_effects:
            self.editor.current_effects.discard(tool)
        else:
            self.editor.current_effects.add(tool)
        self._refresh_tool_buttons()

    def _select_shape(self, tool: Tool):
        """Select a shape (exclusive). Click again to deselect back to effects mode."""
        self._exit_measure_mode()
        if tool != Tool.IMAGE:
            self.editor.pending_image = None
        if self.editor.current_shape == tool:
            self.editor.current_shape = None
        else:
            self.editor.current_shape = tool
        self._refresh_tool_buttons()

    def _activate_image_tool(self):
        """Open a file dialog to pick an image, then place it on the canvas."""
        if not self.editor.base_image:
            messagebox.showwarning("No Page", "Load a PDF page first.")
            return
        path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff")])
        if not path:
            return
        try:
            img = Image.open(path)
            # Place image at center of the visible canvas area, sized to ~30% of page
            page_w, page_h = self.editor.base_image.size
            iw, ih = img.size
            ar = iw / ih if ih > 0 else 1.0
            # Target: 30% of page width, maintain aspect ratio
            target_w = int(page_w * 0.3)
            target_h = int(target_w / ar) if ar > 0 else target_w
            # Cap at 60% of page height
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
                color=(0, 0, 0),
                opacity=1.0,
                image_data=img.copy(),
            )
            self.editor.annotations.append(ann)
            self.editor.pending_image = None
            self.editor.current_shape = Tool.IMAGE
            self.opacity_var.set(1.0)
            self._sync_editor()
            self._exit_measure_mode()
            self._refresh_tool_buttons()
            self.editor._invalidate()
            # Auto-select the newly placed image
            self.editor.select_annotation(len(self.editor.annotations) - 1)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load image:\n{e}")

    def _delete_selected(self):
        """Delete the currently selected annotation via the toolbar button."""
        self.editor._on_delete_key(None)

    def _toggle_bold(self):
        self._bold_var.set(not self._bold_var.get())
        self._sync_text_format()

    @staticmethod
    def _get_installed_fonts():
        """Return a list of installed font families, filtered to common useful ones."""
        import sys
        from .rendering import _build_font_map, _FONT_MAP
        _build_font_map()
        # Preferred order varies by platform
        if sys.platform == "darwin":
            preferred = [
                "Helvetica", "Helvetica Neue", "Arial", "Times New Roman",
                "SF Pro Text", "Avenir", "Futura", "Courier New",
                "Georgia", "Verdana", "Palatino", "Menlo", "Monaco",
                # Arabic fonts available on macOS
                "Geeza Pro", "Baghdad", "Kuwait", "Nadeem",
            ]
        else:
            preferred = [
                "Arial", "Times New Roman", "Segoe UI", "Tahoma",
                "Calibri", "Courier New", "Georgia", "Verdana",
                "Trebuchet MS", "Palatino Linotype", "Consolas",
                "Comic Sans MS", "Impact",
                # Arabic fonts
                "Traditional Arabic", "Simplified Arabic",
                "Arabic Typesetting", "Sakkal Majalla", "Urdu Typesetting",
                "Andalus",
            ]
        installed = set(k[0] for k in _FONT_MAP)
        result = [f for f in preferred if f.lower() in installed]
        if not result:
            result = ["Arial"] if sys.platform == "win32" else ["Helvetica"]
        return result

    def _toggle_italic(self):
        self._italic_var.set(not self._italic_var.get())
        self._sync_text_format()

    def _pick_font_color(self):
        result = colorchooser.askcolor(title="Font Color")[0]
        if result:
            self._font_color = tuple(int(c) for c in result)
            hex_c = "#%02x%02x%02x" % self._font_color
            self._font_color_btn.configure(fg_color=hex_c, hover_color=hex_c)
            self._sync_text_format()

    def _pick_text_bg_color(self):
        result = colorchooser.askcolor(title="Text Background Color")[0]
        if result:
            self._text_bg_color = tuple(int(c) for c in result)
            self._text_bg_transparent_var.set(False)
            hex_c = "#%02x%02x%02x" % self._text_bg_color
            self._text_bg_btn.configure(fg_color=hex_c, hover_color=hex_c)
            self._sync_text_format()

    def _on_text_edit_start(self):
        """Sync sidebar controls from the editor state when re-editing a text annotation."""
        self._font_var.set(self.editor.current_font_family)
        self._font_size_var.set(self.editor.current_font_size)
        self._bold_var.set(self.editor.current_font_bold)
        self._italic_var.set(self.editor.current_font_italic)
        self._font_color = self.editor.current_font_color
        fg_hex = "#%02x%02x%02x" % self._font_color
        self._font_color_btn.configure(fg_color=fg_hex)
        if self.editor.current_text_bg is None:
            self._text_bg_transparent_var.set(True)
        else:
            self._text_bg_transparent_var.set(False)
            self._text_bg_color = self.editor.current_text_bg
            bg_hex = "#%02x%02x%02x" % self._text_bg_color
            self._text_bg_btn.configure(fg_color=bg_hex)
        self._font_size_label.configure(text=f"{self.editor.current_font_size}pt")
        self._line_spacing_var.set(self.editor.current_line_spacing)
        self._line_spacing_label.configure(text=f"{round(self.editor.current_line_spacing, 1)}x")
        sel = self.c["tool_sel"]
        self._bold_btn.configure(
            border_width=2 if self._bold_var.get() else 0,
            border_color=sel if self._bold_var.get() else "")
        self._italic_btn.configure(
            border_width=2 if self._italic_var.get() else 0,
            border_color=sel if self._italic_var.get() else "")

    def _sync_text_format(self):
        """Push text formatting state to the editor and apply to selection."""
        self.editor.current_font_family = self._font_var.get()
        size = int(self._font_size_var.get())
        self.editor.current_font_size = size
        self.editor.current_font_bold = self._bold_var.get()
        self.editor.current_font_italic = self._italic_var.get()
        self.editor.current_font_color = self._font_color
        if self._text_bg_transparent_var.get():
            self.editor.current_text_bg = None
        else:
            self.editor.current_text_bg = self._text_bg_color
        ls = round(self._line_spacing_var.get(), 1)
        self.editor.current_line_spacing = ls
        self._font_size_label.configure(text=f"{size}pt")
        self._line_spacing_label.configure(text=f"{ls}x")
        # Live-update editor font and spacing if open
        if self.editor._text_editor is not None:
            display_size = max(8, int(size * self.editor.scale))
            weight = "bold" if self._bold_var.get() else "normal"
            slant = "italic" if self._italic_var.get() else "roman"
            self.editor._text_editor.configure(
                font=(self._font_var.get(), display_size, weight, slant))
            extra_px = max(0, int(display_size * (ls - 1.0)))
            self.editor._text_editor.configure(spacing3=extra_px)
        # Visual feedback for bold/italic toggles
        sel = self.c["tool_sel"]
        self._bold_btn.configure(
            border_width=2 if self._bold_var.get() else 0,
            border_color=sel if self._bold_var.get() else "")
        self._italic_btn.configure(
            border_width=2 if self._italic_var.get() else 0,
            border_color=sel if self._italic_var.get() else "")
        # Apply formatting to selected text or future typing
        self.editor.apply_format_to_selection()

    def _refresh_tool_buttons(self):
        """Update visual state of all tool buttons."""
        sel = self.c["tool_sel"]
        for t, btn in self.effect_buttons.items():
            if t in self.editor.current_effects and self.editor.current_shape is None:
                btn.configure(border_width=2, border_color=sel)
            else:
                btn.configure(border_width=0)
        for t, btn in self.shape_buttons.items():
            if t == self.editor.current_shape:
                btn.configure(border_width=2, border_color=sel)
            else:
                btn.configure(border_width=0)
        if hasattr(self, 'ruler_btn'):
            if self.editor._ruler_visible:
                self.ruler_btn.configure(border_width=2, border_color=sel)
            else:
                self.ruler_btn.configure(border_width=0)
        # Show/hide text format row
        if hasattr(self, '_text_row'):
            if self.editor.current_shape == Tool.TEXT:
                self._text_row.pack(fill="x", padx=8, pady=(2, 8))
            else:
                self._text_row.pack_forget()

    def _set_color(self, rgb: tuple):
        self.editor.current_color = rgb
        hex_c = "#%02x%02x%02x" % rgb
        self.color_indicator.configure(fg_color=hex_c, hover_color=hex_c)
        # Highlight the selected preset button
        for btn in self._color_preset_btns:
            if btn._preset_rgb == rgb:
                btn.configure(border_width=2, border_color="white")
            else:
                btn.configure(border_width=0)

    def _pick_custom_color(self):
        result = colorchooser.askcolor(title="Pick Annotation Color")[0]
        if result:
            self._set_color(tuple(int(c) for c in result))

    def _sync_editor(self):
        opacity = self.opacity_var.get()
        width = int(self.width_var.get())
        lift_zoom = self.lift_zoom_var.get()
        self.editor.current_opacity = opacity
        self.editor.current_width = width
        self.editor.current_lift_zoom = lift_zoom
        self.opacity_label.configure(text=f"{int(opacity * 100)}%")
        self.width_label.configure(text=f"{width}px")
        self.lift_zoom_label.configure(text=f"{int((lift_zoom - 1) * 100)}%")

    # -- Zoom helpers ------------------------------------------------

    def _zoom_fit(self):
        self.editor.fit_to_frame()

    def _set_zoom(self, value: float):
        self.editor.set_scale(value)

    def _on_zoom_slider(self, value):
        self.editor.set_scale(float(value))

    def _on_zoom_changed(self, scale: float):
        """Called by editor when zoom changes (scroll wheel, fit, etc.)."""
        self.zoom_var.set(scale)
        self.zoom_label.configure(text=f"{int(scale * 100)}%")

    # -- Ruler / Measure overlay ------------------------------------

    def _toggle_ruler(self):
        self.editor.toggle_floating_ruler()
        self._refresh_tool_buttons()
        if self.editor._ruler_visible:
            self._show_ruler_hint()
        else:
            self._hide_ruler_hint()

    def _show_ruler_hint(self):
        if hasattr(self, '_ruler_hint') and self._ruler_hint.winfo_exists():
            return
        c = self.c
        hint = ctk.CTkFrame(self.editor, fg_color=c["panel"], corner_radius=14,
                             border_width=2, border_color=c["accent"])
        hint.place(relx=0.5, rely=1.0, anchor="s", y=-16)

        ctk.CTkLabel(hint, text="\U0001F4CF  Ruler Controls",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=c["gold"]).pack(padx=20, pady=(14, 6))

        lines = [
            ("\U0001F5B1  Drag", "Move the ruler"),
            ("\u2699  Scroll wheel", "Rotate"),
            ("\u2328  Shift + Scroll", "Fine rotate"),
            ("\u274C  Click Ruler button", "Hide"),
        ]
        for key, desc in lines:
            row = ctk.CTkFrame(hint, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=2)
            ctk.CTkLabel(row, text=key,
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=c["text"], anchor="w", width=190).pack(side="left")
            ctk.CTkLabel(row, text=desc,
                         font=ctk.CTkFont(size=14),
                         text_color=c["text_dim"], anchor="w").pack(side="left")

        # spacer at bottom
        ctk.CTkFrame(hint, height=6, fg_color="transparent").pack()

        self._ruler_hint = hint
        # Auto-dismiss after 6 seconds
        self._ruler_hint_after = self.after(6000, self._hide_ruler_hint)

    def _hide_ruler_hint(self):
        if hasattr(self, '_ruler_hint_after'):
            self.after_cancel(self._ruler_hint_after)
            del self._ruler_hint_after
        if hasattr(self, '_ruler_hint') and self._ruler_hint.winfo_exists():
            self._ruler_hint.destroy()

    def _exit_measure_mode(self):
        """Silently exit measure mode (called when switching to another tool)."""
        if self.editor._measure_mode:
            self.editor.set_measure_mode(False)

    # -- Theme switching ---------------------------------------------

    def _toggle_theme(self):
        self._theme_name = "light" if self._theme_name == "dark" else "dark"
        self.c = dict(self.THEMES[self._theme_name])
        ctk.set_appearance_mode(self.c["mode"])
        self._theme_switch_var.set(self._theme_name == "light")
        self._apply_theme()

    def _apply_theme(self):
        self.configure(fg_color=self.c["bg"])
        for widget, mapping in self._themed_widgets:
            try:
                widget.configure(**{k: self.c[v] for k, v in mapping.items()})
            except Exception:
                pass
        self._reload_banner()
        c = self.c
        # Canvas & scrollbars
        self.editor.canvas.configure(bg=c["canvas_bg"])
        self.editor.v_scroll.configure(bg=c["scroll_trough"], troughcolor=c["scroll_trough"])
        self.editor.h_scroll.configure(bg=c["scroll_trough"], troughcolor=c["scroll_trough"])
        # Rulers
        ruler_colors = (c["ruler_bg"], c["ruler_fg"], c["ruler_tick"])
        self.editor._ruler_colors = ruler_colors
        self.editor.h_ruler.configure(bg=c["ruler_bg"])
        self.editor.v_ruler.configure(bg=c["ruler_bg"])
        self.editor._ruler_corner.configure(bg=c["ruler_bg"])
        self.editor._draw_rulers()
        self._refresh_tool_buttons()
        # Retheme thumbnails
        for i, btn in enumerate(self.thumb_widgets):
            btn.configure(fg_color=c["thumb_bg"], text_color=c["thumb_text"],
                          hover_color=c["tool_hover"])
            if self.current_page_idx >= 0 and i == self.current_page_idx:
                btn.configure(border_width=3, border_color=c["sel_border"])
            else:
                btn.configure(border_width=0)

    def _reload_banner(self):
        banner_path = self.c["banner"]
        try:
            img = Image.open(banner_path)
            img.thumbnail((700, 80), Image.LANCZOS)
            self._banner_img = ctk.CTkImage(light_image=img, dark_image=img,
                                            size=(img.width, img.height))
            self._banner_label.configure(image=self._banner_img, text="")
        except Exception:
            self._banner_label.configure(image="", text="BurhanApp")

    # ---------------------------------------------------------------
    # File dialogs
    # ---------------------------------------------------------------

    def _browse_pdf(self):
        p = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if p:
            self.pdf_entry.delete(0, "end")
            self.pdf_entry.insert(0, p)

    def _browse_output(self):
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
        if p:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, p)

    def _choose_wm_color(self):
        result = colorchooser.askcolor(title="Watermark Color")[0]
        if result:
            self.wm_color = tuple(int(c) for c in result)
            self.wm_color_btn.configure(fg_color="#%02x%02x%02x" % self.wm_color)

    # ---------------------------------------------------------------
    # Page loading
    # ---------------------------------------------------------------

    def _load_pages(self):
        pdf_path = self.pdf_entry.get().strip()
        pages_str = self.pages_entry.get().strip()
        if not pdf_path or not pages_str:
            messagebox.showerror("Error", "Provide a PDF path and page numbers.")
            return
        try:
            page_list = parse_page_ranges(pages_str)
        except ValueError:
            messagebox.showerror("Error", "Invalid pages. Use e.g.: 1-5, 7, 9")
            return
        dpi_str = self.dpi_entry.get().strip()
        dpi = int(dpi_str) if dpi_str else 300
        self.configure(cursor="wait")
        self.update()
        try:
            self.pages = pdf_pages_to_images(pdf_path, page_list, dpi=dpi)
            if not self.pages:
                messagebox.showwarning("Warning", "No pages could be rendered.")
                return
            self.page_annotations = {i: [] for i in range(len(self.pages))}
            self.page_undo = {i: [] for i in range(len(self.pages))}
            self.page_redo = {i: [] for i in range(len(self.pages))}
            self.current_page_idx = -1
            self._rebuild_thumbnails()
            self._select_page(0)
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self.configure(cursor="")

    # ---------------------------------------------------------------
    # Thumbnail sidebar
    # ---------------------------------------------------------------

    def _rebuild_thumbnails(self):
        for w in self.thumb_widgets:
            w.destroy()
        self.thumb_widgets.clear()
        c = self.c
        for i, page_img in enumerate(self.pages):
            thumb = page_img.copy()
            thumb.thumbnail((105, 150), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(thumb.width, thumb.height))
            btn = ctk.CTkButton(
                self.sidebar, text=f"  Page {i + 1}  ", image=ctk_img, compound="top",
                width=110, font=ctk.CTkFont(size=10),
                fg_color=c["thumb_bg"], hover_color=c["tool_hover"],
                text_color=c["thumb_text"],
                command=lambda idx=i: self._select_page(idx),
            )
            btn._ctk_img = ctk_img  # prevent GC
            btn.pack(pady=3)
            self.thumb_widgets.append(btn)

    # ---------------------------------------------------------------
    # Page switching (save / restore per-page state)
    # ---------------------------------------------------------------

    def _save_current_page(self):
        idx = self.current_page_idx
        if idx < 0:
            return
        self.page_annotations[idx] = list(self.editor.annotations)
        self.page_undo[idx] = list(self.editor._undo_stack)
        self.page_redo[idx] = list(self.editor._redo_stack)

    def _select_page(self, idx: int):
        self._save_current_page()
        self.current_page_idx = idx
        self.editor.load_state(
            self.pages[idx],
            list(self.page_annotations.get(idx, [])),
            list(self.page_undo.get(idx, [])),
            list(self.page_redo.get(idx, [])),
        )
        self.after(50, self.editor.fit_to_frame)
        for i, btn in enumerate(self.thumb_widgets):
            if i == idx:
                btn.configure(border_width=3, border_color=self.c["sel_border"])
            else:
                btn.configure(border_width=0)
        self._update_page_indicator()

    def _prev_page(self):
        if not self.pages or self.current_page_idx <= 0:
            return
        self._select_page(self.current_page_idx - 1)

    def _next_page(self):
        if not self.pages or self.current_page_idx >= len(self.pages) - 1:
            return
        self._select_page(self.current_page_idx + 1)

    def _update_page_indicator(self):
        total = len(self.pages)
        idx = self.current_page_idx
        if total == 0 or idx < 0:
            self._page_label.configure(text="No pages loaded", text_color=self.c["text_dim"])
            self._ann_count_label.configure(text="")
            return
        self._page_label.configure(
            text=f"Page {idx + 1} of {total}",
            text_color=self.c["text"])
        ann_n = len(self.editor.annotations)
        self._ann_count_label.configure(
            text=f"{ann_n} annotation{'s' if ann_n != 1 else ''}" if ann_n else "")

    # ---------------------------------------------------------------
    # Export
    # ---------------------------------------------------------------

    def _build_merged(self) -> Image.Image | None:
        """Render all pages with annotations and merge into one image."""
        if not self.pages:
            return None
        self._save_current_page()
        rendered = []
        for i, page_img in enumerate(self.pages):
            anns = self.page_annotations.get(i, [])
            if anns:
                rendered.append(render_annotations(page_img, anns).convert("RGB"))
            else:
                rendered.append(page_img.copy())
        lang = "ar" if "Arabic" in self.lang_var.get() else "en"
        return merge_images(rendered, lang, self.wm_enabled.get(),
                            self.wm_entry.get().strip(), self.wm_color)

    def _export(self):
        out_path = self.out_entry.get().strip()
        if not out_path:
            messagebox.showerror("Error", "Specify an output file.")
            return
        merged = self._build_merged()
        if merged is None:
            messagebox.showerror("Error", "No pages loaded.")
            return

        base, ext = os.path.splitext(out_path)
        if ext.lower() not in (".png", ".jpg", ".jpeg"):
            out_path = base + ".png"
        try:
            merged.save(out_path)
            messagebox.showinfo("Done", f"Saved to:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def _preview(self):
        merged = self._build_merged()
        if merged is None:
            messagebox.showwarning("Preview", "No pages loaded — nothing to preview.")
            return

        win = ctk.CTkToplevel(self)
        win.title("Scan Preview")
        win.geometry("900x700")
        win.transient(self)
        win.grab_set()

        c = self.c
        win.configure(fg_color=c["bg"])

        bar = ctk.CTkFrame(win, fg_color=c["panel"], height=44, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="\U0001F50D  Scan Preview",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=c["gold"]).pack(side="left", padx=12)

        pv_scale = [1.0]
        pv_photo = [None]
        pv_resized = [None]

        canvas = Canvas(win, bg=c["canvas_bg"], highlightthickness=0)
        vs = Scrollbar(win, orient="vertical", command=canvas.yview)
        hs = Scrollbar(win, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
        canvas.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")

        def _show(scale=None):
            if scale is not None:
                pv_scale[0] = scale
            s = pv_scale[0]
            w = max(1, int(merged.width * s))
            h = max(1, int(merged.height * s))
            resized = merged.resize((w, h), Image.BILINEAR)
            pv_photo[0] = ImageTk.PhotoImage(resized)
            pv_resized[0] = resized  # prevent GC while PhotoImage references it
            canvas.delete("all")
            canvas.create_image(0, 0, anchor="nw", image=pv_photo[0])
            canvas.configure(scrollregion=(0, 0, w, h))
            pv_lbl.configure(text=f"{int(s * 100)}%")

        def _fit():
            canvas.update_idletasks()
            cw = canvas.winfo_width() or 800
            ch = canvas.winfo_height() or 600
            s = min(cw / merged.width, ch / merged.height, 3.0)
            _show(max(0.05, s))

        def _wheel(e):
            if hasattr(e, 'num') and e.num == 4:
                delta = 1
            elif hasattr(e, 'num') and e.num == 5:
                delta = -1
            else:
                delta = 1 if e.delta > 0 else -1
            factor = 1.15 if delta > 0 else 1 / 1.15
            _show(max(0.05, min(5.0, pv_scale[0] * factor)))

        canvas.bind("<MouseWheel>", _wheel)
        canvas.bind("<Button-4>", _wheel)
        canvas.bind("<Button-5>", _wheel)

        # Auto-fit on window resize (debounced)
        auto_fit = [True]  # track whether auto-fit is active
        _resize_after_id = [None]

        def _on_resize(e):
            if not auto_fit[0]:
                return
            if _resize_after_id[0]:
                canvas.after_cancel(_resize_after_id[0])
            _resize_after_id[0] = canvas.after(80, _fit)

        canvas.bind("<Configure>", _on_resize)

        def _show_manual(scale):
            auto_fit[0] = False
            _show(scale)

        btn_kw = dict(height=30, corner_radius=6, font=ctk.CTkFont(size=11), width=44,
                      fg_color=c["btn"], hover_color=c["btn_hover"])
        ctk.CTkButton(bar, text="Fit", command=lambda: (auto_fit.__setitem__(0, True), _fit()),
                      **btn_kw).pack(side="left", padx=(12, 2))
        ctk.CTkButton(bar, text="1x", command=lambda: _show_manual(1.0), **btn_kw).pack(side="left", padx=2)
        ctk.CTkButton(bar, text="50%", command=lambda: _show_manual(0.5), **btn_kw).pack(side="left", padx=2)
        pv_lbl = ctk.CTkLabel(bar, text="100%", width=50,
                              font=ctk.CTkFont(size=11, weight="bold"),
                              text_color=c["blue_light"])
        pv_lbl.pack(side="left", padx=6)

        ctk.CTkButton(bar, text="Close", width=60, height=30, corner_radius=6,
                      fg_color=c["red"], hover_color=c["red_hover"],
                      text_color="white", font=ctk.CTkFont(size=11),
                      command=win.destroy).pack(side="right", padx=10)

        # Override wheel to disable auto-fit when user zooms manually
        def _wheel_manual(e):
            auto_fit[0] = False
            _wheel(e)

        canvas.bind("<MouseWheel>", _wheel_manual)
        canvas.bind("<Button-4>", _wheel_manual)
        canvas.bind("<Button-5>", _wheel_manual)

        win.after(100, _fit)

    # ---------------------------------------------------------------
    # Reset
    # ---------------------------------------------------------------

    def _reset(self):
        self.pages.clear()
        self.page_annotations.clear()
        self.page_undo.clear()
        self.page_redo.clear()
        self.current_page_idx = -1
        self.editor.base_image = None
        self.editor.annotations.clear()
        self.editor._undo_stack.clear()
        self.editor._redo_stack.clear()
        self.editor.pending_image = None
        self.editor.canvas.delete("all")
        self._rebuild_thumbnails()
        self._page_label.configure(text="No pages loaded")
        self._ann_count_label.configure(text="")

    # ---------------------------------------------------------------
    # Shortcuts
    # ---------------------------------------------------------------

    def _bind_shortcuts(self):
        self.bind_all("<Control-z>", lambda e: self.editor.undo())
        self.bind_all("<Control-y>", lambda e: self.editor.redo())
        self.bind_all("<Control-Z>", lambda e: self.editor.undo())
        # macOS: Command+Z / Command+Y
        self.bind_all("<Command-z>", lambda e: self.editor.undo())
        self.bind_all("<Command-y>", lambda e: self.editor.redo())
        self.bind_all("<Command-Z>", lambda e: self.editor.undo())
        # Page navigation
        self.bind_all("<Left>", lambda e: self._prev_page())
        self.bind_all("<Right>", lambda e: self._next_page())
        self.bind_all("<Prior>", lambda e: self._prev_page())  # PgUp
        self.bind_all("<Next>", lambda e: self._next_page())   # PgDn

