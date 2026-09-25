#!/home/user/kanji/backend/venv/bin/python3
"""
audit_weak_evidence.py — rows where the evidence behind a decomposition is
weaker than it looks, so a fix based on it needs a render before it is trusted.

## Why this exists

Written 2026-09-25, after the owner caught three bad fixes out of the eight in
that morning's chunk 79. Three separate mistakes, none of them careless reading
of the data — each was a *category* error about what a source says:

1. **冊** was split into 冂 + 廾, then argued over (廾 or 卄?), when
   `heisig-kanjis.csv`'s row for frame 1967 is **empty**: Heisig names no
   components because he teaches the character whole, and then uses it whole in
   柵 ("tree; wood; tome"). An empty components column is not "no evidence", it
   is positive evidence of atomicity, and it was read as the former.
2. **蝿** was rewritten from 虫,田,亀 to 虫,日,电 on cjkvi's `⿰虫⿻日电`. **⿻ is
   an overlay operator**: it says two shapes *share strokes*, not that the
   visible top box is a 日. Rendered, that box is plainly divided by a vertical
   — a 田, which the original row had right. An IDS was read as a parts list.
3. **祢** was changed from 𠂉 to 𠂊 on cjkvi's `⿰礻尔` plus a render — of the
   standalone codepoint 尔 rather than of the component inside 祢. Its siblings
   称 and 弥, which this file spells with 𠂉, say the same shape; cjkvi itself
   spells them `⿰禾尓`/`⿰弓尓`, contradicting its own 祢 entry.

This script mechanises the first two. The third is a rule, not a check:
**render the component inside its host, beside a sibling host of the same
shape** — a render of the lone codepoint is a Unicode table with extra steps.

## What it reports

**`heisig-atomic`** (128 rows) — this file decomposes a row whose CSV components column is
empty *and* whose character is used as a named whole somewhere else in the CSV.
Heisig teaches these whole. Splitting them is not automatically wrong (cjkvi may
have real structure, and it can live in the labelled alternate) but the primary
should be his reading, which is no reading.

**`not-a-parts-list`** (177 rows) — the host's cjkvi entry, or that of a child
it has no row for, uses ⿻ or ⿴. ⿻ overlays two shapes so they share strokes;
⿴ encloses one in another so the inner can be partly drawn by the outer's
lines. Either way the children are not the visible pieces, and the structural
channel should be read the way `audit_phantom_parts.py` already reads a circled
placeholder: present, but not speaking clearly.

Two narrowings earned by running it. The other enclosure-ish operators behave
(⿺辶秀 really is 辶 plus 秀), and including them gave 441 rows of road radical.
And recursion only goes into children with **no row here** — 艹 is ⿻十丨 and 大
is ⿻一人, so descending into settled shapes flagged every kanji containing
either and gave 619. The readings that actually go wrong are the unnamed
intermediates (𣶒, 𠂡, 疌), which is exactly the set with no row. Both of the
2026-09-25 failures, 蝿 and 淵, are in the 177.

Reports only, like its siblings, and **it does not say a row is wrong** — it
says what kind of evidence a row rests on. Neither list is a queue to burn
down; both are meant to be consulted with `--host` before changing a row, which
is the moment the three mistakes above were made. A row already carrying an
empty primary (its structure parked in the labelled alternate, the way 冊 is
now) is not reported at all.

Usage:
    ./venv/bin/python3 audit_weak_evidence.py               # both sections
    ./venv/bin/python3 audit_weak_evidence.py --kind atomic
    ./venv/bin/python3 audit_weak_evidence.py --host 蝿     # one character
"""
import argparse
import csv
import sys

import database
from audit_phantom_parts import CSV_PATH, part_identities
from audit_overflatten import IDS_OPS, _raw_ids

