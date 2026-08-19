"""
audit_flattening.py — deterministic detector for the "redundant flattening"
bug pattern that has been the majority of content fixes across the search-
quality audit (docs/2026-08-search-quality-audit.md, sessions 9-19): a
data.txt override lists a compound kanji's own already-decomposed parts
directly, instead of just referencing the compound itself, e.g. 灯 listed
as `一,火,亅` instead of `火,丁` (丁 already = `一,亅`).

## How it works

For every system (owner_id=1) rtk* kanji K with a decomposition of >=2
parts, and every other system rtk*/rad* kanji M with its own decomposition
of >=2 parts: if M's full resolved part-id set is a subset of K's resolved
part-id set, K is very likely flattening M in place rather than referencing
it. Flags K, the redundant parts it could collapse to M, and what K's
decomposition would look like if collapsed.

This is a proxy, not a certainty — the same primitive set can legitimately
arise two different ways (convergent decomposition), and this script does
not attempt to verify visual/stroke-order plausibility, only structural
redundancy. Every flagged candidate still needs the same manual judgement
call prior sessions have applied: does collapsing to M actually match K's
real visual structure, or is the parts-set overlap coincidental. Treat the
output as a worklist, not a diff to apply blindly.

Usage:
    python3 audit_flattening.py [--min-frame N] [--max-frame N]

Never touches backend/kanji.db.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402


def build_shadow_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="kanji_flatten_audit_"))
    tmp_db = tmp_dir / "shadow.db"
    database.DB_PATH = tmp_db
    database.init_db()
    conn = database.get_db()
    database.migrate_schema(conn)
    conn.close()
    database.import_data()
    return tmp_db


def collect_signatures(conn):
    """id -> (frame, keyword, character, set of resolved part ids), system ja-kanji only,
    decompositions of >=2 parts only (a 1-part decomposition can't meaningfully "contain"
    another compound's full parts-set)."""
    sigs = {}
    rows = conn.execute(
        "SELECT id, frame, keyword, character FROM kanji "
        "WHERE owner_id = 1 AND script = 'ja-kanji' AND id LIKE 'rtk%' ORDER BY frame"
    ).fetchall()
    for r in rows:
        d = database.get_kanji_detail(conn, r["id"], viewer_id=None)
        if not d or not d["decompositions"]:
            continue
        # system decomposition only (owner None/system, first one — matches this
        # audit's longstanding scope of the seeded data, not user contributions)
        sys_decomp = next((dc for dc in d["decompositions"] if dc["owner"] in (None, "system")), None)
        if not sys_decomp:
            continue
        part_ids = {p["id"] for p in sys_decomp["parts_detail"]}
        if len(part_ids) >= 2:
            sigs[r["id"]] = (r["frame"], r["keyword"], r["character"], part_ids)
    return sigs


def find_flattening_candidates(sigs, min_frame=None, max_frame=None):
    candidates = []
    items = list(sigs.items())
    for kid, (kframe, kkeyword, kchar, kparts) in items:
        if min_frame and (kframe or 0) < min_frame:
            continue
        if max_frame and (kframe or 0) > max_frame:
            continue
        if len(kparts) < 3:
            continue  # need room for a >=2-part subset plus something else
        for mid, (mframe, mkeyword, mchar, mparts) in items:
            if mid == kid or mid in kparts:
                continue
            if mparts < kparts:  # proper subset
                remainder = kparts - mparts
                candidates.append((kframe, kid, kkeyword, kchar, mid, mkeyword, mchar, remainder))
    candidates.sort(key=lambda c: (c[0] or 0, c[1]))
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-frame", type=int, default=None)
    parser.add_argument("--max-frame", type=int, default=None)
    args = parser.parse_args()

    print("Building shadow database from source files...", flush=True)
    shadow_db = build_shadow_db()
    conn = database.sqlite3.connect(shadow_db)
    conn.row_factory = database.sqlite3.Row

    sigs = collect_signatures(conn)
    candidates = find_flattening_candidates(sigs, args.min_frame, args.max_frame)
    conn.close()

    print(f"\n{len(candidates)} candidate(s) where a kanji's parts fully contain another "
          f"compound's own parts-set:\n")
    for kframe, kid, kkeyword, kchar, mid, mkeyword, mchar, remainder in candidates:
        remainder_desc = ", ".join(sorted(remainder)) if remainder else "(nothing left over)"
        print(f"  frame {kframe}: {kid} {kchar} ({kkeyword}) contains {mid} {mchar} ({mkeyword})'s "
              f"full parts — remainder: {remainder_desc}")


if __name__ == "__main__":
    main()
