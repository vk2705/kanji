#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
audit_hanzi_weak_evidence.py -- audit_weak_evidence.py's method, applied to
the ~21,000 zh-* rows instead of the ~3,000 rtk* ones.

## Why a separate script, not an extended audit_weak_evidence.py

audit_weak_evidence.py's three sections rest on two ground-truth sources:
Heisig's components column (heisig-kanjis.csv) and cjkvi-ids. Hanzi rows have
only the second -- import_hanzi.py writes them directly FROM cjkvi-ids via
expand_part_terms, so "does our row match cjkvi-ids" is nearly always true by
construction and would not be a useful check. What can still be wrong is the
same thing that was wrong for kanji: cjkvi-ids' OWN structure misread as a flat
parts list. So this script keeps only the two sections that check the source's
shape rather than cross-reference a second source:

- **not-a-parts-list** -- unchanged from audit_weak_evidence.py: a host (or an
  unresolved child of it) whose cjkvi-ids entry uses an overlay (shared-stroke)
  or enclosure operator, so its listed children are not the visible pieces.
- **opaque-intermediate** -- cjkvi-ids stops at a child with no row in this
  database, so nothing beneath it is structurally verifiable. For rtk* rows
  this is only reported when it explains an existing phantom-parts finding
  (which needs the Heisig CSV to compute); hanzi has no such finding to key
  off, so here it is reported directly for any host whose own primary
  decomposition contains a term that opaque_children() would swallow.

No "heisig-atomic" section here -- there is no components column for hanzi to
be empty or not.

This is a report, like its sibling: it does not say a row is wrong, only what
kind of evidence it rests on. Render the flagged glyph inside its host (see
render_glyphs.py) before changing anything -- the project's standing rule,
restated in CLAUDE.md's "Verifying a primitive's real identity" section.

Usage:
    ./venv/bin/python3 audit_hanzi_weak_evidence.py               # both sections
    ./venv/bin/python3 audit_hanzi_weak_evidence.py --kind overlay
    ./venv/bin/python3 audit_hanzi_weak_evidence.py --host 蝿     # one character
    ./venv/bin/python3 audit_hanzi_weak_evidence.py --json out.json  # machine-readable, for build_hanzi_worklist.py
"""
import argparse
import json
import sys

import database
from audit_overflatten import IDS_OPS, _raw_ids
from audit_weak_evidence import OVERLAY_OPS, opaque_children


def own_decompositions(conn, kid):
    """[(label, [part terms]), ...] for this row's system decompositions."""
    out = {}
    for row in conn.execute(
        """SELECT d.id, d.label, p.part_term, p.position
             FROM decompositions d JOIN parts p ON p.decomposition_id = d.id
            WHERE d.kanji_id = ? AND d.owner_id = 1
            ORDER BY d.id, p.position""",
        (kid,),
    ):
        out.setdefault(row["id"], (row["label"], []))[1].append(row["part_term"])
    return list(out.values())


def hanzi_hosts(conn):
    return conn.execute(
        """SELECT k.id, k.character
             FROM kanji k
            WHERE k.owner_id = 1 AND k.script LIKE 'zh-%'
              AND k.character IS NOT NULL AND k.character NOT IN ('', '?', '??')
            ORDER BY k.id"""
    ).fetchall()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--kind", choices=("overlay", "opaque"), help="only one section")
    ap.add_argument("--host", help="only this character")
    ap.add_argument("--json", metavar="PATH", help="write machine-readable findings here too")
    args = ap.parse_args()

    conn = database.get_db()
    raw = _raw_ids()
    have_row = {
        row["character"] for row in conn.execute(
            "SELECT DISTINCT character FROM kanji WHERE owner_id = 1 "
            "AND character IS NOT NULL AND character NOT IN ('', '?', '??')"
        )
    }

    overlay_hits, opaque_hits = [], []
    for host in hanzi_hosts(conn):
        glyph = host["character"]
        if args.host and glyph != args.host:
            continue
        # import_hanzi.py labels its one system decomposition 'ids' (unlike
        # kanji's unlabelled primary), so take the first system row rather
        # than filtering on label is None.
        decompositions = own_decompositions(conn, host["id"])
        primary = decompositions[0][1] if decompositions else []
        if not primary:
            continue  # atomic row, nothing to check

        overlay_reading = None
        for body, tags in raw.get(glyph, ()):
            if body == glyph:
                continue
            if any(op in body for op in OVERLAY_OPS):
                overlay_reading = (body, tags)
                break
            inner = [c for c in body if c not in IDS_OPS and not c.isascii() and c not in have_row]
            deeper = next(
                ((c, b) for c in inner for b, _t in raw.get(c, ())
                 if b != c and any(op in b for op in OVERLAY_OPS)), None
            )
            if deeper:
                overlay_reading = (f"{body} via {deeper[0]}={deeper[1]}", tags)
                break
        if overlay_reading:
            overlay_hits.append((host["id"], glyph, overlay_reading[0], overlay_reading[1], primary))
            continue  # don't double-report a row under both sections

        opaque = opaque_children(raw, glyph, have_row)
        # Only worth reporting when one of our own parts is actually inside the
        # opaque region -- otherwise the row's evidence doesn't depend on it.
        if opaque and (set(primary) & opaque or not (set(primary) - opaque - {glyph})):
            relevant = opaque & (set(primary) or opaque)
            if relevant:
                opaque_hits.append((host["id"], glyph, "".join(sorted(relevant)), primary))

    if args.kind != "opaque":
        print("-- not-a-parts-list: the host's cjkvi-ids entry (or an unresolved "
              "child's) uses an overlay or enclosure operator, so its children "
              "are not the visible pieces --")
        for kid, glyph, body, tags, primary in overlay_hits:
            print(f"  {glyph} {kid:14} cjkvi {body}{('[' + tags + ']') if tags else '':10} "
                  f"we read {','.join(primary)}")
        print(f"  {len(overlay_hits)} row(s)\n")

    if args.kind != "overlay":
        print("-- opaque-intermediate: cjkvi-ids stops at a child with no row "
              "here, so nothing inside it is structurally verifiable --")
        for kid, glyph, opaque, primary in opaque_hits:
            print(f"  {glyph} {kid:14} cjkvi stops at {opaque:6} we read {','.join(primary)}")
        print(f"  {len(opaque_hits)} row(s)")

    if args.json:
        payload = {
            "overlay": [
                {"id": kid, "char": glyph, "cjkvi": body, "tags": tags, "our_parts": primary}
                for kid, glyph, body, tags, primary in overlay_hits
            ],
            "opaque": [
                {"id": kid, "char": glyph, "opaque": opaque, "our_parts": primary}
                for kid, glyph, opaque, primary in opaque_hits
            ],
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print(f"\nwrote {args.json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
