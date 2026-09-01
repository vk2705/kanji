#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""Create a local backup and copy its paired artifacts to an rclone remote.

Configure KANJI_BACKUP_REMOTE as an rclone destination such as
"encrypted-s3:kanji-production". Provider credentials stay in rclone's config,
never in this repository. Configure retention with the destination's lifecycle rules.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import backup_db

REMOTE_ENV = "KANJI_BACKUP_REMOTE"


def main() -> None:
    remote = os.environ.get(REMOTE_ENV, "").strip()
    if not remote:
        print(f"{REMOTE_ENV} is not set", file=sys.stderr)
        raise SystemExit(1)
    if shutil.which("rclone") is None:
        print("rclone is not installed or not on PATH", file=sys.stderr)
        raise SystemExit(1)

    before = set(backup_db.BACKUP_DIR.glob("kanji-*.db")) | set(backup_db.BACKUP_DIR.glob("uploads-*.tar.gz"))
    backup_db.main()
    after = set(backup_db.BACKUP_DIR.glob("kanji-*.db")) | set(backup_db.BACKUP_DIR.glob("uploads-*.tar.gz"))
    created = sorted(after - before)
    if not any(path.name.startswith("kanji-") for path in created):
        print("No new database backup was created", file=sys.stderr)
        raise SystemExit(1)

    for artifact in created:
        subprocess.run(
            ["rclone", "copyto", str(artifact), f"{remote.rstrip('/')}/{artifact.name}"],
            check=True,
        )
        print(f"Copied {artifact.name} to {remote}")


if __name__ == "__main__":
    main()
