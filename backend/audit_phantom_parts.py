#!/home/user/kanji/backend/venv/bin/python3
"""
audit_phantom_parts.py — detector for *phantom parts*: a part this project
lists for a kanji that neither of the two independent ground truths can
account for.

## The bug shape

Found 2026-09-13 while looking for something else. `rtk1997:盾:shield:斤,十,目,厂`
lists 斤 ("ax"). 盾 contains no ax: cjkvi-ids expands it to 𠂆 + 目 + 十, and
heisig-kanjis.csv's own components column for 盾 reads "drag; ten; needle; eye".
Both sources agree, and neither mentions an ax. The same stray 斤 sits in
`rtk553:栃` (whose real parts are tree + cliff + ten thousand).

This matters more than it looks. Every phantom part is a *pure* search-noise
generator: it can only ever make a search for that primitive return a kanji
that does not contain it. The audit's other detectors cannot see this class —
audit_csv_regressions.py looks for concepts we *dropped* relative to the CSV
(the opposite direction), and audit_flattening*.py / audit_overflatten.py both
reason about parts that *are* genuinely in the glyph, just spelled at the wrong
level. A part that is simply not there at all falls through all of them.

## How it works

Two independent sources have to *both* fail to account for a part before it is
reported:

1. **Structural** — the part's glyph is reachable from the host by expanding
   cjkvi-ids recursively and then continuing through *this project's own*
   decompositions. Both halves are needed. cjkvi-ids bottoms out at mid-level
   components rather than at strokes (左 is `⿸𠂇工`, and 𠂇 is atomic there), so
   cjkvi alone reports every stroke primitive Heisig legitimately teaches; once
   the expansion continues through our own `𠂇 = ノ,一`, ノ and 一 are accounted
   for. RADICAL_VARIANTS applies throughout, so 氵 and 水 are the same evidence.
   Unlike audit_overflatten.py this uses the union of *every* region variant a
   cjkvi line carries, not just `[J]`: picking one shape matters when choosing a
   decomposition to follow, but here more variants can only mean fewer false
   accusations (器 is `⿳吅大吅` under `[J]` and `⿳吅犬吅` elsewhere — the 犬
   Heisig teaches is real either way).
2. **Heisig** — one of the part's own names matches a name in the host's
   `components` column in heisig-kanjis.csv. This is the name-level check, and
   it is what rescues the shape-abstraction primitives that have no glyph of
   their own in the tree ("animal legs", "st. bernard"): Heisig names them even
   when Unicode does not decompose to them.

Passing *either* clears the part. Only a part that fails both is reported, so a
gap in cjkvi-ids (it has no entry for the host at all -> the host is skipped
entirely) or a terse CSV row cannot on its own manufacture a finding.

Note the CSV only covers the ~2200 6th-edition frames, so for anything above
that the Heisig channel is silent and the structural one is carrying the whole
check alone. `--in-csv-range` restricts the run to hosts where both channels
actually have something to say.

## The structural channel's blind spot (2026-09-20)

cjkvi-ids writes a component it has no codepoint for as a circled number, and
**those numbers are per-entry placeholders, not identifiers** — ③ is the bottom
of 不 in `⿱一③`, the left of 北 in `⿰③匕`, the left of 印 in `⿰③卩` and a 止
variant in 此's second reading `⿰③匕`, all different shapes. ⑤ is 皀 in 即
(`⿰⑤卩`), something else entirely in 叚 (`⿰⑤⿱コ又`), and the top of 其. So a
placeholder is a hole, and nothing may ever be inferred from two entries sharing
one. The closure treats them as opaque glyphs, which is safe — they match
nothing — but it means that for a host whose expansion contains one, the
structural channel cannot clear *anything* that lives inside the hole, and the
Heisig name channel is silently carrying the check alone.

Those findings are reported in their own section rather than mixed in, because
"cjkvi-ids cannot reach it" is not the same claim as "it is not in the glyph",
and this is exactly the set where the difference bites. 16 of the 58
phantom-carrying kanji were in that state when this was added, so it is not a
corner case.

This deliberately does not auto-fix. Every hit still has to be rendered and
looked at (`render_glyphs.py`) before anything is edited — the standing method
for this audit, and the reason several confident-looking verdicts in its history
had to be retracted.

Usage:
    ./venv/bin/python3 audit_phantom_parts.py            # all findings
    ./venv/bin/python3 audit_phantom_parts.py --term ax  # only parts naming TERM
"""
import argparse
import csv
import os
import sys

import database
from audit_overflatten import IDS_OPS, RADICAL_VARIANTS, _raw_ids

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heisig-kanjis.csv")

# cjkvi-ids' marks for a component with no codepoint. Per entry, not per shape —
# see "The structural channel's blind spot" above before reading anything into one.
PLACEHOLDERS = frozenset("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳")


