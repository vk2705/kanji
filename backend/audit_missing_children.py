#!/home/user/kanji/backend/venv/bin/python3
"""
audit_missing_children.py — a part that is *in* the glyph, named by Heisig,
and absent from this project's decomposition of it.

## The bug shape

The mirror image of audit_phantom_parts.py. That one finds parts we list which
are not in the kanji; this one finds parts in the kanji which we do not list.

`audit_csv_regressions.py` already reports the symptom — 基 "drops" the concepts
"animal legs" and "eight" — but it reports it on every *host*, and a host is
almost never where the fix goes. 欺 棋 旗 期 碁 基 all dropped the same pair, and
all six were fine: the row that needed the 八 was 其, which they all go through.
Finding that meant reading six near-identical report blocks and working out by
hand what they had in common, once per family, which is most of what chunks 43
through 61 spent their time on.

So this script asks a narrower question with a much better answer rate:

> For a host that drops a concept, does **cjkvi-ids** name a child that the
> decomposition does not list, and does that child **answer to the dropped
> name**? And if so, which of the host's own parts should have been carrying it?

## Why two sources, and what that buys

Nothing is reported unless cjkvi-ids and heisig-kanjis.csv agree: cjkvi has to
put the shape inside the host, *and* Heisig has to name it there. Requiring both
is what separates this from the adjacency prospector tried first (chunk 54),
which guessed a home for a dropped name from its neighbours in the CSV list, and
was wrong about as often as right — one source cannot corroborate itself.

It also makes the deliberately-atomic rows take care of themselves, with no
carve-out. 言 心 虫 車 酉 are atomic *in cjkvi-ids too*, so it never offers their
children, and their ~230 hosts never appear here even though the CSV report
counts them (under its own separate "via a deliberately atomic part" heading).

## The `via` column

For each finding it also names the host's own part that cjkvi puts the missing
child inside. That is the row to edit, and it is what turns a six-line family
into one line of work:

    rtk1904   基 fundamentals    +八 (animal legs/eight)   via 其

Findings with the same `via` are one fix. The trailing summary groups them that
way, most hosts first.

## What it does not do

It does not auto-fix and it does not settle anything by itself. cjkvi-ids is
coarser than Heisig in places and wrong in others (it writes a component it has
no codepoint for as a per-entry circled placeholder, and its region variants
disagree with each other — 敝's left half has three different spellings there).
Every hit still has to be rendered and looked at (`render_glyphs.py`) before
data.txt is touched: the standing method for this audit, and the reason several
confident-looking verdicts in its history had to be retracted.

Reads the live `kanji.db` and reports only, same convention as its siblings.
Needs cjkvi-ids downloaded (`/tmp/ids.txt`, or set `CJKVI_IDS`).

Usage:
    ./venv/bin/python3 audit_missing_children.py               # all findings
    ./venv/bin/python3 audit_missing_children.py --term eight  # one dropped name
    ./venv/bin/python3 audit_missing_children.py --summary     # just the fix list
"""
import argparse
import collections
import csv
import sys

import database
from audit_phantom_parts import (
    CSV_PATH,
    all_variant_ids,
    claimants,
    normalise,
    part_identities,
)

DEFAULT_MAX_DEPTH = 4
DEFAULT_EXPAND = 2


def cjkvi_children(ids, ch, depth=DEFAULT_EXPAND, _seen=None):
    """Every glyph cjkvi-ids puts inside `ch`, expanded `depth` levels.

    One level is not enough: cjkvi spells 基 as ⿱其土 and only 其's own entry
    mentions the 八. It is also not a closure — expanding to the bottom turns
    every host into a bag of strokes and the `via` column stops meaning
    anything.
    """
    if _seen is None:
        _seen = set()
    if ch in _seen or depth < 0:
        return set()
    _seen.add(ch)
    out = set()
    for glyph in ids.get(ch, ()):
        if glyph == ch:
            continue
        out.add(glyph)
        out |= cjkvi_children(ids, glyph, depth - 1, _seen)
    return out


def row_for_glyph(identities, glyph):
    """Every system row whose character is `glyph`, RADICAL_VARIANTS applied."""
    target = normalise(glyph)
    return {
        kid for kid, (ch, _names) in identities.items()
        if ch and normalise(ch) == target
    }


def reachable(conn, claims, kid, max_depth=DEFAULT_MAX_DEPTH, _cache=None):
    """Ids reachable from kid through this project's own decompositions.

    Every system decomposition counts, labelled alternates included — that is
    how audit_csv_regressions.py decides a concept is not dropped, and this has
    to agree with it or the two disagree about what is even a finding. 足 is the
    case in point: its primary is 口 + 龰 and its cjkvi alternate 口 + 止, and
    the ten hosts that reach "stop" through the alternate must not be reported.
    """
    if _cache is None:
        _cache = {}
    if kid in _cache:
        return _cache[kid]
    seen, frontier = set(), [(kid, 0)]
    while frontier:
        cur, depth = frontier.pop()
        if depth > max_depth:
            continue
        for row in conn.execute(
            """SELECT p.part_term FROM parts p
                 JOIN decompositions d ON d.id = p.decomposition_id
                WHERE d.kanji_id = ? AND d.owner_id = 1""",
            (cur,),
        ).fetchall():
            term = row["part_term"].strip().lower()
            candidates = set(claims.get(term, ()))
            resolved = database.resolve_alias(conn, row["part_term"])
            if resolved:
                candidates.add(resolved)
            for cid in candidates - seen - {cur}:
                seen.add(cid)
                frontier.append((cid, depth + 1))
    _cache[kid] = seen
    return seen


