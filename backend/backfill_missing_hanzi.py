#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
backfill_missing_hanzi.py — one-off patch for the self-referencing-variant bug in
import_hanzi.py (fixed 2026-08-22; see that file's history for the bug itself).

import_hanzi.py's ambiguity check (`has_simp and has_trad`) treated a
self-referencing kSimplifiedVariant/kTraditionalVariant (Unihan's way of saying
"this char already IS that form", e.g. 报's kSimplifiedVariant points to 报 itself)
as a genuine second variant direction, so any character with one real cross-reference
plus a self-reference on the other field got wrongly flagged "ambiguous" and skipped
entirely. Found chasing a report that 報's simplified form 报 couldn't be found at
all. Affects 430 characters in the CJK Unified block (270 missing from kanji.db
outright; the other 160 happened to already have an unrelated ja-kanji row for the
same glyph, but were still missing their own zh-* hanzi row).

This is *not* safe to fix by just re-running import_hanzi.py --- that script refuses
to run once any non-ja-kanji row exists, and even if forced, would re-insert every
hanzi row from scratch rather than just the missing ones. Instead this script:
  1. Re-parses Unihan_Variants.txt / Unihan_Readings.txt / ids.txt (same sources,
     same scope, same per-field parsing as import_hanzi.py) using the *fixed*
     ambiguity logic to recompute the correct character-to-script assignment.
  2. Inserts only the hanzi-{cp} rows that don't already exist (kanji + aliases +
     IDS-derived decomposition, matching import_hanzi.py's Pass 1/3 conventions
     exactly).
  3. Backfills variant_of links in *both* directions: the newly-inserted characters'
     own link, and any pre-existing character (like 報/hanzi-5831) whose variant_of
     was left NULL because its counterpart didn't exist yet at original-import time.

One-off, not part of the app's runtime. Safe to re-run --- every step is either
INSERT OR IGNORE or checks the row doesn't already exist first.

Usage:
    python3 backfill_missing_hanzi.py [--unihan-dir /tmp/unihan_extracted] [--ids-file /tmp/ids.txt] [--dry-run]
"""

import argparse
from pathlib import Path

from database import get_db, _insert_alias, _build_char_lookup, expand_part_terms
from import_hanzi import (
    CJK_UNIFIED_SCOPE, parse_unihan_variants, parse_unihan_readings, parse_ids,
    _strip_pinyin_tones,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--unihan-dir", type=Path, default=Path("/tmp/unihan_extracted"))
    parser.add_argument("--ids-file", type=Path, default=Path("/tmp/ids.txt"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    variants = parse_unihan_variants(args.unihan_dir / "Unihan_Variants.txt", CJK_UNIFIED_SCOPE)
    readings = parse_unihan_readings(args.unihan_dir / "Unihan_Readings.txt", CJK_UNIFIED_SCOPE)
    ids_data = parse_ids(args.ids_file, CJK_UNIFIED_SCOPE)
    all_chars = sorted(set(variants) | set(readings) | set(ids_data), key=ord)

    # Same fixed logic as the patched import_hanzi.py::main().
    char_script: dict[str, str] = {}
    for ch in all_chars:
        v = variants.get(ch, {})
        has_simp = v.get("simplified") is not None and v.get("simplified") != ch
        has_trad = v.get("traditional") is not None and v.get("traditional") != ch
        if has_simp and has_trad:
            continue
        char_script[ch] = "zh-Hans" if has_trad else ("zh-Hant" if has_simp else "zh-Hani")

    conn = get_db()
    existing_ids = {r["id"] for r in conn.execute("SELECT id FROM kanji").fetchall()}

    missing = {ch: s for ch, s in char_script.items() if f"hanzi-{ord(ch):x}" not in existing_ids}
    print(f"{len(char_script)} characters in corrected scope; {len(missing)} missing from kanji.db.")

    if args.dry_run:
        for ch in list(missing)[:20]:
            print(f"  {ch}  script={missing[ch]}  def={readings.get(ch, {}).get('definition')}  "
                  f"components={ids_data.get(ch)}")
        conn.close()
        return

    # ── Pass 1: insert the missing kanji rows + basic aliases ──────────────────
    for ch, script in missing.items():
        cid = f"hanzi-{ord(ch):x}"
        definition = readings.get(ch, {}).get("definition")
        keyword = definition.split(";")[0].strip().lower() if definition else ch
        conn.execute(
            "INSERT OR IGNORE INTO kanji (id, character, keyword, owner_id, visibility, script) "
            "VALUES (?, ?, ?, 1, 'public', ?)",
            (cid, ch, keyword, script)
        )
        _insert_alias(conn, cid, ch)
        if keyword != ch:
            _insert_alias(conn, cid, keyword)
        mandarin = readings.get(ch, {}).get("mandarin")
        if mandarin:
            _insert_alias(conn, cid, _strip_pinyin_tones(mandarin))
    print(f"Inserted {len(missing)} hanzi kanji rows.")

    # ── Pass 2: variant_of links, both for newly-inserted rows and any
    # pre-existing row whose counterpart just showed up for the first time ──────
    all_known_ids = existing_ids | {f"hanzi-{ord(ch):x}" for ch in missing}
    linked = 0
    for ch, v in variants.items():
        cid = f"hanzi-{ord(ch):x}"
        if cid not in all_known_ids:
            continue
        current = conn.execute("SELECT variant_of FROM kanji WHERE id = ?", (cid,)).fetchone()
        if current is None or current["variant_of"] is not None:
            continue
        simp = v.get("simplified") if v.get("simplified") != ch else None
        trad = v.get("traditional") if v.get("traditional") != ch else None
        target = simp or trad
        target_id = f"hanzi-{ord(target):x}" if target else None
        if target_id and target_id in all_known_ids:
            conn.execute("UPDATE kanji SET variant_of = ? WHERE id = ?", (target_id, cid))
            linked += 1
    print(f"Linked/backfilled {linked} variant_of pairs.")

    # ── Pass 3: IDS decompositions for the newly-inserted characters only ──────
    char_lookup = _build_char_lookup(conn)
    decomps_created = 0
    for ch in missing:
        components = ids_data.get(ch)
        if not components:
            continue
        cid = f"hanzi-{ord(ch):x}"
        expanded_terms = expand_part_terms(conn, components, char_lookup, script_group="zh")
        cur = conn.execute(
            "INSERT INTO decompositions (kanji_id, owner_id, visibility, label) VALUES (?, 1, 'public', 'ids')",
            (cid,)
        )
        conn.executemany(
            "INSERT INTO parts (kanji_id, part_term, position, decomposition_id) VALUES (?, ?, ?, ?)",
            [(cid, term, pos, cur.lastrowid) for pos, term in enumerate(expanded_terms)]
        )
        decomps_created += 1
    print(f"Created {decomps_created} IDS-derived decompositions.")

    conn.commit()
    conn.close()
    print("Backfill complete.")


if __name__ == "__main__":
    main()
