#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
hanzi_worklist_next.py -- the daily driver for docs/hanzi_decomposition_worklist.json.
Same shape and workflow as worklist_next.py, for the kanji worklist.

  ./venv/bin/python3 hanzi_worklist_next.py                 # print the next 20 pending
  ./venv/bin/python3 hanzi_worklist_next.py -n 20           # ...N of them
  ./venv/bin/python3 hanzi_worklist_next.py --id hanzi-6cef # show one, full detail
  ./venv/bin/python3 hanzi_worklist_next.py --decide hanzi-6cef --status use-cjkvi \
        --parts 水,包 --by claude       # record a decision (also writes the DB? NO -- see below)

Recording a decision only updates the worklist JSON (status/decision/
reviewed_by/reviewed_at). Applying the decision to kanji.db is a SEPARATE,
deliberate edit (there is no data.txt for hanzi -- see CLAUDE.md's "Import
pipeline" section and build_hanzi_worklist.py's docstring), made directly
against the live DB the same way sync_system_data.py writes owner_id=1 parts
rows, followed by a docs/2026-08-search-quality-audit.md entry (doc-per-commit
rule applies here same as kanji). After the fix lands, re-run
audit_hanzi_weak_evidence.py --json ... then build_hanzi_worklist.py -- the
decided row is preserved regardless, since this worklist never auto-drops rows
the way the kanji one does (no second source to newly "agree" with).

Process: ~20 hanzi per day, no full-list passes, same cadence as kanji.
"""
import argparse
import datetime
import json
from pathlib import Path

WL = Path(__file__).parent.parent / "docs" / "hanzi_decomposition_worklist.json"


def load():
    return json.loads(WL.read_text(encoding="utf-8"))


def save(rows):
    WL.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def show(e):
    print(f"\n{e['id']}  {e['char']}   [{e['kind']}] [{e['status']}]")
    print(f"  ours   : {', '.join(e['our_parts']) or '(atomic / none)'}")
    if e["kind"] == "overlay":
        print(f"  cjkvi  : {e['cjkvi_reading']}{' [' + e['cjkvi_tags'] + ']' if e.get('cjkvi_tags') else ''}")
    else:
        print(f"  opaque : cjkvi stops at {e['opaque_children']}")
    if e.get("decision"):
        print(f"  DECIDED: {e['status']} -> {', '.join(e['decision'])}  by {e['reviewed_by']} {e['reviewed_at']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--id")
    ap.add_argument("--decide", metavar="ID")
    ap.add_argument("--status", choices=["keep-ours", "use-cjkvi", "custom", "needs-render", "pending"])
    ap.add_argument("--parts", help="comma-separated final decomposition for the decision")
    ap.add_argument("--by", default="claude")
    ap.add_argument("--pending-count", action="store_true")
    ap.add_argument("--kind", choices=["overlay", "opaque"], help="only rows of this kind")
    a = ap.parse_args()
    rows = load()
    by_id = {r["id"]: r for r in rows}

    if a.pending_count:
        p = sum(1 for r in rows if r["status"] == "pending")
        print(f"{p} pending / {len(rows)} total")
        return
    if a.id:
        if a.id in by_id:
            show(by_id[a.id])
        else:
            print(f"{a.id} not in worklist")
        return
    if a.decide:
        e = by_id.get(a.decide)
        if not e:
            print(f"{a.decide} not in worklist")
            return
        if not a.status:
            print("need --status")
            return
        e["status"] = a.status
        e["decision"] = [p.strip() for p in a.parts.split(",")] if a.parts else None
        e["reviewed_by"] = a.by
        e["reviewed_at"] = datetime.date.today().isoformat()
        save(rows)
        show(e)
        print("\n(worklist updated; now make the kanji.db edit directly if the decision changes our data)")
        return

    pending = [r for r in rows if r["status"] == "pending"]
    if a.kind:
        pending = [r for r in pending if r["kind"] == a.kind]
    print(f"{len(pending)} pending / {len(rows)} total -- next {min(a.n, len(pending))}:")
    for e in pending[:a.n]:
        show(e)


if __name__ == "__main__":
    main()
