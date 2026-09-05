#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
build_decomp_worklist.py — (re)generate docs/decomposition_worklist.json:
the finite list of rtk* kanji whose CURRENT data.txt decomposition disagrees
with Google's AI-Overview breakdown (backend/google_decompositions.json).

This is the audit's standing worklist. It is meant to SHRINK: as each kanji
gets a human decision, set its "status" away from "pending" (and fill
"decision"/"reviewed_by"/"reviewed_at"); re-running this script PRESERVES
those decided rows and only refreshes the still-"pending" ones plus adds any
newly-disagreeing kanji. Never re-review a decided kanji.

Run after: a new google_decompositions.json (more Google data mined), or a
data.txt content-fix commit (some disagreements resolved -> drop out).

    ./venv/bin/python3 build_decomp_worklist.py [--stats]

Read-only except for the worklist JSON. Does not touch kanji.db.
"""
import json, sys, re
from pathlib import Path

HERE = Path(__file__).parent
DATA_TXT = HERE / "data.txt"
GOOGLE = HERE / "google_decompositions.json"
IDS = Path("/tmp/ids.txt")   # cjkvi-ids; optional, only for the reviewer's reference column
WORKLIST = HERE.parent / "docs" / "decomposition_worklist.json"

IDC = set("⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻")

# Visual-variant / stroke-name equivalence. Each group collapses to its first
# member for comparison, so "｜ vs 丨" or "ノ vs 丿" isn't flagged as a real
# disagreement. Names Heisig uses for a glyph are mapped to that glyph too.
_VARIANT_GROUPS = [
    ("丨", "｜", "|"), ("丿", "ノ", "/"), ("乀", "㇏"), ("亅", "亅"),
    ("水", "氵", "氺"), ("刀", "刂"), ("阝", "⻏", "⻖", "卩"), ("艸", "艹", "艹"),
    ("心", "忄", "⺗"), ("手", "扌"), ("人", "亻", "𠆢", "𡆵"), ("竹", "⺮"),
    ("火", "灬"), ("肉", "月"), ("辵", "辶", "⻌", "⻍"), ("犬", "犭"),
    ("金", "钅", "釒"), ("糸", "糹", "纟"), ("言", "讠", "訁"), ("食", "飠", "饣"),
    ("目", "罒", "⺫"), ("小", "⺌", "⼩", "ツ", "𭕄", "𠮠"), ("八", "ハ", "丷"),
    ("玉", "王"), ("示", "礻"), ("衣", "衤"), ("卜", "⺊", "⼘"),
]
_VARIANT = {}
for grp in _VARIANT_GROUPS:
    for x in grp:
        _VARIANT[x] = grp[0]

# Heisig primitive keyword -> canonical glyph, for the names data.txt stores
# instead of a glyph. Only unambiguous, common ones.
_NAME_TO_GLYPH = {
    "top hat": "亠", "lid": "亠", "cave": "广", "enclosure": "囗",
    "mouth": "口", "sun": "日", "moon": "月", "tree": "木", "water": "氵",
    "fire": "火", "person": "亻", "human legs": "儿", "animal legs": "八",
    "katakana ha": "ハ", "needle": "十", "drop": "丶", "walking stick": "丨",
}

def load_ids():
    m = {}
    if not IDS.exists():
        return m
    for line in IDS.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        p = line.split("\t")
        if len(p) < 3 or len(p[1]) != 1:
            continue
        m[p[1]] = p[2].split("[")[0]
    return m

def ids_leaves(ch, ids, d=0, seen=None):
    if seen is None:
        seen = set()
    if ch in seen or d > 10:
        return {ch}
    seen = seen | {ch}
    seq = ids.get(ch)
    if not seq or seq == ch:
        return {ch}
    out = set()
    for c in seq:
        if c in IDC or c == ch:
            continue
        out |= ids_leaves(c, ids, d + 1, seen) if (c in ids and ids[c] != c) else {c}
    return out or {ch}

def parse_data_txt():
    """id -> (character, keyword, [primary-decomposition parts]) for rtk* rows.
    parts field is 'a,b,c;alt1,alt2' -- take the primary (before ';').
    Each entry can be a CJK glyph or a primitive NAME; we keep glyphs, and for
    names we keep them verbatim (the reviewer sees them; resolving every alias
    here would just reintroduce the stale-DB problem)."""
    out = {}
    for raw in DATA_TXT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        f = line.split(":")
        if len(f) < 4 or not f[0].startswith("rtk"):
            continue
        kid, ch, aliases, parts = f[0], f[1], f[2], f[3]
        primary = parts.split(";")[0]
        terms = [t.strip() for t in primary.split(",") if t.strip()]
        kw = aliases.split(",")[0].strip()
        out[kid] = (ch, kw, terms)
    return out

def is_glyph(s):
    return len(s) == 1 and ord(s) > 0x2E80

def canon(t):
    """map a term (glyph or Heisig name) to a canonical glyph for comparison."""
    if not is_glyph(t):
        t = _NAME_TO_GLYPH.get(t.strip().lower(), t.strip().lower())
    return _VARIANT.get(t, t)

def norm_set(terms):
    return frozenset(canon(t) for t in terms)

def main():
    stats_only = "--stats" in sys.argv
    ids = load_ids()
    data = parse_data_txt()
    google = json.loads(GOOGLE.read_text(encoding="utf-8"))
    g_by_char = {}
    for gid, g in google.items():
        if g.get("parts"):
            g_by_char.setdefault(g["character"], g)

    # preserve decided rows
    decided = {}
    if WORKLIST.exists():
        for row in json.loads(WORKLIST.read_text(encoding="utf-8")):
            if row.get("status") and row["status"] != "pending":
                decided[row["id"]] = row

    rows = []
    n_agree = n_decided_kept = n_pending = 0
    for kid, (ch, kw, our_terms) in sorted(data.items(), key=lambda x: int(re.sub(r"\D", "", x[0]) or 0)):
        if not ch or ch in ("?", "??"):
            continue
        g = g_by_char.get(ch)
        if not g:
            continue
        our_n = norm_set(our_terms)
        goog_n = norm_set(g["parts"])
        if our_n == goog_n:
            n_agree += 1
            continue
        # also treat as agree if one is a subset of the other AND the only
        # difference is granularity (the extra terms in the bigger set are
        # themselves sub-parts of a term in the smaller set, per cjkvi)
        small, big = sorted((our_n, goog_n), key=len)
        if small and small < big:
            extra = big - small
            covered = set()
            for parent in small:
                covered |= ids_leaves(parent, ids)
            if extra <= {canon(c) for c in covered}:
                n_agree += 1
                continue
        if kid in decided:
            rows.append(decided[kid])
            n_decided_kept += 1
            continue
        n_pending += 1
        rows.append({
            "id": kid,
            "char": ch,
            "keyword": kw,
            "our_parts": our_terms,
            "google_parts": g["parts"],
            "google_primitive_names": g.get("primitive_names", {}),
            "google_confidence": g.get("confidence"),
            "google_note": g.get("note", ""),
            "cjkvi_ids": ids.get(ch, ""),
            "cjkvi_leaves": sorted(ids_leaves(ch, ids)) if ch in ids else [],
            "status": "pending",
            "decision": None,
            "reviewed_by": None,
            "reviewed_at": None,
        })

    if stats_only:
        from collections import Counter
        print(f"agree (skipped)      : {n_agree}")
        print(f"decided (kept)       : {n_decided_kept}")
        print(f"pending review       : {n_pending}")
        print(f"worklist total       : {len(rows)}")
        print("pending by Google confidence:",
              Counter(r["google_confidence"] for r in rows if r["status"] == "pending"))
        return

    WORKLIST.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {WORKLIST.relative_to(HERE.parent)}: {len(rows)} rows "
          f"({n_pending} pending, {n_decided_kept} already decided; {n_agree} agree and were skipped)")

if __name__ == "__main__":
    main()
