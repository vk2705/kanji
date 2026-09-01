#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""Restore a paired kanji database and uploads archive into a stopped backend.

The restore is staged and validated before either live path is replaced. Run the
service stop/start commands outside this script so service management stays explicit.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

REQUIRED_TABLES = {"kanji", "aliases", "parts", "users", "sessions", "decompositions", "stories"}


def validate_database(path: Path) -> None:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        conn.close()
    except sqlite3.Error as exc:
        raise ValueError(f"invalid SQLite backup: {exc}") from exc
    if integrity != "ok":
        raise ValueError(f"database integrity check failed: {integrity}")
    missing = REQUIRED_TABLES - tables
    if missing:
        raise ValueError(f"database backup is missing required tables: {', '.join(sorted(missing))}")


def extract_uploads(archive: Path, destination: Path) -> None:
    destination.mkdir()
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"unsafe path in uploads archive: {member.name}")
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"unsupported entry in uploads archive: {member.name}")
            target = destination / member_path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = source.extractfile(member)
            if extracted is None:
                raise ValueError(f"could not read uploads archive entry: {member.name}")
            with extracted, open(target, "wb") as output:
                shutil.copyfileobj(extracted, output)


def restore(db_backup: Path, uploads_backup: Path | None, target_dir: Path) -> None:
    if not db_backup.is_file():
        raise ValueError(f"database backup does not exist: {db_backup}")
    if uploads_backup is not None and not uploads_backup.is_file():
        raise ValueError(f"uploads backup does not exist: {uploads_backup}")

    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kanji-restore-", dir=target_dir.parent) as temp_name:
        staging = Path(temp_name)
        staged_db = staging / "kanji.db"
        shutil.copy2(db_backup, staged_db)
        validate_database(staged_db)

        staged_uploads = staging / "uploads"
        if uploads_backup is not None:
            extract_uploads(uploads_backup, staged_uploads)
        else:
            staged_uploads.mkdir()

        live_db = target_dir / "kanji.db"
        live_uploads = target_dir / "uploads"
        previous_db = target_dir / ".kanji.db.restore-previous"
        previous_uploads = target_dir / ".uploads.restore-previous"
        previous_db.unlink(missing_ok=True)
        if previous_uploads.exists():
            shutil.rmtree(previous_uploads)

        try:
            if live_db.exists():
                os.replace(live_db, previous_db)
            if live_uploads.exists():
                os.replace(live_uploads, previous_uploads)
            os.replace(staged_db, live_db)
            os.replace(staged_uploads, live_uploads)
        except Exception:
            live_db.unlink(missing_ok=True)
            if live_uploads.exists():
                shutil.rmtree(live_uploads)
            if previous_db.exists():
                os.replace(previous_db, live_db)
            if previous_uploads.exists():
                os.replace(previous_uploads, live_uploads)
            raise
        else:
            previous_db.unlink(missing_ok=True)
            if previous_uploads.exists():
                shutil.rmtree(previous_uploads)


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore kanji.db and uploads from a paired backup")
    parser.add_argument("db_backup", type=Path, help="kanji-YYYYMMDD-HHMMSS.db backup")
    parser.add_argument("--uploads", type=Path, help="matching uploads-YYYYMMDD-HHMMSS.tar.gz backup")
    parser.add_argument("--target-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--confirm", action="store_true", help="required before replacing target data")
    args = parser.parse_args()

    if not args.confirm:
        parser.error("--confirm is required; stop kanji-backend.service before restoring")
    try:
        restore(args.db_backup.resolve(), args.uploads.resolve() if args.uploads else None, args.target_dir.resolve())
    except (OSError, sqlite3.Error, tarfile.TarError, ValueError) as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Restored database and uploads into {args.target_dir.resolve()}")


if __name__ == "__main__":
    main()
