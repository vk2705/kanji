"""
import_hanzi.py — Import Chinese hanzi (simplified + traditional) into kanji.db.

Unlike import_rtk.py (which only ever appends to data.txt, letting import_data() do the
actual DB write later), the DB is the source of truth now, so this writes directly into
kanji.db as system-owned (owner_id=1), public rows.

Sources:
  - Unihan.zip (unicode.org) — kSimplifiedVariant/kTraditionalVariant for the
    simplified<->traditional link and script tagging, kDefinition/kMandarin for the
    English gloss and a pinyin alias.
  - cjkvi-ids ids.txt (github.com/cjkvi/cjkvi-ids) — first-level IDS structural
    decomposition into components, reusing the same "part term can be a kanji
    character" mechanism the RTK data already uses (see expand_part_terms).

Scope: the CJK Unified Ideographs block only (U+4E00-U+9FFF, ~20k chars) — covers
essentially all modern Chinese usage without the long tail of rare/historical
characters in the full multi-plane Unihan set.

Usage:
    python3 import_hanzi.py [--unihan-zip PATH] [--ids-file PATH] [--dry-run]

Downloads Unihan.zip and ids.txt to /tmp if paths aren't given. One-time, manually
invoked — not wired into the app's startup, since it's a large download+parse unlike
the small bundled RTK seed files. Safe to interrupt and re-run from scratch (guarded:
refuses to run again once any non-ja-kanji rows exist), but not safe to resume
mid-run — delete the partial hanzi-* rows first if a run was interrupted.
"""

import argparse
import re
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

from database import get_db, _insert_alias, _build_char_lookup, expand_part_terms

UNIHAN_URL = "https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip"
IDS_URL = "https://raw.githubusercontent.com/cjkvi/cjkvi-ids/master/ids.txt"

CJK_UNIFIED_SCOPE = set(range(0x4E00, 0x9FFF + 1))

# Ideographic Description Characters (⿰ .. ⿻) used to structurally combine components
# in an IDS string — not real characters, stripped out before we look at components.
IDC_OPERATORS = set(range(0x2FF0, 0x2FFC))

# A trailing region-variant tag like "与[GTKV]" that some IDS entries carry, marking
# which locales use that particular glyph shape — not part of the decomposition itself.
_REGION_TAG_RE = re.compile(r"\[[A-Z]+\]$")


def download(url: str, dest: Path):
    print(f"Downloading {url} ...", flush=True)
    urllib.request.urlretrieve(url, dest)
    print(f"  -> saved to {dest}", flush=True)


def _is_han_component(ch: str) -> bool:
    """True if ch is a real CJK ideograph codepoint (as opposed to an IDS placeholder
    like a circled-digit compatibility ref, or a Latin/Greek letter used as a filler)."""
    cp = ord(ch)
    return (
        0x3400 <= cp <= 0x4DBF     # CJK Ext A
        or 0x4E00 <= cp <= 0x9FFF  # CJK Unified Ideographs
        or 0xF900 <= cp <= 0xFAFF  # CJK Compatibility Ideographs
        or 0x20000 <= cp <= 0x3FFFF  # supplementary planes (Ext B and beyond)
    )


def _strip_pinyin_tones(pinyin: str) -> str:
    """'hàn' -> 'han' — decompose tone-marked vowels and drop the combining marks."""
    decomposed = unicodedata.normalize("NFKD", pinyin)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


def parse_unihan_variants(path: Path, scope: set[int]) -> dict[str, dict]:
    """{char: {'simplified': target_char|None, 'traditional': target_char|None}}."""
    result: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) != 3:
                continue
            cp_str, field, value = cols
            if field not in ("kSimplifiedVariant", "kTraditionalVariant"):
                continue
            cp = int(cp_str[2:], 16)
            if cp not in scope:
                continue
            char = chr(cp)
            # A field can list multiple space-separated targets; take the first.
            target_char = chr(int(value.split()[0][2:], 16))
            entry = result.setdefault(char, {"simplified": None, "traditional": None})
            if field == "kSimplifiedVariant":
                entry["simplified"] = target_char
            else:
                entry["traditional"] = target_char
    return result


def parse_unihan_readings(path: Path, scope: set[int]) -> dict[str, dict]:
    """{char: {'definition': str|None, 'mandarin': str|None}}."""
    result: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) != 3:
                continue
            cp_str, field, value = cols
            if field not in ("kDefinition", "kMandarin"):
                continue
            cp = int(cp_str[2:], 16)
            if cp not in scope:
                continue
            char = chr(cp)
            entry = result.setdefault(char, {"definition": None, "mandarin": None})
            if field == "kDefinition":
                entry["definition"] = value
            else:
                entry["mandarin"] = value.split()[0]  # first reading if polyphonic
    return result


