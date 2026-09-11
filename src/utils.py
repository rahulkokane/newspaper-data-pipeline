import hashlib
import re
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "data" / "incoming"
ARCHIVE = ROOT / "data" / "archive"
FAILED = ROOT / "data" / "failed"
ARTICLES = ROOT / "data" / "articles"


def setup_dirs():
    for p in [INCOMING, ARCHIVE, FAILED, ARTICLES]:
        p.mkdir(parents=True, exist_ok=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def clean_text(text):
    text = text.replace("\u00ad", "")
    text = text.replace("\x01", "")
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = text.replace("ﬀ", "ff").replace("ﬃ", "ffi").replace("ﬄ", "ffl")
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_filename(text):
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("._") or "file"


def move_to_folder(src, folder, filename=None):
    folder.mkdir(parents=True, exist_ok=True)
    dst = folder / (filename or src.name)
    if dst.exists():
        stem, suffix = dst.stem, dst.suffix
        i = 1
        while dst.exists():
            dst = folder / f"{stem}_{i}{suffix}"
            i += 1
    shutil.move(str(src), str(dst))
    return dst
