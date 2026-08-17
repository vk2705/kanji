"""
coverage_status.py — track which rtk* kanji have actually been individually
reviewed against a real source, out of all ~3000, for the "check all kanji"
mandate (docs/2026-08-search-quality-audit.md, session 16).

## Why this exists

Sessions 1-16 fixed real bugs, but always by starting from a report or a
systematic script's flagged candidates — nobody has been tracking, across
sessions, which of the ~3000 rtk kanji have actually been looked at and
confirmed correct (or fixed) versus never individually checked at all. Since
each session's container doesn't persist, that coverage state has to live in
the repo, not in any one session's memory, same reasoning as the audit doc's
own progress log.

## What counts as "reviewed"

A kanji counts as reviewed if its `backend/data.txt` line was added or
edited by a content-fix commit *after* the search-quality audit began
(commit 0a46e3d, "Name 58 of 69 previously-unnamed radical primitives" —
the first Finding-1-phase fix). Everything before that point was the
original bulk import, not a deliberate review, so it's excluded even though
technically "touched" by git history. This is a proxy, not a perfect
record — a line edited for an unrelated reason (e.g. a typo fix) would count
as "reviewed" even if nobody actually checked that kanji's decomposition
correctness — but it's the only honestly-derivable signal without hand-
maintaining a separate log, and errs toward under-counting rather than
over-counting (a kanji with zero data.txt edits since the audit began has
definitely never been individually fixed, even if someone eyeballed it and
decided it was already fine — there's no record of that either way).

## Usage

    python3 coverage_status.py [--out ../docs/kanji_review_coverage.tsv]

Regenerates the coverage TSV from current git history + a fresh import.
Run this after any content-fix commit lands, so the persisted file stays
accurate; it's cheap and safe to run any time (read-only against git and a
throwaway shadow DB, never touches kanji.db).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

AUDIT_START_COMMIT = "0a46e3d"  # first Finding-1-phase content-fix commit


def build_shadow_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="kanji_coverage_"))
    tmp_db = tmp_dir / "shadow.db"
    database.DB_PATH = tmp_db
    database.init_db()
    conn = database.get_db()
    database.migrate_schema(conn)
    conn.close()
    database.import_data()
    return tmp_db


def reviewed_ids() -> set[str]:
    """Every rad*/rtk* id whose data.txt line was added or changed by a commit
    after (and including) AUDIT_START_COMMIT — see module docstring for why
    that's the cutoff, not the repo's full history."""
    result = subprocess.run(
        ["git", "log", f"{AUDIT_START_COMMIT}^..HEAD", "-p", "--", "data.txt"],
        cwd=Path(__file__).parent, capture_output=True, text=True, check=True
    )
    ids = set()
    for line in result.stdout.splitlines():
        if line.startswith("+rad") or line.startswith("+rtk"):
            pid = line[1:].split(":", 1)[0]
            if pid.replace("rad", "").replace("rtk", "").replace(".", "").isdigit() or "." in pid:
                ids.add(pid)
    return ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
                         default=Path(__file__).parent.parent / "docs" / "kanji_review_coverage.tsv")
    args = parser.parse_args()

    print("Building shadow database from source files...", flush=True)
    shadow_db = build_shadow_db()
    conn = database.sqlite3.connect(shadow_db)
    conn.row_factory = database.sqlite3.Row

    rows = conn.execute(
        "SELECT id, character, keyword, frame FROM kanji "
        "WHERE id LIKE 'rtk%' AND owner_id = 1 ORDER BY frame"
    ).fetchall()
    conn.close()

    reviewed = reviewed_ids()

    lines = ["id\tcharacter\tkeyword\tframe\treviewed"]
    reviewed_count = 0
    for r in rows:
        is_reviewed = r["id"] in reviewed
        reviewed_count += is_reviewed
        lines.append(f"{r['id']}\t{r['character']}\t{r['keyword']}\t{r['frame']}\t"
                     f"{'yes' if is_reviewed else 'no'}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    total = len(rows)
    pct = 100 * reviewed_count / total if total else 0
    print(f"{reviewed_count}/{total} rtk kanji reviewed ({pct:.1f}%) since the audit began "
          f"({AUDIT_START_COMMIT}). Written to {args.out}")


if __name__ == "__main__":
    main()
