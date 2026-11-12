"""Straight horizontal and vertical segments: table borders, underlines, rules.

Both stroked lines and the edges of filled rectangles count, since PDFs draw table borders either
way. Curves are ignored.
"""

from __future__ import annotations

from typing import List

from .model import Page, Segment, Shape

TOLERANCE = 1.0  # how far (points) a segment may lean and still count as straight


def _edges(page: Page):
    for it in page.items:
        if not isinstance(it, Shape):
            continue
        for pts, closed in it.subpaths:
            xy = [p[-2:] for p in pts]
            kinds = [p[0] for p in pts]
            if closed:
                xy.append(xy[0])
                kinds.append("l")
            for k, a, b in zip(kinds[1:], xy, xy[1:]):
                if k == "l":
                    yield a, b


def vertical_segments(page: Page, min_len: float = 4.0) -> List[Segment]:
    """Vertical strokes and edges as ``Segment(x, y_top, y_bottom)``."""
    return [Segment((a[0] + b[0]) / 2, min(a[1], b[1]), max(a[1], b[1]))
            for a, b in _edges(page)
            if abs(a[0] - b[0]) < TOLERANCE and abs(a[1] - b[1]) >= min_len]


def horizontal_segments(page: Page, min_len: float = 4.0) -> List[Segment]:
    """Horizontal strokes and edges as ``Segment(y, x_left, x_right)``."""
    return [Segment((a[1] + b[1]) / 2, min(a[0], b[0]), max(a[0], b[0]))
            for a, b in _edges(page)
            if abs(a[1] - b[1]) < TOLERANCE and abs(a[0] - b[0]) >= min_len]
