#!/usr/bin/env python3
"""Build crawlable public kanji detail pages, browse hubs and the sitemap.

The interactive UI is a React SPA, but search crawlers need an HTML document at a
stable URL to reliably discover a kanji and its decomposition. This script writes
only anonymous/public data to frontend/public/kanji/ and the sitemap files; Vite
then copies them to the deployed frontend directory.

The sitemap is a sitemap *index* (/sitemap.xml) pointing at chunk files
(/sitemap-N.xml) of at most SITEMAP_CHUNK URLs each, rather than one 3.7 MB file
of 24k URLs: Search Console reported "Couldn't fetch" / "could not be read" for
the single file for weeks while serving it was verifiably fine, and small chunks
are both the documented-safe shape and easier to diagnose (each chunk gets its
own status line in Search Console).
"""

from __future__ import annotations

import argparse
import html
import shutil
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import quote


SITE_URL = "https://kanji.alteon.help"
MCP_URL = "https://kanjimcp.alteon.help/mcp"

# These pages are the project's crawlable public surface, so the credit that
# lives on the About page has to be on them too rather than one click away —
# a crawler and a first-time visitor both land here, not there. See
# docs/DATA_SOURCES.md for the full provenance.
BOOK_URL = "https://uhpress.hawaii.edu/title/remembering-the-kanji-1/"

ATTRIBUTION = f"""      <p>Frame numbers and many building-block names follow
        <a href="{BOOK_URL}">Remembering the
        Kanji</a> by James W. Heisig (University of Hawai&#39;i Press). This is an unofficial
        study aid, not affiliated with or endorsed by the author or publisher, and it does not
        reproduce the book&#39;s mnemonic stories.</p>
      <p>Structural decompositions from cjkvi-ids; readings and character data from kanjidic2
        and KRADFILE (EDRDG, CC BY-SA) and from the Unicode Consortium&#39;s Unihan database.
        <a href="https://github.com/vk2705/kanji/blob/master/docs/DATA_SOURCES.md">Full data
        provenance</a>.</p>
      <p>AI assistants can query the same data: a free, read-only
        <a href="/guide/#ai-access">MCP server</a> at <code>{MCP_URL}</code> offers search by parts,
        decomposition lookup and keyword search.</p>
"""

# The static pages load no JavaScript and no app stylesheet, so they carry their
# own small one — the same palette as App.css, with a light variant.
PAGE_STYLE = """    <style>
      :root { --bg: #0f0f13; --text: #e0e0f0; --muted: #8888aa; --accent: #9d92f5; --kanji: #f0c060; --card: #1a1a22; }
      @media (prefers-color-scheme: light) {
        :root { --bg: #fafafc; --text: #1c1c28; --muted: #5c5c78; --accent: #5a4bd6; --kanji: #a0661a; --card: #efeff5; }
      }
      body { background: var(--bg); color: var(--text); font-family: "Segoe UI", system-ui, sans-serif;
             line-height: 1.6; margin: 0; padding: 0 16px; }
      main, footer { max-width: 760px; margin: 0 auto; }
      main { padding: 24px 0; }
      footer { color: var(--muted); font-size: 0.85rem; border-top: 1px solid var(--card); padding: 16px 0 32px; }
      a { color: var(--accent); }
      h1 { font-size: 2rem; margin: 0.4em 0; }
      h1 .glyph { color: var(--kanji); font-family: "Noto Serif CJK JP", "Hiragino Mincho ProN", serif; }
      .glyph-list a, .cjk { font-family: "Noto Serif CJK JP", "Hiragino Mincho ProN", serif; }
      .facts { background: var(--card); border-radius: 8px; padding: 12px 16px; }
      .facts dt { color: var(--muted); font-size: 0.85rem; }
      .facts dd { margin: 0 0 8px; }
      .glyph-list { display: flex; flex-wrap: wrap; gap: 6px 14px; padding: 0; list-style: none; }
      nav.pager { display: flex; justify-content: space-between; gap: 12px; margin-top: 24px; }
    </style>
"""

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "frontend" / "public" / "kanji"
DEFAULT_SITEMAP = ROOT / "frontend" / "public" / "sitemap.xml"

