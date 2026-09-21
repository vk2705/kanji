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

## The record is cumulative, not recomputed (fixed 2026-09-21)

This script died the moment the repo's history was rewritten. `AUDIT_START_COMMIT`
is a short hash, and `git log <hash>^..HEAD` on a hash that no longer exists
exits 128 — so every run since the anonymized export has crashed, silently
leaving the TSV frozen at whatever it said on 2026-09-12 while nine days of
audit work went unrecorded.

Recomputing coverage from git was the wrong shape to begin with. The current
history's oldest `data.txt` commit is 2026-09-05, weeks *after* the audit began,
so everything before that is simply gone and no anchor can bring it back. So the
**TSV is now the record** and each run unions into it: a kanji marked reviewed
stays reviewed. That makes the count monotonic, immune to the next history
rewrite, and matches what this file's own docstring said from the start — the
coverage state has to live in the repo, not in any one session's memory.

If the anchor commit does resolve, it is still used to narrow the git scan. If
it does not, the scan starts *after* the oldest surviving `data.txt` commit.
That exclusion is the whole point, and the first attempt at this fix got it
wrong: under a truncated history the oldest commit adds the entire file, so
scanning it counts all ~3,000 ids as "+rtk…" additions and cheerfully reports
100% reviewed. The bulk import was never a review — that was true of the
original anchor and it is true of whatever commit now stands in its place.

Because the record is cumulative, a bad scan is **permanent**: the first run of
this fix wrote 3000/3000 and the union then preserved it, and it took a
`git checkout` to undo. So there is a guard — if the git scan on its own claims
more than `SUSPICIOUS_SCAN_SHARE` of all rows, the run refuses to write and
says what it thinks went wrong. A loud failure is recoverable; a silent 100%
is not.

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

# A git scan that claims this share of every row has been individually reviewed
# is not reporting coverage, it is reporting a bulk import it failed to exclude.
# See "The record is cumulative" in the docstring for how that gets baked in.
SUSPICIOUS_SCAN_SHARE = 0.95


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


def previously_reviewed(path: Path) -> set[str]:
    """Ids the persisted TSV already marks reviewed.

    The record is cumulative: a kanji someone looked at in August stays looked
    at, whatever git can still see. See the module docstring.
    """
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 5 and cols[4].strip() == "yes":
            ids.add(cols[0])
    return ids


def _log_range() -> str:
    """`<anchor>^..HEAD` when the anchor still resolves, else the whole history.

    A rewritten history drops the anchor, and `git log <gone>^..HEAD` exits 128.
    Falling back to everything git can see is safe here: the oldest surviving
    data.txt commit is already after the audit started, so the scan can only
    under-report, and the TSV union above makes up the difference.
    """
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{AUDIT_START_COMMIT}^{{commit}}"],
        cwd=Path(__file__).parent, capture_output=True, text=True,
    )
    if probe.returncode == 0:
        return f"{AUDIT_START_COMMIT}^..HEAD"
    oldest = subprocess.run(
        ["git", "log", "--format=%H", "--reverse", "--", "data.txt"],
        cwd=Path(__file__).parent, capture_output=True, text=True, check=True,
    ).stdout.split("\n", 1)[0].strip()
    print(f"note: {AUDIT_START_COMMIT} is not in this history (it was rewritten); "
          f"scanning data.txt commits after {oldest[:7]}, the oldest one left — "
          f"that commit adds the whole file and is the bulk import, not a review",
          flush=True)
    return f"{oldest}..HEAD"


def reviewed_ids() -> set[str]:
    """Every rad*/rtk* id whose data.txt line was added or changed in the scan
    range — see module docstring for why that range can be the whole history."""
    result = subprocess.run(
        ["git", "log", _log_range(), "-p", "--", "data.txt"],
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

    scanned = reviewed_ids()
    scanned_here = {r["id"] for r in rows} & scanned
    if rows and len(scanned_here) > SUSPICIOUS_SCAN_SHARE * len(rows):
        sys.exit(
            f"refusing to write: the git scan alone marks {len(scanned_here)}/{len(rows)} "
            f"rows reviewed, which means it is counting a commit that adds data.txt "
            f"wholesale rather than editing it. Fix the scan range (see _log_range) "
            f"before re-running — this file is cumulative, so a bad run sticks."
        )
    reviewed = scanned | previously_reviewed(args.out)

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
    print(f"{reviewed_count}/{total} rtk kanji reviewed ({pct:.1f}%) since the audit began. "
          f"Written to {args.out}")


if __name__ == "__main__":
    main()
