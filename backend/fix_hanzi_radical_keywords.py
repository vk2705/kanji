#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
fix_hanzi_radical_keywords.py — one-off: replace mechanical Unihan-derived
keywords ("radical number 9", "kangxi radical 35", ...) on simplified/
traditional-only radical-shorthand rows with real descriptive keywords, so
they read like every other primitive in the database.

## Why this exists

Owner-reported (2026-09-30): 讠 (hanzi-8ba0, the simplified "speech" radical
used as a decomposition part 154 times) showed "simplified kangxi radical
149" instead of a name like "words" — Heisig's own name for its traditional
counterpart 言 (hanzi-8a00, rtk357: "words, speech"/"say"). Unihan's
kRSUnicode-derived data supplied a radical *number* as the gloss for several
radical-shorthand forms instead of a meaning, because these compressed forms
(亻 夊 爫 牜 罒 耂 覀 訁 讠 釒) either don't exist in
traditional/Japanese script (so Heisig never named them) or, for 艮, got the
mechanical gloss even though a same-glyph ja-kanji row (kangxi138/rad1015)
already carries a real name ("stopping").

This is NOT the data.txt/CSV pipeline (ja-kanji only, see
sync_system_data.py's own docstring) — these are zh-Hani/zh-Hans/zh-Hant
rows from the one-time import_hanzi.py seed, which has no equivalent
resync tool. A direct, targeted, idempotent UPDATE is the only option, same
as every other one-off audit/fix script in this repo.

## What each fix is based on

Every target has a full, unabbreviated sibling character already in this
database with an established keyword (Heisig's via a rtk*/kangxi* row, or
Unihan's own gloss on the hanzi-* row for that full character) — see the
comment beside each entry. Shapes were confirmed with render_glyphs.py
before writing this (project convention: never trust a codepoint table
alone, CLAUDE.md's "render it, don't just reason about it").

## Safety

Only touches kanji.keyword and the matching alias row (owner_id=1, whose
`alias` text equals the OLD keyword exactly) for the eleven ids below.
Never touches pinyin-romanization or bare-glyph alias rows. Idempotent:
running twice is a no-op the second time (the WHERE clause requires the
current keyword to still be an old mechanical string). --dry-run prints the
diff without writing. Back up kanji.db first if running against a live DB
with real user accounts (see backup_db.py).
"""
import argparse
import sqlite3

DB_PATH = "kanji.db"

# id -> (new_keyword, [old English alias fragments to drop], new_english_alias,
#         old_russian_alias, new_russian_alias)
# The old English alias fragments are whatever _load comma-split out of the
# old keyword (owner_id=1); the old Russian alias is add_ru_aliases.py's
# machine translation of the old keyword (owner_id=10, the ru-aliases
# pseudo-account — NOT owner_id=1). Other aliases (pinyin, bare glyph, any
# other synonym) are left untouched.
FIXES = {
    # aligns with hanzi-4eba 人 "man" / rtk1023 "person" — compressed left-side person radical
    "hanzi-4ebb": ("person", ["radical number 9"], "person", "радикальное число 9", "человек"),
    # radical 35, distinct from kangxi34 夂 "walking legs"/"go slowly" — traditional Kangxi gloss
    "hanzi-590a": ("winter walk", ["kangxi radical 35"], "winter walk", "канкси радикал 35", "зимняя походка"),
    # aligns with hanzi-722a 爪 "claw, nail, talon" — compressed top-of-kanji claw radical
    "hanzi-722b": ("claw", ["radical 87"], "claw", "радикальный 87", "коготь"),
    # aligns with hanzi-725b 牛 "cow, ox, bull" — compressed left-side ox radical
    "hanzi-725c": ("ox", ["an ox, a cow radical 93", "an ox", "a cow radical 93"], "ox", "корова радикал 93", "бык"),
    # aligns with hanzi-7f51 网 "net" — compressed top-of-kanji net radical
    "hanzi-7f52": ("net", ["radical 122"], "net", "радикальный 122", "сеть"),
    # aligns with hanzi-8001 老 "old, aged" — compressed top-of-kanji old-age radical
    "hanzi-8002": ("old", ["variant of kangxi radical 125"], "old", "вариант радикала кангси 125", "старый"),
    # aligns with kangxi138/rad1015 艮 "stopping" (same glyph, ja-kanji row)
    "hanzi-826e": ("stopping", ["kangxi radical 138"], "stopping", "канкси радикал 138", "остановка"),
    # aligns with hanzi-897f 西 "west(ern)" — variant top-of-kanji covering/west shape
    "hanzi-8980": ("west", ["variant of kangxi radical 146"], "west", "вариант радикала кангси 146", "запад"),
    # aligns with hanzi-8a00 言 "words, speech" — traditional (unsimplified) speech radical
    "hanzi-8a01": ("words", ["kangxi radical 149"], "words", "канкси радикал 149", "слова"),
    # aligns with hanzi-8a00 言 "words, speech" — simplified compressed speech radical (the reported case)
    "hanzi-8ba0": ("words", ["simplified kangxi radical 149"], "words", "упрощенный радикал кангси 149", "слова"),
    # aligns with hanzi-91d1 金 "gold" — traditional (unsimplified) gold radical
    "hanzi-91d2": ("gold", ["kangxi radical 167"], "gold", "канкси радикал 167", "золото"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    changed = 0
    for kid, (new_keyword, old_en_fragments, new_en_alias, old_ru_alias, new_ru_alias) in FIXES.items():
        row = c.execute("SELECT character, keyword FROM kanji WHERE id = ?", (kid,)).fetchone()
        if row is None:
            print(f"SKIP {kid}: no such kanji row")
            continue
        already_done = row["keyword"] == new_keyword
        if not already_done and row["keyword"] != old_en_fragments[0]:
            print(f"SKIP {kid} {row['character']}: keyword is '{row['keyword']}', not the expected old value '{old_en_fragments[0]}' — not touching")
            continue

        print(f"{'OK  ' if already_done else 'FIX '} {kid} {row['character']}: "
              f"{'already' if already_done else repr(row['keyword']) + ' ->'} '{new_keyword}'")
        if not already_done:
            changed += 1
        if args.dry_run:
            continue

        c.execute(
            "UPDATE kanji SET keyword = ? WHERE id = ? AND owner_id = 1",
            (new_keyword, kid),
        )
        # Replace the old mechanical alias text: the English fragment(s)
        # _load_parts_file comma-split out of the old keyword (owner_id=1),
        # collapsed to one new alias; and its Russian translation from
        # add_ru_aliases.py (owner_id=10, the ru-aliases pseudo-account, NOT
        # owner_id=1 — see CLAUDE.md's Internationalization section). Leave
        # every other alias (pinyin, bare glyph, any other synonym) alone.
        c.execute(
            "UPDATE aliases SET alias = ? WHERE kanji_id = ? AND owner_id = 1 AND alias = ?",
            (new_en_alias, kid, old_en_fragments[0]),
        )
        for extra_fragment in old_en_fragments[1:]:
            c.execute(
                "DELETE FROM aliases WHERE kanji_id = ? AND owner_id = 1 AND alias = ?",
                (kid, extra_fragment),
            )
        c.execute(
            "UPDATE aliases SET alias = ? WHERE kanji_id = ? AND owner_id = 10 AND alias = ?",
            (new_ru_alias, kid, old_ru_alias),
        )

    if args.dry_run:
        print(f"\n--dry-run: {changed} row(s) would change, nothing written")
        conn.rollback()
    else:
        conn.commit()
        print(f"\nCommitted: {changed} row(s) changed")


if __name__ == "__main__":
    main()
