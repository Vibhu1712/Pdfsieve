"""Plain data classes for what pdfsieve finds on a page.

Every coordinate is in *page space*: PDF points (1/72 inch), origin at the TOP-LEFT of the visible
page (the CropBox), x to the right, y downwards, after the page's /Rotate has been applied. That is
the same convention as most image libraries, so a box can be scaled straight onto a rendered image.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple, Optional, Tuple, Union

RGB = Tuple[int, int, int]


@dataclass
class Glyph:
    """One character of real text, as the PDF draws it."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    """The Unicode text of the character (ligatures such as "ﬁ" stay as one character here)."""
    size: float
    """Font size in points, as it appears on the page."""
    font: str
    """The PDF's font name, e.g. ``"ABCDEF+Arial-BoldMT"``."""
    color: Optional[RGB]
    """Fill colour as (r, g, b) 0..255, or None when it can't be known (patterns, Lab, ...)."""
    visible: bool
    """False for invisible text (render modes 3 and 7), e.g. the hidden OCR layer of a scan."""
    upright: bool
    """True when the writing runs left to right (``turn == 0``)."""
    run: int = 0
    """Which text-showing operation drew it; characters of one table cell usually share a run."""
    base: float = 0.0
    """Baseline y in page space."""
    turn: int = 0
    """Writing direction: 0 normal, 90 reads bottom-to-top, 180 upside down, 270 top-to-bottom."""


@dataclass
class Shape:
    """One painted path.

    ``subpaths`` is a list of ``(points, closed)``. ``points`` starts with ``("m", x, y)`` and
    continues with ``("l", x, y)`` straight segments and ``("c", x1, y1, x2, y2, x3, y3)`` cubic
    Bézier curves, all in page space.
    """

    subpaths: list
    fill: Optional[RGB]
    """Fill colour, or None when the path is not filled (or filled with a pattern/shading)."""
    stroke: Optional[RGB]
    """Stroke colour, or None when the path is not stroked."""
    width: float
    """Stroke width in points on the page."""
    evenodd: bool
    """True for the even-odd fill rule, False for non-zero winding."""


@dataclass
class Picture:
    """One embedded image (an image XObject or inline image)."""

    stream: object
    """The pdfminer ``PDFStream`` holding the image data."""
    matrix: tuple
    """``(a, b, c, d, e, f)``: maps the unit square of the image onto page space."""
    color: Optional[RGB]
    """Paint colour for stencil masks (1-bit images painted in the current fill colour)."""

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """The image's bounding box on the page as (x0, y0, x1, y1)."""
        a, b, c, d, e, f = self.matrix
        xs = (e, e + a, e + c, e + a + c)
        ys = (f, f + b, f + d, f + b + d)
        return (min(xs), min(ys), max(xs), max(ys))


Item = Union[Shape, Picture]


class Word(NamedTuple):
    """A word: characters on one line with no space or wide gap between them."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


class Segment(NamedTuple):
    """A straight horizontal or vertical stroke or edge, e.g. a table border.

    For vertical segments ``a0``/``a1`` are the top and bottom y and ``pos`` is x;
    for horizontal segments they are the left and right x and ``pos`` is y.
    """

    pos: float
    a0: float
    a1: float

    @property
    def length(self) -> float:
        return self.a1 - self.a0


@dataclass
class Page:
    """Everything pdfsieve recorded on one page."""

    width: float
    """Width of the visible page in points, after rotation."""
    height: float
    """Height of the visible page in points, after rotation."""
    rotation: int
    """The page's /Rotate value (0, 90, 180 or 270); already applied to all coordinates."""
    glyphs: list = field(default_factory=list)
    """Every character, in drawing order (a list of :class:`Glyph`)."""
    items: list = field(default_factory=list)
    """Shapes and pictures in drawing order (:class:`Shape` and :class:`Picture`)."""
    fonts: set = field(default_factory=set)
    """Names of the fonts used for text on the page."""
    curves: int = 0
    """Number of Bézier curve segments; a large number with no text usually means text drawn as
    outlines (e.g. "Microsoft Print to PDF" output)."""
    images: int = 0
    """Number of images drawn on the page."""
    undefined: int = 0
    """Characters the fonts could not map to Unicode (shown as U+FFFD in ``glyphs``)."""
    index: int = 0
    """0-based page number."""

    @property
    def shapes(self) -> list:
        """Only the :class:`Shape` items."""
        return [i for i in self.items if isinstance(i, Shape)]

    @property
    def pictures(self) -> list:
        """Only the :class:`Picture` items."""
        return [i for i in self.items if isinstance(i, Picture)]

    def words(self, *, visible_only: bool = False) -> list:
        """The page's words as :class:`Word` tuples, line by line, top to bottom.

        ``visible_only=True`` skips invisible text, such as the hidden OCR layer of a scanned page.
        """
        from .words import words_from

        glyphs = [g for g in self.glyphs if g.visible] if visible_only else self.glyphs
        return words_from(glyphs)

    def lines(self, *, visible_only: bool = False) -> list:
        """The page's text as lines of words: a list of lists of :class:`Word`."""
        from .words import lines_from

        glyphs = [g for g in self.glyphs if g.visible] if visible_only else self.glyphs
        return lines_from(glyphs)

    def text(self, *, visible_only: bool = False) -> str:
        """Plain text of the page: words joined by spaces, one line of text per line."""
        return "\n".join(" ".join(w.text for w in line) for line in self.lines(visible_only=visible_only))

    def vertical_lines(self, min_len: float = 4.0) -> list:
        """Straight vertical strokes and edges (table borders) as :class:`Segment` (x, top, bottom)."""
        from .segments import vertical_segments

        return vertical_segments(self, min_len)

    def horizontal_lines(self, min_len: float = 4.0) -> list:
        """Straight horizontal strokes and edges as :class:`Segment` (y, left, right)."""
        from .segments import horizontal_segments

        return horizontal_segments(self, min_len)


def to_rgb(color, space=None) -> Optional[RGB]:
    """A PDF colour as (r, g, b) 0..255, or None when it can't be known (patterns, shadings)."""
    name = getattr(space, "name", "") or ""
    if name == "Pattern":
        return None
    try:
        if isinstance(color, (int, float)):
            vals = [float(color)]
        else:
            vals = [float(v) for v in color]
    except (TypeError, ValueError):
        return None
    vals = [min(max(v, 0.0), 1.0) for v in vals]
    if len(vals) == 1:
        g = vals[0]
        if name in ("Separation", "DeviceN"):  # tint: 1 = full ink
            g = 1 - g
        elif name == "Indexed":
            return None
        v = round(g * 255)
        return (v, v, v)
    if len(vals) == 3:
        if name == "Lab":
            return None
        return (round(vals[0] * 255), round(vals[1] * 255), round(vals[2] * 255))
    if len(vals) == 4:
        c, m, y, k = vals
        return (round(255 * (1 - min(1, c + k))), round(255 * (1 - min(1, m + k))),
                round(255 * (1 - min(1, y + k))))
    return None
