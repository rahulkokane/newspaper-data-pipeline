"""V4 spatial newspaper article extractor.

The extractor treats the PDF as a 2-D newspaper layout instead of a flat
text document. It works in four stages:

1. Recover PDF lines/words with coordinates.
2. Detect headline blocks.
3. Build an independent geometric region for every headline.
4. Reconstruct only the text that belongs to that region, then detect
   header metadata (byline/location) inside the region.

The output is intentionally conservative: ambiguous layout signals lower
confidence instead of silently inventing article boundaries.
"""

import re
from dataclasses import dataclass
from typing import Optional

from .pdf_parser import extract_page_section
from .utils import clean_text


MIN_HEADLINE_FONT = 14.5
HEADER_Y = 80
FOOTER_Y = 30

IGNORE_HEADLINES = {
    "THE HINDU", "INBRIEF", "IN BRIEF", "INSIDE", "SNAPSHOTS",
    "PARLEY", "OPINION", "SPORT", "STATES", "NEWS", "CHENNAI",
}

BYLINE_SOURCES = {
    "THE HINDU BUREAU",
    "PRESS TRUST OF INDIA",
    "AGENCE FRANCE-PRESSE",
    "PTI", "ANI", "AFP", "REUTERS", "SPORTS BUREAU",
}

PHOTO_MARKERS = (
    "FILE PHOTO", "AP/", "AP PHOTO", "FLICKR", "COURTESY",
)

PHOTO_CREDIT_RE = re.compile(
    r"(?:^|\W)(?:ANI|PTI|AFP|REUTERS|AP)(?:$|\W)", re.I
)

LOCATION_RE = re.compile(r"^[A-Z][A-Z .,'&()/-]{2,50}$")

# These are usually labels, not people's names.
NON_AUTHOR = {
    "SPECIAL CORRESPONDENT", "STAFF REPORTER", "CORRESPONDENT",
    "OUR CORRESPONDENT", "OUR BUREAU", "STAFF WRITER",
}


@dataclass
class Line:
    id: int
    block_id: int
    x0: float
    y0: float
    x1: float
    y1: float
    font: float
    text: str
    spans: list


def _clean_line(text):
    return clean_text(text.replace("\x01", ""))


def _line_objects(page):
    """Recover actual PDF lines, retaining their geometry."""
    result = []
    line_id = 0

    for block_id, block in enumerate(
        page.get_text("dict").get("blocks", [])
    ):
        if "lines" not in block:
            continue

        for raw_line in block["lines"]:
            spans = [
                s for s in raw_line.get("spans", [])
                if s.get("text", "").strip()
            ]
            if not spans:
                continue

            text = _clean_line(
                "".join(s.get("text", "") for s in spans)
            )
            if not text:
                continue

            x0, y0, x1, y1 = map(float, raw_line["bbox"])
            font = max(float(s.get("size", 0)) for s in spans)

            result.append(Line(
                id=line_id,
                block_id=block_id,
                x0=x0, y0=y0, x1=x1, y1=y1,
                font=font,
                text=text,
                spans=spans,
            ))
            line_id += 1

    return result


def _merge_hyphenated(lines):
    """Merge line fragments such as 'govern-' + 'ment'."""
    result = []

    for line in lines:
        if (
            result
            and re.search(r"[A-Za-z]-$", result[-1].text)
            and line.y0 >= result[-1].y1 - 2
        ):
            result[-1].text = (
                result[-1].text[:-1] + line.text
            )
            result[-1].x1 = max(result[-1].x1, line.x1)
            result[-1].y1 = max(result[-1].y1, line.y1)
        else:
            result.append(line)

    return result


def _is_short_label(text):
    return (
        text.upper() in IGNORE_HEADLINES
        or (
            text.isupper()
            and len(text.split()) <= 4
        )
    )


def is_headline(line, page_height):
    if line.y0 < HEADER_Y or line.y0 > page_height - FOOTER_Y:
        return False

    if line.font < MIN_HEADLINE_FONT:
        return False

    text = line.text.strip()
    upper = text.upper()

    if upper in IGNORE_HEADLINES:
        return False

    if "FRIDAY, AUGUST" in upper:
        return False

    if "THE HINDU" in upper and len(text) < 80:
        return False

    if _is_short_label(text):
        return False

    alpha = sum(c.isalpha() for c in text)

    return (
        len(text) >= 15
        and len(text.split()) >= 3
        and alpha >= 8
    )


