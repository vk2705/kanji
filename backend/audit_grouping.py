#!/home/user/kanji/backend/venv/bin/python3
"""
audit_grouping.py: neighbouring parts of a kanji that together *are* a kanji
Heisig has already taught, but are listed separately instead of by that name.

## The bug shape

Found 2026-11-07 on 鴻 "large goose", by the owner rather than by any detector:
the row was 工,水,鳥, which is accurate, since every piece is drawn and nothing is
missing. But the left two pieces, 氵 + 工 side by side, are exactly 江 "creek"
(frame 148), so "creek + bird" is the breakdown a Heisig learner can actually
use. No check caught it, because nothing was *wrong*: the full re-review asks
whether parts are present, absent or lookalikes, and its "right level" rule only
fires when Heisig's components column names the unit, which for frames past
the 1-2042 core it usually does not.

## How it finds them

Matching parts as a bag is useless here (tried first): 別's 口,力,刀 contain
every part of 召 without 別 containing 召. Position is what matters, so this works
on cjkvi-ids' layout tree instead:

1. Flatten each same-direction chain into one ordered run. ⿰ and ⿲ are left to
   right, ⿱ and ⿳ top to bottom; a child with its own same-direction IDS is
   spliced in. 鴻 = ⿰氵䲨 with 䲨 = ⿰工鳥 becomes the left-to-right run
   氵 | 工 | 鳥. That splicing is what sees past cjkvi's own grouping (it puts 工
   with the bird, not the water).
2. Each taught kanji gets the same treatment, indexed by (direction, run):
   江 = ⿰氵工 is ("lr", 氵, 工).
3. Every contiguous proper sub-run of a host's run that equals some taught
   kanji's run is a candidate: 氵 | 工 in 鴻 matches 江.

A candidate is reported only if the matching kanji is taught *before* the host
(a lower frame, so the learner already knows it) and the host's system
decompositions do not already name it.

## What it does not decide

Every finding still needs a human (or a review run) to look at the render and
decide whether the grouping is the useful one: sometimes the separate pieces
are what Heisig's story uses. Like the other audit_*.py scripts it never
writes to data.txt.

Usage:
    ./venv/bin/python3 audit_grouping.py                    # full report to stdout
    ./venv/bin/python3 audit_grouping.py --markdown FILE    # write the report file

Needs cjkvi-ids downloaded (`/tmp/ids.txt`, or set `CJKVI_IDS`).
"""
import argparse
import csv
import os
import sqlite3
import sys
from datetime import date

from audit_overflatten import RADICAL_VARIANTS, load_ids

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kanji.db")
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heisig-kanjis.csv")

BINARY = set("⿰⿱⿴⿵⿶⿷⿸⿹⿺⿻")
TERNARY = set("⿲⿳")
DIRECTION = {"⿰": "lr", "⿲": "lr", "⿱": "tb", "⿳": "tb"}
# How many pieces of a matched run must be parts our row already lists. 2 is
# precise but misses 克 = 十,兄, where the 口 of 古 is hidden inside 兄; 1 keeps
# it, at the price of a few stroke-level coincidences (美's 一大 = 天).
MIN_LISTED = 1
# cjkvi's circled numbers are per-entry placeholders, not identifiers (see
# audit_phantom_parts.py): ⑤ in 卿 is not the ⑤ of any other kanji.
PLACEHOLDERS = {chr(c) for c in range(0x2460, 0x2474)}


def parse(ids):
    """Prefix IDS string -> nested (op, [children]) tuples; leaves are chars."""
    pos = 0

    def node():
        nonlocal pos
        ch = ids[pos]
        pos += 1
        if ch in BINARY or ch in TERNARY:
            n = 3 if ch in TERNARY else 2
            return (ch, [node() for _ in range(n)])
        return ch

    try:
        tree = node()
    except IndexError:
        return None
    return tree if pos == len(ids) else None


def tree_of(ids, ch):
    entry = ids.get(ch)
    if not entry or entry == ch:
        return ch
    return parse(entry) or ch


