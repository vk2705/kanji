#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
add_ru_aliases.py — attach a Russian-language alias to every kanji/hanzi row
whose English keyword we have a translation for (owner-requested, 2026-09-01:
"перевести названия каждого иероглифа по хейсигу на русский и добавить как
алиас" — translate each kanji's Heisig name into Russian and add it as an
alias, so a Russian-speaking user can search by the Russian word too).

## Why a separate pseudo-account, not owner_id=1

These aliases are machine-translated, not part of Heisig's book or the CSV/
data.txt source files — attaching them to the reserved system account
(owner_id=1) would make them indistinguishable from real Heisig data. Instead
this script creates (idempotently) a dedicated account, 'ru-aliases', with no
password (auth_provider='system', same pattern the reserved system account
itself uses) so nobody can log in as it — it's edited only by re-running this
script, matching the 'ai-mnemonics' pseudo-account CLAUDE.md already queues
for bulk LLM-generated mnemonics, applied here to bulk LLM-generated
translations instead. Its aliases are public by default (visibility='public')
so any anonymous visitor benefits from them immediately.

## Matching strategy

Matches by *keyword text*, not by id or script, against every public,
system-owned (owner_id=1) kanji/hanzi row — so translating one English word
("one") automatically covers every row that happens to share that exact
keyword, ja-kanji and every zh-* script alike (e.g. rtk1/一, hanzi-4e00/一,
and rarer synonyms like hanzi-5e7a/幺 which CSV/Unihan also gloss "one").
This is deliberate: Heisig's RTK keyword and a hanzi's Unihan-derived English
gloss are both just English labels for a meaning, and a correct Russian
translation of that meaning is correct for any row carrying it, regardless of
which pipeline (import_data vs import_hanzi) originally created the row.

TRANSLATIONS only covers a pilot batch (RTK frames 1-100) as of this
writing — see docs/2026-08-search-quality-audit.md for the reasoning behind
starting with a small, spot-checked batch rather than trying to translate
this app's ~24000 kanji+hanzi keywords in one pass. Extend the dict and
re-run to add more; already-inserted aliases are left untouched (INSERT OR
IGNORE, same idempotency guarantee create_alias() already gives every other
caller).

Usage:
    python3 add_ru_aliases.py [--dry-run] [--limit N]

Safe to re-run: every alias insert is INSERT OR IGNORE against the
UNIQUE(kanji_id, alias, owner_id) constraint, so a repeat run with an
unchanged TRANSLATIONS dict adds nothing new.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

RU_ALIASES_USERNAME = "ru-aliases"
RU_ALIASES_DISPLAY_NAME = "Russian Aliases (auto-translated)"