def own_part_ids(conn, claims, kid):
    """The ids this project lists directly as kid's parts, across all its
    decompositions — the candidates for the `via` column."""
    out = set()
    for row in conn.execute(
        """SELECT p.part_term FROM parts p
             JOIN decompositions d ON d.id = p.decomposition_id
            WHERE d.kanji_id = ? AND d.owner_id = 1""",
        (kid,),
    ).fetchall():
        out |= set(claims.get(row["part_term"].strip().lower(), ()))
        resolved = database.resolve_alias(conn, row["part_term"])
        if resolved:
            out.add(resolved)
    return out


def findings(conn, identities, claims, ids, args):
    cache = {}

    def answers_to(name):
        candidates = set(claims.get(name, ()))
        resolved = database.resolve_alias(conn, name)
        if resolved:
            candidates.add(resolved)
        return candidates

    out = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            frame = (row["id_6th_ed"] or "").strip()
            if not frame.isdigit():
                continue
            kid = f"rtk{frame}"
            if kid not in identities:
                continue
            host = identities[kid][0]
            if not host or host not in ids:
                continue  # no structural ground truth for this host at all
            names = [n.strip().lower() for n in row["components"].split(";") if n.strip()]
            if not names:
                continue
            reach = reachable(conn, claims, kid, args.max_depth, cache)
            dropped = [
                n for n in names
                if n not in identities[kid][1] and not (answers_to(n) & reach)
            ]
            if args.term:
                dropped = [n for n in dropped if n == args.term.lower()]
            if not dropped:
                continue
            parts = own_part_ids(conn, claims, kid)
            for glyph in sorted(cjkvi_children(ids, host, args.expand)):
                rows = row_for_glyph(identities, glyph)
                if not rows or rows & reach:
                    continue
                hit = sorted({n for n in dropped if answers_to(n) & rows})
                if not hit:
                    continue
                via = sorted(
                    pid for pid in parts
                    if identities[pid][0]
                    and glyph in cjkvi_children(ids, identities[pid][0], args.expand)
                )
                out.append((kid, host, row["keyword_6th_ed"], glyph, hit, via))
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--term", help="only report this one dropped name")
    ap.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH,
                    help="how deep our own decompositions are followed (default 4, "
                         "matching audit_csv_regressions.py)")
    ap.add_argument("--expand", type=int, default=DEFAULT_EXPAND,
                    help="how many levels of cjkvi-ids to expand (default 2)")
    ap.add_argument("--summary", action="store_true",
                    help="print only the grouped fix list, not the per-host lines")
    args = ap.parse_args()

    conn = database.get_db()
    identities = part_identities(conn)
    claims = claimants(identities)
    ids = all_variant_ids()
    hits = findings(conn, identities, claims, ids, args)

    if not args.summary:
        for kid, host, keyword, glyph, names, via in hits:
            tail = "   via " + " / ".join(
                f"{identities[pid][0]} {pid}" for pid in via) if via else ""
            print(f"{kid:10} {host} {keyword:22} +{glyph} ({'/'.join(names)}){tail}")

    # Grouped by the row to edit, not by the glyph: 㐮 is missing five children
    # at once and that is one afternoon, not five.
    hosts_of = collections.defaultdict(set)
    glyphs_of = collections.defaultdict(set)
    loose = collections.defaultdict(set)
    for kid, _host, _kw, glyph, _names, via in hits:
        if len(via) == 1:
            hosts_of[via[0]].add(kid)
            glyphs_of[via[0]].add(glyph)
        else:
            loose[kid].add(glyph)
    print("\n-- one fix each, most hosts first --")
    for key, hosts in sorted(hosts_of.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  {len(hosts):4} host(s)  add {' '.join(sorted(glyphs_of[key]))}"
              f"  to {identities[key][0]} {key}"
              f"    e.g. {' '.join(sorted(identities[h][0] for h in hosts)[:4])}")
    if loose:
        # No part of the host carries the missing shape, so the host's own row
        # is where it goes — one line each, since they share nothing.
        print("\n-- no part carries these; the host's own row is the fix --")
        for kid in sorted(loose, key=lambda k: identities[k][0]):
            print(f"       {identities[kid][0]} {kid:9} add {' '.join(sorted(loose[kid]))}")
    print(f"\n{len(hits)} finding(s) across {len({h[0] for h in hits})} kanji: "
          f"{len(hosts_of)} shared row(s) to edit, {len(loose)} host row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
