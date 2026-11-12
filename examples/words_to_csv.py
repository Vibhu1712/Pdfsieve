"""Write every word of a PDF, with its page and box, to a CSV file.

    python examples/words_to_csv.py sample.pdf words.csv
"""

import csv
import sys

import pdfsieve

src, dst = sys.argv[1], sys.argv[2]
with pdfsieve.open(src) as doc, open(dst, "w", newline="", encoding="utf-8") as f:
    out = csv.writer(f)
    out.writerow(["page", "x0", "y0", "x1", "y1", "text"])
    for page in doc:
        for w in page.words(visible_only=True):
            out.writerow([page.index + 1, f"{w.x0:.1f}", f"{w.y0:.1f}", f"{w.x1:.1f}", f"{w.y1:.1f}", w.text])
print("wrote", dst)
