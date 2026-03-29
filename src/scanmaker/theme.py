"""Theme definitions for BurhanApp — dark & light QSS stylesheets + palette constants."""

# ── Palette constants (used by code outside QSS) ─────────────────────

DARK_PALETTE = {
    "editor_bg": "#141518",
    "thumb_active_border": "#3b82f6",
    "thumb_active_bg": "#1e3a5f",
}

LIGHT_PALETTE = {
    "editor_bg": "#d4d8e0",
    "thumb_active_border": "#2563eb",
    "thumb_active_bg": "#dbeafe",
}


# ── QSS Stylesheets ──────────────────────────────────────────────────

DARK_QSS = """
/* ── Base ── */
QMainWindow {
    background-color: #181a20;
    color: #e2e4e9;
    font-family: "Segoe UI", sans-serif;
    font-size: 12px;
}
QWidget {
    background-color: transparent;
    color: #e2e4e9;
    font-family: "Segoe UI", sans-serif;
    font-size: 12px;
}

/* ── Panels ── */
QFrame#panel {
    background-color: #22252e;
    border-radius: 10px;
    border: 1px solid #2c2f38;
    padding: 4px;
}

/* ── Toolbar area ── */
QWidget#toolbar_area {
    background-color: #22252e;
    border-radius: 8px;
    border: 1px solid #2c2f38;
    padding: 4px;
}

/* ── Tool groups ── */
QFrame#tool_group {
    background-color: #292c36;
    border-radius: 8px;
    border: 1px solid #343844;
    margin: 2px;
    min-height: 38px;
}

QFrame#toolbar_divider {
    background-color: #444a58;
    margin: 4px 2px;
}

QLabel#group_label {
    color: #6e7280;
    font-size: 9px;
    font-weight: 600;
    padding: 0 3px;
    background: transparent;
}

/* ── Buttons ── */
QToolButton {
    background-color: #333844;
    color: #e2e4e9;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
    font-size: 11px;
    border: 1px solid #3e4350;
    min-width: 32px;
}
QToolButton:hover {
    background-color: #3e4456;
    border-color: #4e5468;
}
QToolButton:checked {
    background-color: #10b981;
    color: white;
    border-color: #059669;
}
QToolButton:pressed { background-color: #292c36; }

QPushButton {
    background-color: #292c36;
    color: #e2e4e9;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    border: 1px solid #343844;
}
QPushButton:hover {
    background-color: #343844;
    border-color: #4e5468;
}
QPushButton:pressed { background-color: #22252e; }

QPushButton#green {
    background-color: #10b981;
    color: white;
    border: none;
    padding: 6px 16px;
}
QPushButton#green:hover { background-color: #34d399; }

QPushButton#red {
    background-color: #ef4444;
    color: white;
    border: none;
}
QPushButton#red:hover { background-color: #f87171; }

QPushButton#action_btn {
    background-color: #292c36;
    border: 1px solid #343844;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
    color: #e2e4e9;
}
QPushButton#action_btn:hover {
    background-color: #343844;
    border-color: #4e5468;
}

QCheckBox#theme_toggle {
    spacing: 0;
}
QCheckBox#theme_toggle::indicator {
    width: 48px; height: 26px;
    border-radius: 13px;
    background-color: #292c36;
    border: 1px solid #343844;
    image: url(none);
}
QCheckBox#theme_toggle::indicator:unchecked {
    background-color: #292c36;
}
QCheckBox#theme_toggle::indicator:checked {
    background-color: #3b82f6;
    border-color: #2563eb;
}

/* ── Labels ── */
QLabel { color: #e2e4e9; }
QLabel#dim { color: #6e7280; font-size: 14px; }
QLabel#gold { color: #f59e0b; font-weight: bold; font-size: 16px; }
QLabel#value_gold { color: #f59e0b; font-weight: bold; font-size: 11px; }
QLabel#value_blue { color: #60a5fa; font-weight: bold; font-size: 11px; }

/* ── Inputs ── */
QLineEdit {
    background-color: #292c36;
    color: #e2e4e9;
    border: 1px solid #343844;
    border-radius: 6px;
    padding: 5px 10px;
    selection-background-color: #3b82f6;
}
QLineEdit:focus { border-color: #3b82f6; }

QComboBox {
    background-color: #292c36;
    color: #e2e4e9;
    border-radius: 6px;
    padding: 5px 10px;
    border: 1px solid #343844;
}
QComboBox:hover { border-color: #4e5468; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #22252e;
    color: #e2e4e9;
    selection-background-color: #3b82f6;
    border: 1px solid #343844;
}

QCheckBox { spacing: 6px; color: #e2e4e9; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid #4e5468;
    background: #292c36;
}
QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; }

/* ── Sliders ── */
QSlider::groove:horizontal {
    background: #292c36;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #3b82f6;
    width: 16px; height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover { background: #60a5fa; }
QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 3px; }

/* ── Scrollbars ── */
QScrollArea { background-color: transparent; border: none; }
QScrollBar:vertical {
    background: transparent; width: 8px; border: none;
}
QScrollBar::handle:vertical {
    background: #3e4350; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #4e5468; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent; height: 8px; border: none;
}
QScrollBar::handle:horizontal {
    background: #3e4350; border-radius: 4px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #4e5468; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Hint cards ── */
QFrame#hint_card {
    background-color: #292c36;
    border-radius: 8px;
    border: 1px solid #343844;
    border-left: 3px solid #f59e0b;
    margin: 0px;
}
QFrame#hint_card:hover {
    border-color: #4e5468;
    border-left-color: #fbbf24;
    background-color: #2e3240;
}

/* ── Sidebar thumbnails ── */
QPushButton#thumb_btn {
    background-color: #292c36;
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 4px;
}
QPushButton#thumb_btn:hover {
    background-color: #333844;
    border-color: #4e5468;
}

/* ── Export bar buttons ── */
QPushButton#preview_btn {
    background-color: #3b82f6; color: white; font-weight: bold;
    border-radius: 6px; padding: 6px 16px; border: none;
}
QPushButton#preview_btn:hover { background-color: #60a5fa; }
QPushButton#export_btn {
    background-color: #f59e0b; color: #181a20; font-weight: bold;
    font-size: 13px; border-radius: 6px; padding: 6px 20px; border: none;
}
QPushButton#export_btn:hover { background-color: #fbbf24; }

/* ── Misc ── */
QSplitter::handle {
    background-color: transparent;
    width: 12px;
    image: none;
}
QSplitter::handle:horizontal {
    border-left: 1px solid #343844;
    border-right: 1px solid #343844;
    margin-top: 40%;
    margin-bottom: 40%;
}
QFrame#sidebar_sep { background-color: #343844; }
QFrame#vsep { background-color: #3e4350; }
QFrame#toolbar_row {
    background-color: #22252e; border-radius: 8px;
    border: 1px solid #2c2f38;
}
"""

