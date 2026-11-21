#!/usr/bin/env python3
"""Export the live database as a standalone, documented dataset.

Why this exists: the repository is an application, not a dataset. `data.txt`
is a bespoke colon-delimited seed file, it carries no Chinese rows at all
(those are written straight into SQLite by `import_hanzi.py`), and `kanji.db`
— the only place the audit's corrections actually live — is gitignored. So
somebody who wants the decomposition data cannot get it by cloning the repo.
This script produces the thing they would actually want: flat CSVs, one row
per fact, with every name tagged by where it came from.

Two sources, same output:

    ./export_dataset.py --from-db kanji.db --out ../dataset
    ./export_dataset.py --from-api --out ../dataset          # anywhere

`--from-db` is for running on prod, where the whole database is right there.
`--from-api` enumerates every public character from the deployed sitemap and
reads each one through the public API, so it works from a laptop with no
server access — slower (~9k requests), and it sees exactly what an anonymous
visitor sees, which is the right scope for something being published anyway.

Provenance is the point, not a footnote. `--open-only` drops the two name
sets that cannot be redistributed: Heisig's frame keywords and primitive
names (his book is copyrighted; they are identified by matching
`heisig-kanjis.csv`, the same CSV the import reads), and the WaniKani radical
names (Tofugu's). What survives is the structural data — which shapes a
character is built from, keyed by glyph rather than by anyone's English name
for it — plus readings from kanjidic2/Unihan and this project's own work.

Stdlib only, so the system python3 runs it.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_SITE = "https://kumiji.kermit.is-a.dev"
HEISIG_CSV = Path(__file__).parent / "heisig-kanjis.csv"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Alias owners that are pseudo-accounts rather than real contributors.
OWNER_RU = "ru-aliases"
OWNER_WANIKANI = "wanikani-aliases"
OWNER_SYSTEM = "system"

# Name provenance classes. The first two cannot be published openly.
SRC_HEISIG = "heisig"            # Remembering the Kanji, copyrighted
SRC_WANIKANI = "wanikani"        # WaniKani radical names, Tofugu's
SRC_RU = "ru-machine"            # machine-translated by this project
SRC_IDENTIFIER = "identifier"    # the glyph, the row id, the frame number
SRC_PROJECT = "project-or-open"  # this project's work, or open-data derived
RESTRICTED = {SRC_HEISIG, SRC_WANIKANI}


def heisig_names() -> set[str]:
    """Every name the book supplies: frame keywords and component names.

    Both 5th- and 6th-edition keyword columns, plus the semicolon-separated
    `components` column, lowercased and stripped. Matching a name against
    this set is what `provenance_report.py --list-heisig` does against the
    live database; doing it from the CSV keeps this script runnable without
    one.
    """
    if not HEISIG_CSV.exists():
        sys.exit(f"{HEISIG_CSV} missing; needed to identify Heisig-derived names")
    names: set[str] = set()
    with HEISIG_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            for col in ("keyword_5th_ed", "keyword_6th_ed"):
                if v := (row.get(col) or "").strip().lower():
                    names.add(v)
            for part in (row.get("components") or "").split(";"):
                if v := part.strip().lower():
                    names.add(v)
    names.discard("")
    return names


def classify(alias: str, owner: str, row: dict, heisig: set[str]) -> str:
    """Where one name for one character came from."""
    if owner == OWNER_WANIKANI:
        return SRC_WANIKANI
    if owner == OWNER_RU:
        return SRC_RU
    a = alias.strip()
    if a == (row.get("character") or "") or a == row["id"]:
        return SRC_IDENTIFIER
    if row.get("frame") is not None and a == str(row["frame"]):
        return SRC_IDENTIFIER
    if a.lower() in heisig:
        return SRC_HEISIG
    return SRC_PROJECT


# ---------------------------------------------------------------- API source

def _get(url: str, retries: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kumiji-export"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — retry anything transient
            last = e
            time.sleep(2 ** attempt * 0.5)
    raise RuntimeError(f"GET {url} failed after {retries} tries: {last}")


def ids_from_sitemap(site: str) -> list[str]:
    """Every public character id, read from the deployed sitemap."""
    index = ET.fromstring(_get(f"{site}/sitemap.xml"))
    urls: list[str] = []
    for loc in index.findall("sm:sitemap/sm:loc", SITEMAP_NS):
        chunk = ET.fromstring(_get(loc.text.strip()))
        urls += [u.text.strip() for u in chunk.findall("sm:url/sm:loc", SITEMAP_NS)]
    ids = set()
    for u in urls:
        m = re.search(r"/kanji/([^/]+)\.html$", u)
        if m and not m.group(1).startswith("browse-"):
            ids.add(m.group(1))
    return sorted(ids)


def rows_from_api(site: str, workers: int, cache: Path | None = None) -> list[dict]:
    ids = ids_from_sitemap(site)
    print(f"{len(ids)} characters listed in the sitemap", file=sys.stderr)
    out: list[dict] = []
    have: set[str] = set()

    # Records are appended to the cache as they arrive, not held until the end:
    # a full run is ~9k requests against a small VM that does not take kindly to
    # concurrency, so it takes the better part of an hour, and losing all of it
    # to one interruption is not acceptable. Re-running picks up where it left
    # off instead.
    if cache:
        if cache.exists():
            with cache.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # a half-written final line from a hard kill
                    if row.get("id"):
                        out.append(row)
                        have.add(row["id"])
            if have:
                print(f"resuming: {len(have)} already cached in {cache}", file=sys.stderr)
        cache.parent.mkdir(parents=True, exist_ok=True)

    todo = [i for i in ids if i not in have]
    print(f"{len(todo)} to fetch", file=sys.stderr)
    done = 0

    def fetch(cid: str) -> dict | None:
        try:
            return json.loads(_get(f"{site}/kanji/api/kanji/{cid}"))
        except Exception as e:  # noqa: BLE001
            print(f"  ! {cid}: {e}", file=sys.stderr)
            return None

    fh = cache.open("a", encoding="utf-8") if cache else None
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for row in pool.map(fetch, todo):
                done += 1
                if done % 250 == 0:
                    print(f"  {done}/{len(todo)}", file=sys.stderr, flush=True)
                if row:
                    out.append(row)
                    if fh:
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                        fh.flush()
    finally:
        if fh:
            fh.close()
    return out


# ----------------------------------------------------------------- DB source

def rows_from_db(path: Path) -> list[dict]:
    """Same shape the API returns, straight out of SQLite (public rows only)."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    chars = conn.execute(
        "SELECT * FROM kanji WHERE visibility = 'public' ORDER BY id"
    ).fetchall()

    aliases: dict[str, list[dict]] = {}
    for r in conn.execute(
        "SELECT a.kanji_id, a.alias, COALESCE(u.username, 'system') AS owner "
        "FROM aliases a LEFT JOIN users u ON u.id = a.owner_id "
        "WHERE a.visibility = 'public'"
    ):
        aliases.setdefault(r["kanji_id"], []).append({"alias": r["alias"], "owner": r["owner"]})

    decs: dict[str, dict[int, dict]] = {}
    for r in conn.execute(
        "SELECT d.id, d.kanji_id, d.label, p.part_term, p.position "
        "FROM decompositions d JOIN parts p ON p.decomposition_id = d.id "
        "WHERE d.visibility = 'public' ORDER BY d.kanji_id, d.id, p.position"
    ):
        slot = decs.setdefault(r["kanji_id"], {}).setdefault(
            r["id"], {"id": r["id"], "label": r["label"], "parts_detail": []}
        )
        slot["parts_detail"].append({"term": r["part_term"], "id": None, "character": None})

    out = []
    for c in chars:
        row = dict(c)
        row["aliases"] = aliases.get(c["id"], [])
        row["decompositions"] = list(decs.get(c["id"], {}).values())
        out.append(row)
    conn.close()
    return out


