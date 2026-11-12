from __future__ import annotations

import io
import json

import pytest

import pdfsieve
from pdfsieve import Glyph, Picture, Shape, Word
from pdfsieve.__main__ import main, parse_pages


def find(words, text):
    hits = [w for w in words if w.text == text]
    assert hits, f"{text!r} not in {[w.text for w in words]}"
    return hits[0]


def test_open_basics(pdfs):
    with pdfsieve.open(pdfs["invoice"]) as doc:
        assert doc.page_count == 2 == len(doc)
        assert not doc.encrypted
        meta = doc.metadata()
        assert meta["title"] == "Sample invoice"
        assert meta["author"] == "pdfsieve tests"
        w, h = doc.size(0)
        assert round(w) == 595 and round(h) == 842
        assert [p.index for p in doc] == [0, 1]
        assert doc[-1].index == 1
        with pytest.raises(IndexError):
            doc.page(5)


def test_words_and_coordinates(pdfs):
    with pdfsieve.open(pdfs["invoice"]) as doc:
        page = doc.page(0)
        words = page.words()
        inv = find(words, "Invoice")
        # drawn with its baseline 80 pt from the top at x = 72, 16 pt bold
        assert abs(inv.x0 - 72) < 0.5
        assert inv.y0 < 80 < inv.y1
        assert 10 < inv.height < 22
        # words on one line read left to right
        line = [w.text for w in words if abs(w.cy - inv.cy) < 2]
        assert line == ["Invoice", "No", "1234"]
        assert find(words, "5,000.00").x0 == pytest.approx(380, abs=0.5)
        assert page.text().splitlines()[0] == "Invoice No 1234"
        assert "Billed to: Ravi Kumar" in page.text()
        assert doc.page(1).text() == "Second page"


def test_fonts_and_glyphs(pdfs):
    with pdfsieve.open(pdfs["invoice"]) as doc:
        page = doc.page(0)
        assert {"Helvetica", "Helvetica-Bold"} <= page.fonts
        g = page.glyphs[0]
        assert isinstance(g, Glyph)
        assert g.text == "I" and g.font == "Helvetica-Bold" and g.size == pytest.approx(16)
        assert g.visible and g.upright and g.turn == 0
        assert g.color == (0, 0, 0)
        assert g.y0 < g.base < g.y1


def test_lines_and_shapes(pdfs):
    with pdfsieve.open(pdfs["invoice"]) as doc:
        page = doc.page(0)
        vx = sorted({round(s.pos) for s in page.vertical_lines()})
        assert vx == [72, 222, 372, 400, 500, 522]  # table rules, plus the red box's edges
        hy = sorted({round(s.pos) for s in page.horizontal_lines(min_len=200)})
        assert hy == [150, 175, 200]
        for s in page.vertical_lines():
            if round(s.pos) == 72:
                assert round(s.a0) == 150 and round(s.a1) == 200 and round(s.length) == 50
        red = [s for s in page.shapes if s.fill == (255, 0, 0)]
        assert len(red) == 1
        xs = [p[-2] for p in red[0].subpaths[0][0]]
        ys = [p[-1] for p in red[0].subpaths[0][0]]
        assert (round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))) == (400, 250, 500, 300)
        assert all(isinstance(i, (Shape, Picture)) for i in page.items)


def test_rotated_page(pdfs):
    with pdfsieve.open(pdfs["rotated"]) as doc:
        page = doc.page(0)
        assert page.rotation == 90
        mb = doc._pages[0].mediabox
        # the visible page is the MediaBox turned a quarter: width and height swap
        assert (page.width, page.height) == pytest.approx((mb[3] - mb[1], mb[2] - mb[0]))
        assert doc.size(0) == pytest.approx((page.width, page.height), abs=0.1)
        assert page.text() == "Rotated page text"
        for w in page.words():
            assert 0 <= w.x0 < w.x1 <= page.width and 0 <= w.y0 < w.y1 <= page.height
        # turned with the page, the line now runs down the left-hand side
        assert all(g.turn == 270 for g in page.glyphs)
        words = page.words()
        assert words[0].height > words[0].width and words[0].x0 > 60


def test_sideways_and_invisible(pdfs):
    with pdfsieve.open(pdfs["sideways"]) as doc:
        page = doc.page(0)
        texts = [w.text for w in page.words()]
        assert texts[:2] == ["Upright", "line"]
        assert "Going" in texts and "up" in texts
        going = find(page.words(), "Going")
        assert going.height > going.width  # runs up the page
        turned = [g for g in page.glyphs if g.text == "G"][0]
        assert turned.turn == 90 and not turned.upright
        assert "hidden" in texts
        assert "hidden" not in [w.text for w in page.words(visible_only=True)]
        assert "hidden layer" not in page.text(visible_only=True)


def test_image(pdfs):
    with pdfsieve.open(pdfs["image"]) as doc:
        page = doc.page(0)
        assert page.images == 1
        pic = page.pictures[0]
        assert [round(v) for v in pic.bbox] == [100, 200, 300, 300]


def test_outline_text_has_no_words(pdfs):
    with pdfsieve.open(pdfs["outlines"]) as doc:
        page = doc.page(0)
        assert page.words() == [] and page.text() == ""
        assert page.curves >= 8  # two circles of four Bézier quarters
        ring = page.shapes[0]
        assert ring.evenodd and len(ring.subpaths) == 2