LIGHT_QSS = """
/* ── Base ── */
QMainWindow {
    background-color: #f0f2f5;
    color: #111827;
    font-family: "Segoe UI", sans-serif;
    font-size: 12px;
}
QWidget {
    background-color: transparent;
    color: #111827;
    font-family: "Segoe UI", sans-serif;
    font-size: 12px;
}

/* ── Panels ── */
QFrame#panel {
    background-color: #ffffff;
    border-radius: 10px;
    border: 1px solid #e2e5ea;
    padding: 4px;
}

/* ── Toolbar area ── */
QWidget#toolbar_area {
    background-color: #ffffff;
    border-radius: 8px;
    border: 1px solid #e2e5ea;
    padding: 4px;
}

/* ── Tool groups ── */
QFrame#tool_group {
    background-color: #e8eaef;
    border-radius: 8px;
    border: 1px solid #d8dbe2;
    margin: 2px;
    min-height: 38px;
}

QFrame#toolbar_divider {
    background-color: #c0c4cc;
    margin: 4px 2px;
}

QLabel#group_label {
    color: #6b7280;
    font-size: 9px;
    font-weight: 600;
    padding: 0 3px;
    background: transparent;
}

/* ── Buttons ── */
QToolButton {
    background-color: #d4d8e0;
    color: #111827;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
    font-size: 11px;
    border: 1px solid #c4c8d0;
    min-width: 32px;
}
QToolButton:hover {
    background-color: #c4c8d4;
    border-color: #b0b4c0;
}
QToolButton:checked {
    background-color: #059669;
    color: white;
    border-color: #047857;
}
QToolButton:pressed { background-color: #b4b8c4; }

QPushButton {
    background-color: #d4d8e0;
    color: #111827;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    border: 1px solid #c4c8d0;
}
QPushButton:hover {
    background-color: #c4c8d4;
    border-color: #b0b4c0;
}
QPushButton:pressed { background-color: #b4b8c4; }

QPushButton#green {
    background-color: #059669;
    color: white;
    border: none;
    padding: 6px 16px;
}
QPushButton#green:hover { background-color: #10b981; }

QPushButton#red {
    background-color: #dc2626;
    color: white;
    border: none;
}
QPushButton#red:hover { background-color: #ef4444; }

QPushButton#action_btn {
    background-color: #d4d8e0;
    border: 1px solid #c4c8d0;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
    color: #111827;
}
QPushButton#action_btn:hover {
    background-color: #c4c8d4;
    border-color: #b0b4c0;
}

QCheckBox#theme_toggle {
    spacing: 0;
}
QCheckBox#theme_toggle::indicator {
    width: 48px; height: 26px;
    border-radius: 13px;
    background-color: #d4d8e0;
    border: 1px solid #c4c8d0;
    image: url(none);
}
QCheckBox#theme_toggle::indicator:unchecked {
    background-color: #d4d8e0;
}
QCheckBox#theme_toggle::indicator:checked {
    background-color: #3b82f6;
    border-color: #2563eb;
}

/* ── Labels ── */
QLabel { color: #111827; }
QLabel#dim { color: #6b7280; font-size: 14px; }
QLabel#gold { color: #d97706; font-weight: bold; font-size: 16px; }
QLabel#value_gold { color: #d97706; font-weight: bold; font-size: 11px; }
QLabel#value_blue { color: #2563eb; font-weight: bold; font-size: 11px; }

/* ── Inputs ── */
QLineEdit {
    background-color: #e8eaef;
    color: #111827;
    border: 1px solid #d8dbe2;
    border-radius: 6px;
    padding: 5px 10px;
    selection-background-color: #2563eb;
}
QLineEdit:focus { border-color: #2563eb; }

QComboBox {
    background-color: #e8eaef;
    color: #111827;
    border-radius: 6px;
    padding: 5px 10px;
    border: 1px solid #d8dbe2;
}
QComboBox:hover { border-color: #b0b4c0; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #111827;
    selection-background-color: #2563eb;
    border: 1px solid #d8dbe2;
}

QCheckBox { spacing: 6px; color: #111827; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid #b0b4c0;
    background: #e8eaef;
}
QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }

/* ── Sliders ── */
QSlider::groove:horizontal {
    background: #d4d8e0;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #2563eb;
    width: 16px; height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover { background: #3b82f6; }
QSlider::sub-page:horizontal { background: #2563eb; border-radius: 3px; }

/* ── Scrollbars ── */
QScrollArea { background-color: transparent; border: none; }
QScrollBar:vertical {
    background: transparent; width: 8px; border: none;
}
QScrollBar::handle:vertical {
    background: #c4c8d0; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #b0b4c0; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent; height: 8px; border: none;
}
QScrollBar::handle:horizontal {
    background: #c4c8d0; border-radius: 4px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #b0b4c0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Hint cards ── */
QFrame#hint_card {
    background-color: #ffffff;
    border-radius: 8px;
    border: 1px solid #d8dbe2;
    border-left: 3px solid #d97706;
    margin: 0px;
}
QFrame#hint_card:hover {
    border-color: #c4c8d0;
    border-left-color: #f59e0b;
    background-color: #f8f9fb;
}

/* ── Sidebar thumbnails ── */
QPushButton#thumb_btn {
    background-color: #e8eaef;
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 4px;
}
QPushButton#thumb_btn:hover {
    background-color: #d4d8e0;
    border-color: #b0b4c0;
}

/* ── Export bar buttons ── */
QPushButton#preview_btn {
    background-color: #2563eb; color: white; font-weight: bold;
    border-radius: 6px; padding: 6px 16px; border: none;
}
QPushButton#preview_btn:hover { background-color: #3b82f6; }
QPushButton#export_btn {
    background-color: #d97706; color: white; font-weight: bold;
    font-size: 13px; border-radius: 6px; padding: 6px 20px; border: none;
}
QPushButton#export_btn:hover { background-color: #f59e0b; }

/* ── Misc ── */
QSplitter::handle {
    background-color: transparent;
    width: 12px;
    image: none;
}
QSplitter::handle:horizontal {
    border-left: 1px solid #d8dbe2;
    border-right: 1px solid #d8dbe2;
    margin-top: 40%;
    margin-bottom: 40%;
}
QFrame#sidebar_sep { background-color: #d8dbe2; }
QFrame#vsep { background-color: #c4c8d0; }
QFrame#toolbar_row {
    background-color: #ffffff; border-radius: 8px;
    border: 1px solid #e2e5ea;
}
"""


def get_qss(theme_name: str) -> str:
    """Return the QSS string for the given theme ('dark' or 'light')."""
    return DARK_QSS if theme_name == "dark" else LIGHT_QSS


def get_palette(theme_name: str) -> dict:
    """Return the palette dict for the given theme ('dark' or 'light')."""
    return DARK_PALETTE if theme_name == "dark" else LIGHT_PALETTE
