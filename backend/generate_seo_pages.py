#!/usr/bin/env python3
"""Build crawlable public kanji detail pages and their sitemap.

The interactive UI is a React SPA, but search crawlers need an HTML document at a
stable URL to reliably discover a kanji and its decomposition. This script writes
only anonymous/public data to frontend/public/kanji/ and sitemap.xml; Vite then
copies both to the deployed frontend directory.
"""

from __future__ import annotations

import argparse
import html
import shutil
import sqlite3
from pathlib import Path
from urllib.parse import quote


SITE_URL = "https://kanji.alteon.help"

# These pages are the project's crawlable public surface, so the credit that
# lives on the About page has to be on them too rather than one click away —
# a crawler and a first-time visitor both land here, not there. See
# docs/DATA_SOURCES.md for the full provenance.
ATTRIBUTION = """      <p>Frame numbers and many building-block names follow
        <a href="https://uhpress.hawaii.edu/title/remembering-the-kanji-1/">Remembering the
        Kanji</a> by James W. Heisig (University of Hawai&#39;i Press). This is an unofficial
        study aid, not affiliated with or endorsed by the author or publisher, and it does not
        reproduce the book&#39;s mnemonic stories.</p>
      <p>Structural decompositions from cjkvi-ids; readings and character data from kanjidic2
        and KRADFILE (EDRDG, CC BY-SA) and from the Unicode Consortium&#39;s Unihan database.
        <a href="https://github.com/vk2705/kanji/blob/master/docs/DATA_SOURCES.md">Full data
        provenance</a>.</p>
"""
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "frontend" / "public" / "kanji"
DEFAULT_SITEMAP = ROOT / "frontend" / "public" / "sitemap.xml"


def page_url(kanji_id: str) -> str:
    return f"{SITE_URL}/kanji/{quote(kanji_id, safe='')}.html"


def display_character(character: str | None) -> str:
    return "" if character in (None, "", "?", "??") else character


def part_label(part: dict) -> str:
    character = display_character(part.get("character"))
    keyword = part.get("keyword") or part.get("id") or "unnamed part"
    return f"{character} {keyword}".strip()


def render_page(entry: dict) -> str:
    character = display_character(entry["character"])
    keyword = entry["keyword"] or entry["id"]
    title = f"{character} {keyword} kanji decomposition | RTK Kanji Search".strip()
    decomposition_text = "; ".join(
        " + ".join(part_label(part) for part in decomposition["parts_detail"])
        for decomposition in entry["decompositions"]
        if decomposition["parts_detail"]
    )
    description = f"{character} ({keyword}) decomposition: {decomposition_text or 'not listed'}."
    alias_text = ", ".join(alias["alias"] for alias in entry["aliases"])
    metadata = []
    if entry.get("frame"):
        metadata.append(f"RTK frame {entry['frame']}")
    if entry.get("stroke_count"):
        metadata.append(f"{entry['stroke_count']} strokes")
    if entry.get("onyomi"):
        metadata.append(f"On'yomi: {entry['onyomi']}")
    if entry.get("kunyomi"):
        metadata.append(f"Kun'yomi: {entry['kunyomi']}")
    if entry.get("pinyin"):
        metadata.append(f"Pinyin: {entry['pinyin']}")

    decomposition_sections = []
    for number, decomposition in enumerate(entry["decompositions"], start=1):
        parts = decomposition["parts_detail"]
        if not parts:
            continue
        label = decomposition.get("label") or ("Primary decomposition" if number == 1 else f"Decomposition {number}")
        items = "\n".join(
            f'        <li><a href="{html.escape(page_url(part["id"]), quote=True)}">{html.escape(part_label(part))}</a></li>'
            if part.get("id") else f"        <li>{html.escape(part_label(part))}</li>"
            for part in parts
        )
        decomposition_sections.append(
            f"      <section>\n        <h2>{html.escape(label)}</h2>\n        <ol>\n{items}\n        </ol>\n      </section>"
        )

    canonical = page_url(entry["id"])
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <meta name="description" content="{html.escape(description, quote=True)}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="{html.escape(canonical, quote=True)}">
  </head>
  <body>
    <main>
      <p><a href="/">RTK Kanji Search</a></p>
      <h1>{html.escape(f'{character} {keyword}'.strip())}</h1>
      <p>Kanji ID: {html.escape(entry['id'])}</p>
      {f'<p>{html.escape("; ".join(metadata))}</p>' if metadata else ''}
      {f'<p>Also known as: {html.escape(alias_text)}</p>' if alias_text else ''}
      <h2>Decomposition</h2>
{chr(10).join(decomposition_sections) if decomposition_sections else '      <p>No public decomposition is listed.</p>'}
      <p><a href="/?kanji={quote(entry['id'], safe='')}">Open the interactive kanji page</a></p>
    </main>
    <footer>
{ATTRIBUTION}    </footer>
  </body>
</html>
"""


def write_sitemap(sitemap_path: Path, entries: list[dict]) -> None:
    urls = [
        (f"{SITE_URL}/", "weekly", "1.0"),
        (f"{SITE_URL}/privacy.html", "yearly", "0.2"),
        *[(page_url(entry["id"]), "weekly", "0.8") for entry in entries],
    ]
    body = "\n".join(
        f"  <url><loc>{html.escape(url)}</loc><changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>"
        for url, changefreq, priority in urls
    )
    sitemap_path.parent.mkdir(parents=True, exist_ok=True)
    sitemap_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n",
        encoding="utf-8",
    )


def generate(db_path: Path, output_dir: Path, sitemap_path: Path) -> int:
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        entry_rows = conn.execute(
            "SELECT id, character, keyword, frame, stroke_count, onyomi, kunyomi, pinyin "
            "FROM kanji WHERE visibility = 'public' ORDER BY id"
        ).fetchall()
        entries = [
            {
                **dict(row),
                "aliases": [],
                "decompositions": [],
            }
            for row in entry_rows
        ]
        entries_by_id = {entry["id"]: entry for entry in entries}
        decomposition_rows = conn.execute(
            "SELECT d.id, d.kanji_id, d.label, p.part_term, p.position "
            "FROM decompositions d "
            "JOIN parts p ON p.decomposition_id = d.id "
            "JOIN kanji k ON k.id = d.kanji_id "
            "WHERE d.visibility = 'public' AND k.visibility = 'public' "
            "ORDER BY d.kanji_id, (d.owner_id = 1) DESC, d.id, p.position"
        ).fetchall()
        decompositions: dict[int, dict] = {}
        for row in decomposition_rows:
            decomposition = decompositions.setdefault(
                row["id"],
                {"id": row["id"], "label": row["label"], "parts_detail": []},
            )
            decomposition["parts_detail"].append({"keyword": row["part_term"]})
            entry = entries_by_id[row["kanji_id"]]
            if decomposition not in entry["decompositions"]:
                entry["decompositions"].append(decomposition)
        for entry in entries:
            (output_dir / f"{quote(entry['id'], safe='')}.html").write_text(
                render_page(entry), encoding="utf-8"
            )
        write_sitemap(sitemap_path, entries)
    finally:
        conn.close()
    print(f"Generated {len(entries)} public kanji pages in {output_dir}")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(__file__).with_name("kanji.db"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sitemap", type=Path, default=DEFAULT_SITEMAP)
    args = parser.parse_args()
    generate(args.db, args.output_dir, args.sitemap)


if __name__ == "__main__":
    main()