def test_password(pdfs):
    with pytest.raises(pdfsieve.PasswordError):
        pdfsieve.open(pdfs["locked"])
    with pytest.raises(PermissionError):  # PasswordError is also a PermissionError
        pdfsieve.open(pdfs["locked"], password="wrong")
    with pdfsieve.open(pdfs["locked"], password="secret") as doc:
        assert doc.encrypted
        assert doc.page(0).text() == "Top secret"


def test_sources_bytes_and_file_object(pdfs):
    with open(pdfs["invoice"], "rb") as f:
        data = f.read()
    with pdfsieve.open(data) as doc:
        assert doc.page(1).text() == "Second page"
    f = io.BytesIO(data)
    doc = pdfsieve.open(f)
    assert doc.page(0).text().startswith("Invoice")
    doc.close()
    assert not f.closed  # caller's file stays open


def test_not_a_pdf(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(pdfsieve.PdfSieveError):
        pdfsieve.open(str(bad))
    with pytest.raises(FileNotFoundError):
        pdfsieve.open(str(tmp_path / "missing.pdf"))


def test_forget_rereads(pdfs):
    with pdfsieve.open(pdfs["invoice"]) as doc:
        first = doc.page(0)
        assert doc.page(0) is first
        doc.forget(0)
        again = doc.page(0)
        assert again is not first and again.text() == first.text()


# ------------------------------------------------------------- word grouping, no PDF needed

def g(x0, text, size=10.0, run=1, y=100.0):
    return Glyph(x0, y - size, x0 + 0.5 * size, y, text, size, "F", None, True, True, run, y, 0)


def test_words_from_gaps_and_ligatures():
    glyphs = [g(0, "a"), g(5, "b"), g(10, " "), g(15, "c"), g(20, "ﬁ"), g(30, "d")]
    words = pdfsieve.words_from(glyphs)
    assert [w.text for w in words] == ["ab", "cfi", "d"]  # 5 pt gap before "d" splits it
    assert isinstance(words[0], Word) and words[0][:4] == (0, 90, 10, 100)


def test_words_from_splits_separate_runs_sooner():
    same_run = [g(0, "1"), g(5.9, "2")]          # gap 0.9 = 0.09 x size, same operation: joined
    other_run = [g(0, "1"), g(5.9, "2", run=2)]  # same gap, separate operation: split
    assert [w.text for w in pdfsieve.words_from(same_run)] == ["12"]
    assert [w.text for w in pdfsieve.words_from(other_run)] == ["1", "2"]


def test_fake_bold_is_read_once():
    glyphs = [g(0, "A"), g(0.2, "A"), g(5, "B"), g(5.2, "B")]
    assert [w.text for w in pdfsieve.words_from(glyphs)] == ["AB"]


def test_lines_from_orders_top_to_bottom():
    glyphs = [g(0, "z", y=200), g(0, "a", y=100), g(5, "b", y=100.5)]
    lines = pdfsieve.lines_from(glyphs)
    assert [[w.text for w in line] for line in lines] == [["ab"], ["z"]]


def test_to_rgb():
    class CS:
        def __init__(self, name):
            self.name = name

    assert pdfsieve.to_rgb(0.5) == (128, 128, 128)
    assert pdfsieve.to_rgb((1, 0, 0)) == (255, 0, 0)
    assert pdfsieve.to_rgb((0, 0, 0, 1)) == (0, 0, 0)  # CMYK black
    assert pdfsieve.to_rgb((1, 0, 0, 0)) == (0, 255, 255)  # cyan
    assert pdfsieve.to_rgb(1, CS("Separation")) == (0, 0, 0)  # full tint = ink
    assert pdfsieve.to_rgb((1, 0, 0), CS("Pattern")) is None
    assert pdfsieve.to_rgb("bad") is None


# ------------------------------------------------------------- command line

def test_cli_text(pdfs, capsys):
    assert main([pdfs["invoice"], "-p", "2"]) == 0
    assert capsys.readouterr().out.strip() == "Second page"


def test_cli_words_json_info(pdfs, capsys):
    assert main([pdfs["invoice"], "-f", "words", "-p", "1"]) == 0
    first = capsys.readouterr().out.splitlines()[0].split("\t")
    assert first[0] == "1" and first[-1] == "Invoice"
    assert main([pdfs["invoice"], "-f", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [p["page"] for p in data] == [1, 2]
    assert data[0]["lines"][0][0][-1] == "Invoice"
    assert main([pdfs["invoice"], "-f", "info"]) == 0
    out = capsys.readouterr().out
    assert "Pages:     2" in out and "Sample invoice" in out


def test_cli_errors(pdfs, tmp_path, capsys):
    assert main([str(tmp_path / "nope.pdf")]) == 2
    assert main([pdfs["invoice"], "-p", "9"]) == 2
    assert main([pdfs["locked"]]) == 2
    assert "password" in capsys.readouterr().err


def test_parse_pages():
    assert parse_pages(None, 3) == [0, 1, 2]
    assert parse_pages("1,3-4", 5) == [0, 2, 3]
    assert parse_pages("4-", 5) == [3, 4]
    assert parse_pages("2,2", 5) == [1]