def _merge_headline_lines(lines, page_height):
    """Group adjacent large-font lines and validate the combined headline."""
    candidates = [
        x for x in lines
        if HEADER_Y <= x.y0 <= page_height - FOOTER_Y
        and x.font >= MIN_HEADLINE_FONT
        and x.text.strip().upper() not in IGNORE_HEADLINES
        and "FRIDAY, AUGUST" not in x.text.upper()
    ]
    candidates.sort(key=lambda x: (x.y0, x.x0))
    groups = []
    for line in candidates:
        placed = False
        for group in reversed(groups):
            last = group[-1]
            if (line.y0 - last.y1 <= 12
                    and min(line.x1, last.x1) > max(line.x0, last.x0) + 5
                    and abs(line.font - last.font) <= 5):
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])
    headlines = []
    for group in groups:
        group.sort(key=lambda x: (x.y0, x.x0))
        text = clean_text(" ".join(x.text for x in group))
        if (len(text) < 15 or len(text.split()) < 3
                or sum(c.isalpha() for c in text) < 8):
            continue
        headlines.append({
            "x0": min(x.x0 for x in group),
            "y0": min(x.y0 for x in group),
            "x1": max(x.x1 for x in group),
            "y1": max(x.y1 for x in group),
            "font": max(x.font for x in group),
            "text": text,
            "line_ids": [x.id for x in group],
        })
    return headlines

def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _x_overlap_ratio(a, b):
    overlap = _overlap(a["x0"], a["x1"], b["x0"], b["x1"])
    width = max(1.0, min(
        a["x1"] - a["x0"],
        b["x1"] - b["x0"],
    ))
    return overlap / width


def _column_edges(lines, page_width):
    """Infer dominant newspaper column starts from repeated text-line x positions."""
    histogram = {}
    for line in lines:
        if line.y0 <= HEADER_Y or line.font > 13:
            continue
        if line.x0 <= 15 or line.x1 >= page_width - 15:
            continue
        key = round(line.x0 / 5) * 5
        histogram[key] = histogram.get(key, 0) + 1

    peaks = sorted(x for x, count in histogram.items() if count >= 15)
    centers = []
    for x in peaks:
        if not centers or x - centers[-1] > 35:
            centers.append(float(x))
        else:
            centers[-1] = (centers[-1] + x) / 2

    if not centers:
        return [0.0, page_width]

    edges = [0.0]
    for left, right in zip(centers, centers[1:]):
        edges.append((left + right) / 2)
    edges.append(page_width)
    return edges

def _headline_region(headline, edges, page_width):
    """Map a headline to the column span it physically occupies."""
    touched = []

    for i in range(len(edges) - 1):
        left, right = edges[i], edges[i + 1]

        if _overlap(
            headline["x0"], headline["x1"],
            left, right,
        ) > 12:
            touched.append(i)

    if not touched:
        center = (headline["x0"] + headline["x1"]) / 2
        idx = min(
            range(len(edges) - 1),
            key=lambda i: abs(
                ((edges[i] + edges[i + 1]) / 2) - center
            ),
        )
        touched = [idx]

    left = edges[min(touched)]
    right = edges[max(touched) + 1]

    # Do not use the headline bbox as the right edge: many newspaper
    # headlines span a whole column but their final line is shorter.
    return max(0, left - 3), min(page_width, right + 3)


def _next_headline_boundary(headline, headlines, page_height):
    """Find the first competing headline below this article region."""
    boundary = page_height - FOOTER_Y

    for other in headlines:
        if other is headline:
            continue

        if other["y0"] <= headline["y1"]:
            continue

        # Strong horizontal overlap means the next headline terminates
        # this article's vertical region.
        if _x_overlap_ratio(headline, other) >= 0.20:
            boundary = min(boundary, other["y0"])

    return boundary


def _in_region(line, region):
    center = (line.x0 + line.x1) / 2
    return region[0] <= center <= region[1]


def _looks_like_location(text):
    text = text.strip()
    return bool(
        LOCATION_RE.fullmatch(text)
        and 1 <= len(text.split()) <= 6
    )


