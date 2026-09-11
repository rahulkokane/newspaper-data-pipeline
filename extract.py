"""
Batch PDF -> JSON article extraction pipeline.

Input:
    data/incoming/*.pdf

Successful output:
    data/articles/YYYY-MM-DD.json

Successful PDFs:
    data/archive/

Failed PDFs:
    data/failed/

The article extraction logic remains in src/article_extractor.py.
"""

import json
import re
import traceback
from datetime import datetime
from pathlib import Path

import fitz

from src.article_extractor import extract_articles
from src.pdf_parser import extract_publication_date
from src.utils import (
    INCOMING,
    ARCHIVE,
    FAILED,
    ARTICLES,
    move_to_folder,
    sha256_file,
    setup_dirs,
)


def edition_date_from_filename(pdf_path: Path):
    """
    Extract an edition date from filenames such as:

        th.th_international.28_08_2026.pdf

    Returns:
        YYYY-MM-DD string, or None if not found.
    """
    # Current filename format:
    #     the_hindu_2026-08-18.pdf
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", pdf_path.stem)

    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"

    # Also accept the older format for compatibility:
    #     th.th_international.28_08_2026.pdf
    match = re.search(r"(\d{2})_(\d{2})_(\d{4})", pdf_path.stem)

    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"

    return None


def pdf_is_valid(pdf_path: Path):
    """Basic safety check before sending a file to the extractor."""
    if pdf_path.suffix.lower() != ".pdf":
        return False, "File extension is not .pdf"

    if not pdf_path.exists():
        return False, "File does not exist"

    if pdf_path.stat().st_size < 10_000:
        return False, "PDF is suspiciously small"

    try:
        with open(pdf_path, "rb") as f:
            header = f.read(5)

        if header != b"%PDF-":
            return False, "File does not start with %PDF-"

        # Open it once to make sure it is a readable PDF.
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()

        if page_count == 0:
            return False, "PDF contains zero pages"

        return True, f"{page_count} pages"

    except Exception as exc:
        return False, f"Cannot open PDF: {exc}"


def save_articles(output_path: Path, pdf_path: Path, edition_date: str,
                  publication_date, articles):
    """Write one self-contained JSON document per newspaper edition."""
    data = {
        "source": "The Hindu",
        "edition_date": edition_date,
        "publication_date": publication_date,
        "pdf_file": pdf_path.name,
        "pdf_sha256": sha256_file(pdf_path),
        "extracted_at": datetime.now().astimezone().isoformat(),
        "article_count": len(articles),
        "articles": articles,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def process_pdf(pdf_path: Path):
    print()
    print("=" * 72)
    print(f"Processing: {pdf_path.name}")

    valid, reason = pdf_is_valid(pdf_path)
    if not valid:
        raise ValueError(f"PDF validation failed: {reason}")

    print(f"PDF valid: {reason}")

    edition_date = edition_date_from_filename(pdf_path)

    if not edition_date:
        raise ValueError(
            f"Could not determine edition date from filename: {pdf_path.name}"
        )

    output_path = ARTICLES / f"{edition_date}.json"

    # Idempotency: don't extract the same edition twice.
    if output_path.exists():
        print(f"Already extracted: {output_path.name}")
        print("Skipping this PDF.")
        return "skipped"

    print(f"Edition date: {edition_date}")
    print("Opening PDF...")

    doc = fitz.open(pdf_path)

    try:
        publication_date = extract_publication_date(doc)
        print(f"Publication date found in PDF: {publication_date}")

        print("Running V4 article extractor...")
        articles = extract_articles(doc)
    finally:
        doc.close()

    print(f"Articles extracted: {len(articles)}")

    save_articles(
        output_path=output_path,
        pdf_path=pdf_path,
        edition_date=edition_date,
        publication_date=publication_date,
        articles=articles,
    )

    print(f"JSON saved: {output_path}")

    archive_path = move_to_folder(pdf_path, ARCHIVE)
    print(f"PDF archived: {archive_path}")

    return "success"


def main():
    setup_dirs()

    pdf_files = sorted(INCOMING.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {INCOMING}")
        return

    print(f"Found {len(pdf_files)} PDF(s) in {INCOMING}")

    successful = 0
    skipped = 0
    failed = 0

    for pdf_path in pdf_files:
        try:
            result = process_pdf(pdf_path)

            if result == "success":
                successful += 1
            elif result == "skipped":
                skipped += 1

        except Exception as exc:
            failed += 1

            print()
            print(f"ERROR: {pdf_path.name}")
            print(f"Reason: {exc}")
            traceback.print_exc()

            try:
                failed_path = move_to_folder(pdf_path, FAILED)
                print(f"Failed PDF moved to: {failed_path}")
            except Exception as move_exc:
                print(f"Could not move failed PDF: {move_exc}")

    print()
    print("=" * 72)
    print("EXTRACTION COMPLETE")
    print("=" * 72)
    print(f"Successful: {successful}")
    print(f"Skipped:    {skipped}")
    print(f"Failed:     {failed}")
    print(f"Articles:   {ARTICLES}")
    print(f"Archive:    {ARCHIVE}")
    print(f"Failed:     {FAILED}")


if __name__ == "__main__":
    main()
