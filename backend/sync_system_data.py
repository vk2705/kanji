#!/usr/bin/env python3
"""
sync_system_data.py — reconcile a live, already-seeded kanji.db's system rows
(owner_id=1, script='ja-kanji') with the current heisig-kanjis.csv /
data_from_pdf.txt / data.txt content, without wiping user data.

## Why this exists

kanji.db is not committed to git and is not a rebuildable cache once it holds
real accounts: `database.py::import_data()` seeds it exactly once (it's a
no-op the moment any owner_id=1 row already exists — see its own docstring),
and there is deliberately no `/admin/reimport` endpoint (CLAUDE.md
"Architecture"). So on a live server, `git pull` + restart does NOT pick up
a data.txt edit — the restart only re-runs the idempotent schema migration,
not a re-seed. Deleting kanji.db to force a reseed is not a safe workaround
either: the same file holds every real user's account, private decompositions
and stories, so deleting it destroys those along with the stale system data.

Re-running import_data() itself against a live DB (e.g. by removing its
already-seeded guard) is *also* not safe: its
`DELETE FROM parts WHERE kanji_id IN (SELECT id FROM kanji WHERE owner_id=1)`
deletes every parts row for a system kanji_id regardless of which
decomposition owns it — including a real user's own alternate decomposition
on a system kanji, since `parts` rows aren't scoped to decomposition-owner at
that granularity. That blanket delete is only safe against an empty DB, which
is the only case import_data() is guarded to actually run against.

## What this script does instead

Builds a disposable "target" copy of the DB via the real import pipeline
(the same build_shadow_db() approach backend/audit_*.py already use — so the
merge/override logic lives in exactly one place, database.py::import_data(),
never duplicated here), then diffs its owner_id=1 + script='ja-kanji' rows
against the live DB's, and applies only the difference:

  - kanji: insert missing ids, update changed fields (character/keyword/
    frame/stroke_count/jlpt). Never touches `image_url` (not something
    data.txt can express — clobbering it would erase a manually-attached
    primitive picture) or any row with a different owner_id.
  - aliases: add what the source now has, remove what it no longer does.
    Scoped to owner_id=1 rows on ja-kanji kanji only — a user's own alias on
    a system kanji (a different owner_id) is untouched.
  - decompositions/parts: for each kanji's *system* decomposition
    (owner_id=1) specifically — never a user's alternate decomposition on
    the same kanji_id — replaces its parts list if the source's differs,
    creates the decomposition row if the source now wants one where there
    was none, deletes it if the source now wants none (an atomic primitive
    with no listed parts, same convention as e.g. rtk1743 門).

Explicitly out of scope: zh-* hanzi rows (seeded separately by the one-off
import_hanzi.py from cjkvi-ids IDS data, not from these three files — this
script only ever looks at script='ja-kanji' rows, so hanzi data is untouched
either way) and the eventual source-pseudo-owner architecture described in
docs/2026-08-search-quality-audit.md (which would let this become a generic
per-source sync instead of a single hard-coded "system ja-kanji" scope).

Supersedes backend/fix_kradfile_proxies.py, a one-off hand-written patch for
exactly one data.txt change — this script produces the same effect (and every
future data.txt content fix) generically by diffing against the source files,
rather than needing a new hard-coded script per fix.

## Usage

    python3 sync_system_data.py [--db kanji.db] [--dry-run] [--no-backup]

Meant to be run after every `git pull` that might have touched data.txt,
data_from_pdf.txt, or heisig-kanjis.csv. Safe to run repeatedly — idempotent,
a no-op if nothing changed since the last run. Takes a timestamped backup of
--db before writing (skip with --no-backup); everything else runs in one
transaction, rolled back on any error so a failure can't leave a half-applied
sync behind.
"""
import argparse
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

SYSTEM_JA_KANJI = "owner_id = 1 AND script = 'ja-kanji'"


