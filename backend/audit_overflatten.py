#!/home/user/kanji/backend/venv/bin/python3
"""Detect (and optionally emit fixes for) over-flattened decompositions.

The bug class this targets, in this audit's vocabulary: a kanji lists the raw
sub-strokes of a component instead of referencing that component directly. E.g.
結 listing 口,士,糸 when its real structure is 糸 + 吉, and 吉 is itself a taught
kanji. This is what makes a common-primitive search ("mouth") return hundreds of
kanji: every host that shattered a compound into letters shows up as a direct
match for every letter.

Ground truth is cjkvi-ids' *top level* only — the direct children of the
character. If one of those children is itself registered in our database and our
parts contain that child's descendants instead of the child, that is a
collapsible over-flattening.

Deliberately conservative: a candidate is only reported when the collapse leaves
our part set a subset of cjkvi-ids' own top level, so a "fix" can never invent a
component the real glyph doesn't have. Anything messier is left for a human pass
— see --show-skipped.

Usage:
    ./venv/bin/python3 audit_overflatten.py                    # summary + candidates
    ./venv/bin/python3 audit_overflatten.py --term mouth       # only hosts a search for TERM returns
    ./venv/bin/python3 audit_overflatten.py --term bow --emit  # emit fixed data.txt lines
"""
import argparse
import os
import sys

import database

IDS_PATH = os.environ.get("CJKVI_IDS", "/tmp/ids.txt")
IDS_OPS = set("⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻")

# cjkvi-ids spells a radical in its combining form; this project registers the
# free-standing kanji and has done so since the 刂->刀 decision early in the
# audit. Same primitive, different codepoint — mapping them is notation, not a
# judgement call, so it stays a flat table rather than anything inferred.
RADICAL_VARIANTS = {
    "氵": "水", "氺": "水",
    "糹": "糸", "纟": "糸",
    "刂": "刀",
    "衤": "衣",
    "飠": "食", "饣": "食",
    "爫": "爪",
    "户": "戸",
    "兑": "兌",
    "覀": "西",
    "釒": "金", "钅": "金",
    "訁": "言", "讠": "言",
    "牜": "牛",
    "𤣩": "王",
    "灬": "灬",
    # Stroke primitives: this project spells them with the katakana/fullwidth
    # forms it registered long ago, cjkvi-ids with the CJK stroke codepoints.
    "丿": "ノ",
    "丨": "｜",
    "乚": "乙",
    "⺉": "刀",
    # 𧾷 is the combining form of 足, which this project already uses in every
    # one of its hosts (促/路/踊 …).
    "𧾷": "足",
}


def load_ids(path=IDS_PATH):
    """character -> its first listed IDS decomposition string."""
    table = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) >= 3:
                table.setdefault(fields[1], fields[2])
    return table


def top_level(ids, ch):
    """Direct children of ch per cjkvi-ids, or None when ch is atomic there."""
    entry = ids.get(ch)
    if not entry or entry == ch:
        return None
    kids = {RADICAL_VARIANTS.get(c, c) for c in entry if c not in IDS_OPS and not c.isascii()}
    return kids or None


def descendants(ids, ch, _depth=0, _seen=None):
    """Every component strictly below ch in the IDS tree."""
    if _seen is None:
        _seen = set()
    if ch in _seen or _depth > 12:
        return set()
    _seen = _seen | {ch}
    kids = top_level(ids, ch)
    if not kids:
        return set()
    out = set(kids)
    for kid in kids:
        out |= descendants(ids, kid, _depth + 1, _seen)
    return out


def read_data_txt(path):
    """rtk id -> (raw line, character, [part tokens]) for lines with a real glyph."""
    rows = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.rstrip("\n")
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.split(":")
            if len(fields) < 4 or not fields[0].startswith("rtk"):
                continue
            kid, ch, parts = fields[0], fields[1], [p for p in fields[3].split(",") if p]
            if len(ch) != 1:
                continue
            rows[kid] = (stripped, ch, parts)
    return rows


def registered_chars(conn):
    """Every single-character glyph our database can resolve as a part token."""
    known = set()
    for (ch,) in conn.execute("SELECT character FROM kanji WHERE character IS NOT NULL"):
        if ch and len(ch) == 1:
            known.add(ch)
    for (alias,) in conn.execute("SELECT alias FROM aliases"):
        if alias and len(alias) == 1:
            known.add(alias)
    return known


def alias_to_char(conn):
    """Multi-character alias -> the glyph it resolves to.

    Needed so a word-form token is recognised as the component it already is:
    "state of mind" is 忄, so a host carrying it must not also be handed a
    second, duplicate 忄 when its decomposition is rebuilt.
    """
    mapping = {}
    rows = conn.execute(
        "SELECT a.alias, k.character FROM aliases a JOIN kanji k ON k.id = a.kanji_id "
        "WHERE k.character IS NOT NULL AND length(k.character) = 1"
    )
    for alias, ch in rows:
        if len(alias) > 1:
            mapping.setdefault(alias, ch)
    return mapping


