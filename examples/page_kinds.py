"""Tell digital pages from scans and from text drawn as outlines, before choosing OCR.

    python examples/page_kinds.py some.pdf
"""

import sys

import pdfsieve


def kind(page):
    words = page.words(visible_only=True)
    if words:
        if page.undefined > 0.3 * max(len(page.glyphs), 1):
            return "text layer exists but most characters have no Unicode mapping: needs OCR"
        return f"digital text ({len(words)} words)"
    if page.words():
        return "scan with an invisible OCR layer (text is there, just hidden)"
    if page.curves >= 150:
        return f"text drawn as outlines ({page.curves} curves), e.g. 'Microsoft Print to PDF': needs OCR"
    if page.images:
        return f"scanned image ({page.images} image(s)): needs OCR"
    return "empty page"


with pdfsieve.open(sys.argv[1]) as doc:
    for page in doc:
        print(f"page {page.index + 1}: {kind(page)}")
