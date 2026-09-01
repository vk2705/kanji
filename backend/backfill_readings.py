#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
backfill_readings.py — populate kanji.onyomi/kunyomi/pinyin on an already-seeded
kanji.db (owner-requested, 2026-09-01: display each kanji's real-world Japanese/
Chinese pronunciations, not just its RTK keyword).

Why this is a separate script rather than folded into import_data()/sync_system_data.py:
those two only ever read heisig-kanjis.csv/data.txt/data_from_pdf.txt, none of which
carry reading data at all, and import_hanzi.py refuses to run a second time against a
populated DB (its one-time-seed guard). Readings instead come straight from two
external reference files, independent of the primitive/decomposition data pipeline:

  - kanjidic2.xml.gz (ja_on/ja_kun elements) -> kanji.onyomi/kunyomi, for
    script='ja-kanji' rows. Same source import_rtk.py already uses for keyword/
    frame lookups, just not previously parsed for readings.
  - Unihan_Readings.txt's kMandarin field -> kanji.pinyin, for script='zh-*' rows.
    Same file/field import_hanzi.py already parses (currently only to seed a
    tone-stripped pinyin alias) -- this script keeps the toned form for display
    instead of stripping it.

Matches by character, not by id, so it's agnostic to whether a row is a system
(owner_id=1) or user-contributed kanji sharing that glyph -- a user's own private
明 gets the same real-world readings as the system's public rtk20.

Safe to re-run: UPDATEs only rows whose corresponding column is still NULL, unless
--force is given (re-checks and overwrites every matched row, e.g. after a kanjidic2/
Unihan version bump). Never touches decompositions, aliases, or any other column.

Usage:
    python3 backfill_readings.py [--kanjidic2 PATH] [--unihan-zip PATH] [--dry-run] [--force]

Downloads kanjidic2.xml.gz and Unihan.zip to /tmp if paths aren't given (same URLs
import_rtk.py / import_hanzi.py already use, plus an HTTPS mirror for kanjidic2 since
the plain-HTTP EDRDG FTP mirror those scripts default to was unreachable from this
sandbox when this script was first written -- see their own --kanjidic2/--unihan-zip
flags if a different mirror or a pre-downloaded file is needed instead).
"""
import argparse
import gzip
import sys
import zipfile
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

KANJIDIC2_URL = "https://www.edrdg.org/kanjidic/kanjidic2.xml.gz"
UNIHAN_URL = "https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip"


def download(url: str, dest: Path):
    print(f"Downloading {url} ...", flush=True)
    urllib.request.urlretrieve(url, dest)
    print(f"  -> saved to {dest}", flush=True)


def load_kanjidic2_readings(path: Path) -> dict[str, dict]:
    """{char: {'onyomi': 'メイ, ミョウ, ミン' or None, 'kunyomi': '...' or None}}.
    Readings kept in kanjidic2's own order (roughly most-common-first); duplicates
    within a type collapsed. Okurigana dots/leading hyphens (e.g. 'あ.かり', '-あ.け')
    are kept as-is -- that's kanjidic2's own notation for the okurigana boundary and
    prefix/suffix-only readings, not noise to strip."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as f:
        data = f.read()
    root = ET.fromstring(data)
    result: dict[str, dict] = {}
    for c in root.findall("character"):
        lit = c.find("literal").text
        on = []
        kun = []
        for r in c.findall(".//reading"):
            rt = r.get("r_type")
            if rt == "ja_on" and r.text not in on:
                on.append(r.text)
            elif rt == "ja_kun" and r.text not in kun:
                kun.append(r.text)
        if on or kun:
            result[lit] = {
                "onyomi": ", ".join(on) if on else None,
                "kunyomi": ", ".join(kun) if kun else None,
            }
    return result


def load_unihan_pinyin(path: Path) -> dict[str, str]:
    """{char: pinyin} from Unihan_Readings.txt's kMandarin field -- Unicode's own
    "most customary" reading for a polyphonic character, same field import_hanzi.py
    already uses (there, stripped of tone marks, for a search alias; here, kept
    toned, for display)."""
    result: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) != 3:
                continue
            cp_str, field, value = cols
            if field != "kMandarin":
                continue
            char = chr(int(cp_str[2:], 16))
            result[char] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kanjidic2", type=Path, default=None)
    parser.add_argument("--unihan-zip", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Parse and report counts, write nothing")
    parser.add_argument("--force", action="store_true",
                         help="Overwrite rows that already have a value, not just NULL ones")
    args = parser.parse_args()

    kanjidic2_path = args.kanjidic2 or Path("/tmp/kanjidic2.xml.gz")
    if not kanjidic2_path.exists():
        download(KANJIDIC2_URL, kanjidic2_path)

    unihan_zip = args.unihan_zip or Path("/tmp/Unihan.zip")
    if not unihan_zip.exists():
        download(UNIHAN_URL, unihan_zip)
    extract_dir = Path("/tmp/unihan_extracted")
    readings_txt = extract_dir / "Unihan_Readings.txt"
    if not readings_txt.exists():
        print(f"Extracting Unihan_Readings.txt from {unihan_zip} ...", flush=True)
        with zipfile.ZipFile(unihan_zip) as z:
            z.extract("Unihan_Readings.txt", extract_dir)

    print("Parsing kanjidic2 readings...", flush=True)
    ja_readings = load_kanjidic2_readings(kanjidic2_path)
    print(f"  {len(ja_readings)} characters with on'yomi/kun'yomi data", flush=True)

    print("Parsing Unihan pinyin...", flush=True)
    pinyin = load_unihan_pinyin(readings_txt)
    print(f"  {len(pinyin)} characters with pinyin data", flush=True)

    conn = database.get_db()

    null_clause = "" if args.force else " AND onyomi IS NULL AND kunyomi IS NULL"
    ja_rows = conn.execute(
        f"SELECT id, character FROM kanji WHERE script = 'ja-kanji'{null_clause}"
    ).fetchall()
    ja_updates = [
        (v["onyomi"], v["kunyomi"], r["id"])
        for r in ja_rows
        if (v := ja_readings.get(r["character"]))
    ]

    py_null_clause = "" if args.force else " AND pinyin IS NULL"
    zh_rows = conn.execute(
        f"SELECT id, character FROM kanji WHERE script != 'ja-kanji'{py_null_clause}"
    ).fetchall()
    zh_updates = [
        (pinyin[r["character"]], r["id"])
        for r in zh_rows
        if r["character"] in pinyin
    ]

    print(f"\n{'Would update' if args.dry_run else 'Updating'} "
          f"{len(ja_updates)} ja-kanji rows with onyomi/kunyomi "
          f"(of {len(ja_rows)} candidates), "
          f"{len(zh_updates)} zh-* rows with pinyin (of {len(zh_rows)} candidates).")

    if args.dry_run:
        for onyomi, kunyomi, kid in ja_updates[:10]:
            print(f"  {kid}: onyomi={onyomi!r} kunyomi={kunyomi!r}")
        for py, kid in zh_updates[:10]:
            print(f"  {kid}: pinyin={py!r}")
        return

    conn.executemany("UPDATE kanji SET onyomi = ?, kunyomi = ? WHERE id = ?", ja_updates)
    conn.executemany("UPDATE kanji SET pinyin = ? WHERE id = ?", zh_updates)
    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