HUB_CHUNK = 1000
SITEMAP_CHUNK = 5000
MAX_HOSTS_SHOWN = 40
MAX_ALIASES_SHOWN = 12


def page_url(kanji_id: str) -> str:
    return f"{SITE_URL}/kanji/{quote(kanji_id, safe='')}.html"


def page_path(kanji_id: str) -> str:
    return f"/kanji/{quote(kanji_id, safe='')}.html"


def display_character(character: str | None) -> str:
    return "" if character in (None, "", "?", "??") else character


def script_group(script: str | None) -> str:
    return "zh" if (script or "").startswith("zh") else "ja"


def script_noun(entry: dict) -> str:
    script = entry.get("script") or "ja-kanji"
    return {
        "zh-Hans": "simplified Chinese hanzi",
        "zh-Hant": "traditional Chinese hanzi",
        "zh-Hani": "Chinese hanzi",
    }.get(script, "Japanese kanji")


def strip_tones(text: str) -> set[str]:
    """Tone-stripped syllables of a pinyin string: 'wàn mò' -> {'wan', 'mo'}."""
    bare = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return {syllable for syllable in bare.lower().replace(",", " ").split() if syllable}


def first_keyword(entry: dict) -> str:
    return (entry.get("keyword") or entry["id"]).split(",")[0].strip()


def entry_label(entry: dict) -> str:
    return f"{display_character(entry.get('character'))} {first_keyword(entry)}".strip()


def load_term_targets(conn: sqlite3.Connection) -> dict[str, dict[str, tuple[str, str]]]:
    """script group ("ja"/"zh") -> part_term -> (glyph, kanji id) it denotes.

    A `parts` row's term is sometimes the glyph, sometimes a name, sometimes an
    id (`prim-tall`), and a decomposition usually stores the glyph *and* its
    canonical name as two rows. All three forms have to resolve to the same
    row so the caller can collapse them back to one component.

    Terms resolve per script group, the way database._resolve_parts_detail
    scopes by the viewed kanji's own script. Without that, hanzi rows (no
    frame, so they ranked as "primitives") won names from RTK rows, and their
    tone-stripped pinyin aliases made it worse: 明's headline came out
    "孙 + 月" because 孙 is read sūn, and 好's picked up 仔 for "child".

    A name can also be claimed by several rows within one script, and picking
    the wrong one puts a component in the page that is not in the character:
    "lid" is 亠's name and also the keyword of the kanji 蓋, and the first
    draft of this rendered 享 as "亠 + 蓋 + 口 + 子". So claimants rank: same
    script group first, then a real name over a pinyin transliteration, then a
    row with no frame (a primitive, which is what a decomposition means), and
    among real frames the earliest one, since Heisig introduces a shape at or
    before the frame that first needs it (the rule audit_anachronistic_names.py
    runs on).
    """
    best: dict[str, dict[str, tuple]] = {"ja": {}, "zh": {}}

    def offer(term: str, rank_tail: tuple, row_group: str, target: tuple[str, str]) -> None:
        for group, table in best.items():
            rank = (row_group != group, *rank_tail)
            if term not in table or rank < table[term][0]:
                table[term] = (rank, target)

    for row in conn.execute(
        "SELECT id, character, frame, script FROM kanji WHERE visibility = 'public'"
    ):
        glyph = display_character(row["character"])
        if not glyph:
            continue
        target = (glyph, row["id"])
        group = script_group(row["script"])
        # An id or a glyph is exact, so it outranks every name (the leading 0).
        offer(row["id"].lower(), (0, 0, 0, 0, row["id"]), group, target)
        offer(glyph.lower(), (0, 0, 0 if row["frame"] else 1, row["frame"] or 0, row["id"]), group, target)

    for row in conn.execute(
        "SELECT a.alias, k.id, k.character, k.frame, k.script, k.pinyin FROM aliases a "
        "  JOIN kanji k ON k.id = a.kanji_id "
        " WHERE k.visibility = 'public' AND a.visibility = 'public'"
    ):
        glyph = display_character(row["character"])
        term = (row["alias"] or "").lower()
        if not glyph or not term:
            continue
        is_pinyin = bool(row["pinyin"]) and term in strip_tones(row["pinyin"])
        rank_tail = (1, is_pinyin, 1 if row["frame"] else 0, row["frame"] or 0, row["id"])
        offer(term, rank_tail, script_group(row["script"]), (glyph, row["id"]))

    return {
        group: {term: target for term, (_rank, target) in table.items()}
        for group, table in best.items()
    }