def run_of(ids, node, direction, stop=frozenset(), _depth=0):
    """Flatten a node into its ordered run along `direction`, splicing in any
    child (or leaf with its own IDS) that runs the same way. Leaves in `stop`
    (the host's own listed parts) are never opened."""
    if _depth > 8:
        return [node]
    if isinstance(node, str):
        if node in stop:
            return [node]
        sub = tree_of(ids, node)
        if isinstance(sub, tuple) and DIRECTION.get(sub[0]) == direction:
            return run_of(ids, sub, direction, stop, _depth + 1)
        return [node]
    op, kids = node
    if DIRECTION.get(op) != direction:
        return [node]
    out = []
    for k in kids:
        out.extend(run_of(ids, k, direction, stop, _depth + 1))
    return out


def key(item):
    """Hashable, comparable form of a run element (leaf char or subtree)."""
    if isinstance(item, str):
        return item
    op, kids = item
    return op + "".join(key(k) for k in kids)


def chains(ids, node, stop=frozenset(), _depth=0):
    """Yield (direction, run) for every same-direction chain in the tree,
    expanding leaves through cjkvi so inner structure is visited too, except
    the host's own listed parts: a match wholly inside one of those (土 inside
    王) is not a regrouping of the host, so they stay closed."""
    if _depth > 8:
        return
    if isinstance(node, str):
        if node in stop:
            return
        sub = tree_of(ids, node)
        if isinstance(sub, tuple):
            yield from chains(ids, sub, stop, _depth + 1)
        return
    op, kids = node
    d = DIRECTION.get(op)
    if d:
        run = run_of(ids, node, d, stop)
        yield d, run
        for item in run:
            if not isinstance(item, str) or tree_of(ids, item) != item:
                yield from chains(ids, item, stop, _depth + 1)
    else:
        for k in kids:
            yield from chains(ids, k, stop, _depth + 1)


def load_rows(conn):
    """rtk kanji: id -> (frame, character, keyword, set of resolved part ids and
    terms across every system decomposition)."""
    rows = {}
    for r in conn.execute(
        "SELECT id, character, keyword, frame FROM kanji "
        "WHERE id LIKE 'rtk%' AND owner_id = 1 AND frame IS NOT NULL"
    ):
        rows[r["id"]] = {"frame": r["frame"], "char": r["character"],
                         "keyword": r["keyword"], "terms": set(), "primary": []}
    for r in conn.execute(
        "SELECT d.kanji_id, d.id AS did, d.label, p.part_term, p.position FROM parts p "
        "JOIN decompositions d ON d.id = p.decomposition_id "
        "WHERE d.owner_id = 1 AND d.kanji_id LIKE 'rtk%' ORDER BY d.id, p.position"
    ):
        row = rows.get(r["kanji_id"])
        if row is None:
            continue
        row["terms"].add(r["part_term"].strip().lower())
        if r["label"] is None:
            row.setdefault("primary_did", r["did"])
            if row["primary_did"] == r["did"]:
                row["primary"].append(r["part_term"])
    return rows


def find(ids, rows):
    by_char = {}
    index = {}
    for kid, row in rows.items():
        ch = row["char"]
        if not ch or ch in ("?", "??"):
            continue
        by_char.setdefault(ch, kid)
        tree = tree_of(ids, ch)
        if not isinstance(tree, tuple):
            continue
        d = DIRECTION.get(tree[0])
        if not d:
            continue
        run = tuple(key(x) for x in run_of(ids, tree, d))
        if len(run) >= 2:
            index.setdefault((d, run), []).append(kid)

    findings = {}
    for hid, host in rows.items():
        ch = host["char"]
        if not ch or ch in ("?", "??"):
            continue
        seen = set()
        stop = frozenset(t for t in host["terms"] if len(t) == 1 and t != ch)
        for d, run in chains(ids, tree_of(ids, ch), stop):
            keys = [key(x) for x in run]
            for i in range(len(keys)):
                for j in range(i + 2, len(keys) + 1):
                    if j - i == len(keys) and run is not None and i == 0:
                        continue  # the whole chain is the host itself
                    # A real regrouping joins pieces our row actually lists (鴻:
                    # 氵=水 and 工). A run built from strokes inside one piece that
                    # cjkvi spells as a variant (土 in the 羊 top, 二 in 行) is not.
                    listed = sum(1 for x in keys[i:j]
                                 if RADICAL_VARIANTS.get(x, x) in host["terms"] or x in host["terms"])
                    if listed < MIN_LISTED or PLACEHOLDERS & set("".join(keys[i:j])):
                        continue
                    for kid in index.get((d, tuple(keys[i:j])), ()):
                        k = rows[kid]
                        if kid == hid or kid in seen or k["frame"] >= host["frame"]:
                            continue
                        names = {k["char"], (k["keyword"] or "").lower()}
                        if names & host["terms"]:
                            continue
                        seen.add(kid)
                        findings.setdefault(hid, []).append(
                            (kid, "".join(keys[i:j]), d))
    return findings