# English keyword (lowercase, exact match against kanji.keyword) -> Russian
# translation. Pilot batch: RTK frames 1-100. Each was translated by hand
# against the real keyword text pulled from a live-imported DB, not guessed
# from memory of what frame N "usually" is -- see the audit doc entry for
# spot-check notes on the handful of non-obvious ones (旬/"decameron" ->
# "декада", since Heisig's keyword is itself a wordplay on a 10-day period;
# 中/"in" -> "внутри" rather than the bare preposition "в", closer to how
# 中 is actually used as a primitive meaning "inside/within").
TRANSLATIONS = {
    "one": "один",
    "two": "два",
    "three": "три",
    "four": "четыре",
    "five": "пять",
    "six": "шесть",
    "seven": "семь",
    "eight": "восемь",
    "nine": "девять",
    "ten": "десять",
    "mouth": "рот",
    "day": "день",
    "month": "месяц",
    "rice field": "рисовое поле",
    "eye": "глаз",
    "old": "старый",
    "i": "я",
    "risk": "риск",
    "companion": "товарищ",
    "bright": "яркий",
    "chant": "распевать",
    "sparkle": "сверкание",
    "goods": "товары",
    "spine": "хребет",
    "prosperous": "процветающий",
    "early": "ранний",
    "rising sun": "восходящее солнце",
    "generation": "поколение",
    "stomach": "желудок",
    "nightbreak": "рассвет",
    "gall bladder": "жёлчный пузырь",
    "span": "промежуток",
    "concave": "вогнутый",
    "convex": "выпуклый",
    "olden times": "старые времена",
    "oneself": "сам",
    "white": "белый",
    "hundred": "сто",
    "in": "внутри",
    "thousand": "тысяча",
    "tongue": "язык",
    "measuring box": "мерная коробка",
    "rise up": "подниматься",
    "round": "круглый",
    "measurement": "мера",
    "elbow": "локоть",
    "specialty": "специальность",
    "dr.": "доктор",
    "fortune-telling": "гадание",
    "above": "сверху",
    "below": "снизу",
    "eminent": "выдающийся",
    "morning": "утро",
    "derision": "насмешка",
    "only": "только",
    "shellfish": "ракушка",
    "pop song": "песня",
    "upright": "честный",
    "employee": "служащий",
    "post a bill": "расклеивать афиши",
    "see": "видеть",
    "newborn babe": "младенец",
    "beginning": "начало",
    "page": "страница",
    "stubborn": "упрямый",
    "mediocre": "посредственный",
    "ten thousand": "десять тысяч",
    "phrase": "фраза",
    "texture": "текстура",
    "decameron": "декада",
    "ladle": "половник",
    "bull's eye": "мишень",
    "neck": "шея",
    "fish guts": "рыбьи потроха",
    "riot": "бунт",
    "straightaway": "прямо",
    "tool": "инструмент",
    "true": "истинный",
    "craft": "ремесло",
    "left": "левый",
    "right": "правый",
    "possess": "обладать",
    "defeat": "поражение",
    "bribe": "взятка",
    "tribute": "дань",
    "paragraph": "абзац",
    "sword": "меч",
    "blade": "лезвие",
    "cut": "резать",
    "seduce": "соблазнять",
    "shining": "сияющий",
    "rule": "правило",
    "vice-": "вице-",
    "separate": "отдельный",
    "street": "улица",
    "village": "деревня",
    "can": "мочь",
    "place on the head": "класть на голову",
    "child": "ребёнок",
    "cavity": "полость",
}


def ensure_ru_aliases_account(conn) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO users (username, auth_provider, display_name) "
        "VALUES (?, 'system', ?)",
        (RU_ALIASES_USERNAME, RU_ALIASES_DISPLAY_NAME),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM users WHERE username = ?", (RU_ALIASES_USERNAME,)
    ).fetchone()
    return row["id"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None,
                         help="only process the first N matching rows (by id)")
    args = parser.parse_args()

    conn = database.get_db()
    owner_id = ensure_ru_aliases_account(conn)
    print(f"ru-aliases account id={owner_id}")

    placeholders = ",".join("?" * len(TRANSLATIONS))
    rows = conn.execute(
        f"SELECT id, character, keyword, script FROM kanji "
        f"WHERE owner_id = 1 AND visibility = 'public' AND keyword IN ({placeholders}) "
        f"ORDER BY id",
        list(TRANSLATIONS.keys()),
    ).fetchall()

    if args.limit:
        rows = rows[: args.limit]

    inserted = 0
    skipped_existing = 0
    for row in rows:
        ru = TRANSLATIONS[row["keyword"]]
        existing = conn.execute(
            "SELECT 1 FROM aliases WHERE kanji_id = ? AND alias = ? AND owner_id = ?",
            (row["id"], ru, owner_id),
        ).fetchone()
        if existing:
            skipped_existing += 1
            continue
        print(f"  {row['id']} {row['character']} ({row['keyword']}) -> {ru}")
        if not args.dry_run:
            database.create_alias(conn, row["id"], owner_id, ru, "public")
        inserted += 1

    print(f"\n{'Would insert' if args.dry_run else 'Inserted'} {inserted} alias(es), "
          f"{skipped_existing} already present. {len(rows)} row(s) matched "
          f"{len(TRANSLATIONS)} translated keyword(s).")


if __name__ == "__main__":
    main()
