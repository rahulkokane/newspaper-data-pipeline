import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "database" / "newspaper.db"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS newspapers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            publication_date TEXT,
            edition TEXT,
            status TEXT NOT NULL,
            archive_path TEXT,
            article_count INTEGER DEFAULT 0,
            error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)


def get_by_hash(file_hash):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM newspapers WHERE file_hash = ?",
            (file_hash,)
        ).fetchone()


def insert_newspaper(file_hash, filename, publication_date=None, edition=None):
    with connect() as conn:
        cur = conn.execute("""
            INSERT INTO newspapers
            (file_hash, filename, publication_date, edition, status)
            VALUES (?, ?, ?, ?, 'processing')
        """, (file_hash, filename, publication_date, edition))
        return cur.lastrowid


def mark_completed(file_hash, archive_path, article_count):
    with connect() as conn:
        conn.execute("""
            UPDATE newspapers
            SET status='completed', archive_path=?, article_count=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE file_hash=?
        """, (archive_path, article_count, file_hash))


def mark_failed(file_hash, error):
    with connect() as conn:
        conn.execute("""
            UPDATE newspapers
            SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP
            WHERE file_hash=?
        """, (error[:4000], file_hash))
