"""
Isolated tests for backup_db.py's uploads/ backup (architecture review finding #5,
2026-08-31: kanji.db's image_url column can point at a file in uploads/ that a
kanji.db-only restore would silently be missing -- uploads/ wasn't backed up at
all before this). Doesn't need conftest.py's temp-DB fixtures -- these tests point
backup_db.py's own module-level paths at throwaway directories directly.
"""
import sqlite3
import tarfile
from datetime import datetime, timedelta

import backup_db


def _prepare(monkeypatch, tmp_path, uploads_files: dict[str, bytes] | None = None):
    db_path = tmp_path / "kanji.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    uploads_dir = tmp_path / "uploads"
    if uploads_files:
        uploads_dir.mkdir()
        for name, content in uploads_files.items():
            (uploads_dir / name).write_bytes(content)

    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(backup_db, "DB_PATH", db_path)
    monkeypatch.setattr(backup_db, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", backup_dir)
    return db_path, uploads_dir, backup_dir


def test_missing_uploads_dir_skips_cleanly(monkeypatch, tmp_path, capsys):
    _prepare(monkeypatch, tmp_path, uploads_files=None)
    backup_db.main()
    out = capsys.readouterr().out
    assert "skipping uploads backup" in out
    archives = list((tmp_path / "backups").glob("uploads-*.tar.gz"))
    assert archives == []


def test_empty_uploads_dir_skips_cleanly(monkeypatch, tmp_path, capsys):
    _, uploads_dir, backup_dir = _prepare(monkeypatch, tmp_path, uploads_files=None)
    uploads_dir.mkdir()
    backup_db.main()
    out = capsys.readouterr().out
    assert "skipping uploads backup" in out
    assert list(backup_dir.glob("uploads-*.tar.gz")) == []


def test_uploads_with_files_are_archived(monkeypatch, tmp_path):
    _, uploads_dir, backup_dir = _prepare(
        monkeypatch, tmp_path, uploads_files={"usr1.png": b"fake-png-bytes", "usr2.gif": b"fake-gif-bytes"}
    )
    backup_db.main()

    archives = list(backup_dir.glob("uploads-*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0]) as tf:
        names = {m.name.lstrip("./") for m in tf.getmembers() if m.isfile()}
        assert names == {"usr1.png", "usr2.gif"}
        for member in tf.getmembers():
            if member.name.endswith("usr1.png"):
                extracted = tf.extractfile(member).read()
                assert extracted == b"fake-png-bytes"


def test_db_backup_still_happens_regardless_of_uploads(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, uploads_files=None)
    backup_db.main()
    db_backups = list((tmp_path / "backups").glob("kanji-*.db"))
    assert len(db_backups) == 1


def test_old_backups_of_both_kinds_get_pruned(monkeypatch, tmp_path):
    """Two real runs of main() on the same day/second would collide on
    backup_db.py's own %Y%m%d-%H%M%S naming (a real, pre-existing, second-resolution
    limitation of the naming scheme -- not something this test is meant to cover;
    in practice backups run once a day, far enough apart to never collide). To test
    pruning in isolation without that collision, fabricate an "old" backup file
    directly with a distinct, deliberately-stale name instead of relying on a real
    prior main() call."""
    _, uploads_dir, backup_dir = _prepare(
        monkeypatch, tmp_path, uploads_files={"usr1.png": b"x"}
    )
    backup_dir.mkdir(exist_ok=True)

    old_stamp = "20200101-000000"
    old_db = backup_dir / f"kanji-{old_stamp}.db"
    old_upload = backup_dir / f"uploads-{old_stamp}.tar.gz"
    old_db.write_bytes(b"old db backup placeholder")
    old_upload.write_bytes(b"old uploads backup placeholder")

    old_time = (datetime.now() - timedelta(days=backup_db.RETAIN_DAYS + 1)).timestamp()
    import os
    os.utime(old_db, (old_time, old_time))
    os.utime(old_upload, (old_time, old_time))

    backup_db.main()

    remaining_db = list(backup_dir.glob("kanji-*.db"))
    remaining_uploads = list(backup_dir.glob("uploads-*.tar.gz"))
    assert old_db not in remaining_db, "the stale db backup should have been pruned"
    assert old_upload not in remaining_uploads, "the stale uploads backup should have been pruned"
    # The fresh backup main() just took should still be present.
    assert len(remaining_db) == 1
    assert len(remaining_uploads) == 1