def _looks_like_author(text):
    text = text.strip()

    if text.upper() in NON_AUTHOR:
        return False

    if not re.fullmatch(
        r"[A-Za-z][A-Za-z .,'’&-]{2,70}",
        text,
    ):
        return False

    if not 1 <= len(text.split()) <= 6:
        return False

    if text.endswith((".", ":", ";", "?", "!")):
        return False

    words = text.lower().split()
    sentence_words = {
        "the", "a", "an", "and", "or", "but", "on", "in",
        "for", "to", "with", "from", "was", "were", "is",
        "are", "has", "have", "had", "government", "committee",
        "report", "said", "according",
    }

    # A normal body/deck sentence is unlikely to satisfy this.
    if (
        len(words) >= 4
        and sum(
            w.strip(".,'’") in sentence_words
            for w in words
        ) >= 2
    ):
        return False

    return True


def _detect_metadata(region_lines, headline):
    """Inspect only the header immediately below the headline."""
    candidates = [
        x for x in region_lines
        if headline["y1"] < x.y0 < headline["y1"] + 85
    ]
    candidates.sort(key=lambda x: (x.y0, x.x0))

    author = None
    location = None
    metadata_ids = set()
    author_conf = 0.0
    location_conf = 0.0

    # Combine same-line agency source + location.
    source_pattern = "|".join(
        re.escape(x)
        for x in sorted(BYLINE_SOURCES, key=len, reverse=True)
    )
    source_rx = re.compile(
        r"^\s*("
        + source_pattern
        + r")"
        r"(?:\s+([A-Z][A-Z .&'/-]{2,50}))?"
        r"\s*$",
        re.I,
    )

    for line in candidates[:8]:
        match = source_rx.match(line.text.strip())

        if match:
            author = match.group(1).strip()
            metadata_ids.add(line.id)
            author_conf = 0.99

            if match.group(2):
                location = match.group(2).strip().title()
                location_conf = 0.99

            break

    # Normal person byline followed by location.
    if author is None:
        for i, line in enumerate(candidates[:8]):
            if not _looks_like_author(line.text):
                continue

            if i + 1 < len(candidates):
                nxt = candidates[i + 1]

                # Require location to be visually close.
                gap = nxt.y0 - line.y1

                if (
                    gap <= 18
                    and _looks_like_location(nxt.text)
                ):
                    author = line.text.strip()
                    location = nxt.text.strip().title()

                    metadata_ids.update({
                        line.id,
                        nxt.id,
                    })

                    author_conf = 0.97
                    location_conf = 0.97
                    break

    # Standalone short byline.
    if author is None:
        for line in candidates[:5]:
            if (
                _looks_like_author(line.text)
                and len(line.text.split()) <= 3
                and line.font <= 12
            ):
                author = line.text.strip()
                metadata_ids.add(line.id)
                author_conf = 0.82
                break

    # Location immediately after a standalone byline.
    if author and location is None:
        author_line_y = max(
            x.y1 for x in candidates
            if x.id in metadata_ids
        )

        for line in candidates:
            if line.y0 < author_line_y:
                continue

            if (
                line.y0 - author_line_y <= 18
                and _looks_like_location(line.text)
            ):
                location = line.text.strip().title()
                metadata_ids.add(line.id)
                location_conf = 0.90
                break

    return {
        "author": author,
        "location": location,
        "metadata_ids": metadata_ids,
        "author_confidence": author_conf,
        "location_confidence": location_conf,
    }


def _is_caption(line):
    upper = line.text.upper()

    if any(x in upper for x in PHOTO_MARKERS):
        return True

    if PHOTO_CREDIT_RE.search(line.text):
        return True

    return (
        "..." in line.text
        and line.font <= 9.5
        and len(line.text) < 180
    )


def _is_noise(line):
    text = line.text.strip()

    if len(text) <= 2:
        return True

    if (
        text.isupper()
        and len(text.split()) <= 4
        and line.font <= 10.5
    ):
        return True

    return False


def _body_reading_order(lines, region, column_edges):
    """Order text by the newspaper's real column grid, preserving PDF blocks."""
    lines = [x for x in lines if _in_region(x, region)]
    if not lines:
        return []

    def column_index(line):
        center = (line.x0 + line.x1) / 2
        return min(
            range(len(column_edges) - 1),
            key=lambda i: abs(
                ((column_edges[i] + column_edges[i + 1]) / 2) - center
            ),
        )

    # Keep lines belonging to the same PDF block together. This is important
    # for newspaper pull-quotes and for text whose first line is indented.
    grouped = {}
    for line in lines:
        grouped.setdefault(line.block_id, []).append(line)

    blocks = []
    for block_lines in grouped.values():
        block_lines.sort(key=lambda x: (x.y0, x.x0))
        blocks.append(block_lines)

    blocks.sort(key=lambda group: (
        column_index(group[0]),
        group[0].y0,
        group[0].x0,
    ))

    result = []
    for group in blocks:
        result.extend(group)
    return result

