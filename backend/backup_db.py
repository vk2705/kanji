#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
Nightly backup of kanji.db (via SQLite's online backup API) and uploads/ (via a
tar.gz snapshot). Keeps 14 days of each.

uploads/ backup added 2026-08-31 (architecture review finding #5): kanji.db's
image_url column can point at a file in uploads/ that a kanji.db-only restore
would silently be missing — before this, only the DB itself was backed up
(CLAUDE.md's own Deployment section used to say so explicitly). Skipped entirely,
with a message rather than an error, when uploads/ doesn't exist or is empty (a
fresh install, or before anyone's uploaded an image yet) — nothing to snapshot.
"""
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "kanji.db"
UPLOADS_DIR = Path(__file__).parent / "uploads"
BACKUP_DIR = Path(__file__).parent / "backups"
RETAIN_DAYS = 14


def backup_db(stamp: str):
    dest = BACKUP_DIR / f"kanji-{stamp}.db"
    src_conn = sqlite3.connect(DB_PATH)
    dest_conn = sqlite3.connect(dest)
    with dest_conn:
        src_conn.backup(dest_conn)
    src_conn.close()
    dest_conn.close()
    print(f"Backed up {DB_PATH} -> {dest}")


def backup_uploads(stamp: str):
    if not UPLOADS_DIR.exists() or not any(UPLOADS_DIR.iterdir()):
        print(f"{UPLOADS_DIR} doesn't exist or is empty, skipping uploads backup.")
        return
    # shutil.make_archive wants a base name without the format's own extension —
    # it appends .tar.gz itself.
    archive_base = BACKUP_DIR / f"uploads-{stamp}"
    archive_path = shutil.make_archive(str(archive_base), "gztar", root_dir=UPLOADS_DIR)
    print(f"Backed up {UPLOADS_DIR} -> {archive_path}")


def prune(pattern: str, retain_days: int = RETAIN_DAYS):
    cutoff = datetime.now() - timedelta(days=retain_days)
    for f in BACKUP_DIR.glob(pattern):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            print(f"Pruned old backup {f}")


def main():
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH}, nothing to back up.", file=sys.stderr)
        sys.exit(1)

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    backup_db(stamp)
    backup_uploads(stamp)

    prune("kanji-*.db")
    prune("uploads-*.tar.gz")


if __name__ == "__main__":
    main()
