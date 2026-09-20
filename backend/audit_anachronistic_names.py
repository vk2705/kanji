#!/home/user/kanji/backend/venv/bin/python3
"""
audit_anachronistic_names.py — a Heisig component name that resolves to a kanji
taught *after* the first kanji that uses it.

## The bug shape

Found 2026-09-20, twice in one day, by accident both times.

`heisig-kanjis.csv`'s components column for 走 (frame 410) reads "soil; dirt;
ground; mend". `resolve_alias("mend")` answered **綴, frame 2222** — a kanji
whose *keyword* happens to be "mend". Heisig introduces a primitive at or before
the frame that first needs it; he cannot be naming 走's bottom after a character
1,800 frames further on that the reader has not met. The resolution was a pure
keyword collision, and the primitive it should have named (龰) had no row here
at all.

The same day, "stick" — used in 62 component rows, the first of them 旧 at frame
35 — was found resolving to 貼 ("post a bill", frame 60), whose alias list
carried "stick" in the adhesive sense.

Both were invisible to every other check in this directory, because every other
check asks whether a name resolves, and both of these resolved. What neither
asked is whether the answer is *possible*.

## The test

For each name in the components column:

* collect its hosts and take the **lowest frame number** among them — the first
  kanji in the book that needs the primitive;
* collect every row that answers to the name (all claimants, not just
  `resolve_alias`'s canonical pick — a name shared between a primitive row and
  some frame's keyword is ordinary, and the primitive is the right answer);
* a claimant with no frame at all (a `prim-*` or `kangxi*` row) always clears
  the name, since a primitive is not taught at a frame;
* a claimant whose **glyph is actually in that first host** clears it too, and
  this half is not optional — see below;
* what is left is **anachronistic**: every row answering to the name is taught
  later than the first kanji that uses it, and none of them is in that kanji.

## Why the frame test alone is not enough

The first draft of this script used frame order by itself and immediately
accused 世 (frame 28) of an anachronism for naming "twenty", which resolves to
廿 at frame 1274. That accusation is wrong, and wrong in a way worth writing
down: **Heisig routinely teaches a shape as a primitive long before its own
kanji frame.** 廿 *is* 世's top, and "twenty" is exactly the right answer; the
1,246-frame gap means only that the kanji comes later than the primitive, which
is the normal arrangement in the book.

What distinguishes 廿 from 綴 is not the arithmetic but the glyph: 廿 is in 世
and 綴 is nowhere near 走. So the second test asks whether the claimant's
character is reachable in the first host — through cjkvi-ids, through this
project's own decompositions, and including the host's own row, which
`audit_phantom_parts.py` deliberately excludes. That exclusion is right there
(the decomposition is the thing under test) and wrong here (the decomposition is
evidence about what the glyph contains, and the *name* is what is under test).

## What it does not catch

A collision with an *earlier* frame. If some frame 100 kanji's keyword happened
to be "mend", this check would pass and the resolution would still be wrong.
That case needs the render, like everything else here. This tool only finds the
subset arithmetic can refute and the glyph cannot rescue — which is the subset
that has been slipping past the other tools.

Reports only, and prints the gap so the worst offenders sort to the top.

Usage:
    ./venv/bin/python3 audit_anachronistic_names.py           # findings
    ./venv/bin/python3 audit_anachronistic_names.py --all     # every named row
"""
import argparse
import csv
import sys

import database
from audit_phantom_parts import (
    CSV_PATH,
    accounted_glyphs,
    all_variant_ids,
    claimants,
    flat_parts,
    normalise,
    own_parts,
    part_identities,
)


def name_first_host(path=CSV_PATH):
    """name -> (lowest frame that uses it, that frame's glyph, how many hosts)."""
    table = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                frame = int(row["id_6th_ed"])
            except (TypeError, ValueError):
                continue
            for name in {n.strip().lower() for n in row["components"].split(";") if n.strip()}:
                best = table.get(name)
                if best is None or frame < best[0]:
                    table[name] = [frame, row["kanji"], 0]
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            for name in {n.strip().lower() for n in row["components"].split(";") if n.strip()}:
                if name in table:
                    table[name][2] += 1
    return {n: tuple(v) for n, v in table.items()}


def frames(conn):
    """kanji id -> frame number, for the rows that have one."""
    return {
        row["id"]: row["frame"]
        for row in conn.execute(
            "SELECT id, frame FROM kanji WHERE owner_id = 1 AND frame IS NOT NULL"
        )
    }


def in_host(ids, closure, host_char, glyph):
    """Is `glyph` anywhere in `host_char`, by any evidence this project has?

    Unlike audit_phantom_parts.accounted_glyphs, the host's *own* decomposition
    counts. There the decomposition is the claim under test; here the name is,
    and the decomposition is just evidence about what the glyph contains.
    """
    if not glyph:
        return False
    tree = accounted_glyphs(ids, closure, host_char)
    tree |= closure.get(host_char, set()) | closure.get(normalise(host_char), set())
    return normalise(glyph) in tree or glyph in tree


def findings(conn, identities, claims, frame_of, hosts, ids, closure):
    out = []
    for name, (first_frame, first_char, host_count) in hosts.items():
        candidates = set(claims.get(name, ()))
        resolved = database.resolve_alias(conn, name)
        if resolved:
            candidates.add(resolved)
        if not candidates:
            continue  # suggest_heisig_aliases.py owns the resolves-to-nothing class
        if any(c not in frame_of for c in candidates):
            continue  # a primitive row answers to it; primitives have no frame
        earliest = min(frame_of[c] for c in candidates)
        if earliest <= first_frame:
            continue
        if any(in_host(ids, closure, first_char, identities.get(c, [None])[0])
               for c in candidates):
            continue  # late frame, but the glyph really is in there — 廿 in 世
        pick = min(candidates, key=lambda c: frame_of[c])
        out.append((earliest - first_frame, name, host_count, first_frame, first_char,
                    pick, identities.get(pick, [None])[0], frame_of[pick]))
    out.sort(reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--all", action="store_true",
                    help="also list the names that pass, with what answers to them")
    args = ap.parse_args()

    conn = database.get_db()
    identities = part_identities(conn)
    claims = claimants(identities)
    frame_of = frames(conn)
    hosts = name_first_host()
    ids = all_variant_ids()
    closure = flat_parts(own_parts(conn, identities, claims))
    hits = findings(conn, identities, claims, frame_of, hosts, ids, closure)

    for gap, name, host_count, first_frame, first_char, pick, pick_char, pick_frame in hits:
        print(f"{name!r:<34} first used by {first_char} (frame {first_frame}), "
              f"{host_count} host(s) — only answer is {pick_char} {pick} "
              f"(frame {pick_frame}), {gap} frames too late")
    if args.all:
        print("\n-- names whose answer is possible --")
        for name in sorted(hosts):
            candidates = set(claims.get(name, ()))
            resolved = database.resolve_alias(conn, name)
            if resolved:
                candidates.add(resolved)
            if not candidates or any(h[1] == name for h in hits):
                continue
            print(f"  {name!r:<34} {sorted(candidates)}")
    print(f"\n{len(hits)} anachronistic name(s) of {len(hosts)} named in the components column")
    return 0


if __name__ == "__main__":
    sys.exit(main())
