"""Command line: ``pdfsieve file.pdf`` (or ``python -m pdfsieve file.pdf``)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import PdfSieveError, __version__
from . import open as open_pdf


def parse_pages(spec: Optional[str], count: int) -> List[int]:
    """'1,3-5' -> [0, 2, 3, 4] (input is 1-based, output 0-based). None means every page."""
    if not spec:
        return list(range(count))
    out: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo = int(a) if a.strip() else 1
            hi = int(b) if b.strip() else count
        else:
            lo = hi = int(part)
        for n in range(lo, hi + 1):
            if not 1 <= n <= count:
                raise ValueError(f"page {n} out of range (the PDF has {count} pages)")
            if n - 1 not in out:
                out.append(n - 1)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdfsieve",
        description="Print the text, words or full content of PDF pages, with coordinates "
                    "(points, origin top-left).")
    ap.add_argument("pdf", help="the PDF file")
    ap.add_argument("-p", "--pages", help="pages to read, 1-based, e.g. 1,3-5 (default: all)")
    ap.add_argument("-f", "--format", choices=("text", "words", "json", "info"), default="text",
                    help="text: plain text; words: one word per line with its box; json: words, "
                         "lines and page facts; info: document and page summary (default: text)")
    ap.add_argument("--visible-only", action="store_true",
                    help="skip invisible text, such as the hidden OCR layer of a scan")
    ap.add_argument("--password", default="", help="password for an encrypted PDF")
    ap.add_argument("-V", "--version", action="version", version=f"pdfsieve {__version__}")
    args = ap.parse_args(argv)

    try:
        doc = open_pdf(args.pdf, password=args.password)
    except (OSError, PdfSieveError) as exc:
        print(f"pdfsieve: {exc}", file=sys.stderr)
        return 2
    with doc:
        try:
            pages = parse_pages(args.pages, doc.page_count)
        except ValueError as exc:
            print(f"pdfsieve: {exc}", file=sys.stderr)
            return 2
        vis = args.visible_only
        if args.format == "info":
            meta = doc.metadata()
            print(f"File:      {args.pdf}")
            print(f"Pages:     {doc.page_count}   encrypted: {doc.encrypted}")
            for k in ("title", "author", "producer", "creator"):
                if meta.get(k):
                    print(f"{k.capitalize() + ':':<10} {meta[k]}")
            for i in pages:
                p = doc.page(i)
                print(f"Page {i + 1}: {p.width:.1f} x {p.height:.1f} pt, rotate {p.rotation}, "
                      f"{len(p.words(visible_only=vis))} words, {p.images} images, "
                      f"{len(p.shapes)} shapes, {p.curves} curves, {len(p.fonts)} fonts"
                      + (f", {p.undefined} unmapped chars" if p.undefined else "")
                      + (f"  [damaged: {doc.errors[i]}]" if i in doc.errors else ""))
            return 0
        if args.format == "json":
            out = []
            for i in pages:
                p = doc.page(i)
                out.append({
                    "page": i + 1, "width": round(p.width, 2), "height": round(p.height, 2),
                    "rotation": p.rotation, "images": p.images, "curves": p.curves,
                    "fonts": sorted(f for f in p.fonts if f),
                    "lines": [[[round(w.x0, 2), round(w.y0, 2), round(w.x1, 2), round(w.y1, 2), w.text]
                               for w in line] for line in p.lines(visible_only=vis)],
                })
            json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
            print()
            return 0
        for n, i in enumerate(pages):
            p = doc.page(i)
            if args.format == "words":
                for w in p.words(visible_only=vis):
                    print(f"{i + 1}\t{w.x0:.1f}\t{w.y0:.1f}\t{w.x1:.1f}\t{w.y1:.1f}\t{w.text}")
            else:
                if n:
                    print("\f", end="")
                print(p.text(visible_only=vis))
    return 0


if __name__ == "__main__":
    sys.exit(main())
