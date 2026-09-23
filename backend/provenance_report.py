#!/home/user/kanji/backend/venv/bin/python3
"""
provenance_report.py — which parts of this database came from where.

## Why this exists

The database is a merge of several sources with very different standing. Most of
it is open data under known licences (kanjidic2, KRADFILE, Unihan, cjkvi-ids).
Some of it is this project's own work (the `prim-*` descriptive names, the
decomposition corrections of the 2026-08/09 audit, the Russian aliases). And
some of it is Heisig's — the keyword for each RTK frame, and the primitive names
his components column emits — which is the copyrighted part of *Remembering the
Kanji*, an in-print commercial book.

That last set was never separated from the rest, so nobody could say how large
it is or remove it without removing everything. This script answers both:

* a count per category, so the size of the Heisig-derived set is a number rather
  than an impression;
* `--list-heisig`, an exact list of the rows and alias strings that would have
  to go if the project ever had to take them down, so that is one scripted edit
  and not an archaeology project.

## What it cannot do

Tell you whether a name is *only* Heisig's. "one", "mouth" and "tree" are his
keywords and also the ordinary English glosses any dictionary gives; using them
is not borrowing from him. A first draft of this script guessed at that line
with a heuristic (punctuation, word count) and got "teepee", "wigwam" and
"spiderman" wrong in the safe direction, which is the worst direction for a
number meant to size a risk. So it does not guess.

What it splits instead is a distinction the source itself makes: a **frame
keyword** (the gloss for a whole kanji, usually an ordinary English word) versus
a **primitive name** (what the `components` column calls a building block).
Heisig's invention is concentrated in the second — that is where "st. bernard",
"fred astaire", "radio caroline" and "musashimaru" live — and it is also the
column this app's parts search is built on. See `docs/DATA_SOURCES.md`.

Reads the live `kanji.db` and reports only, same convention as the `audit_*.py`
scripts.

Usage:
    ./venv/bin/python3 provenance_report.py                # the counts
    ./venv/bin/python3 provenance_report.py --list-heisig  # the takedown list
"""
import argparse
import collections
import csv
import os
import sys

import database

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heisig-kanjis.csv")

def heisig_strings(path=CSV_PATH):
    """(keywords by frame, every name the components column emits)."""
    keywords, components = {}, set()
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            frame = (row.get("id_6th_ed") or "").strip()
            names = {
                n.strip().lower()
                for n in (row.get("components") or "").split(";")
                if n.strip()
            }
            components |= names
            if frame.isdigit():
                keywords[f"rtk{frame}"] = {
                    (row.get(col) or "").strip().lower()
                    for col in ("keyword_6th_ed", "keyword_5th_ed")
                    if (row.get(col) or "").strip()
                }
    return keywords, components


def classify(conn, keywords, components):
    """(category -> count, category -> sample, heisig rows -> the strings)."""
    counts = collections.Counter()
    samples = collections.defaultdict(list)
    takedown = collections.defaultdict(set)

    rows = conn.execute(
        "SELECT id, character, keyword, frame, script FROM kanji WHERE owner_id = 1"
    ).fetchall()
    by_id = {r["id"]: r for r in rows}

    aliases = conn.execute(
        "SELECT a.kanji_id, a.alias, u.username"
        "  FROM aliases a JOIN users u ON u.id = a.owner_id"
    ).fetchall()

    for row in aliases:
        kid, name = row["kanji_id"], (row["alias"] or "").strip().lower()
        entry = by_id.get(kid)
        if not entry or not name:
            continue
        if row["username"] == "ru-aliases":
            category = "project-russian"
        elif name == (entry["character"] or "").lower() or name == kid.lower():
            category = "mechanical"
        elif entry["frame"] and name == str(entry["frame"]):
            category = "mechanical"
        elif name in components:
            # The building-block names — where his invention is concentrated,
            # and what this app's parts search runs on.
            category = "heisig-primitive-name"
            takedown[kid].add(name)
        elif name in keywords.get(kid, ()):
            category = "heisig-frame-keyword"
            takedown[kid].add(name)
        else:
            category = "project-or-open-data"
        counts[category] += 1
        if len(samples[category]) < 6:
            samples[category].append(f"{entry['character'] or '?'} {name}")

    row_counts = collections.Counter()
    for entry in rows:
        if entry["script"] and entry["script"].startswith("zh"):
            row_counts["hanzi rows (Unihan + cjkvi-ids)"] += 1
        elif entry["id"].startswith("rtk"):
            row_counts["rtk rows (frame numbers from the book)"] += 1
        elif entry["id"].startswith("kangxi"):
            row_counts["kangxi rows (Unicode CJKRadicals.txt)"] += 1
        else:
            row_counts["prim-* rows (named by this project)"] += 1

    return counts, samples, takedown, row_counts


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--list-heisig", action="store_true",
                    help="print every row id and the Heisig-derived strings on it")
    args = ap.parse_args()

    conn = database.get_db()
    keywords, components = heisig_strings()
    counts, samples, takedown, row_counts = classify(conn, keywords, components)

    print("-- rows, by where the row itself comes from --")
    for label, n in row_counts.most_common():
        print(f"  {n:6}  {label}")

    print("\n-- names (keywords + aliases), by source --")
    total = sum(counts.values())
    for category, n in counts.most_common():
        print(f"  {n:6}  {category:22} {' · '.join(samples[category])}")
    print(f"  {total:6}  total")

    heisig = counts["heisig-primitive-name"] + counts["heisig-frame-keyword"]
    print(f"\n{heisig} name(s) on {len(takedown)} row(s) come from Heisig's own "
          f"columns: {counts['heisig-primitive-name']} building-block names and "
          f"{counts['heisig-frame-keyword']} frame keywords.")
    print("Many of both are also the ordinary English word for the thing; this "
          "script does not guess which, see the docstring.")

    if args.list_heisig:
        print("\n-- the takedown list --")
        for kid in sorted(takedown):
            print(f"  {kid:12} {', '.join(sorted(takedown[kid]))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
