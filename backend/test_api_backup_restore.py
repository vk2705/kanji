"""Round-trip and archive-safety tests for restore_backup.py."""
import io
import tarfile
from pathlib import Path

import pytest

import backup_db
import restore_backup


def test_backup_restore_round_trip(db_path, conn, tmp_path, monkeypatch):
    conn.execute(
        "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
        "VALUES ('restore-me', '復', 'restore', 1, 'public', 'ja-kanji')"
    )
    conn.commit()

    source_uploads = tmp_path / "source-uploads"
    source_uploads.mkdir()
    (source_uploads / "restore-me.png").write_bytes(b"image payload")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(backup_db, "DB_PATH", db_path)
    monkeypatch.setattr(backup_db, "UPLOADS_DIR", source_uploads)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", backup_dir)

    backup_db.backup_db("20260831-120000")
    backup_db.backup_uploads("20260831-120000")

    target = tmp_path / "restored-backend"
    restore_backup.restore(
        backup_dir / "kanji-20260831-120000.db",
        backup_dir / "uploads-20260831-120000.tar.gz",
        target,
    )

    restore_backup.validate_database(target / "kanji.db")
    assert (target / "uploads" / "restore-me.png").read_bytes() == b"image payload"


def test_restore_rejects_unsafe_upload_archive(db_path, tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    payload = b"escape"
    with tarfile.open(archive, "w:gz") as output:
        info = tarfile.TarInfo("../outside.txt")
        info.size = len(payload)
        output.addfile(info, io.BytesIO(payload))

    with pytest.raises(ValueError, match="unsafe path"):
        restore_backup.restore(db_path, archive, tmp_path / "target")
    assert not (tmp_path / "outside.txt").exists()
