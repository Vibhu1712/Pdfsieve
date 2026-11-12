"""Reading a PDF with pdfminer.six and recording what each page draws."""

from __future__ import annotations

import builtins
import io
import logging
import math
import os
from typing import BinaryIO, Dict, Iterator, Optional, Tuple, Union

from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.layout import LTChar
from pdfminer.pdfdocument import PDFDocument, PDFPasswordIncorrect
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1
from pdfminer.utils import apply_matrix_pt

from .model import Glyph, Page, Picture, Shape, to_rgb

logging.getLogger("pdfminer").setLevel(logging.ERROR)

Source = Union[str, "os.PathLike[str]", bytes, bytearray, memoryview, BinaryIO]


class PdfSieveError(Exception):
    """Base class for pdfsieve errors."""


class PasswordError(PdfSieveError, PermissionError):
    """The PDF needs a password that wasn't given (or the given one is wrong)."""


class EmptyDocumentError(PdfSieveError, ValueError):
    """The PDF has no pages."""


BLACK = (0, 0, 0)


def _color(value, space):
    # A colour never set is the PDF default, black. Older pdfminer.six leaves it as None.
    return BLACK if value is None else to_rgb(value, space)


def _ncolor(gstate, ncs=None):
    """The fill colour of a graphics state. pdfminer.six before 2025 doesn't record the colour
    space there, so the colour is then read by its number of components alone."""
    return _color(gstate.ncolor, ncs if ncs is not None else getattr(gstate, "ncs", None))


def _scolor(gstate):
    return _color(gstate.scolor, getattr(gstate, "scs", None))


def _turn(matrix) -> int:
    """Which way a character's writing points on the page, to the nearest quarter turn."""
    a, b = matrix[0], matrix[1]
    return int(round(math.degrees(math.atan2(b, a)) / 90.0)) % 4 * 90


class _Interpreter(PDFPageInterpreter):
    """Lets the device see the graphics state when an image is drawn, so stencil masks get the
    current fill colour."""

    def do_Do(self, xobjid):
        self.device._gstate = self.graphicstate
        super().do_Do(xobjid)

    def do_EI(self, obj):
        self.device._gstate = self.graphicstate
        super().do_EI(obj)