def normalise(ch):
    return RADICAL_VARIANTS.get(ch, ch)


def csv_components(path=CSV_PATH):
    """kanji glyph -> set of Heisig component names, lowercased.

    Rows whose components column is blank are left out entirely rather than
    stored as an empty set — an absent answer is not the answer "nothing".
    """
    table = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            names = {n.strip().lower() for n in row["components"].split(";") if n.strip()}
            if row["kanji"] and names:
                table[row["kanji"]] = names
    return table


def all_variant_ids(path=None):
    """character -> every shape any region's decomposition of it mentions.

    The union, not the `[J]` pick: see the module docstring on why evidence
    wants every variant even though following a structure wants one.
    """
    table = {}
    raw = _raw_ids(path) if path else _raw_ids()
    for ch, variants in raw.items():
        shapes = set()
        for body, _tags in variants:
            if body == ch:
                continue
            shapes |= {c for c in body if c not in IDS_OPS and not c.isascii()}
        if shapes:
            table[ch] = shapes
    return table


def own_parts(conn, identities, claims):
    """kanji glyph -> [{every glyph a part of it could mean}, ...], one set per part.

    Per *part*, not one flat set, and every claimant of the name rather than
    just resolve_alias's canonical pick — 衣 lists "lid", which canonicalises to
    the kanji 蓋 even though the shape meant is 亠. Flattening that away made
    衣's own pieces look absent from every host that contains 衣.
    """
    table = {}
    char_of = {
        kid: char for kid, (char, _names) in identities.items() if char not in (None, "", "?", "??")
    }
    rows = conn.execute(
        """SELECT d.kanji_id, p.part_term
             FROM parts p
             JOIN decompositions d ON d.id = p.decomposition_id
            WHERE d.owner_id = 1"""
    ).fetchall()
    for row in rows:
        host = char_of.get(row["kanji_id"])
        if not host:
            continue
        term = row["part_term"].strip().lower()
        candidates = set(claims.get(term, ()))
        resolved = database.resolve_alias(conn, row["part_term"])
        if resolved:
            candidates.add(resolved)
        glyphs = {normalise(char_of[c]) for c in candidates if c in char_of}
        if glyphs:
            table.setdefault(host, []).append(glyphs)
    return table


def flat_parts(ours):
    """The per-part sets collapsed to one glyph set per host, for the closure."""
    return {host: set().union(*sets) for host, sets in ours.items()}


def accounted_glyphs(ids, ours, ch):
    """Every glyph reachable from ch through cjkvi-ids and then our own parts.

    Includes ch itself: a kanji trivially accounts for a part naming the kanji
    (self-identity is a real, deliberate relationship in this project's search).

    The host's *own* decomposition is deliberately not part of the closure — it
    is the thing under test, and letting it in would make every part account for
    itself and the whole check vacuous. Every other kanji's decomposition is
    fair game, since that is our evidence about what the intermediate shapes
    cjkvi-ids stops at are made of.
    """
    seen = set()
    stack = [normalise(ch), ch]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        reachable = set(ids.get(cur, ()))
        if cur != ch and normalise(cur) != normalise(ch):
            reachable |= ours.get(cur, set())
        for nxt in reachable:
            for form in (nxt, normalise(nxt)):
                if form not in seen:
                    stack.append(form)
    return seen


def _spelled_out(ours, part_char, tree):
    """Is the part present in the host, spelled as its own pieces rather than itself?

    The closure runs downward from the host, but cjkvi-ids does not always stop
    at the same level this project does: 裏 is `⿳亠里𧘇`, so the 衣 ("robe")
    Heisig teaches is in the glyph without 衣 ever appearing in the expansion.
    Checking that *every* piece of 衣 (亠 and 𧘇) is in the tree recovers it,
    without letting a part clear itself — a part with no decomposition of its
    own (斤, 二) can never pass this, which is exactly the class worth reporting.
    """
    if not part_char:
        return False
    pieces = ours.get(part_char) or ours.get(normalise(part_char))
    if not pieces or len(pieces) < 2:
        return False
    return all(alternatives & tree for alternatives in pieces)


def part_identities(conn):
    """kanji id -> (character, {every name it answers to, lowercased})."""
    table = {}
    for row in conn.execute(
        "SELECT id, character, keyword FROM kanji WHERE owner_id = 1"
    ):
        names = set()
        if row["keyword"]:
            names |= {n.strip().lower() for n in row["keyword"].split(",") if n.strip()}
        table[row["id"]] = [row["character"], names]
    for row in conn.execute("SELECT kanji_id, alias FROM aliases WHERE owner_id = 1"):
        entry = table.get(row["kanji_id"])
        if entry is not None and row["alias"]:
            entry[1] |= {n.strip().lower() for n in row["alias"].split(",") if n.strip()}
    return table


