# BurhanApp

A modern PDF annotation and scan-generation tool built with Python, CustomTkinter, and PyMuPDF.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **PDF Viewer** — Load multi-page PDFs and navigate with arrow keys or Page Up/Down
- **Annotation Tools** — Highlight, underline, border, text lift, arrow, rectangle, ellipse
- **Image Overlay** — Place images with drag-to-draw, resize (edge or corner), move, and delete
- **Rich Text Annotations** — Drag to create text boxes with per-character bold/italic/color/font formatting
- **Line Spacing Control** — Adjustable line spacing (1.0x–3.0x) for text annotations
- **Floating Ruler** — Snip & Sketch–style ruler overlay with rotation (scroll/Shift+scroll)
- **Measurement Tool** — Measure distances on the page in pixels
- **Light & Dark Theme** — Toggle between light and dark UI modes
- **Preview & Export** — Preview rendered output, export pages as PNG/JPEG or merged PDF
- **Undo/Redo** — Full undo/redo history for all annotations
- **Cross-platform** — Works on Windows and macOS (keyboard shortcuts, trackpad gestures, font resolution)

## Download

### Windows
Download the latest release from the [Releases](../../releases) page — grab the `.zip` file, extract it, and run `BurhanApp.exe`.

### From Source (Windows or macOS)
```bash
git clone https://github.com/YOUR_USERNAME/BurhanApp.git
cd BurhanApp
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

## Usage

1. Click **Open PDF** to load a PDF file
2. Select an annotation tool from the toolbar (Highlight, Underline, Arrow, etc.)
3. **Drag on the page** to draw annotations
4. Use **Image** to overlay images — click to select, Delete to remove, right-click drag to move/resize
5. Use **Text** to create rich text boxes — click an existing one to re-edit
6. **Preview** to see the full rendered result, **Export** to save as PNG/JPEG/PDF

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Z / ⌘+Z | Undo |
| Ctrl+Y / ⌘+Y | Redo |
| ← → | Previous / Next page |
| PgUp / PgDn | Previous / Next page |
| Ctrl+Scroll / ⌘+Scroll | Zoom in/out |
| Delete / Backspace | Delete selected image |
| Escape | Deselect |

### Mouse Controls

| Action | Windows | macOS |
|--------|---------|-------|
| Draw annotation | Left-click drag | Left-click drag |
| Move image/text | Right-click drag | Two-finger tap + drag / Ctrl+click drag |
| Resize image | Right-click edge/corner | Two-finger tap edge/corner + drag |
| Select image | Left-click on image | Left-click on image |
| Zoom | Ctrl + scroll | ⌘ + scroll / pinch |

## Building the Executable

```bash
pip install pyinstaller
pyinstaller BurhanApp.spec --noconfirm
```

The output will be in `dist/BurhanApp/`. Zip the folder for distribution.

## Project Structure

```
BurhanApp/
├── run.py                  # Entry point
├── BurhanApp.spec          # PyInstaller build config
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Package metadata
├── assets/                 # Images and resources
└── src/scanmaker/          # Main package
    ├── __init__.py
    ├── __main__.py          # CLI entry point
    ├── app.py               # Main application window
    ├── canvas.py            # Interactive annotation canvas
    ├── models.py            # Data models (Tool, Annotation, TextRun)
    ├── rendering.py         # PDF rendering & annotation compositing
    └── utils.py             # Utility functions
```

## Requirements

- Python 3.10+
- customtkinter >= 5.2
- PyMuPDF >= 1.27
- Pillow >= 10.0

## License

MIT License — see [LICENSE](LICENSE) for details.
