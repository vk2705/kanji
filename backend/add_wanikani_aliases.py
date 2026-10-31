#!/usr/bin/env python3
"""
add_wanikani_aliases.py — attach each WaniKani radical's name to the row for its
glyph, so a WaniKani learner can search by the names they already know
("tsunami" + "mouth", "triceratops" + "sun"). Owner request, 2026-10-31.

## Where the names come from, and why a separate account

`wanikani_radicals.json` is WaniKani's public radical list (wanikani.com/radicals,
all six difficulty bands, levels 1-60, fetched 2026-10-31): level, slug, glyph and
name for 491 radicals. The names are Tofugu's own creative work, not open data,
so they are kept apart from everything else: owned by a dedicated `wanikani-aliases`
pseudo-account (auth_provider='system', no password, the `ru-aliases` pattern), so
every one of them is attributable on the detail page, countable by
provenance_report.py, and removable in one command (`--remove-all`). The owner
chose to add them and remove them if WaniKani objects.

## Matching

By glyph, not by name: each radical's name goes on the system rows whose
`character` is WaniKani's glyph — the ja-kanji rows, or the zh-* rows when no
Japanese row has the glyph. Ten radicals are written with a lookalike (katakana
ト for 卜, half-width ｲ for 亻, …); `map_to` in the JSON gives the real glyph,
each pair verified by rendering side by side (render_glyphs.py, 2026-10-31).
Seven radicals whose glyph has only a zh-* row here are written with a stand-in
in the Japanese decompositions (海 = 水 + 毎, not 氵; 利 = 禾 + 刀); `ja_glyph`
names that stand-in, read off our own system decompositions of typical hosts,
and the name goes on its ja-kanji row too, or Japanese-mode search would never
see it: 氵→水, 刂→刀, 爫→爪, 覀→西, 耂→老, 乚→乙, 丨→｜.
Skipped: the 15 image-only radicals (no Unicode glyph to match on), and those
whose glyph has no row here (ホ Angel, L Lion, 㠯 Bear …) — the report lists them.

A name a row already carries from any owner is not duplicated. A WaniKani name
that is also another row's name ("ground" is 土 here, 一 in WaniKani) makes the
term ambiguous on purpose: parts search then offers both meanings in its picker.

Usage:
    ./add_wanikani_aliases.py --dry-run
    ./add_wanikani_aliases.py
    ./add_wanikani_aliases.py --remove-all     # takedown: delete every WaniKani alias

Safe to re-run: it converges the account's aliases on the JSON, adding what is
missing and deleting what the JSON no longer produces.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

USERNAME = "wanikani-aliases"
DISPLAY_NAME = "WaniKani radical names"
DATA_PATH = Path(__file__).parent / "wanikani_radicals.json"


def ensure_account(conn) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO users (username, auth_provider, display_name) VALUES (?, 'system', ?)",
        (USERNAME, DISPLAY_NAME),
    )
    conn.commit()
    return conn.execute("SELECT id FROM users WHERE username = ?", (USERNAME,)).fetchone()["id"]


def target_rows(conn, glyph: str) -> list:
    rows = conn.execute(
        "SELECT id, character, script FROM kanji "
        "WHERE owner_id = 1 AND visibility = 'public' AND character = ? ORDER BY id",
        (glyph,),
    ).fetchall()
    ja = [r for r in rows if r["script"] == "ja-kanji"]
    return ja or rows


def wanted_aliases(conn) -> tuple[dict[tuple[str, str], dict], list[str]]:
    """{(kanji_id, alias): radical} for every alias the JSON calls for, plus skip notes."""
    wanted, skipped = {}, []
    for radical in json.loads(DATA_PATH.read_text()):
        glyph = radical.get("map_to") or radical["char"]
        name = radical["meaning"].strip().lower()
        if not glyph:
            skipped.append(f"L{radical['level']} {radical['meaning']}: image-only, no glyph")
            continue
        rows = target_rows(conn, glyph)
        if not rows:
            skipped.append(f"L{radical['level']} {radical['char']} {radical['meaning']}: no row for {glyph}")
            continue
        if radical.get("ja_glyph"):
            rows += [r for r in target_rows(conn, radical["ja_glyph"]) if r["script"] == "ja-kanji"]
        for row in rows:
            wanted[(row["id"], name)] = radical
    return wanted, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--remove-all", action="store_true", help="delete every alias this account owns")
    args = parser.parse_args()

    conn = database.get_db()
    owner_id = ensure_account(conn)
    current = {(r["kanji_id"], r["alias"]) for r in conn.execute(
        "SELECT kanji_id, alias FROM aliases WHERE owner_id = ?", (owner_id,))}

    if args.remove_all:
        print(f"{'Would remove' if args.dry_run else 'Removed'} {len(current)} WaniKani alias(es)")
        if not args.dry_run:
            conn.execute("DELETE FROM aliases WHERE owner_id = ?", (owner_id,))
            conn.commit()
        return

    wanted, skipped = wanted_aliases(conn)
    # Names a row already has from another owner (system, ru-aliases, a user) add nothing.
    already = {(r["kanji_id"], r["alias"].lower()) for r in conn.execute(
        "SELECT kanji_id, alias FROM aliases WHERE owner_id != ? AND visibility = 'public'", (owner_id,))}
    already |= {(r["id"], (r["keyword"] or "").lower()) for r in conn.execute(
        "SELECT id, keyword FROM kanji WHERE visibility = 'public'")}
    wanted = {k: v for k, v in wanted.items() if k not in already}

    to_add = sorted(set(wanted) - current)
    to_remove = sorted(current - set(wanted))
    for kanji_id, alias in to_add:
        r = wanted[(kanji_id, alias)]
        print(f"  + {kanji_id} <- {alias}  (WaniKani {r['char']}, L{r['level']})")
        if not args.dry_run:
            database.create_alias(conn, kanji_id, owner_id, alias, "public")
    for kanji_id, alias in to_remove:
        print(f"  - {kanji_id} {alias}")
        if not args.dry_run:
            conn.execute("DELETE FROM aliases WHERE owner_id = ? AND kanji_id = ? AND alias = ?",
                         (owner_id, kanji_id, alias))
    conn.commit()

    print(f"\nSkipped {len(skipped)} radical(s):")
    for note in skipped:
        print(f"  {note}")
    verb = "Would add" if args.dry_run else "Added"
    print(f"\n{verb} {len(to_add)}, {'would remove' if args.dry_run else 'removed'} {len(to_remove)}; "
          f"{len(current) - len(to_remove)} already present. Account id={owner_id}.")


if __name__ == "__main__":
    main()