def claimants(identities):
    """name -> every kanji id that answers to it.

    A part term is a name, and a name can be shared (both 匚 and 箱 are "box").
    resolve_alias picks one canonical id for search, but for *evidence* every
    claimant counts: a decomposition writing "box" for 匚 is not wrong just
    because the term happens to canonicalise to 箱. Same rule the search itself
    follows for ambiguous terms.
    """
    table = {}
    for kid, (_char, names) in identities.items():
        for name in names:
            table.setdefault(name, set()).add(kid)
    return table


def findings(conn, ids, ours, heisig, identities, claims, term=None, in_csv_range=False):
    closure = flat_parts(ours)
    out = []
    hosts = conn.execute(
        """SELECT k.id, k.character, k.keyword
             FROM kanji k
            WHERE k.owner_id = 1 AND k.id LIKE 'rtk%'
              AND k.character IS NOT NULL AND k.character NOT IN ('', '?', '??')
            ORDER BY k.frame"""
    ).fetchall()
    for host in hosts:
        if host["character"] not in ids:
            continue  # no structural ground truth for this host at all
        if in_csv_range and host["character"] not in heisig:
            continue  # only one channel would be speaking; see the docstring
        tree = accounted_glyphs(ids, closure, host["character"])
        names = heisig.get(host["character"], set())
        # Only the first (system, unlabelled) decomposition is this project's own
        # claim about the kanji; the cjkvi-derived alternates are by construction
        # structural and would trivially clear the check.
        rows = conn.execute(
            """SELECT p.part_term
                 FROM parts p
                 JOIN decompositions d ON d.id = p.decomposition_id
                WHERE d.kanji_id = ? AND d.owner_id = 1 AND d.label IS NULL
                ORDER BY p.position""",
            (host["id"],),
        ).fetchall()
        # A decomposition stores both the term as written and its canonical name
        # (口 *and* "mouth"), so report once per distinct part, not once per row.
        seen = set()
        for row in rows:
            part = row["part_term"]
            resolved = database.resolve_alias(conn, part)
            if resolved is None:
                continue  # audit_radicals.py owns the unresolvable-term class
            candidates = claims.get(part.strip().lower(), set()) | {resolved}
            # 「｜」and its name "pipe" are one part written twice, but they
            # canonicalise to different ids (prim-pipe vs the kanji 管), so an
            # id-keyed dedupe reports each host twice. Overlapping claimant sets
            # are the same part.
            if candidates & seen:
                continue
            if any(
                identities.get(c, [None, set()])[0]
                and normalise(identities[c][0]) in tree
                for c in candidates
            ):
                continue  # structural evidence, from any row answering to this name
            if any(_spelled_out(ours, identities.get(c, [None])[0], tree) for c in candidates):
                continue  # structural evidence, spelled as the part's own pieces
            if any(identities.get(c, [None, set()])[1] & names for c in candidates):
                continue  # Heisig evidence
            char, part_names = identities.get(resolved, [None, set()])
            if term and term.lower() not in part_names:
                continue
            seen |= candidates
            out.append((host["id"], host["character"], host["keyword"], part, char, resolved,
                        bool(tree & PLACEHOLDERS)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--term", help="only report parts that answer to this name")
    ap.add_argument(
        "--in-csv-range",
        action="store_true",
        help="only hosts heisig-kanjis.csv covers, so both channels are speaking",
    )
    ap.add_argument(
        "--hide-blind",
        action="store_true",
        help="drop the findings whose host has an unencoded cjkvi-ids placeholder in "
             "its expansion, leaving only the ones both channels actually examined",
    )
    args = ap.parse_args()

    conn = database.get_db()
    ids = all_variant_ids()
    heisig = csv_components()
    identities = part_identities(conn)
    claims = claimants(identities)
    ours = own_parts(conn, identities, claims)
    hits = findings(
        conn,
        ids,
        ours,
        heisig,
        identities,
        claims,
        args.term,
        args.in_csv_range,
    )

    def show(rows):
        for kid, char, keyword, part, part_char, resolved, _blind in rows:
            shown = f"{part} ({part_char})" if part_char and part_char != part else part
            print(f"{kid}\t{char}\t{keyword}\tphantom part: {shown} -> {resolved}")

    solid = [h for h in hits if not h[6]]
    blind = [] if args.hide_blind else [h for h in hits if h[6]]
    show(solid)
    if blind:
        print("\n-- cjkvi-ids cannot see inside these hosts (unencoded placeholder in the\n"
              "   expansion), so only the Heisig name channel is speaking. Weaker evidence:\n")
        show(blind)
    shown = solid + blind
    tail = (f" — {len(blind)} of them across {len({h[0] for h in blind})} kanji rest on the"
            f" Heisig channel alone") if blind else ""
    print(f"\n{len(shown)} phantom part(s) across {len({h[0] for h in shown})} kanji{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
