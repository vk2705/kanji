#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
build_hanzi_worklist.py -- (re)generate docs/hanzi_decomposition_worklist.json:
the finite list of hanzi-* rows whose decomposition rests on weak cjkvi-ids
evidence (audit_hanzi_weak_evidence.py's "overlay" and "opaque" findings).

## Why this isn't build_decomp_worklist.py's disagreement check

The kanji worklist enters a kanji when OUR data.txt decomposition disagrees
with a second, independent source (Google's AI-Overview breakdown). Hanzi rows
were written directly FROM cjkvi-ids by import_hanzi.py, so "ours vs cjkvi-ids"
is true by construction almost everywhere -- that check would produce an
essentially empty worklist, not a useful one. There is no Heisig book and no
Google-check data for hanzi either (tools/heisig-google-check/ is kanji-only
and CAPTCHA-gated to the owner's home computer regardless).

So this worklist is seeded differently: it holds every hanzi row where cjkvi-
ids' OWN structure is the kind that has already produced wrong kanji
decompositions when misread as a flat parts list (an overlay/enclosure
operator, or an opaque intermediate with no row here) -- see
audit_hanzi_weak_evidence.py's docstring and CLAUDE.md's "Three ways the
sources lie" section for the reasoning this mirrors. A row here is not
necessarily wrong; it is a row whose evidence needs a render before it is
trusted, same as the kanji audit's stance.

This is the audit's standing worklist, same shape as decomposition_worklist.json:
meant to SHRINK as each row gets a human decision. Re-running this script
PRESERVES decided rows (by id) and only refreshes/adds still-undecided ones.
Never re-review a decided row.

Run after: a new /tmp/ids.txt (cjkvi-ids updated), or a hanzi data-fix commit
(some findings resolved -> drop out on the next audit run).

    ./venv/bin/python3 audit_hanzi_weak_evidence.py --json /tmp/hanzi_weak_evidence.json
    ./venv/bin/python3 build_hanzi_worklist.py [--stats]

Read-only except for the worklist JSON. Does not touch kanji.db.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
FINDINGS = Path("/tmp/hanzi_weak_evidence.json")
WORKLIST = HERE.parent / "docs" / "hanzi_decomposition_worklist.json"


def main():
    stats_only = "--stats" in sys.argv
    if not FINDINGS.exists():
        print(f"missing {FINDINGS} -- run:\n"
              f"  ./venv/bin/python3 audit_hanzi_weak_evidence.py --json {FINDINGS}",
              file=sys.stderr)
        return 1
    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))

    decided = {}
    if WORKLIST.exists():
        for row in json.loads(WORKLIST.read_text(encoding="utf-8")):
            if row.get("status") and row["status"] != "pending":
                decided[row["id"]] = row

    rows = []
    n_decided_kept = n_pending = 0

    for f in findings.get("overlay", []):
        kid = f["id"]
        if kid in decided:
            rows.append(decided[kid])
            n_decided_kept += 1
            continue
        n_pending += 1
        rows.append({
            "id": kid,
            "char": f["char"],
            "kind": "overlay",
            "our_parts": f["our_parts"],
            "cjkvi_reading": f["cjkvi"],
            "cjkvi_tags": f.get("tags", ""),
            "status": "pending",
            "decision": None,
            "reviewed_by": None,
            "reviewed_at": None,
        })

    for f in findings.get("opaque", []):
        kid = f["id"]
        if kid in decided:
            rows.append(decided[kid])
            n_decided_kept += 1
            continue
        n_pending += 1
        rows.append({
            "id": kid,
            "char": f["char"],
            "kind": "opaque",
            "our_parts": f["our_parts"],
            "opaque_children": f["opaque"],
            "status": "pending",
            "decision": None,
            "reviewed_by": None,
            "reviewed_at": None,
        })

    rows.sort(key=lambda r: r["id"])

    if stats_only:
        print(f"decided (kept)       : {n_decided_kept}")
        print(f"pending review       : {n_pending}")
        print(f"worklist total       : {len(rows)}")
        return 0

    WORKLIST.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {WORKLIST.relative_to(HERE.parent)}: {len(rows)} rows "
          f"({n_pending} pending, {n_decided_kept} already decided)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