def build_shadow_db() -> Path:
    """Run the real import pipeline against a throwaway sqlite file, exactly like
    audit_decomposition.py / audit_radicals.py do, so this script's idea of "correct"
    always matches production's actual merge logic rather than a re-guessed copy of it."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="kanji_sync_"))
    tmp_db = tmp_dir / "shadow.db"
    orig_db_path = database.DB_PATH
    try:
        database.DB_PATH = tmp_db
        database.init_db()
        conn = database.get_db()
        database.migrate_schema(conn)
        conn.close()
        database.import_data()
    finally:
        database.DB_PATH = orig_db_path
    return tmp_db


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def sync_kanji(shadow: sqlite3.Connection, live: sqlite3.Connection, dry_run: bool) -> dict:
    fields = ["character", "keyword", "frame", "stroke_count", "jlpt"]
    shadow_rows = {r["id"]: dict(r) for r in shadow.execute(
        f"SELECT id, {', '.join(fields)} FROM kanji WHERE {SYSTEM_JA_KANJI}")}
    live_rows = {r["id"]: dict(r) for r in live.execute(
        f"SELECT id, {', '.join(fields)} FROM kanji WHERE {SYSTEM_JA_KANJI}")}

    inserted, updated = [], []
    for kid, srow in shadow_rows.items():
        if kid not in live_rows:
            if not dry_run:
                live.execute(
                    "INSERT INTO kanji (id, character, keyword, frame, stroke_count, jlpt, "
                    "owner_id, visibility, script) VALUES (?, ?, ?, ?, ?, ?, 1, 'public', 'ja-kanji')",
                    (kid, srow["character"], srow["keyword"], srow["frame"],
                     srow["stroke_count"], srow["jlpt"])
                )
            inserted.append(kid)
        else:
            lrow = live_rows[kid]
            changed = {f: srow[f] for f in fields if srow[f] != lrow[f]}
            if changed:
                if not dry_run:
                    set_clause = ", ".join(f"{f} = ?" for f in changed)
                    live.execute(f"UPDATE kanji SET {set_clause} WHERE id = ?",
                                 (*changed.values(), kid))
                updated.append(kid)

    removed_from_source = sorted(set(live_rows) - set(shadow_rows))
    return {"inserted": inserted, "updated": updated, "removed_from_source": removed_from_source}


def sync_aliases(shadow: sqlite3.Connection, live: sqlite3.Connection, dry_run: bool) -> dict:
    q = f"""SELECT a.kanji_id, a.alias FROM aliases a JOIN kanji k ON k.id = a.kanji_id
            WHERE a.{SYSTEM_JA_KANJI}"""
    shadow_pairs = {(r["kanji_id"], r["alias"]) for r in shadow.execute(q)}
    live_pairs = {(r["kanji_id"], r["alias"]) for r in live.execute(q)}

    to_add = sorted(shadow_pairs - live_pairs)
    to_remove = sorted(live_pairs - shadow_pairs)

    if not dry_run:
        live.executemany(
            "INSERT OR IGNORE INTO aliases (kanji_id, alias, owner_id, visibility) VALUES (?, ?, 1, 'public')",
            to_add
        )
        live.executemany(
            "DELETE FROM aliases WHERE kanji_id = ? AND alias = ? AND owner_id = 1",
            to_remove
        )
    return {"added": to_add, "removed": to_remove}


def sync_decompositions(shadow: sqlite3.Connection, live: sqlite3.Connection, dry_run: bool) -> dict:
    decomp_q = f"""SELECT d.id, d.kanji_id FROM decompositions d JOIN kanji k ON k.id = d.kanji_id
                   WHERE d.{SYSTEM_JA_KANJI}"""

    shadow_decomp = {r["kanji_id"]: r["id"] for r in shadow.execute(decomp_q)}
    shadow_parts = {
        kid: [r["part_term"] for r in shadow.execute(
            "SELECT part_term FROM parts WHERE decomposition_id = ? ORDER BY position", (did,))]
        for kid, did in shadow_decomp.items()
    }

    live_decomp_rows = list(live.execute(decomp_q))
    live_decomp: dict[str, int] = {}
    dupes = []
    for r in live_decomp_rows:
        if r["kanji_id"] in live_decomp:
            dupes.append(r["kanji_id"])
        else:
            live_decomp[r["kanji_id"]] = r["id"]

    created, replaced, removed = [], [], []
    for kid in sorted(set(shadow_parts) | set(live_decomp)):
        target_terms = shadow_parts.get(kid, [])
        live_did = live_decomp.get(kid)
        live_terms = []
        if live_did is not None:
            live_terms = [r["part_term"] for r in live.execute(
                "SELECT part_term FROM parts WHERE decomposition_id = ? ORDER BY position", (live_did,))]

        if target_terms == live_terms:
            continue

        if not target_terms:
            if not dry_run:
                live.execute("DELETE FROM parts WHERE decomposition_id = ?", (live_did,))
                live.execute("DELETE FROM decompositions WHERE id = ?", (live_did,))
            removed.append(kid)
        elif live_did is None:
            if not dry_run:
                cur = live.execute(
                    "INSERT INTO decompositions (kanji_id, owner_id, visibility, label) "
                    "VALUES (?, 1, 'public', NULL)", (kid,)
                )
                new_did = cur.lastrowid
                live.executemany(
                    "INSERT INTO parts (kanji_id, part_term, position, decomposition_id) VALUES (?, ?, ?, ?)",
                    [(kid, term, pos, new_did) for pos, term in enumerate(target_terms)]
                )
            created.append(kid)
        else:
            if not dry_run:
                live.execute("DELETE FROM parts WHERE decomposition_id = ?", (live_did,))
                live.executemany(
                    "INSERT INTO parts (kanji_id, part_term, position, decomposition_id) VALUES (?, ?, ?, ?)",
                    [(kid, term, pos, live_did) for pos, term in enumerate(target_terms)]
                )
            replaced.append(kid)

    return {"created": created, "replaced": replaced, "removed": removed, "duplicate_system_decomps": dupes}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=database.DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true", help="skip the pre-write backup copy")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"error: {args.db} does not exist — this script syncs an already-seeded live DB, "
              f"it doesn't create one from scratch (that's import_data()'s job on first startup).")
        raise SystemExit(1)

    if not args.dry_run and not args.no_backup:
        backup_path = args.db.with_name(f"{args.db.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(args.db, backup_path)
        print(f"Backed up {args.db} -> {backup_path}")

    print("Building target state from heisig-kanjis.csv / data_from_pdf.txt / data.txt ...")
    shadow_path = build_shadow_db()
    shadow = open_db(shadow_path)
    live = open_db(args.db)

    try:
        kanji_result = sync_kanji(shadow, live, args.dry_run)
        alias_result = sync_aliases(shadow, live, args.dry_run)
        decomp_result = sync_decompositions(shadow, live, args.dry_run)
        if not args.dry_run:
            live.commit()
    except Exception:
        live.rollback()
        raise
    finally:
        shadow.close()
        live.close()

    mode = "DRY RUN — nothing written" if args.dry_run else "APPLIED"
    print(f"\n[{mode}]")
    print(f"kanji:          {len(kanji_result['inserted'])} inserted, {len(kanji_result['updated'])} updated")
    if kanji_result["removed_from_source"]:
        print(f"  ! {len(kanji_result['removed_from_source'])} system ja-kanji ids exist live but not in "
              f"source anymore (NOT auto-deleted, review manually): "
              f"{', '.join(kanji_result['removed_from_source'][:20])}"
              f"{' ...' if len(kanji_result['removed_from_source']) > 20 else ''}")
    print(f"aliases:        {len(alias_result['added'])} added, {len(alias_result['removed'])} removed")
    print(f"decompositions: {len(decomp_result['created'])} created, "
          f"{len(decomp_result['replaced'])} replaced, {len(decomp_result['removed'])} removed (now atomic)")
    if decomp_result["duplicate_system_decomps"]:
        print(f"  ! found more than one owner_id=1 decomposition on the same kanji_id for: "
              f"{', '.join(decomp_result['duplicate_system_decomps'])} — only the first was reconciled, "
              f"the rest were left alone; this shouldn't normally happen, worth a manual look.")

    total_changes = (
        len(kanji_result["inserted"]) + len(kanji_result["updated"])
        + len(alias_result["added"]) + len(alias_result["removed"])
        + len(decomp_result["created"]) + len(decomp_result["replaced"]) + len(decomp_result["removed"])
    )
    if total_changes == 0:
        print("\nNo changes — live DB already matches the source files.")


if __name__ == "__main__":
    main()
