#!/home/user/kanji/backend/venv/bin/python3
"""
suggest_heisig_aliases.py — find Heisig's own primitive names that this
database cannot be searched by, and work out which row each one belongs on.

## Why

heisig-kanjis.csv's `components` column is written in Heisig's vocabulary, and
that vocabulary is what a reader of the book actually types into the search box.
299 of its 1156 distinct names resolved to nothing here (2026-09-13): 木 is
registered as "tree" but the book also calls it "wood" (169 rows), 月 as "moon"
but also "part of the body" (105), 艹 as "flowers" (95). Every one of those is a
search that silently returns nothing for someone reading along with the book.

Most are a missing *alias* on a row that already exists. Some are a primitive
this project never registered at all — 龶 "grow up", named in 36 CSV rows, was
one — and those are worth more than an alias: they are a missing entry.

## How a name is matched to a row

The components column is a recursive expansion, and when Heisig has several
names for one primitive the expansion emits *all* of them, every time: 月 always
comes out as "moon; month; flesh; part of the body". So two names for the same
shape have the **same host set**, exactly — not merely a similar one.

Grouping the names by host set is therefore the whole algorithm, and it checks
itself: of the 130 groups it finds, most already contain two or more names this
database *can* resolve, and those agree on the row essentially every time
("moon" and "flesh" both land on rtk13; "pinnacle", "acropolis" and "parthenon"
all on kangxi170). A group's already-registered members vouch for where its
unregistered ones belong.

Three outcomes, and the script separates them because they need different work:

- **matched** — the group has resolvable members, they all agree on one row, and
  the unresolvable names in it belong on that row as aliases.
- **ambiguous** — the group's resolvable members disagree. Reported, never
  guessed at. These are worth reading: "oyster" resolving to 蛎 and "clam" to 蠣
  when both are 貝's names in the book is a real mis-attribution, not a tie.
- **unregistered** — no member resolves at all, so there is no row to alias onto
  and the primitive itself is missing ("wheat"/"cereal", "hanko"/"chop-seal").

An earlier version of this script intersected our own decomposition trees over a
name's hosts instead. It is kept out of the history deliberately: the approach
needed three separate guards to suppress degenerate matches (it "proved" jewel
meant 一, because 一 is inside almost everything), it depended on this project's
own decompositions being right — the very thing under audit — and it still
missed "wood" because 3 of 166 hosts happened to lack 木 in our tree. Host-set
identity needs no guard beyond a minimum size and leans only on the CSV.

Nothing here writes to data.txt. It prints what it found; applying it is a
separate, deliberate edit.

Usage:
    ./venv/bin/python3 suggest_heisig_aliases.py           # matched names
    ./venv/bin/python3 suggest_heisig_aliases.py --all     # + ambiguous, unregistered
    ./venv/bin/python3 suggest_heisig_aliases.py --min-hosts 5
"""
import argparse
import collections
import csv
import os
import sys

import database
from audit_phantom_parts import accounted_glyphs, all_variant_ids, normalise

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heisig-kanjis.csv")
# Two names sharing a single host is a coincidence; sharing three host sets
# exactly is not. Low enough to keep real but rare primitives, high enough that
# noise does not survive.
MIN_HOSTS = 3
# A shape has to be in this fraction of a name's hosts to be proposed as its row.
PRESENCE = 0.9


def csv_rows(path=CSV_PATH):
    """(kanji glyph, [component names]) for every CSV row that lists components."""
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            names = [n.strip().lower() for n in row["components"].split(";") if n.strip()]
            if row["kanji"] and names:
                yield row["kanji"], names


def name_groups(min_hosts=MIN_HOSTS, path=CSV_PATH):
    """[(host set, [names emitted on exactly those hosts])], largest first."""
    hosts = collections.defaultdict(set)
    for char, names in csv_rows(path):
        for name in set(names):
            hosts[name].add(char)
    groups = collections.defaultdict(list)
    for name, host_set in hosts.items():
        if len(host_set) >= min_hosts:
            groups[frozenset(host_set)].append(name)
    return sorted(groups.items(), key=lambda kv: -len(kv[0]))


def structural_support(ids, kid_char, hosts):
    """Fraction of the group's hosts that actually contain the proposed row's glyph.

    The vouching is only as good as the vouching name, and a name can resolve to
    the wrong row: this database aliases "knot" onto 浬 (a nautical knot), which
    has nothing to do with the 厶-shaped knot Heisig means, so 浬 ends up
    vouching for "piglet's tail". cjkvi-ids has no stake in either and settles
    it — if the row's glyph is not in the hosts, the vouch is worthless.
    """
    if not kid_char or kid_char in ("?", "??"):
        return None
    hit = 0
    for host in hosts:
        if normalise(kid_char) in accounted_glyphs(ids, {}, host):
            hit += 1
    return hit / len(hosts) if hosts else 0.0