def resolve_parts(entry: dict, targets: dict[str, dict[str, tuple[str, str]]]) -> None:
    """Attach glyph/id to every part, and the deduplicated component list.

    `components` is the glyph list of the first decomposition whose every part
    resolves to a real character: 享's own reading is prim-tall + 子, and
    "享 = 子" would be worse than useless in a search result, while its cjkvi
    alternate 亠 + 口 + 子 is complete. It stays [] when nothing resolves
    cleanly, and the page then says nothing about components above the fold
    rather than something wrong.
    """
    table = targets[script_group(entry.get("script"))]
    entry["components"] = []
    for decomposition in entry["decompositions"]:
        resolved = []
        seen: set[str] = set()
        complete = True
        for part in decomposition["parts_detail"]:
            target = table.get((part["term"] or "").lower())
            if not target:
                complete = False
                resolved.append({"term": part["term"]})
                continue
            glyph, kanji_id = target
            # The glyph and its name are usually stored as two rows: one chip.
            if kanji_id in seen or kanji_id == entry["id"]:
                continue
            seen.add(kanji_id)
            resolved.append({"term": part["term"], "glyph": glyph, "id": kanji_id})
        decomposition["resolved"] = resolved
        if complete and resolved and not entry["components"]:
            entry["components"] = [part["glyph"] for part in resolved]


def has_content(entry: dict) -> bool:
    """A page worth putting in the sitemap: it lists at least one decomposition part.

    Atomic shapes with nothing but a keyword dilute the sitemap. They keep
    their page and stay linked from the hubs and from every character that
    contains them; they are just not volunteered to crawlers.
    """
    return any(d["parts_detail"] for d in entry["decompositions"]) or bool(entry.get("hosts"))


def link(entry: dict, text: str | None = None) -> str:
    return f'<a href="{html.escape(page_path(entry["id"]), quote=True)}">{html.escape(text or entry_label(entry))}</a>'