def heisig_components(path=CSV_PATH):
    """character -> set of names in heisig-kanjis.csv's components column."""
    out = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            names = {n.strip().lower() for n in (r.get("components") or "").split(";")}
            out[r["kanji"]] = names - {""}
    return out


def split_by_heisig(rows, findings, heisig):
    """Drop suggestions Heisig's own components column contradicts: when he
    names a host's pieces and the suggested kanji is not among them, he chose a
    different grouping on purpose (克 is "ten; elder brother", not 古 "old").
    Only an empty column (no data, or a kanji taught whole) leaves it open."""
    kept, contradicted = {}, 0
    for h, items in findings.items():
        names = heisig.get(rows[h]["char"], set())
        for kid, shape, d in items:
            k = rows[kid]
            if names and (k["keyword"] or "").lower() not in names:
                contradicted += 1
                continue
            kept.setdefault(h, []).append((kid, shape, d))
    return kept, contradicted


def report_lines(rows, findings, today, contradicted=0):
    hosts = sorted(findings, key=lambda h: -rows[h]["frame"])
    out = [
        "# Grouping recommendations",
        "",
        f"Generated by `backend/audit_grouping.py` on {today}; regenerate, don't edit.",
        "",
        "Each row is a kanji whose neighbouring pieces, side by side (`lr`) or",
        "stacked (`tb`), form a kanji Heisig teaches **earlier**, while our",
        "decomposition lists those pieces separately instead of by that name.",
        "Example that started this: 鴻 was `工,水,鳥`; 氵+工 is 江 \"creek\" (frame 148),",
        "so it became `江,鳥`. These are candidates, not fixes: check the render and",
        "whether the named unit is the useful grouping before changing `data.txt`.",
        "Ordered from frame 3000 down. Suggestions that Heisig's own components",
        "column contradicts (he names the pieces and not this kanji) are left out.",
        "",
        f"**{len(hosts)} kanji, {sum(len(v) for v in findings.values())} suggestions** "
        f"({contradicted} more dropped as contradicted by Heisig).",
        "",
        "| Kanji | Frame | Current parts | Could name | As | Taught at |",
        "|---|---|---|---|---|---|",
    ]
    for h in hosts:
        host = rows[h]
        glyphs = [t for t in host["primary"] if not t.isascii()]
        parts = ",".join(glyphs or host["primary"])
        for kid, shape, d in findings[h]:
            k = rows[kid]
            out.append(
                f"| {host['char']} {host['keyword']} | {host['frame']} | `{parts}` | "
                f"{k['char']} {k['keyword']} | {shape} ({d}) | {k['frame']} |")
    out.append("")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--markdown", help="write the report to this file")
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()
    if not os.path.exists(os.environ.get("CJKVI_IDS", "/tmp/ids.txt")):
        sys.exit("cjkvi-ids not found: download it to /tmp/ids.txt or set CJKVI_IDS")
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    ids = load_ids()
    rows = load_rows(conn)
    findings, contradicted = split_by_heisig(rows, find(ids, rows), heisig_components())
    lines = report_lines(rows, findings, date.today().isoformat(), contradicted)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print(f"{len(findings)} kanji written to {args.markdown}")
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
