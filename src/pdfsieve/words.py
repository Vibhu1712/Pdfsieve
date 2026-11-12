"""Joining characters into words and lines.

Two characters belong to the same word when they sit on the same line with no space character
between them and no gap wider than about an eighth of the letter size. Justified text squeezes its
spaces down to about a sixth, so the threshold is tight on purpose. Characters drawn by separate
text operations (typically separate table cells) need an even smaller gap to be split.

Sideways text (``Glyph.turn`` 90, 180 or 270) is grouped in its own reading direction and
returned after the upright text.
"""

from __future__ import annotations

from typing import Iterable, List

from .model import Glyph, Word

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}

# Word-splitting thresholds, as fractions of the letter size.
GAP = 0.12        # any gap wider than this ends a word
RUN_GAP = 0.08    # ...or this, between characters from different text operations
LINE_TOL = 0.35   # centres closer than this (vertically) are on the same line

# Turn boxes into a frame where the writing runs left to right, and back.
_INTO = {0: lambda x, y: (x, y), 90: lambda x, y: (-y, x),
         180: lambda x, y: (-x, -y), 270: lambda x, y: (y, -x)}
_BACK = {0: lambda x, y: (x, y), 90: lambda x, y: (y, -x),
         180: lambda x, y: (-x, -y), 270: lambda x, y: (-y, x)}


def lines_from(glyphs: Iterable[Glyph]) -> List[List[Word]]:
    """Group characters into lines of :class:`Word`, top to bottom (upright text first)."""
    glyphs = list(glyphs)
    out: List[List[Word]] = []
    for turn in (0, 90, 180, 270):
        into, back = _INTO[turn], _BACK[turn]
        boxes = []
        for g in glyphs:
            if g.turn != turn or not g.text:
                continue
            (ax, ay), (bx, by) = into(g.x0, g.y0), into(g.x1, g.y1)
            boxes.append((min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), g.text, g.size, g.run))
        for line in _lines(boxes):
            words = []
            for x0, y0, x1, y1, text in line:
                (ax, ay), (bx, by) = back(x0, y0), back(x1, y1)
                words.append(Word(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), text))
            if words:
                out.append(words)
    return out


def words_from(glyphs: Iterable[Glyph]) -> List[Word]:
    """Join characters into words. Returns :class:`Word` tuples ``(x0, y0, x1, y1, text)``,
    line by line."""
    return [w for line in lines_from(glyphs) for w in line]


def _lines(boxes: list) -> list:
    """boxes: (x0, y0, x1, y1, text, size, run) with the writing running left to right.
    Returns lines, each a list of (x0, y0, x1, y1, text) words."""
    seen = set()
    chars = []
    for b in boxes:
        key = (round(b[0], 0), round(b[1], 0), b[4])  # fake bold prints each letter twice
        if key in seen and b[4].strip():
            continue
        seen.add(key)
        chars.append(b)
    chars.sort(key=lambda b: ((b[1] + b[3]) / 2, b[0]))
    lines: list = []
    for b in chars:
        cy = (b[1] + b[3]) / 2
        for line in reversed(lines[-4:]):
            ref = line[-1]
            if abs(cy - (ref[1] + ref[3]) / 2) <= LINE_TOL * max(min(ref[5], b[5]), 1):
                line.append(b)
                break
        else:
            lines.append([b])
    out = []
    for line in lines:
        line.sort(key=lambda b: b[0])
        words: list = []
        cur: list = []

        def flush():
            if cur:
                text = "".join(LIGATURES.get(c[4], c[4]) for c in cur)
                words.append((min(c[0] for c in cur), min(c[1] for c in cur),
                              max(c[2] for c in cur), max(c[3] for c in cur), text))
                cur.clear()

        for b in line:
            if not b[4].strip():
                flush()
                continue
            if cur:
                gap, size = b[0] - cur[-1][2], max(min(b[5], cur[-1][5]), 1)
                if gap > GAP * size or (b[6] != cur[-1][6] and gap > RUN_GAP * size):
                    flush()
            cur.append(b)
        flush()
        if words:
            out.append(words)
    return out