def structural_candidates(ids, by_char, hosts, breadth):
    """Registered rows whose glyph every host contains, rarest shape first.

    Used when the vouching row fails its structural check: the hosts still have
    something in common, and naming it is usually the actual answer. "church"
    and "gravestone" arrive vouched by "tombstone" -> 碑, which is in none of
    個古固嫡居据摘故敵枯; what all ten do contain is 古, which is the primitive
    Heisig means.

    A host stays a candidate for its own group — 古 is both a host here and the
    answer — so the intersection keeps them. Ranking is by how many kanji in the
    corpus contain the shape at all, rarest first, which floats 古 above the 口
    and 十 that any set of kanji has in common.

    Near-universal rather than universal, because a strict intersection is
    brittle in exactly the wrong place: 163 of "wood"'s 166 hosts contain 木 and
    the three that do not are cjkvi-ids spelling quirks, so requiring all 166
    returned nothing at all for the single largest missing name.
    """
    trees = [accounted_glyphs(ids, {}, host) for host in hosts]
    if not trees:
        return []
    seen = collections.Counter()
    for tree in trees:
        seen.update(tree)
    cutoff = max(1, int(len(trees) * PRESENCE))
    scored = [
        (glyph, by_char[glyph], n / len(trees))
        for glyph, n in seen.items()
        if n >= cutoff and glyph in by_char
    ]
    scored.sort(key=lambda row: breadth.get(row[0], 0))
    return scored[:4]


def corpus_breadth(ids, chars):
    """glyph -> how many of chars contain it, for ranking a shape's specificity."""
    counts = collections.Counter()
    for ch in chars:
        counts.update(accounted_glyphs(ids, {}, ch))
    return counts


def classify(conn, groups):
    matched, ambiguous, unregistered = [], [], []
    for host_set, names in groups:
        resolved = {n: database.resolve_alias(conn, n) for n in names}
        known = {r for r in resolved.values() if r is not None}
        missing = sorted(n for n, r in resolved.items() if r is None)
        if not missing:
            continue  # every name in this group is already searchable
        if not known:
            unregistered.append((sorted(names), len(host_set), sorted(host_set)))
        elif len(known) == 1:
            matched.append((missing, known.pop(), sorted(resolved.items()), sorted(host_set)))
        else:
            ambiguous.append((sorted(resolved.items()), len(host_set)))
    return matched, ambiguous, unregistered


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--all", action="store_true", help="also show ambiguous and unregistered groups")
    ap.add_argument("--min-hosts", type=int, default=MIN_HOSTS)
    args = ap.parse_args()

    conn = database.get_db()
    labels = {
        row["id"]: f"{row['character'] or '-'} ({row['keyword']})"
        for row in conn.execute("SELECT id, character, keyword FROM kanji WHERE owner_id = 1")
    }
    matched, ambiguous, unregistered = classify(conn, name_groups(args.min_hosts))
    ids = all_variant_ids()
    char_of = {
        row["id"]: row["character"]
        for row in conn.execute("SELECT id, character FROM kanji WHERE owner_id = 1")
    }
    by_char = {}
    for kid, char in char_of.items():
        if char and char not in ("?", "??"):
            by_char.setdefault(char, kid)
    breadth = corpus_breadth(ids, [c for c in by_char if c in ids])

    print(f"{len(matched)} group(s) where already-registered names vouch for the row:\n")
    for missing, kid, resolved, hosts in matched:
        vouch = ", ".join(n for n, r in resolved if r is not None)
        support = structural_support(ids, char_of.get(kid), hosts)
        flag = "" if support is None or support >= 0.9 else "   <-- CHECK"
        shown = "n/a" if support is None else f"{support:.2f}"
        print(f"  {kid:<22} {labels.get(kid, '?'):<28} {len(hosts):>4} hosts   cjkvi support {shown}{flag}")
        print(f"      add: {', '.join(missing)}")
        print(f"      vouched by: {vouch}   e.g. {''.join(hosts[:10])}")
        if flag:
            alt = structural_candidates(ids, by_char, hosts, breadth)
            if alt:
                shown_alt = ", ".join(f"{g} {labels.get(k, k)} {f:.2f}" for g, k, f in alt)
                print(f"      every host does contain: {shown_alt}")
    if args.all:
        print(f"\n{len(ambiguous)} ambiguous group(s) — registered members disagree:\n")
        for resolved, n_hosts in ambiguous:
            shown = ", ".join(f"{n}->{labels.get(r, r)}" for n, r in resolved)
            print(f"  {n_hosts:>4} hosts   {shown}")
        print(f"\n{len(unregistered)} group(s) where no name in the group resolves:\n")
        for names, n_hosts, hosts in unregistered:
            print(f"  {n_hosts:>4} hosts   {', '.join(names):<40} e.g. {''.join(hosts[:12])}")
            # No registered name to vouch, so structure is the only evidence
            # there is: either it names a row whose *other* names we have
            # (艹 is registered as "mugwort", never as "flowers"), or nothing
            # is common to the hosts and the primitive itself is missing.
            alt = structural_candidates(ids, by_char, hosts, breadth)
            if alt:
                shown = ", ".join(f"{g} {labels.get(k, k)} {f:.2f}" for g, k, f in alt)
                print(f"           every host contains: {shown}")
            else:
                print("           nothing common to every host — likely a missing row")
    return 0


if __name__ == "__main__":
    sys.exit(main())