def render_page(entry: dict, entries_by_id: dict[str, dict]) -> str:
    """One crawlable page.

    The <title>, <meta description> and <h1> carry the character, its component
    *glyphs*, its stroke count and its readings — structural and reading data
    from cjkvi-ids, kanjidic2 and Unihan, all open. They deliberately do not
    carry the keyword or the component names, which are the part of this
    database that comes from Heisig's book (see docs/DATA_SOURCES.md). Those
    stay in the body, where they are what makes the page worth reading, but
    they are not served into a search result as the answer itself.
    """
    character = display_character(entry["character"])
    subject = character or entry["id"]
    keyword = first_keyword(entry)
    components = " + ".join(entry["components"])
    noun = script_noun(entry)
    short_noun = "hanzi" if script_group(entry.get("script")) == "zh" else "kanji"

    headline = f"{subject} = {components}" if components else subject
    title = f"{headline} — {short_noun} components, readings, strokes | RTK Kanji Search"

    facts = []
    if components:
        facts.append(f"{subject} is written {components}")
    if entry.get("stroke_count"):
        strokes = entry["stroke_count"]
        facts.append(f"{strokes} stroke" + ("" if strokes == 1 else "s"))
    if entry.get("onyomi"):
        facts.append(f"on'yomi {entry['onyomi']}")
    if entry.get("kunyomi"):
        facts.append(f"kun'yomi {entry['kunyomi']}")
    if entry.get("pinyin"):
        facts.append(f"pinyin {entry['pinyin']}")
    description = (
        ". ".join(facts) + ". " if facts else f"{subject}: a {short_noun} in this index. "
    ) + "Look up kanji and hanzi by the shapes they are built from."

    # --- the prose summary: the page's main paragraph ------------------------
    primary = next((d["resolved"] for d in entry["decompositions"] if d.get("resolved")), [])
    linked_parts = [
        link(entries_by_id[p["id"]], f"{p['glyph']} ({first_keyword(entries_by_id[p['id']])})")
        for p in primary if p.get("id") in entries_by_id
    ]
    sentences = [f"<span class=\"cjk\">{html.escape(subject)}</span> is a {noun}"]
    if entry.get("stroke_count"):
        sentences[0] += f" written with {entry['stroke_count']} stroke" + ("" if entry["stroke_count"] == 1 else "s")
    sentences[0] += f", listed here under the keyword “{html.escape(keyword)}”."
    if linked_parts:
        joined = linked_parts[0] if len(linked_parts) == 1 else ", ".join(linked_parts[:-1]) + " and " + linked_parts[-1]
        sentences.append(f"It is built from {joined}.")
    elif not entry["decompositions"]:
        sentences.append("It is treated as a basic building block: it is not broken down any further here.")
    if entry.get("frame"):
        sentences.append(
            f'In <a href="{BOOK_URL}">Remembering the Kanji</a> by James W. Heisig it is frame {entry["frame"]}.'
        )
    hosts = entry.get("hosts") or []
    if hosts:
        sentences.append(
            f"It appears as a component in {len(hosts)} other character" + ("" if len(hosts) == 1 else "s")
            + " in this index."
        )
    summary = " ".join(sentences)

    # How a user would find this character with the parts search — the tool's
    # whole point, phrased as an instruction a visitor can follow.
    search_names = [first_keyword(entries_by_id[p["id"]]) for p in primary if p.get("id") in entries_by_id]
    how_to_find = ""
    if len(search_names) >= 2:
        how_to_find = (
            f"      <h2>How to find {html.escape(subject)} without knowing its reading</h2>\n"
            f"      <p>On RTK Kanji Search, open the parts search and type "
            + " + ".join(f"“{html.escape(name)}”" for name in search_names[:3])
            + f". {html.escape(subject)} is among the results, together with every other character "
            f"containing the same shapes.</p>\n"
        )

    # --- facts box ---------------------------------------------------------
    fact_rows = [("Keyword", html.escape(keyword))]
    if entry.get("frame"):
        fact_rows.append(("RTK frame", str(entry["frame"])))
    if entry.get("stroke_count"):
        fact_rows.append(("Strokes", str(entry["stroke_count"])))
    if entry.get("onyomi"):
        fact_rows.append(("On'yomi (Sino-Japanese reading)", html.escape(entry["onyomi"])))
    if entry.get("kunyomi"):
        fact_rows.append(("Kun'yomi (native Japanese reading)", html.escape(entry["kunyomi"])))
    if entry.get("pinyin"):
        fact_rows.append(("Pinyin (Mandarin)", html.escape(entry["pinyin"])))
    fact_rows.append(("Script", noun.capitalize()))
    aliases = [a for a in entry["aliases"] if a.lower() != keyword.lower()][:MAX_ALIASES_SHOWN]
    if aliases:
        fact_rows.append(("Also known as", html.escape(", ".join(aliases))))
    for other in entry.get("counterparts") or []:
        fact_rows.append((f"Same glyph as a {script_noun(other)}", link(other)))
    facts_box = "\n".join(f"        <dt>{k}</dt><dd>{v}</dd>" for k, v in fact_rows)

    # --- decompositions ----------------------------------------------------
    decomposition_sections = []
    for number, decomposition in enumerate(entry["decompositions"], start=1):
        parts = decomposition.get("resolved") or []
        if not parts:
            continue
        label = decomposition.get("label") or ("Primary decomposition" if number == 1 else f"Decomposition {number}")
        if label == "alternative":
            label = "Alternative decomposition"
        items = "\n".join(
            f"          <li>{link(entries_by_id[p['id']], p['glyph'] + ' ' + first_keyword(entries_by_id[p['id']]))}</li>"
            if p.get("id") in entries_by_id else f"          <li>{html.escape(p['term'])}</li>"
            for p in parts
        )
        decomposition_sections.append(
            f"      <section>\n        <h3>{html.escape(label)}</h3>\n        <ol>\n{items}\n        </ol>\n      </section>"
        )
    decomposition_html = (
        "\n".join(decomposition_sections) if decomposition_sections
        else "      <p>No decomposition is listed: this shape is used whole.</p>"
    )

    # --- characters containing this one -----------------------------------
    hosts_html = ""
    if hosts:
        shown = hosts[:MAX_HOSTS_SHOWN]
        items = "\n".join(f"        <li>{link(h)}</li>" for h in shown)
        more = (
            f"\n      <p>…and {len(hosts) - len(shown)} more. "
            f'<a href="/?kanji={quote(entry["id"], safe="")}">See them all in the interactive search</a>.</p>'
            if len(hosts) > len(shown) else ""
        )
        hosts_html = (
            f"      <h2>Characters that contain {html.escape(subject)}</h2>\n"
            f'      <ul class="glyph-list">\n{items}\n      </ul>{more}\n'
        )

    # --- previous/next in RTK order ----------------------------------------
    pager = ""
    if entry.get("prev") or entry.get("next"):
        prev_link = f"<span>← {link(entry['prev'])}</span>" if entry.get("prev") else "<span></span>"
        next_link = f"<span>{link(entry['next'])} →</span>" if entry.get("next") else "<span></span>"
        pager = f'      <nav class="pager" aria-label="RTK order">{prev_link}{next_link}</nav>\n'

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
{PAGE_STYLE}  </head>
  <body>
    <main>
      <p><a href="/">RTK Kanji Search</a> › <a href="/kanji/">Browse</a></p>
      <h1><span class="glyph">{html.escape(headline)}</span></h1>
      <p>{summary}</p>
      <dl class="facts">
{facts_box}
      </dl>
      <h2>Decomposition</h2>
{decomposition_html}
{hosts_html}{how_to_find}      <p><a href="/?kanji={quote(entry['id'], safe='')}">Open {html.escape(subject)} in the interactive kanji search</a>
        to expand every part down to its smallest pieces, add your own names and mnemonic stories,
        or search for other characters by their parts.</p>
{pager}    </main>
    <footer>
{ATTRIBUTION}    </footer>
  </body>
