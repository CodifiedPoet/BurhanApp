"""Data models — Tool enum and Annotation dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class Tool(Enum):
    HIGHLIGHT = auto()
    UNDERLINE = auto()
    BORDER = auto()
    ARROW = auto()
    CURVED_ARROW = auto()
    TEXT_LIFT = auto()
    RECTANGLE = auto()
    ELLIPSE = auto()
    ROUNDED_RECT = auto()
    LINE = auto()
    FREEHAND = auto()
    CALLOUT = auto()
    BRACKET = auto()
    STAR = auto()
    DIAMOND = auto()
    CONNECTOR = auto()
    IMAGE = auto()
    TEXT = auto()


# Effects that can be freely combined on a rectangular region
EFFECTS = frozenset({Tool.HIGHLIGHT, Tool.UNDERLINE, Tool.BORDER, Tool.TEXT_LIFT})
# Shapes are exclusive standalone tools
SHAPES = frozenset({Tool.ARROW, Tool.CURVED_ARROW, Tool.RECTANGLE, Tool.ELLIPSE,
                    Tool.ROUNDED_RECT, Tool.LINE, Tool.FREEHAND,
                    Tool.CALLOUT, Tool.BRACKET, Tool.STAR, Tool.DIAMOND,
                    Tool.CONNECTOR})
# Overlay tools that behave like shapes (exclusive, click/drag to place)
OVERLAYS = frozenset({Tool.IMAGE, Tool.TEXT})


@dataclass
class TextRun:
    """A contiguous span of text with uniform formatting."""
    text: str
    font_family: str = "Arial"
    font_size: int = 24
    font_bold: bool = False
    font_italic: bool = False
    font_color: tuple = (0, 0, 0)


@dataclass
class Annotation:
    tools: frozenset  # set of Tool values
    x1: int
    y1: int
    x2: int
    y2: int
    color: tuple = (255, 255, 0)
    opacity: float = 0.4
    line_width: int = 3
    lift_zoom: float = 1.08
    line_style: str = "solid"       # "solid", "dashed", "dotted"
    arrow_head: str = "filled"      # "filled", "open", "diamond", "double", "none"
    curve_offset: float = 0.25     # Bezier bow amount (fraction of line length)
    # Callout tail anchor (image coords, relative to box)
    tail_x: int = 0
    tail_y: int = 0
    # Bracket style: "curly" or "square"
    bracket_style: str = "curly"
    # Star / polygon
    polygon_sides: int = 5            # number of outer points
    star_inner_ratio: float = 0.45    # inner radius as fraction of outer
    # Connector line style: "straight" or "elbow"
    connector_style: str = "straight"
    # Gradient fill: "none", "linear", "radial"
    gradient_type: str = "none"
    gradient_color2: tuple = (255, 255, 255)  # second gradient stop color
    # Freehand pen points (list of (x, y) tuples in image coords)
    points: list = field(default_factory=list)
    # Image overlay fields
    image_data: object = None  # PIL Image (kept as object to avoid circular import)
    # Text annotation fields
    text: str = ""
    font_family: str = "Arial"
    font_size: int = 24
    font_bold: bool = False
    font_italic: bool = False
    font_color: tuple = (0, 0, 0)          # RGB text color
    bg_color: tuple | None = (255, 255, 255)  # RGB background or None for transparent
    line_spacing: float = 1.2  # line-height multiplier (1.0 = tight, 2.0 = double)
    # Rich text: list of TextRun spans (overrides text/font_* when present)
    text_runs: list = field(default_factory=list)