# The IDS operators whose children are not a flat list of the visible pieces.
# Only these two: ⿻ overlays two shapes so they SHARE strokes, and ⿴ encloses
# one in another so the inner can be partly drawn by the outer's lines. The
# other enclosure-ish operators (⿵ ⿶ ⿷ ⿸ ⿹ ⿺) behave: ⿺辶秀 really is 辶 plus
# 秀 side by side, and including them buried the signal under 441 rows of road
# radical. ⿰ ⿱ ⿲ ⿳ lay pieces out in a row or column, which is what a parts
# field means, and are not reported at all.
OVERLAY_OPS = "⿻⿴"


def heisig_columns(path=CSV_PATH):
    """(glyphs whose own components column is empty, names the CSV ever emits)."""
    empty, named = set(), set()
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            glyph = (row.get("kanji") or "").strip()
            names = {n.strip().lower() for n in (row.get("components") or "").split(";") if n.strip()}
            named |= names
            if glyph and not names:
                empty.add(glyph)
    return empty, named


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


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--kind", choices=("atomic", "overlay"),
                    help="only one of the two sections")
    ap.add_argument("--host", help="only this character")
    args = ap.parse_args()

    conn = database.get_db()
    identities = part_identities(conn)
    empty_rows, csv_names = heisig_columns()
    raw = _raw_ids()

    have_row = {g for g, _n in identities.values() if g and g not in ("", "?", "??")}
    atomic_hits, overlay_hits = [], []
    for kid, (glyph, names) in sorted(identities.items()):
        if not glyph or glyph in ("", "?", "??"):
            continue
        if args.host and glyph != args.host:
            continue
        decompositions = own_decompositions(conn, kid)
        primary = next((terms for label, terms in decompositions if label is None), [])
        if not primary:
            continue  # already atomic, or already carrying only an alternate

        if glyph in empty_rows and (names & csv_names):
            atomic_hits.append((kid, glyph, identities[kid][1], primary))

        # One level down as well: 淵 is ⿰氵𣶒, which is well behaved, but 𣶒
        # itself is ⿴⿰片爿一 and that is where the reading goes wrong. A host
        # whose *child* is an overlay is resting on the same weak evidence.
        for body, tags in raw.get(glyph, ()):
            if body == glyph:
                continue
            reading = body
            if not any(op in body for op in OVERLAY_OPS):
                # Only into children this file has no row for. 艹 is ⿻十丨 and
                # 大 is ⿻一人, so recursing into settled shapes flags every
                # kanji containing either and buries the signal. The readings
                # that go wrong are the unnamed intermediates -- 𣶒, 𠂡, 疌 --
                # which is exactly the set with no row here.
                inner = [c for c in body
                         if c not in IDS_OPS and not c.isascii() and c not in have_row]
                deeper = next(
                    ((c, b) for c in inner for b, _t in raw.get(c, ())
                     if b != c and any(op in b for op in OVERLAY_OPS)), None)
                if not deeper:
                    continue
                reading = f"{body} via {deeper[0]}={deeper[1]}"
            overlay_hits.append((kid, glyph, reading, tags, primary))
            break

    if args.kind != "overlay":
        print("-- heisig-atomic: his components column is empty and he uses the "
              "character as a named whole elsewhere --")
        for kid, glyph, names, primary in atomic_hits:
            heisig_name = sorted(names & csv_names)
            print(f"  {glyph} {kid:12} we split it {','.join(primary):28} "
                  f"he calls it {'/'.join(heisig_name[:3])}")
        print(f"  {len(atomic_hits)} row(s)\n")

    if args.kind != "atomic":
        print("-- not-a-parts-list: the host's cjkvi entry uses an overlay or "
              "enclosure operator, so its children are not the visible pieces --")
        for kid, glyph, body, tags, primary in overlay_hits:
            print(f"  {glyph} {kid:12} cjkvi {body}{('[' + tags + ']') if tags else '':10} "
                  f"we read {','.join(primary)}")
        print(f"  {len(overlay_hits)} row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