</html>
"""


def _hub_page(title: str, url: str, intro: str, items: list[tuple[str, str]], nav: list[tuple[str, str]]) -> str:
    links = "\n".join(
        f'        <li><a href="{html.escape(href, quote=True)}">{html.escape(label)}</a></li>'
        for href, label in items
    )
    navigation = " · ".join(
        f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>' for href, label in nav
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} | RTK Kanji Search</title>
    <meta name="description" content="{html.escape(intro, quote=True)}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="{html.escape(url, quote=True)}">
{PAGE_STYLE}  </head>
  <body>
    <main>
      <p><a href="/">RTK Kanji Search</a></p>
      <h1>{html.escape(title)}</h1>
      <p>{html.escape(intro)}</p>
      <p>{navigation}</p>
      <ol class="glyph-list">
{links}
      </ol>
    </main>
    <footer>
{ATTRIBUTION}    </footer>
  </body>
</html>
"""


def write_hubs(output_dir: Path, entries: list[dict]) -> list[str]:
    """Browsable index pages, so crawlers reach every kanji by links and not only
    via the sitemap. Returns the hub URLs, for the sitemap."""
    rtk = sorted((e for e in entries if e["id"].startswith("rtk") and e.get("frame")), key=lambda e: e["frame"])
    other = [e for e in entries if not (e["id"].startswith("rtk") and e.get("frame")) and has_content(e)]
    chunks = [other[i:i + HUB_CHUNK] for i in range(0, len(other), HUB_CHUNK)]

    index_url = f"{SITE_URL}/kanji/"
    nav = [("/kanji/", "Japanese kanji")] + [
        (f"/kanji/browse-{n}.html", f"Hanzi and primitives {n}") for n in range(1, len(chunks) + 1)
    ]
    urls = [index_url]
    (output_dir / "index.html").write_text(
        _hub_page(
            "Japanese kanji in Remembering the Kanji order",
            index_url,
            f"All {len(rtk)} kanji of Remembering the Kanji in frame order. Each page shows the "
            "building blocks the kanji is made of, its on'yomi and kun'yomi readings, its stroke "
            "count and the other kanji that contain it.",
            [(page_path(e["id"]), f"{e['frame']}. {entry_label(e)}") for e in rtk],
            nav,
        ),
        encoding="utf-8",
    )
    for n, chunk in enumerate(chunks, start=1):
        url = f"{SITE_URL}/kanji/browse-{n}.html"
        (output_dir / f"browse-{n}.html").write_text(
            _hub_page(
                f"Hanzi and primitives, part {n} of {len(chunks)}",
                url,
                "Chinese hanzi (simplified and traditional) and the primitive shapes characters are "
                "built from. Each page shows the parts, the pinyin reading and the characters that "
                "use it.",
                [(page_path(e["id"]), entry_label(e)) for e in chunk],
                nav,
            ),
            encoding="utf-8",
        )
        urls.append(url)
    return urls


