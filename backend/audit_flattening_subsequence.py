"""
audit_flattening_subsequence.py — like audit_flattening.py, but catches redundant
flattening where the flattened compound's own parts are present *in order* but
NOT adjacent (something else sits between them), which audit_flattening.py's
deliberately strict contiguous-run requirement misses by design.

Added 2026-09-01 after an owner bug report (格, 燥, 礎, 磨, 椅) turned up five
real redundant-flattening bugs in a row that audit_flattening.py's own detector
had never flagged — in every case, M's own resolved part-id sequence appeared
in K's parts as an order-preserving SUBSEQUENCE, not a contiguous run (e.g. 格
was 口,木,夂 — 各's own parts 口,夂 are both there, in order, but 木 sits
between them). This is a real, previously-undetected blind spot, not just an
unreviewed-kanji gap.

This is strictly noisier than the contiguous-run check (a longer gap between
matched tokens is more likely coincidental), so treat its output as a rougher
worklist that needs the same CSV+render verification as always — probably
more so.

Usage:
    python3 audit_flattening_subsequence.py [--min-frame N] [--max-frame N]

Never touches backend/kanji.db.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402
from audit_flattening import build_shadow_db, collect_signatures  # noqa: E402


def _subsequence_at(haystack: list[str], needle: list[str]) -> list[int] | None:
    """Indices in haystack where needle appears as an order-preserving (not
    necessarily contiguous) subsequence, or None. Returns the *first* greedy
    match positions."""
    positions = []
    hi = 0
    for n in needle:
        found = None
        for i in range(hi, len(haystack)):
            if haystack[i] == n:
                found = i
                break
        if found is None:
            return None
        positions.append(found)
        hi = found + 1
    return positions


def find_candidates(sigs, min_frame=None, max_frame=None):
    candidates = []
    items = list(sigs.items())
    for kid, (kframe, kkeyword, kchar, kparts) in items:
        if min_frame and (kframe or 0) < min_frame:
            continue
        if max_frame and (kframe or 0) > max_frame:
            continue
        if len(kparts) < 3:
            continue
        for mid, (mframe, mkeyword, mchar, mparts) in items:
            if mid == kid or mid in kparts or len(mparts) < 2 or len(mparts) >= len(kparts):
                continue
            positions = _subsequence_at(kparts, mparts)
            if positions is None:
                continue
            contiguous = positions == list(range(positions[0], positions[0] + len(positions)))
            if contiguous:
                continue  # audit_flattening.py already catches this case
            gap = positions[-1] - positions[0] + 1 - len(mparts)
            remainder = [p for i, p in enumerate(kparts) if i not in positions]
            candidates.append((kframe, kid, kkeyword, kchar, mid, mkeyword, mchar, remainder, gap))
    candidates.sort(key=lambda c: (c[0] or 0, c[1], -len(c[7])))
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
    candidates = find_candidates(sigs, args.min_frame, args.max_frame)
    conn.close()

    print(f"\n{len(candidates)} candidate(s) where a kanji's parts contain another "
          f"compound's own parts as an order-preserving (non-contiguous) subsequence:\n")
    for kframe, kid, kkeyword, kchar, mid, mkeyword, mchar, remainder, gap in candidates:
        remainder_desc = ", ".join(remainder) if remainder else "(nothing left over)"
        print(f"  frame {kframe}: {kid} {kchar} ({kkeyword}) contains {mid} {mchar} ({mkeyword})'s "
              f"full parts (gap={gap}) — remainder: {remainder_desc}")


if __name__ == "__main__":
    main()
