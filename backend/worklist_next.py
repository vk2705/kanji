#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
worklist_next.py — the daily driver for docs/decomposition_worklist.json.

  ./venv/bin/python3 worklist_next.py                 # print the next 20 pending
  ./venv/bin/python3 worklist_next.py -n 20           # ...N of them
  ./venv/bin/python3 worklist_next.py --id rtk165     # show one, full detail
  ./venv/bin/python3 worklist_next.py --decide rtk165 --status use-google \
        --parts 土,亘 --by claude       # record a decision (also writes data.txt? NO -- see below)

Recording a decision only updates the worklist JSON (status/decision/
reviewed_by/reviewed_at). Applying the decision to backend/data.txt is a
SEPARATE, deliberate edit + commit (so the doc-per-commit rule and the
render-it check still gate every real change). After the data.txt fix lands,
re-run build_decomp_worklist.py -- the decided row is preserved, and if the
new decomposition now agrees with Google it simply drops off next rebuild.

Process (owner, 2026-09-05): ~20 kanji per day, no full-list passes.
"""
import argparse, json, datetime
from pathlib import Path

WL = Path(__file__).parent.parent / "docs" / "decomposition_worklist.json"

def load(): return json.loads(WL.read_text(encoding="utf-8"))
def save(rows): WL.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

def show(e, full=False):
    print(f"\n{e['id']}  {e['char']}  \"{e['keyword']}\"   [{e['status']}]")
    print(f"  ours   : {', '.join(e['our_parts']) or '(atomic / none)'}")
    print(f"  google : {', '.join(e['google_parts'])}   ({e['google_confidence']})")
    if e.get("google_primitive_names"):
        print(f"           names: " + "; ".join(f"{k}={v}" for k, v in e["google_primitive_names"].items()))
    if e.get("google_note"):
        print(f"  g-note : {e['google_note']}")
    print(f"  cjkvi  : {e['cjkvi_ids']}   leaves: {' '.join(e['cjkvi_leaves'])}")
    if e.get("decision"):
        print(f"  DECIDED: {e['status']} -> {', '.join(e['decision'])}  by {e['reviewed_by']} {e['reviewed_at']}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--id")
    ap.add_argument("--decide", metavar="ID")
    ap.add_argument("--status", choices=["keep-ours", "use-google", "custom", "needs-render", "pending"])
    ap.add_argument("--parts", help="comma-separated final decomposition for the decision")
    ap.add_argument("--by", default="claude")
    ap.add_argument("--pending-count", action="store_true")
    a = ap.parse_args()
    rows = load()
    by_id = {r["id"]: r for r in rows}

    if a.pending_count:
        p = sum(1 for r in rows if r["status"] == "pending")
        print(f"{p} pending / {len(rows)} total")
        return
    if a.id:
        if a.id in by_id: show(by_id[a.id], full=True)
        else: print(f"{a.id} not in worklist")
        return
    if a.decide:
        e = by_id.get(a.decide)
        if not e:
            print(f"{a.decide} not in worklist"); return
        if not a.status:
            print("need --status"); return
        e["status"] = a.status
        e["decision"] = [p.strip() for p in a.parts.split(",")] if a.parts else None
        e["reviewed_by"] = a.by
        e["reviewed_at"] = datetime.date.today().isoformat()
        save(rows)
        show(e)
        print("\n(worklist updated; now make the data.txt edit + commit if the decision changes our data)")
        return

    pending = [r for r in rows if r["status"] == "pending"]
    print(f"{len(pending)} pending / {len(rows)} total — next {min(a.n, len(pending))}:")
    for e in pending[:a.n]:
        show(e)

if __name__ == "__main__":
    main()
