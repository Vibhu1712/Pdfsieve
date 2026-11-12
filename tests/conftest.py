"""Sample PDFs are generated on the fly with reportlab, so the repository holds no binary files."""

from __future__ import annotations

import pytest

reportlab = pytest.importorskip("reportlab")
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

W, H = A4  # 595.27 x 841.89 points


def top(y: float) -> float:
    """reportlab measures y from the bottom; the tests think in pdfsieve's top-down space."""
    return H - y


@pytest.fixture(scope="session")
def pdfs(tmp_path_factory):
    d = tmp_path_factory.mktemp("pdfs")
    out = {}

    # 1. A simple invoice: text, a 3x2 table of lines, a filled box, metadata
    p = str(d / "invoice.pdf")
    c = canvas.Canvas(p, pagesize=A4)
    c.setTitle("Sample invoice")
    c.setAuthor("pdfsieve tests")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, top(80), "Invoice No 1234")
    c.setFont("Helvetica", 11)
    c.drawString(72, top(110), "Billed to: Ravi Kumar")
    # table: 3 columns x 2 rows, x = 72, 222, 372, 522; y = 150, 175, 200
    c.setLineWidth(0.8)
    for x in (72, 222, 372, 522):
        c.line(x, top(150), x, top(200))
    for y in (150, 175, 200):
        c.line(72, top(y), 522, top(y))
    for x, label in ((80, "Item"), (230, "Qty"), (380, "Amount")):
        c.drawString(x, top(168), label)
    for x, label in ((80, "Pens"), (230, "12"), (380, "5,000.00")):
        c.drawString(x, top(193), label)
    c.setFillColorRGB(1, 0, 0)
    c.rect(400, top(300), 100, 50, stroke=0, fill=1)  # red box, top-left at (400, 250)
    c.setFillColorRGB(0, 0, 0)
    c.showPage()
    # page 2: one line of text
    c.setFont("Times-Roman", 12)
    c.drawString(72, top(72), "Second page")
    c.showPage()
    c.save()
    out["invoice"] = p

    # 2. A page with /Rotate 90
    p = str(d / "rotated.pdf")
    c = canvas.Canvas(p, pagesize=A4)
    c.setPageRotation(90)
    c.setFont("Helvetica", 12)
    c.drawString(72, 72, "Rotated page text")  # near the bottom-left corner of the MediaBox
    c.showPage()
    c.save()
    out["rotated"] = p

    # 3. Sideways and invisible text
    p = str(d / "sideways.pdf")
    c = canvas.Canvas(p, pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(72, top(72), "Upright line")
    c.saveState()
    c.translate(300, top(400))
    c.rotate(90)
    c.drawString(0, 0, "Going up")
    c.restoreState()
    t = c.beginText(72, top(500))
    t.setFont("Helvetica", 12)
    t.setTextRenderMode(3)  # invisible, like the OCR layer of a scan
    t.textLine("hidden layer")
    c.drawText(t)
    c.showPage()
    c.save()
    out["sideways"] = p

    # 4. An embedded image
    from PIL import Image

    p = str(d / "image.pdf")
    img = Image.new("RGB", (40, 20), (0, 128, 255))
    ip = str(d / "blue.png")
    img.save(ip)
    c = canvas.Canvas(p, pagesize=A4)
    c.drawImage(ip, 100, top(300), width=200, height=100)  # top-left at (100, 200)
    c.showPage()
    c.save()
    out["image"] = p

    # 5. Password protected
    p = str(d / "locked.pdf")
    c = canvas.Canvas(p, pagesize=A4, encrypt="secret")
    c.setFont("Helvetica", 12)
    c.drawString(72, top(72), "Top secret")
    c.showPage()
    c.save()
    out["locked"] = p

    # 6. Text drawn as outlines (no text layer): a ring "O" made of two circles
    p = str(d / "outlines.pdf")
    c = canvas.Canvas(p, pagesize=A4)
    path = c.beginPath()
    path.circle(200, top(200), 50)
    path.circle(200, top(200), 30)
    c.drawPath(path, stroke=0, fill=1, fillMode=0)  # even-odd: the inner circle is a hole
    c.showPage()
    c.save()
    out["outlines"] = p

    return out
