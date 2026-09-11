import re
import fitz
from .utils import clean_text


def extract_lines(page):
    lines = []
    data = page.get_text("dict")

    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue

            text = clean_text("".join(s.get("text", "") for s in spans))
            if not text:
                continue

            font_max = max(float(s.get("size", 0)) for s in spans)
            font_min = min(float(s.get("size", 0)) for s in spans)

            lines.append({
                "x0": float(line["bbox"][0]),
                "y0": float(line["bbox"][1]),
                "x1": float(line["bbox"][2]),
                "y1": float(line["bbox"][3]),
                "text": text,
                "font_max": font_max,
                "font_min": font_min,
            })

    return lines


def extract_publication_date(doc):
    if not doc:
        return None

    text = clean_text(doc[0].get_text("text"))
    patterns = [
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)

    return None


def extract_page_section(page):
    # The Hindu page header contains the section name.
    # This is deliberately conservative: if it cannot be found,
    # return None instead of guessing.
    lines = extract_lines(page)
    top = [x for x in lines if x["y0"] < 90]
    for line in sorted(top, key=lambda x: (-x["font_max"], x["x0"])):
        t = line["text"].strip()
        if t.upper() in {"THE HINDU", "CHENNAI"}:
            continue
        if 4 <= len(t.split()) <= 4 and line["font_max"] >= 15:
            return t
    return None
