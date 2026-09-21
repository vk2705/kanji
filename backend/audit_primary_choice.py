#!/home/user/kanji/backend/venv/bin/python3
"""
audit_primary_choice.py — find kanji whose *primary* decomposition is worse than
one of their own alternatives.

## The bug shape

A `data.txt` line can carry several decompositions separated by `;`. The first is
the primary: it is the unlabelled one, it is what `KanjiDetail` shows first, and
it is what a reader takes to be this project's answer. The rest are labelled
alternatives (`structural (cjkvi-ids)`).

When the structural alternatives were added in bulk on 2026-09-13, nothing
checked whether the primary they were added *next to* was any good. Often it was
not, and the right answer had just been parked in the second slot:

    左  ノ,一,工;工,𠂇      heisig-kanjis.csv: "by one's side; craft"
    右  ノ,一,口;口,𠂇      heisig-kanjis.csv: "by one's side; mouth"
    乞  ノ,一,乙,人;乙,𠂉    heisig-kanjis.csv: "reclining; lying down; fishhook"

In each of those the primary spells a component out in strokes, the alternative
names the component Heisig actually teaches, and the reader is shown the strokes.
It is also the remaining source of this project's oldest complaint — searching a
stroke primitive like ノ or 一 returns hundreds of kanji, because every host that
shattered a component into letters matches every letter.

## How a decomposition is scored

Two numbers per chunk, both from sources outside this project:

* **unaccounted** — parts that `audit_phantom_parts`' two-channel test cannot
  explain: not reachable in cjkvi-ids' expansion of the host, and not named in
  its `components` column either. Lower is better.
* **covered** — how many of the host's CSV component names the chunk's parts
  answer to. Higher is better.

A chunk only displaces the primary when it is **no worse on both** and strictly
better on one. That asymmetry is deliberate. An earlier version ranked by
`covered` alone and wanted to promote 黙's `灬,犬,里` over its `犬,黒` — but 黒 *is*
里+灬, so the flatter chunk scored higher precisely by being flatter, and taking
that advice would have made the thing this script exists to fix worse. Counting
unaccounted parts alongside coverage is what stops that: flattening a compound
does not reduce unaccounted parts, so it cannot win on its own.

## Above frame 2,200 (`--past-csv`, added 2026-09-21)

`heisig-kanjis.csv` stops at the 6th edition's ~2,200 frames, so for anything
past that there is no `components` column and the coverage half of the score has
nothing to say. That is why this script skipped those rows entirely — and it
meant the one bug shape it exists for went unexamined in ~800 kanji, where
chunks 31-34 kept finding it by hand (毬 燎 炬 雀 夷 肴 擢 燿 繍 犀 煉 …, every
one a stroke-soup primary sitting in front of a labelled alternate that was
already right).

`--past-csv` runs those hosts on the **structural half alone**: a chunk
displaces the primary only if it leaves strictly fewer parts unaccounted for.
That is a weaker rule and deliberately so — with no coverage term it cannot tell
two equally-accounted readings apart, so it proposes nothing in that case rather
than guessing. Every proposal still wants reading, and `--emit` still only
prints; nothing here writes.

Reports only. Swapping a primary changes what every reader sees for that kanji,
and the pairs still want reading one by one.

Usage:
    ./venv/bin/python3 audit_primary_choice.py             # proposed swaps
    ./venv/bin/python3 audit_primary_choice.py --all       # every multi-chunk kanji
    ./venv/bin/python3 audit_primary_choice.py --past-csv  # the same, above frame 2,200
"""
import argparse
import os
import sys

import database
from audit_phantom_parts import (
    all_variant_ids,
    accounted_glyphs,
    claimants,
    csv_components,
    flat_parts,
    normalise,
    own_parts,
    part_identities,
    _spelled_out,
)

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.txt")


