"""pdfsieve: read characters, words, lines, shapes and images from PDF pages, with coordinates.

Pure Python on top of pdfminer.six. Coordinates are PDF points with the origin at the top-left of
the visible page, after the page's rotation.

    >>> import pdfsieve
    >>> with pdfsieve.open("statement.pdf") as doc:
    ...     page = doc.page(0)
    ...     for w in page.words():
    ...         print(round(w.x0), round(w.y0), w.text)
"""

from .model import RGB, Glyph, Item, Page, Picture, Segment, Shape, Word, to_rgb
from .reader import Document, EmptyDocumentError, PasswordError, PdfSieveError, Recorder, open
from .segments import horizontal_segments, vertical_segments
from .words import LIGATURES, lines_from, words_from

__version__ = "0.1.0"

__all__ = [
    "open", "Document", "Page", "Glyph", "Shape", "Picture", "Word", "Segment", "Item", "RGB",
    "words_from", "lines_from", "vertical_segments", "horizontal_segments", "to_rgb",
    "LIGATURES", "Recorder", "PdfSieveError", "PasswordError", "EmptyDocumentError",
    "__version__",
]
