#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""Derive the two small open-data files generate_seo_pages.py reads.

Run by hand when the sources update (rarely); the output is checked in so the
frontend build needs no network access and gives the same pages on every machine.

- seo_data/kanji_meanings.tsv — `character<TAB>meaning` for every kanjidic2
  character with English meanings: the first few, comma-joined. Used in the
  per-kanji page <title> and description. It is kanjidic2 data (EDRDG, CC BY-SA),
  NOT Heisig's keyword: the titles must not serve the book's keywords as the
  answer (see generate_seo_pages.render_page's docstring, docs/DATA_SOURCES.md).
- seo_data/common_hanzi.txt — one character per line: the hanzi worth offering
  to search engines. Unihan kTGH entries 1–3500 (level 1, the "common
  characters" of China's 2013 Table of General Standard Chinese Characters) plus
  every kGradeLevel character (Hong Kong primary-school traditional characters),
  plus the simplified/traditional counterparts of all of those. Hanzi pages not
  in this set get `noindex` and leave the sitemap.

Usage: ./build_seo_data.py [--kanjidic2 PATH] [--unihan PATH]   (downloads if omitted)
"""

from __future__ import annotations

import argparse
import gzip
import re
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

KANJIDIC2_URL = "https://www.edrdg.org/kanjidic/kanjidic2.xml.gz"
UNIHAN_URL = "https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip"
OUT_DIR = Path(__file__).resolve().parent / "seo_data"
MAX_MEANINGS = 3
# kanjidic2 tags radicals with index notes rather than meanings: 亻 "radical
# number 9", 一 "one radical (no.1)". Not something to put in a page title.
RADICAL_NOTE = re.compile(r"radical\s*(number|\(no)", re.IGNORECASE)
TGH_COMMON_LEVEL = 3500

HEADER_MEANINGS = (
    "# Derived from kanjidic2 (EDRDG, CC BY-SA 4.0, https://www.edrdg.org/edrdg/licence.html)\n"
    "# by backend/build_seo_data.py: English <meaning>s, first {n}. Do not edit by hand.\n"
)
HEADER_COMMON = (
    "# Derived from the Unicode Unihan database (Unicode License v3) by\n"
    "# backend/build_seo_data.py: kTGH 1-{n}, kGradeLevel, and their simplified/\n"
    "# traditional variants. Hanzi pages outside this list are noindex. Do not edit by hand.\n"
)


def kanjidic2_meanings(path: Path) -> dict[str, str]:
    with gzip.open(path, "rb") as f:
        root = ET.fromstring(f.read())
    result = {}
    for c in root.findall("character"):
        meanings = []
        for m in c.findall(".//meaning"):
            if m.get("m_lang") is None and m.text and m.text not in meanings and not RADICAL_NOTE.search(m.text):
                meanings.append(m.text)
        if meanings:
            result[c.find("literal").text] = ", ".join(meanings[:MAX_MEANINGS])
    return result


def unihan_common(path: Path) -> set[str]:
    common: set[str] = set()
    variants: dict[str, set[str]] = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            for raw in z.read(name).decode("utf-8").splitlines():
                if not raw.startswith("U+"):
                    continue
                cp, field, value = raw.split("\t", 2)
                char = chr(int(cp[2:], 16))
                if field == "kTGH":
                    # "2013:1234", possibly several space-separated entries
                    if any(int(v.split(":")[1]) <= TGH_COMMON_LEVEL for v in value.split()):
                        common.add(char)
                elif field == "kGradeLevel":
                    common.add(char)
                elif field in ("kSimplifiedVariant", "kTraditionalVariant"):
                    for v in value.split():
                        other = chr(int(v.split("<")[0][2:], 16))
                        variants.setdefault(char, set()).add(other)
    for char in list(common):
        common |= variants.get(char, set())
    return common


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kanjidic2", type=Path)
    parser.add_argument("--unihan", type=Path)
    args = parser.parse_args()
    tmp = Path(tempfile.mkdtemp())
    if not args.kanjidic2:
        args.kanjidic2 = tmp / "kanjidic2.xml.gz"
        urllib.request.urlretrieve(KANJIDIC2_URL, args.kanjidic2)
    if not args.unihan:
        args.unihan = tmp / "Unihan.zip"
        urllib.request.urlretrieve(UNIHAN_URL, args.unihan)

    OUT_DIR.mkdir(exist_ok=True)
    meanings = kanjidic2_meanings(args.kanjidic2)
    with open(OUT_DIR / "kanji_meanings.tsv", "w", encoding="utf-8") as f:
        f.write(HEADER_MEANINGS.format(n=MAX_MEANINGS))
        for char in sorted(meanings):
            f.write(f"{char}\t{meanings[char]}\n")
    common = unihan_common(args.unihan)
    with open(OUT_DIR / "common_hanzi.txt", "w", encoding="utf-8") as f:
        f.write(HEADER_COMMON.format(n=TGH_COMMON_LEVEL))
        for char in sorted(common):
            f.write(char + "\n")
    print(f"{len(meanings)} kanjidic2 meanings, {len(common)} common hanzi -> {OUT_DIR}")


if __name__ == "__main__":
    main()