def collapse(ids, known, ch, parts, aliases=None):
    """Return (new_parts, note) or (None, reason).

    The target is cjkvi-ids' own top level, not a rewrite of our token list.
    Deriving the answer from ground truth rather than mutating our (already
    wrong) parts avoids the trap that a naive "swallow our tokens into the
    biggest component" pass falls into: 呪 is ⿰口兄, and its own 口 would get
    eaten as if it were 兄's internal one, silently deleting the left half.
    """
    aliases = aliases or {}
    top = top_level(ids, ch)
    if not top:
        return None, "atomic in cjkvi-ids"

    # token -> glyph, so word-form aliases count as the component they name.
    resolved = {p: (p if len(p) == 1 else aliases.get(p)) for p in parts}
    glyphs = {g for g in resolved.values() if g}
    if not glyphs:
        return None, "no resolvable tokens"
    if glyphs == top:
        return None, "already matches cjkvi top level"

    unregistered = sorted(c for c in top if c not in known)
    if unregistered:
        return None, f"cjkvi top level needs unregistered component(s) {''.join(unregistered)}"

    # Every token we drop must be something that genuinely lives *below* the
    # target components; anything else is information cjkvi-ids doesn't have and
    # we must not throw away on its say-so.
    below = set()
    for comp in top:
        below |= descendants(ids, comp)
    stray = sorted(glyphs - top - below)
    if stray:
        return None, f"our token(s) {''.join(stray)} are nowhere in the cjkvi tree"

    shattered = sorted(glyphs - top)
    if not shattered:
        return None, "nothing to collapse"

    # Prefer the token the line already uses for a surviving component, so a
    # correct word-form alias is left alone instead of churned into its glyph.
    spelling = {}
    for token, glyph in resolved.items():
        if glyph in top:
            spelling.setdefault(glyph, token)
    new_parts = [spelling.get(c, c) for c in sorted(top)]
    return new_parts, f"{'+'.join(shattered)} -> {''.join(sorted(top - glyphs))}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", help="restrict to hosts a depth-1 parts search for TERM returns")
    ap.add_argument("--emit", action="store_true", help="print corrected data.txt lines only")
    ap.add_argument("--apply", action="store_true", help="rewrite data.txt in place with the fixes")
    ap.add_argument("--show-skipped", action="store_true", help="list candidates the safety gate rejected")
    ap.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "data.txt"))
    args = ap.parse_args()

    ids = load_ids()
    conn = database.get_db()
    known = registered_chars(conn)
    aliases = alias_to_char(conn)
    rows = read_data_txt(args.data)

    scope = None
    if args.term:
        hits = database.search_by_parts(conn, [args.term], viewer_id=None, depth=1)
        scope = {r["id"] for r in hits}

    fixes, skipped = [], []
    for kid, (line, ch, parts) in rows.items():
        if scope is not None and kid not in scope:
            continue
        new_parts, info = collapse(ids, known, ch, parts, aliases)
        if new_parts is None:
            if info not in ("atomic in cjkvi-ids", "nothing to collapse", "no single-glyph tokens"):
                skipped.append((kid, ch, parts, info))
            continue
        fixes.append((kid, ch, line, parts, new_parts, info))

    def rebuilt(line, new_parts):
        head = line.split(":")
        return f"{head[0]}:{head[1]}:{head[2]}:{','.join(new_parts)}"

    if args.emit:
        for kid, ch, line, parts, new_parts, info in fixes:
            print(rebuilt(line, new_parts))
        return

    if args.apply:
        replacements = {kid: rebuilt(line, new_parts) for kid, ch, line, parts, new_parts, info in fixes}
        out = []
        with open(args.data, encoding="utf-8") as fh:
            for raw in fh:
                kid = raw.split(":", 1)[0]
                out.append(replacements[kid] + "\n" if kid in replacements else raw)
        with open(args.data, "w", encoding="utf-8") as fh:
            fh.writelines(out)
        print(f"applied {len(replacements)} fix(es) to {args.data}")
        return

    label = f" among the {len(scope)} hosts a '{args.term}' search returns" if scope else ""
    print(f"{len(fixes)} over-flattened decomposition(s){label}\n")
    for kid, ch, line, parts, new_parts, info in fixes:
        swallows = info
        print(f"  {ch} {kid:9s} {','.join(parts):38s} -> {','.join(new_parts):26s}  ({swallows})")

    if args.show_skipped:
        print(f"\n{len(skipped)} candidate(s) rejected by the safety gate (need a human):")
        for kid, ch, parts, why in skipped:
            print(f"  {ch} {kid:9s} {','.join(parts):38s}  {why}")


if __name__ == "__main__":
    main()
