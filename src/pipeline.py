import json
import logging
from datetime import datetime
from pathlib import Path
import fitz

from . import db
from .article_extractor import extract_all_articles
from .pdf_parser import extract_publication_date
from .utils import (
    setup_dirs, sha256_file, move_to_folder, safe_filename,
    ARCHIVE, FAILED, ARTICLES
)

ROOT = Path(__file__).resolve().parents[1]


def setup_logging():
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=log_dir / "pipeline.log",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def save_articles(articles, publication_date, file_hash):
    date_name = safe_filename(publication_date or datetime.now().strftime("%Y-%m-%d"))
    out_dir = ARTICLES / date_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"articles_{file_hash[:12]}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    return out_file


def process_pdf(pdf_path):
    file_hash = sha256_file(pdf_path)
    existing = db.get_by_hash(file_hash)

    if existing:
        logging.info("DUPLICATE: %s | %s", pdf_path.name, file_hash)
        pdf_path.unlink()
        print(f"DUPLICATE -> deleted: {pdf_path.name}")
        return "duplicate"

    publication_date = None

    try:
        with fitz.open(pdf_path) as doc:
            publication_date = extract_publication_date(doc)
            db.insert_newspaper(
                file_hash,
                pdf_path.name,
                publication_date,
                "international"
            )

            articles = extract_all_articles(doc)

        output_path = save_articles(articles, publication_date, file_hash)

        archive_dir = ARCHIVE / safe_filename(publication_date or "unknown-date")
        archive_path = move_to_folder(pdf_path, archive_dir)

        db.mark_completed(
            file_hash,
            str(archive_path),
            len(articles)
        )

        logging.info(
            "COMPLETED: %s | articles=%d | output=%s",
            pdf_path.name, len(articles), output_path
        )

        print(f"PROCESSED -> {pdf_path.name}")
        print(f"  date: {publication_date}")
        print(f"  articles: {len(articles)}")
        print(f"  output: {output_path}")
        return "completed"

    except Exception as exc:
        logging.exception("FAILED: %s", pdf_path.name)

        if db.get_by_hash(file_hash):
            db.mark_failed(file_hash, repr(exc))

        failed_path = move_to_folder(pdf_path, FAILED)
        print(f"FAILED -> {failed_path.name}: {exc}")
        return "failed"


def run_once():
    setup_dirs()
    db.init_db()

    pdfs = sorted(
        p for p in ROOT.joinpath("data", "incoming").glob("*.pdf")
        if p.is_file()
    )

    if not pdfs:
        print("No PDFs in data/incoming/")
        return

    for pdf in pdfs:
        process_pdf(pdf)