def _join_body(lines):
    parts = []

    for line in lines:
        text = line.text.strip()

        if (
            parts
            and re.search(r"[A-Za-z]-$", parts[-1])
        ):
            parts[-1] = parts[-1][:-1] + text
        else:
            parts.append(text)

    return clean_text(" ".join(parts))


def _quality(article, metadata, region_lines):
    body = article["body"]

    artifacts = sum(
        body.count(x)
        for x in ["", "", "", "￾", "￿"]
    )

    checks = {
        "body_present": len(body) >= 80,
        "no_encoding_artifacts": artifacts == 0,
        "author_not_in_body": True,
        "location_not_in_body": True,
    }

    body_lower = body.lower()

    if article["author"]:
        checks["author_not_in_body"] = (
            body_lower.count(article["author"].lower()) == 0
        )

    if article["location"]:
        # A location can legitimately occur once in an article body,
        # so flag only repeated occurrences.
        checks["location_not_in_body"] = (
            body_lower.count(article["location"].lower()) <= 1
        )

    validation_score = sum(checks.values()) / len(checks)

    extraction_score = 1.0

    if artifacts:
        extraction_score -= min(
            0.5,
            artifacts / max(1, len(body) / 80),
        )

    # Metadata confidence is part of extraction confidence, but missing
    # metadata is not treated as an error because many articles have none.
    metadata_scores = [
        metadata["author_confidence"],
        metadata["location_confidence"],
    ]
    detected = [x for x in metadata_scores if x > 0]

    if detected:
        extraction_score *= sum(detected) / len(detected)

    final_score = max(
        0.0,
        min(1.0, (extraction_score + validation_score) / 2),
    )

    return {
        "body_characters": len(body),
        "body_lines": len(region_lines),
        "encoding_artifacts": artifacts,
        "metadata_confidence": {
            "author": round(metadata["author_confidence"], 3),
            "location": round(metadata["location_confidence"], 3),
        },
        "validation": checks,
        "score": round(final_score, 3),
    }


def extract_article(
    page_number,
    page,
    headline,
    headlines,
    lines,
    column_edges,
):
    page_width = page.rect.width

    region = _headline_region(
        headline,
        column_edges,
        page_width,
    )

    end_y = _next_headline_boundary(
        headline,
        headlines,
        page.rect.height,
    )

    # Only lines physically inside the article's x/y region are eligible.
    region_lines = [
        line for line in lines
        if headline["y1"] < line.y0 < end_y
        and _in_region(line, region)
    ]

    metadata = _detect_metadata(
        region_lines,
        headline,
    )

    body_lines = []

    metadata_ids = metadata["metadata_ids"]

    for line in region_lines:
        if line.id in metadata_ids:
            continue

        if _is_caption(line) or _is_noise(line):
            continue

        # Do not let another headline become body text.
        if is_headline(line, page.rect.height):
            continue

        body_lines.append(line)

    ordered = _body_reading_order(
        body_lines,
        region,
        column_edges,
    )

    body = _join_body(ordered)

    article = {
        "page": page_number,
        "section": extract_page_section(page),
        "title": headline["text"],
        "author": metadata["author"],
        "location": metadata["location"],
        "body": body,
    }

    article["quality"] = _quality(
        article,
        metadata,
        ordered,
    )

    # Internal geometry is useful for debugging but is deliberately omitted
    # from the default JSON output.
    return article


def extract_articles_from_page(page_number, page):
    lines = _line_objects(page)
    lines = _merge_hyphenated(lines)

    headlines = _merge_headline_lines(
        lines,
        page.rect.height,
    )

    edges = _column_edges(
        lines,
        page.rect.width,
    )

    articles = []

    for headline in headlines:
        article = extract_article(
            page_number,
            page,
            headline,
            headlines,
            lines,
            edges,
        )

        if article["quality"]["body_characters"] >= 80:
            articles.append(article)

    return articles


def extract_all_articles(doc):
    result = []

    for page_number, page in enumerate(doc, start=1):
        result.extend(
            extract_articles_from_page(
                page_number,
                page,
            )
        )

    return result


def extract_articles(doc):
    """Compatibility alias for the existing pipeline."""
    return extract_all_articles(doc)