class Recorder(PDFLayoutAnalyzer):
    """A pdfminer device that keeps what was drawn instead of analysing layout."""

    def __init__(self, rsrcmgr):
        super().__init__(rsrcmgr, laparams=None)
        self.page: Optional[Page] = None
        self._mode = 0
        self._run = 0
        self._fill = (0, 0, 0)  # last fill colour seen, used to paint stencil images
        self._gstate = None  # graphics state at the latest image, set by _Interpreter

    def begin_page(self, page, ctm):
        super().begin_page(page, ctm)
        # pdfminer's device space has its origin at the bottom-left of the (rotated) MediaBox.
        # Move to the top-left of the CropBox, which is the page people see.
        box = page.cropbox or page.mediabox
        xs, ys = [], []
        for px, py in ((box[0], box[1]), (box[2], box[3]), (box[0], box[3]), (box[2], box[1])):
            x, y = apply_matrix_pt(ctm, (px, py))
            xs.append(x)
            ys.append(y)
        self._ox, self._top = min(xs), max(ys)
        self.page = Page(max(xs) - min(xs), max(ys) - min(ys), int(page.rotate or 0) % 360)

    def _pt(self, x, y):
        x, y = apply_matrix_pt(self.ctm, (float(x), float(y)))
        return (x - self._ox, self._top - y)

    def render_string(self, textstate, seq, ncs, graphicstate):
        self._mode = getattr(textstate, "render", 0) or 0
        self._run += 1
        super().render_string(textstate, seq, ncs, graphicstate)

    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
        adv = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
        objs = getattr(self.cur_item, "_objs", None)
        item = objs.pop() if objs else None  # we keep our own record; don't let pdfminer's grow
        if not isinstance(item, LTChar):
            return adv
        text = item.get_text()
        if text.startswith("(cid:"):
            self.page.undefined += 1
            text = "�"
        x0, x1 = item.x0 - self._ox, item.x1 - self._ox
        y0, y1 = self._top - item.y1, self._top - item.y0
        base = y1
        turn = _turn(item.matrix)  # pdfminer counts upside-down text as upright; we don't
        size = item.size
        if turn in (90, 270):  # pdfminer's size follows the letter's width there
            size = abs(fontsize) * math.hypot(matrix[2], matrix[3]) or item.size
        if turn == 0:
            try:
                d0 = float(font.get_descent())
            except Exception:
                d0 = 0.0
            base = y1 + (d0 if -0.5 <= d0 <= 0 else -0.2) * item.size
            # pdfminer's box is exactly one font size tall. Use the font's own ascent and
            # descent when it states sensible ones, which is what other engines report.
            try:
                asc, desc = float(font.get_ascent()), float(font.get_descent())
            except Exception:
                asc = desc = 0.0
            desc_d = getattr(font, "descriptor", None) or {}
            if not any(k in desc_d for k in ("FontFile", "FontFile2", "FontFile3")):
                # A font that isn't stored in the PDF (Helvetica, Times...): viewers swap in
                # their own, and these are the line heights they use for it.
                base = y1 + (desc if -0.5 <= desc <= 0 else -0.2) * item.size
                y0, y1 = base - 1.07 * item.size, base + 0.3 * item.size
            elif 0.5 <= asc <= 1.3 and -0.5 <= desc <= 0:
                base = y1 + desc * item.size
                y0, y1 = base - asc * item.size, base - desc * item.size
        self.page.glyphs.append(Glyph(
            x0, y0, x1, y1, text, size, item.fontname or "",
            _ncolor(graphicstate, ncs), self._mode not in (3, 7), turn == 0,
            self._run, base, turn))
        self.page.fonts.add(item.fontname or "")
        return adv

    def paint_path(self, gstate, stroke, fill, evenodd, path):
        subs, cur, start = [], None, None
        for seg in path:
            op = seg[0]
            if op == "m":
                if cur and len(cur) > 1:
                    subs.append((cur, False))
                start = self._pt(seg[1], seg[2])
                cur = [("m",) + start]
            elif cur is None:
                continue
            elif op == "l":
                cur.append(("l",) + self._pt(seg[1], seg[2]))
            elif op in ("c", "v", "y"):
                last = cur[-1][-2:]
                if op == "c":
                    p1, p2, p3 = self._pt(seg[1], seg[2]), self._pt(seg[3], seg[4]), self._pt(seg[5], seg[6])
                elif op == "v":
                    p1, p2, p3 = last, self._pt(seg[1], seg[2]), self._pt(seg[3], seg[4])
                else:
                    p1, p3 = self._pt(seg[1], seg[2]), self._pt(seg[3], seg[4])
                    p2 = p3
                cur.append(("c",) + p1 + p2 + p3)
                self.page.curves += 1
            elif op == "h":
                if len(cur) > 1:
                    subs.append((cur, True))
                cur = [("m",) + start]
        if cur and len(cur) > 1:
            subs.append((cur, False))
        if fill:
            self._fill = _ncolor(gstate) or self._fill
        if not subs:
            return
        a, b, c, d = self.ctm[:4]
        scale = math.sqrt(abs(a * d - b * c)) or 1.0
        self.page.items.append(Shape(
            subs,
            _ncolor(gstate) if fill else None,
            _scolor(gstate) if stroke else None,
            float(gstate.linewidth or 0) * scale, bool(evenodd)))

    def render_image(self, name, stream):
        a, b, c, d, e, f = self.ctm
        # unit square -> page space (y flipped)
        m = (a, -b, c, -d, e - self._ox, self._top - f)
        gs = self._gstate
        color = _ncolor(gs) if gs is not None else None
        self.page.items.append(Picture(stream, m, color or self._fill))
        self.page.images += 1

    def receive_layout(self, ltpage):
        pass