def multi_chunk_lines(path=DATA_PATH):
    """(id, character, [[part, ...], ...]) for every rtk line with a ';'."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.rstrip("\n")
            if not stripped.strip() or stripped.lstrip().startswith("#"):
                continue
            fields = stripped.split(":")
            if len(fields) < 4 or not fields[0].startswith("rtk") or ";" not in fields[3]:
                continue
            chunks = [[p.strip() for p in c.split(",") if p.strip()]
                      for c in fields[3].split(";")]
            if len(fields[1]) == 1 and len([c for c in chunks if c]) > 1:
                out.append((fields[0], fields[1], chunks))
    return out


def deep_names(conn, kid, identities, _cache=None, _chain=frozenset()):
    """Every name reachable from a kanji id through our own decompositions.

    Coverage has to be recursive or it rewards flattening, which is the opposite
    of the point. heisig-kanjis.csv's components column is itself a *recursive*
    expansion, so 黙 lists dog, black, computer and barbecue all at once; a chunk
    that says 犬,黒 then looks like it covers half of what 灬,犬,里 covers, even
    though 黒 simply *is* 里+灬 and the reader can open it. Crediting a part with
    what it contains puts the two level, and the flatter one stops winning.
    """
    if _cache is None:
        _cache = deep_names.cache
    if kid in _cache:
        return _cache[kid]
    if kid in _chain:
        return set()
    names = set(identities.get(kid, [None, set()])[1])
    rows = conn.execute(
        """SELECT p.part_term
             FROM parts p JOIN decompositions d ON d.id = p.decomposition_id
            WHERE d.kanji_id = ? AND d.owner_id = 1""",
        (kid,),
    ).fetchall()
    for row in rows:
        child = database.resolve_alias(conn, row["part_term"])
        if child and child != kid:
            names |= deep_names(conn, child, identities, _cache, _chain | {kid})
    if not _chain:
        _cache[kid] = names
    return names


deep_names.cache = {}


def score(conn, parts, tree, heisig_names, identities, claims, ours):
    """(unaccounted, covered) for one decomposition of one host."""
    unaccounted, covered = 0, set()
    for part in parts:
        resolved = database.resolve_alias(conn, part)
        candidates = claims.get(part.strip().lower(), set())
        if resolved:
            candidates.add(resolved)
        if not candidates:
            continue
        own, deep = set(), set()
        structural = False
        for cand in candidates:
            char, cand_names = identities.get(cand, [None, set()])
            own |= cand_names
            deep |= deep_names(conn, cand, identities)
            if char and (normalise(char) in tree or _spelled_out(ours, char, tree)):
                structural = True
        covered |= deep & heisig_names
        if not structural and not (own & heisig_names):
            unaccounted += 1
    return unaccounted, len(covered)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--all", action="store_true", help="show every multi-chunk kanji")
    ap.add_argument(
        "--past-csv",
        action="store_true",
        help="hosts heisig-kanjis.csv does not cover, scored on unaccounted parts "
             "alone (no components column means no coverage term) -- see the docstring",
    )
    ap.add_argument(
        "--emit",
        action="store_true",
        help="print the corrected data.txt parts field for each proposal, one per "
             "line as 'id\\tparts'. A primary carrying unaccounted parts is "
             "REPLACED (the flattened chunk goes away, which is what actually "
             "takes it out of search); a clean primary is only REORDERED behind "
             "the better chunk, since both readings are legitimate.",
    )
    args = ap.parse_args()

    conn = database.get_db()
    ids = all_variant_ids()
    heisig = csv_components()
    identities = part_identities(conn)
    claims = claimants(identities)
    ours = own_parts(conn, identities, claims)
    closure = flat_parts(ours)

    proposals, examined = [], 0
    for kid, char, chunks in multi_chunk_lines():
        names = heisig.get(char)
        if args.past_csv:
            if names or char not in ids:
                continue
            names = set()
        elif not names or char not in ids:
            continue
        examined += 1
        tree = accounted_glyphs(ids, closure, char)
        scored = [score(conn, c, tree, names, identities, claims, ours) for c in chunks]
        primary = scored[0]
        best_i, best = None, primary
        for i, s in enumerate(scored[1:], start=1):
            if args.past_csv:
                # No coverage term to weigh, so only a strict drop in unaccounted
                # parts counts. Ties are left alone rather than guessed at.
                no_worse, better = True, s[0] < best[0]
            else:
                no_worse = s[0] <= best[0] and s[1] >= best[1]
                better = s[0] < best[0] or s[1] > best[1]
            if no_worse and better:
                best_i, best = i, s
        if best_i is not None:
            proposals.append((kid, char, chunks, primary, best_i, best, sorted(names)))
        elif args.all:
            print(f"  {kid:<9} {char}  keeps its primary  {scored}")

    if args.emit:
        for kid, _char, chunks, primary, i, _best, _names in proposals:
            rest = [c for n, c in enumerate(chunks) if n != i and (primary[0] == 0 or n != 0)]
            ordered = [chunks[i]] + [c for c in rest if c]
            print(f"{kid}\t" + ";".join(",".join(c) for c in ordered))
        return 0

    print(f"{len(proposals)} of {examined} multi-chunk kanji have a better alternative:\n")
    replaced = sum(1 for p in proposals if p[3][0] > 0)
    for kid, char, chunks, primary, i, best, names in proposals:
        verb = "REPLACE" if primary[0] > 0 else "reorder"
        print(f"  {kid:<9} {char}  {verb}  primary {','.join(chunks[0])}   "
              f"(unaccounted {primary[0]}, covered {primary[1]})")
        print(f"  {'':<9}     -> #{i} {','.join(chunks[i])}   "
              f"(unaccounted {best[0]}, covered {best[1]})")
        if names:
            print(f"  {'':<9}     heisig: {'; '.join(names)}")
    print(f"\n{replaced} to replace (primary carries unaccounted parts), "
          f"{len(proposals) - replaced} to reorder only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
