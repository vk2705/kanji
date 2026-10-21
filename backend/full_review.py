#!/usr/bin/env python3
"""full_review.py — the from-scratch re-review of every Japanese kanji.

Owner decision (2026-10-21): the earlier worklist only queued kanji whose
breakdown *disagreed* with Google's AI answer, so a row that was wrong in the
same way Google was wrong never got looked at. 亀 was the case that showed
it: 日,勹,乙 in both, while the real shape is 𠂊 + 电. So every rtk* kanji goes
back through review, in frame order, 50 a day, each decided against the
render, Heisig's components column and cjkvi-ids rather than against Google.

  ./venv/bin/python3 full_review.py --init            # create docs/kanji_full_review.json (once)
  ./venv/bin/python3 full_review.py -n 50             # next 50 pending, with all the evidence
  ./venv/bin/python3 full_review.py --id rtk573       # one row
  ./venv/bin/python3 full_review.py --decide rtk573 --status fixed \\
        --parts 𠂊,电 --note "bottom is the eel shape, top is 𠂊 not 勹" --by claude
  ./venv/bin/python3 full_review.py --pending-count

Statuses: pending, keep (current row is right), fixed (data.txt changed —
--parts is the new primary), needs-render (could not decide; a person should
look). Every decision needs a --note saying why: build_decomposition_history.py
shows it on the kanji's page, and it is how the owner tells a real fix from a
review that made things worse.

Recording a decision only updates the JSON. The data.txt edit, the DB sync,
the tests and the commit are separate steps (see kanji_worklist_daily_prompt.md).
"""
import argparse
import csv
import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = HERE.parent / "docs" / "kanji_full_review.json"
STATUSES = ["pending", "keep", "fixed", "needs-render"]


def load():
    return json.loads(LIST.read_text(encoding="utf-8"))


def save(rows):
    LIST.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def init():
    if LIST.exists():
        sys.exit(f"{LIST} already exists. Decided rows are permanent; refusing to overwrite.")
    data_lines = {}
    for raw in (HERE / "data.txt").read_text(encoding="utf-8").splitlines():
        if raw.startswith("rtk"):
            fields = raw.strip().split(":", 3)
            data_lines[fields[0]] = fields[3] if len(fields) > 3 else ""
    ids = {}
    ids_path = Path("/tmp/ids.txt")
    if ids_path.exists():
        for raw in ids_path.read_text(encoding="utf-8").splitlines():
            cols = raw.split("\t")
            if len(cols) >= 3:
                ids[cols[1]] = " ".join(cols[2:])
    google = json.loads((HERE / "google_decompositions.json").read_text(encoding="utf-8"))
    rows = []
    with open(HERE / "heisig-kanjis.csv", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            if not rec.get("id_6th_ed"):
                continue
            kanji_id = f"rtk{rec['id_6th_ed']}"
            g = google.get(kanji_id) or {}
            rows.append({
                "id": kanji_id,
                "char": rec["kanji"],
                "keyword": rec["keyword_6th_ed"],
                "frame": int(rec["id_6th_ed"]),
                "parts_at_start": data_lines.get(kanji_id, "(not in data.txt: from the CSV/PDF baseline)"),
                "heisig_components": rec["components"],
                "cjkvi_ids": ids.get(rec["kanji"], ""),
                "google_parts": g.get("parts"),
                "status": "pending",
                "decision": None,
                "note": "",
                "reviewed_by": None,
                "reviewed_at": None,
            })
    rows.sort(key=lambda r: r["frame"])
    save(rows)
    print(f"Wrote {LIST}: {len(rows)} kanji, all pending.")


def show(row):
    print(f"\n{row['id']}  {row['char']}  \"{row['keyword']}\"   frame {row['frame']}   [{row['status']}]")
    print(f"  data.txt at start : {row['parts_at_start'] or '(atomic)'}")
    print(f"  Heisig components : {row['heisig_components'] or '(empty: Heisig teaches it whole)'}")
    print(f"  cjkvi-ids         : {row['cjkvi_ids'] or '-'}")
    if row.get("google_parts") is not None:
        print(f"  Google (hint only): {', '.join(row['google_parts']) or '(atomic)'}")
    if row["status"] != "pending":
        decision = f" -> {', '.join(row['decision'])}" if row.get("decision") else ""
        print(f"  DECIDED: {row['status']}{decision}  by {row['reviewed_by']} {row['reviewed_at']}: {row['note']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--init", action="store_true")
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--id")
    ap.add_argument("--decide", metavar="ID")
    ap.add_argument("--status", choices=STATUSES)
    ap.add_argument("--parts", help="comma-separated new primary decomposition (status fixed)")
    ap.add_argument("--note", default="")
    ap.add_argument("--by", default="claude")
    ap.add_argument("--pending-count", action="store_true")
    a = ap.parse_args()

    if a.init:
        init()
        return
    rows = load()
    by_id = {r["id"]: r for r in rows}
    if a.pending_count:
        pending = sum(r["status"] == "pending" for r in rows)
        print(f"{pending} pending / {len(rows)} total")
        return
    if a.id:
        show(by_id[a.id]) if a.id in by_id else print(f"{a.id} is not in the full review")
        return
    if a.decide:
        row = by_id.get(a.decide)
        if not row:
            sys.exit(f"{a.decide} is not in the full review")
        if not a.status or a.status == "pending":
            sys.exit("--decide needs --status keep|fixed|needs-render")
        if not a.note.strip():
            sys.exit("--decide needs --note: say why, it is shown in the kanji's history")
        if a.status == "fixed" and not a.parts:
            sys.exit("--status fixed needs --parts (the new primary decomposition)")
        row["status"] = a.status
        row["decision"] = [p.strip() for p in a.parts.split(",")] if a.parts else None
        row["note"] = a.note.strip()
        row["reviewed_by"] = a.by
        row["reviewed_at"] = datetime.date.today().isoformat()
        save(rows)
        show(row)
        return
    pending = [r for r in rows if r["status"] == "pending"]
    print(f"{len(pending)} pending / {len(rows)} total — next {min(a.n, len(pending))}:")
    for row in pending[:a.n]:
        show(row)


if __name__ == "__main__":
    main()