def write_sitemaps(sitemap_path: Path, urls: list[str]) -> list[Path]:
    """Write /sitemap.xml as an index over /sitemap-N.xml chunk files.

    No <changefreq>/<priority> (Google ignores both) and no per-URL <lastmod>:
    there is no real per-page modification date to report, and Google stops
    trusting lastmod once it sees it is not accurate. The index carries the
    generation date on each chunk, which is accurate for the chunk file.
    """
    directory = sitemap_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("sitemap-*.xml"):
        stale.unlink()
    today = date.today().isoformat()
    written = []
    chunks = [urls[i:i + SITEMAP_CHUNK] for i in range(0, len(urls), SITEMAP_CHUNK)]
    for n, chunk in enumerate(chunks, start=1):
        path = directory / f"sitemap-{n}.xml"
        body = "\n".join(f"  <url><loc>{html.escape(url)}</loc></url>" for url in chunk)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n"
            "</urlset>\n",
            encoding="utf-8",
        )
        written.append(path)
    index_body = "\n".join(
        f"  <sitemap><loc>{SITE_URL}/{path.name}</loc><lastmod>{today}</lastmod></sitemap>"
        for path in written
    )
    sitemap_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{index_body}\n"
        "</sitemapindex>\n",
        encoding="utf-8",
    )
    return written


