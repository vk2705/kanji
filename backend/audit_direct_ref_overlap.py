"""
audit_direct_ref_overlap.py — detector for a third "redundant flattening" bug
shape found 2026-09-04 (docs/2026-08-search-quality-audit.md): a host kanji K
references a taught primitive/compound P *directly* by character (correct!),
but ALSO separately lists one or more of P's own resolved sub-parts alongside
it — redundant, since P already implies those parts recursively. This is what
the whole 石("stone")-family bug was: every host correctly referenced 石, but
almost all of them also carried a stray extra "口" (one of 石's own two parts,
石 = 厂,口) floating redundantly next to it.

This is DIFFERENT from what audit_flattening.py / audit_flattening_subsequence.py
already check. Those look for a host flattening a compound's FULL part-set
*instead of* referencing it (and explicitly skip any host that already
references the compound directly — `mid in kparts` is excluded there, by
design, since that's not the bug they're hunting). This script specifically
requires the opposite: P's id IS present in K's own parts, AND at least one of
P's own part-ids is ALSO present — a partial or full overlap alongside a
direct reference, not instead of one.

Usage:
    python3 audit_direct_ref_overlap.py [--min-usage N]

--min-usage (default 3): only consider primitives P referenced directly by at
least this many hosts, to focus on genuinely common primitives (a one-off
overlap is less likely to be a systemic, high-leverage bug worth a dedicated
look, though it can still be a real bug — this is a worklist, not a verdict).

Never touches backend/kanji.db.
"""
import argparse
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

from audit_flattening import build_shadow_db, collect_signatures  # noqa: E402


def find_overlap_candidates(sigs, min_usage=3):
    # primitive/compound id -> its own resolved part-id list (only kanji with a
    # decomposition of their own can be "redundantly re-flattened")
    own_parts = {pid: parts for pid, (_, _, _, parts) in sigs.items()}

    # how many hosts reference each id directly, to focus on common primitives first
    usage = defaultdict(int)
    for pid, (_, _, _, parts) in sigs.items():
        for p in set(parts):
            usage[p] += 1

    candidates = []
    for kid, (kframe, kkeyword, kchar, kparts) in sigs.items():
        kset = set(kparts)
        for pid in kset:
            if pid == kid or pid not in own_parts:
                continue
            if usage[pid] < min_usage:
                continue
            p_parts = own_parts[pid]
            overlap = kset & set(p_parts)
            if overlap:
                candidates.append((usage[pid], kframe, kid, kkeyword, kchar, pid, sorted(overlap), kparts))
    candidates.sort(key=lambda c: (-c[0], c[1] or 0))
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-usage", type=int, default=3)
    args = parser.parse_args()

    tmp_db = build_shadow_db()
    try:
        conn = database.get_db()
        sigs = collect_signatures(conn)
        candidates = find_overlap_candidates(sigs, min_usage=args.min_usage)
        print(f"{len(candidates)} host(s) directly reference a primitive AND redundantly "
              f"re-list one of its own parts (primitive used by >= {args.min_usage} hosts):\n")
        for usage, kframe, kid, kkeyword, kchar, pid, overlap, kparts in candidates:
            print(f"frame {kframe}: {kid} {kchar} ({kkeyword}) directly references "
                  f"{pid} (used {usage}x) AND also lists its own part(s) {overlap} "
                  f"-- full parts: {kparts}")
    finally:
        import shutil
        shutil.rmtree(tmp_db.parent, ignore_errors=True)


if __name__ == "__main__":
    main()