# -------------------------------------------------------------------- output

def write_dataset(rows: list[dict], out: Path, open_only: bool) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    heisig = heisig_names()
    counts = {"characters": 0, "components": 0, "names": 0, "names_withheld": 0}

    with (out / "characters.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "id", "character", "codepoint", "script", "stroke_count", "jlpt",
            "rtk_frame", "onyomi", "kunyomi", "pinyin", "variant_of",
            "is_primitive", "decomposition_count",
        ])
        for r in sorted(rows, key=lambda x: x["id"]):
            ch = r.get("character") or ""
            cp = f"U+{ord(ch):04X}" if len(ch) == 1 else ""
            w.writerow([
                r["id"], ch, cp, r.get("script") or "", r.get("stroke_count") or "",
                r.get("jlpt") or "", r.get("frame") if r.get("frame") is not None else "",
                r.get("onyomi") or "", r.get("kunyomi") or "", r.get("pinyin") or "",
                r.get("variant_of") or "",
                "yes" if r.get("frame") is None and not str(r["id"]).startswith("hanzi-") else "no",
                len(r.get("decompositions") or []),
            ])
            counts["characters"] += 1

    with (out / "components.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "character_id", "character", "decomposition", "label",
            "position", "component_id", "component_character",
        ])
        for r in sorted(rows, key=lambda x: x["id"]):
            for n, dec in enumerate(r.get("decompositions") or [], start=1):
                label = dec.get("label") or "primary"
                for pos, part in enumerate(dec.get("parts_detail") or [], start=1):
                    w.writerow([
                        r["id"], r.get("character") or "", n, label, pos,
                        part.get("id") or "",
                        part.get("character") or part.get("term") or "",
                    ])
                    counts["components"] += 1

    with (out / "names.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["character_id", "character", "name", "source"])
        for r in sorted(rows, key=lambda x: x["id"]):
            seen = set()
            for a in r.get("aliases") or []:
                name = (a.get("alias") or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                src = classify(name, a.get("owner") or OWNER_SYSTEM, r, heisig)
                if open_only and src in RESTRICTED:
                    counts["names_withheld"] += 1
                    continue
                w.writerow([r["id"], r.get("character") or "", name, src])
                counts["names"] += 1
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--from-db", type=Path, help="read a local kanji.db instead of the API")
    src.add_argument("--from-api", action="store_true", help="read the deployed site (default)")
    p.add_argument("--site", default=DEFAULT_SITE)
    p.add_argument("--out", type=Path, required=True, help="directory to write the CSVs into")
    p.add_argument("--workers", type=int, default=2,
                   help="concurrent API requests (default 2 — the live VM degrades badly\n                        under concurrency: 6 workers pushed it from 0.2s to 10s per request)")
    p.add_argument("--open-only", action="store_true",
                   help="omit Heisig and WaniKani names, which cannot be redistributed")
    p.add_argument("--raw", type=Path,
                   help="JSONL cache of the fetched records; with --from-api it is written\n                        as the run proceeds and reused to resume an interrupted one")
    args = p.parse_args()

    if args.from_db:
        rows = rows_from_db(args.from_db)
        if args.raw:
            args.raw.parent.mkdir(parents=True, exist_ok=True)
            with args.raw.open("w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        rows = rows_from_api(args.site.rstrip("/"), args.workers, args.raw)
    if not rows:
        sys.exit("no rows read")

    counts = write_dataset(rows, args.out, args.open_only)
    print(
        f"wrote {counts['characters']} characters, {counts['components']} component rows, "
        f"{counts['names']} names"
        + (f" ({counts['names_withheld']} withheld as non-redistributable)" if args.open_only else "")
        + f" to {args.out}"
    )


if __name__ == "__main__":
    main()