def generate(db_path: Path, output_dir: Path, sitemap_path: Path) -> int:
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        entry_rows = conn.execute(
            "SELECT id, character, keyword, frame, stroke_count, onyomi, kunyomi, pinyin, "
            "       script "
            "FROM kanji WHERE visibility = 'public' ORDER BY id"
        ).fetchall()
        entries = [{**dict(row), "aliases": [], "decompositions": []} for row in entry_rows]
        entries_by_id = {entry["id"]: entry for entry in entries}

        for row in conn.execute(
            "SELECT a.kanji_id, a.alias FROM aliases a JOIN kanji k ON k.id = a.kanji_id "
            "WHERE a.visibility = 'public' AND k.visibility = 'public' ORDER BY a.rowid"
        ):
            entry = entries_by_id[row["kanji_id"]]
            alias = row["alias"]
            # Skip the glyph itself, bare frame numbers and the tone-stripped
            # pinyin search aliases: all search plumbing, not names a reader
            # would want listed.
            if alias in (entry["character"], entry["id"]) or alias.isdigit():
                continue
            if entry.get("pinyin") and alias.lower() in strip_tones(entry["pinyin"]):
                continue
            if alias not in entry["aliases"]:
                entry["aliases"].append(alias)

        decompositions: dict[int, dict] = {}
        for row in conn.execute(
            "SELECT d.id, d.kanji_id, d.label, p.part_term, p.position "
            "FROM decompositions d "
            "JOIN parts p ON p.decomposition_id = d.id "
            "JOIN kanji k ON k.id = d.kanji_id "
            "WHERE d.visibility = 'public' AND k.visibility = 'public' "
            "ORDER BY d.kanji_id, (d.owner_id = 1) DESC, d.id, p.position"
        ):
            decomposition = decompositions.get(row["id"])
            if decomposition is None:
                decomposition = {"id": row["id"], "label": row["label"], "parts_detail": []}
                decompositions[row["id"]] = decomposition
                entries_by_id[row["kanji_id"]]["decompositions"].append(decomposition)
            decomposition["parts_detail"].append({"term": row["part_term"]})

        targets = load_term_targets(conn)
        for entry in entries:
            resolve_parts(entry, targets)

        # Reverse index: which characters use this one as a part, in any
        # decomposition. Same-script only, so a kanji page lists kanji.
        hosts: dict[str, dict[str, dict]] = {}
        for entry in entries:
            for decomposition in entry["decompositions"]:
                for part in decomposition["resolved"]:
                    part_id = part.get("id")
                    if part_id in entries_by_id and part_id != entry["id"]:
                        hosts.setdefault(part_id, {})[entry["id"]] = entry
        for entry in entries:
            group = script_group(entry.get("script"))
            entry["hosts"] = sorted(
                (h for h in hosts.get(entry["id"], {}).values() if script_group(h.get("script")) == group),
                key=lambda h: (h.get("frame") is None, h.get("frame") or 0, h["id"]),
            )

        # Same glyph in the other script (漢 is both rtk1701 and hanzi-6f22).
        by_glyph: dict[str, list[dict]] = {}
        for entry in entries:
            glyph = display_character(entry["character"])
            if glyph and (entry.get("frame") or entry["id"].startswith("hanzi-")):
                by_glyph.setdefault(glyph, []).append(entry)
        for entry in entries:
            glyph = display_character(entry["character"])
            entry["counterparts"] = [
                other for other in by_glyph.get(glyph, [])
                if other["id"] != entry["id"] and script_group(other.get("script")) != script_group(entry.get("script"))
            ][:2]

        rtk = sorted((e for e in entries if e["id"].startswith("rtk") and e.get("frame")), key=lambda e: e["frame"])
        for previous, following in zip(rtk, rtk[1:]):
            previous["next"] = following
            following["prev"] = previous

        for entry in entries:
            (output_dir / f"{quote(entry['id'], safe='')}.html").write_text(
                render_page(entry, entries_by_id), encoding="utf-8"
            )
        hub_urls = write_hubs(output_dir, entries)
        urls = [f"{SITE_URL}/", f"{SITE_URL}/guide/", *hub_urls, f"{SITE_URL}/privacy.html"] + [
            page_url(entry["id"]) for entry in entries if has_content(entry)
        ]
        chunk_files = write_sitemaps(sitemap_path, urls)
    finally:
        conn.close()
    print(
        f"Generated {len(entries)} public kanji pages in {output_dir}; "
        f"sitemap index with {len(chunk_files)} files, {len(urls)} URLs"
    )
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