def parse_ids(path: Path, scope: set[int]) -> dict[str, list[str]]:
    """
    {char: [component_char, ...]} — first-level, first-alternative-only IDS
    decomposition. Strips IDC structural operators and non-Han placeholder components
    (region-variant annotations, compatibility refs with no real codepoint).
    """
    result: dict[str, list[str]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3:
                continue
            cp_str, char, ids_str = cols[0], cols[1], cols[2]
            cp = int(cp_str[2:], 16)
            if cp not in scope:
                continue
            ids_str = _REGION_TAG_RE.sub("", ids_str)
            components = [
                c for c in ids_str
                if ord(c) not in IDC_OPERATORS and _is_han_component(c) and c != char
            ]
            if components:
                result[char] = components
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--unihan-zip", type=Path, default=None)
    parser.add_argument("--ids-file", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Parse and report counts, write nothing")
    args = parser.parse_args()

    unihan_zip = args.unihan_zip or Path("/tmp/Unihan.zip")
    if not unihan_zip.exists():
        download(UNIHAN_URL, unihan_zip)

    ids_file = args.ids_file or Path("/tmp/ids.txt")
    if not ids_file.exists():
        download(IDS_URL, ids_file)

    extract_dir = Path("/tmp/unihan_extracted")
    if not (extract_dir / "Unihan_Variants.txt").exists():
        print(f"Extracting {unihan_zip} ...", flush=True)
        with zipfile.ZipFile(unihan_zip) as z:
            z.extractall(extract_dir)

    print("Parsing Unihan variants...", flush=True)
    variants = parse_unihan_variants(extract_dir / "Unihan_Variants.txt", CJK_UNIFIED_SCOPE)
    print(f"  {len(variants)} chars with variant data", flush=True)

    print("Parsing Unihan readings...", flush=True)
    readings = parse_unihan_readings(extract_dir / "Unihan_Readings.txt", CJK_UNIFIED_SCOPE)
    print(f"  {len(readings)} chars with reading data", flush=True)

    print("Parsing IDS decomposition...", flush=True)
    ids_data = parse_ids(ids_file, CJK_UNIFIED_SCOPE)
    print(f"  {len(ids_data)} chars with decomposition data", flush=True)

    all_chars = sorted(set(variants) | set(readings) | set(ids_data), key=ord)
    print(f"Total characters in scope: {len(all_chars)}", flush=True)

    char_script: dict[str, str] = {}
    ambiguous = 0
    for ch in all_chars:
        v = variants.get(ch, {})
        has_simp, has_trad = v.get("simplified") is not None, v.get("traditional") is not None
        if has_simp and has_trad:
            ambiguous += 1
            continue
        char_script[ch] = "zh-Hans" if has_trad else ("zh-Hant" if has_simp else "zh-Hani")
    print(f"  {ambiguous} ambiguous chars skipped (both variant fields point differently)", flush=True)

    if args.dry_run:
        print(f"\nDry run — {len(char_script)} characters would be imported. Sample:")
        for ch in all_chars[:20]:
            print(f"  {ch}  script={char_script.get(ch, 'SKIPPED')}  "
                  f"def={readings.get(ch, {}).get('definition')}  "
                  f"components={ids_data.get(ch)}")
        return

    conn = get_db()
    already = conn.execute("SELECT COUNT(*) FROM kanji WHERE script != 'ja-kanji'").fetchone()[0]
    if already > 0:
        print(f"{already} non-Japanese kanji rows already present; refusing to run again "
              f"(not safe to resume a partial run — delete the hanzi-* rows first if needed).")
        conn.close()
        return

    # ── Pass 1: kanji rows + basic aliases (character, keyword, pinyin) ────────
    for ch in char_script:
        cid = f"hanzi-{ord(ch):x}"
        definition = readings.get(ch, {}).get("definition")
        keyword = definition.split(";")[0].strip().lower() if definition else ch
        conn.execute(
            "INSERT OR IGNORE INTO kanji (id, character, keyword, owner_id, visibility, script) "
            "VALUES (?, ?, ?, 1, 'public', ?)",
            (cid, ch, keyword, char_script[ch])
        )
        _insert_alias(conn, cid, ch)
        if keyword != ch:
            _insert_alias(conn, cid, keyword)
        mandarin = readings.get(ch, {}).get("mandarin")
        if mandarin:
            _insert_alias(conn, cid, _strip_pinyin_tones(mandarin))
    print(f"Inserted {len(char_script)} hanzi kanji rows.", flush=True)

    # ── Pass 2: simplified <-> traditional variant links ────────────────────────
    linked = 0
    for ch, v in variants.items():
        if ch not in char_script:
            continue
        target = v.get("simplified") or v.get("traditional")
        if target and target in char_script:
            conn.execute(
                "UPDATE kanji SET variant_of = ? WHERE id = ?",
                (f"hanzi-{ord(target):x}", f"hanzi-{ord(ch):x}")
            )
            linked += 1
    print(f"Linked {linked} simplified<->traditional variant pairs.", flush=True)

    # ── Pass 3: IDS decompositions (single shared char_lookup for performance,
    # built after Pass 1 so it sees every hanzi row just inserted in this same
    # uncommitted transaction — reads see a connection's own uncommitted writes) ──
    char_lookup = _build_char_lookup(conn)
    decomps_created = 0
    for ch, components in ids_data.items():
        if ch not in char_script:
            continue
        cid = f"hanzi-{ord(ch):x}"
        expanded_terms = expand_part_terms(conn, components, char_lookup)
        cur = conn.execute(
            "INSERT INTO decompositions (kanji_id, owner_id, visibility, label) VALUES (?, 1, 'public', 'ids')",
            (cid,)
        )
        conn.executemany(
            "INSERT INTO parts (kanji_id, part_term, position, decomposition_id) VALUES (?, ?, ?, ?)",
            [(cid, term, pos, cur.lastrowid) for pos, term in enumerate(expanded_terms)]
        )
        decomps_created += 1
    print(f"Created {decomps_created} IDS-derived decompositions.", flush=True)

    conn.commit()
    conn.close()
    print("Hanzi import complete.", flush=True)


if __name__ == "__main__":
    main()