class Document:
    """An open PDF. Pages are 0-based.

    ``source`` is a file path, the PDF's bytes, or a binary file object opened for reading.
    A file object you pass in is left open when the document is closed.

    Use it as a context manager, or call :meth:`close` when done::

        with pdfsieve.open("invoice.pdf") as doc:
            for page in doc:
                print(page.text())
    """

    def __init__(self, source: Source, password: str = ""):
        self._own = False
        if isinstance(source, (bytes, bytearray, memoryview)):
            self._fp = io.BytesIO(bytes(source))
            self._own = True
        elif isinstance(source, (str, os.PathLike)):
            self._fp = builtins.open(source, "rb")
            self._own = True
        else:
            self._fp = source
        try:
            self._doc = PDFDocument(PDFParser(self._fp), password=password)
            self._pages = list(PDFPage.create_pages(self._doc))
        except PDFPasswordIncorrect:
            self._close_fp()
            raise PasswordError("This PDF is password-protected; pass the right password.") from None
        except Exception as exc:
            self._close_fp()
            raise PdfSieveError(f"Could not read PDF: {type(exc).__name__}: {exc}") from exc
        if not self._pages:
            self._close_fp()
            raise EmptyDocumentError("The PDF has no pages.")
        self.encrypted: bool = bool(getattr(self._doc, "encryption", None))
        """True when the file is encrypted (it opened, so either no password was needed or the
        one given was right)."""
        self._rsrc = PDFResourceManager(caching=True)
        self._data: Dict[int, Page] = {}
        self.errors: Dict[int, str] = {}
        """Pages that were damaged, with the error. What was read before the fault is kept."""

    # ------------------------------------------------------------- basics

    @property
    def page_count(self) -> int:
        return len(self._pages)

    def __len__(self) -> int:
        return len(self._pages)

    def __iter__(self) -> Iterator[Page]:
        for i in range(len(self._pages)):
            yield self.page(i)

    def __getitem__(self, index: int) -> Page:
        return self.page(index)

    def __enter__(self) -> "Document":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def metadata(self) -> Dict[str, str]:
        """The document information dictionary, with lower-case keys
        (``title``, ``author``, ``producer``, ``creator``, ...)."""
        out: Dict[str, str] = {}
        for info in getattr(self._doc, "info", None) or []:
            for k, v in info.items():
                v = resolve1(v)
                if isinstance(v, bytes):
                    try:
                        v = v.decode("utf-16") if v[:2] in (b"\xfe\xff", b"\xff\xfe") else v.decode("latin-1")
                    except UnicodeError:
                        v = v.decode("latin-1", "replace")
                out[str(k).lower()] = str(v)
        return out

    def page(self, index: int) -> Page:
        """Everything on one page. Read once, then remembered. Negative indexes count from the end."""
        n = len(self._pages)
        if index < 0:
            index += n
        if not 0 <= index < n:
            raise IndexError(f"page {index} out of range (the PDF has {n} pages)")
        if index not in self._data:
            dev = Recorder(self._rsrc)
            try:
                _Interpreter(self._rsrc, dev).process_page(self._pages[index])
            except Exception as exc:  # a damaged page: keep what was read before the fault
                self.errors[index] = f"{type(exc).__name__}: {exc}"
                if dev.page is None:
                    dev.begin_page(self._pages[index], (1, 0, 0, 1, 0, 0))
            dev.page.index = index
            self._data[index] = dev.page
        return self._data[index]

    def size(self, index: int) -> Tuple[float, float]:
        """(width, height) of a page in points, after rotation, without reading its content."""
        if index in self._data:
            p = self._data[index]
            return (p.width, p.height)
        pg = self._pages[index]
        box = pg.cropbox or pg.mediabox
        w, h = abs(box[2] - box[0]), abs(box[3] - box[1])
        return (h, w) if int(pg.rotate or 0) % 180 == 90 else (w, h)

    def forget(self, index: Optional[int] = None) -> None:
        """Drop remembered page content to free memory (one page, or all pages)."""
        if index is None:
            self._data.clear()
        else:
            self._data.pop(index, None)

    def _close_fp(self) -> None:
        if self._own:
            try:
                self._fp.close()
            except Exception:
                pass

    def close(self) -> None:
        self._close_fp()


def open(source: Source, password: str = "") -> Document:  # noqa: A001 - mirrors builtins.open
    """Open a PDF: a path, its bytes, or a binary file object. See :class:`Document`."""
    return Document(source, password=password)
