"""
audit_flattening.py — deterministic detector for the "redundant flattening"
bug pattern that has been the majority of content fixes across the search-
quality audit (docs/2026-08-search-quality-audit.md, sessions 9-19): a
data.txt override lists a compound kanji's own already-decomposed parts
directly, instead of just referencing the compound itself, e.g. 灯 listed
as `一,火,亅` instead of `火,丁` (丁 already = `一,亅`).

## How it works

For every system (owner_id=1) rtk* kanji K with a decomposition of >=3
parts, and every other system rtk*/rad* kanji M with its own decomposition
of >=2 parts: if M's full resolved, ORDER-PRESERVING part-id sequence
appears as a CONTIGUOUS run inside K's resolved part-id sequence, K is very
likely flattening M in place rather than referencing it. Requiring
contiguity (not just set-subset) matters — an earlier version of this
script used plain subset containment and was overwhelmed by coincidental
overlap between unrelated kanji sharing a couple of common small primitives
(session 20's notes). Contiguity matches the actual bug shape: someone
pasted M's raw parts in place, which preserves both order and adjacency.
Flags K, the redundant parts it could collapse to M, and what K's
decomposition would look like if collapsed.

This is a proxy, not a certainty — the same primitive run can legitimately
arise two different ways (convergent decomposition), and this script does
not attempt to verify visual/stroke-order plausibility, only structural
redundancy. Every flagged candidate still needs the same manual judgement
call prior sessions have applied: does collapsing to M actually match K's
real visual structure, or is the overlap coincidental — and does M's own
decomposition itself hold up (session 21 found a case where the "compound"
being referenced was itself wrong, per CSV baseline, which would have
silently propagated the error). Treat the output as a worklist, not a diff
to apply blindly.

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
        part_ids = [p["id"] for p in sys_decomp["parts_detail"]]
        if len(set(part_ids)) >= 2:
            sigs[r["id"]] = (r["frame"], r["keyword"], r["character"], part_ids)
    return sigs


def _contiguous_at(haystack: list[str], needle: list[str]) -> int | None:
    """Index where `needle` appears as a contiguous run in `haystack`, or None. This is
    a much stronger signal than plain subset containment (which any two kanji sharing a
    couple of common small primitives will trip on by coincidence, at real scale, per
    session 20's notes) — the actual bug shape is someone pasting a compound's raw parts
    in place, so a genuine hit preserves both order and adjacency, not just membership."""
    n = len(needle)
    for i in range(len(haystack) - n + 1):
        if haystack[i:i + n] == needle:
            return i
    return None


def find_flattening_candidates(sigs, min_frame=None, max_frame=None):
    candidates = []
    items = list(sigs.items())
    for kid, (kframe, kkeyword, kchar, kparts) in items:
        if min_frame and (kframe or 0) < min_frame:
            continue
        if max_frame and (kframe or 0) > max_frame:
            continue
        if len(kparts) < 3:
            continue  # need room for a >=2-part contiguous run plus something else
        for mid, (mframe, mkeyword, mchar, mparts) in items:
            if mid == kid or mid in kparts or len(mparts) < 2 or len(mparts) >= len(kparts):
                continue
            idx = _contiguous_at(kparts, mparts)
            if idx is not None:
                remainder = kparts[:idx] + kparts[idx + len(mparts):]
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
        remainder_desc = ", ".join(remainder) if remainder else "(nothing left over)"
        print(f"  frame {kframe}: {kid} {kchar} ({kkeyword}) contains {mid} {mchar} ({mkeyword})'s "
              f"full parts — remainder: {remainder_desc}")


if __name__ == "__main__":
    main()
