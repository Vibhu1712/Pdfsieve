"""Read a ruled table into rows and columns, using its border lines.

    python examples/table_cells.py sample.pdf

The idea: horizontal and vertical lines give the grid; each word goes into the cell its centre
falls in. Works for tables drawn with full borders, which most payslips, invoices and statements
use.
"""

import sys

import pdfsieve


def merge(values, tol=1.5):
    """Sorted positions with near-duplicates merged (a border drawn twice, or a box edge)."""
    out = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def table(page, min_len=100):
    hs = page.horizontal_lines(min_len=min_len)
    if not hs:
        return []
    # the table's rules share one left and right end; other long lines (a header bar, a
    # footer rule) don't, so keep the biggest family of lines with the same span
    spans = {}
    for s in hs:
        spans.setdefault((round(s.a0), round(s.a1)), []).append(s)
    hs = max(spans.values(), key=len)
    left, right = min(s.a0 for s in hs), max(s.a1 for s in hs)
    rows = merge(s.pos for s in hs)
    # vertical borders that lie inside the table's horizontal span
    vs = [s for s in page.vertical_lines(min_len=10) if left - 2 <= s.pos <= right + 2
          and s.a0 >= rows[0] - 2 and s.a1 <= rows[-1] + 2]
    cols = merge(s.pos for s in vs)
    grid = [["" for _ in cols[:-1]] for _ in rows[:-1]]
    for w in page.words():
        r = next((i for i in range(len(rows) - 1) if rows[i] <= w.cy < rows[i + 1]), None)
        c = next((i for i in range(len(cols) - 1) if cols[i] <= w.cx < cols[i + 1]), None)
        if r is not None and c is not None:
            grid[r][c] = (grid[r][c] + " " + w.text).strip()
    return grid


with pdfsieve.open(sys.argv[1]) as doc:
    for row in table(doc.page(0)):
        print(" | ".join(f"{cell:<22}" for cell in row))
