#!/usr/bin/env python3
"""Nightly backup of kanji.db via SQLite's online backup API. Keeps 14 days."""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "kanji.db"
BACKUP_DIR = Path(__file__).parent / "backups"
RETAIN_DAYS = 14


def main():
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH}, nothing to back up.", file=sys.stderr)
        sys.exit(1)

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"kanji-{stamp}.db"

    src_conn = sqlite3.connect(DB_PATH)
    dest_conn = sqlite3.connect(dest)
    with dest_conn:
        src_conn.backup(dest_conn)
    src_conn.close()
    dest_conn.close()
    print(f"Backed up {DB_PATH} -> {dest}")

    cutoff = datetime.now() - timedelta(days=RETAIN_DAYS)
    for f in BACKUP_DIR.glob("kanji-*.db"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            print(f"Pruned old backup {f}")


if __name__ == "__main__":
    main()
