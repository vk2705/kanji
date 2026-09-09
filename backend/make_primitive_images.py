#!/home/user/kanji/backend/venv/bin/python3
"""make_primitive_images.py — render a picture for every primitive whose glyph
most fonts can't draw, so the app never shows a reader an empty box.

## Why this exists

The decomposition audit keeps registering compound components that Heisig names
and teaches but that live in the thin end of Unicode: 𭕄 (the owl crown, U+2D544,
CJK Ext G), 𢦏 (harvest festival, U+2298F, Ext B), and most of the components
still queued — 𠂉, 𠃌, 𧘇, 𤰔, 𦍌, 𠦝, 𠂇. These are the *correct* codepoints, and
using a lookalike from a well-supported block instead is the single mistake this
audit has had to undo most often (ツ for 𭕄, 杰 for 灬, 艾 for 艹, 爿 for 丬 …).
So the codepoint stays right and the *rendering* gets fixed instead: a committed
PNG per primitive, which the detail page, result cards and part chips already
know how to display (owner decision, 2026-09-09).

Coverage is the whole problem, so the ranges below are the ones where a reader
plausibly sees tofu:

  * Plane 2 and beyond (U+20000+) — CJK Ext B/C/D/E/F/G. Essentially no system
    font ships these; even here they only render because Unifont is installed,
    and Unifont is a 16px bitmap face that turns to staircases when enlarged.
  * CJK Ext A (U+3400–U+4DBF) — patchy rather than absent. Desktop CJK fonts
    generally have it; Android's do not reliably, and this project ships an
    Android WebView app, so it counts.

## What it produces

`primitive_images/{kanji_id}.png`, committed to the repo (unlike `uploads/`,
which is gitignored user content). Rendered with HanaMin — a Mincho face, which
is what `App.css` already asks for on every glyph surface (`"Noto Serif CJK JP",
"Yu Mincho", serif`), so an image chip sits beside a real glyph chip without
looking like a different typeface — in `--kanji-color` (#f0c060) on transparent,
at 4x the largest display size (`.detail-char-img`, 4rem) so it stays crisp.

Install the font first if it is missing: `apt-get install fonts-hanazono`.
Requires the same headless Chromium `render_glyphs.py` uses; no new dependency.

## Usage

    ./venv/bin/python3 make_primitive_images.py --dry-run   # list what needs one
    ./venv/bin/python3 make_primitive_images.py             # (re)render them all

The DB side is separate and automatic: `database.py::import_data()` points a
system row's `image_url` at `/primitive-images/{id}.png` when the file exists,
and `sync_system_data.py` propagates that to a live DB. Nothing here writes to
the database.
"""
import argparse
import html
import subprocess
import sys
import tempfile
from pathlib import Path

import database
from render_glyphs import find_chrome

IMAGE_DIR = Path(__file__).parent / "primitive_images"

# Codepoint ranges whose glyphs a reader plausibly cannot see — see the module
# docstring for why each is here. Anything outside them renders fine from the
# font stack and must NOT get an image: a picture that duplicates a perfectly
# good glyph is a needless request and a second thing to keep in sync.
UNRENDERABLE_RANGES = (
    (0x3400, 0x4DBF),      # CJK Ext A — patchy, notably on Android
    (0x20000, 0x3FFFF),    # CJK Ext B and beyond — effectively absent everywhere
)

# Mincho, to match App.css's glyph surfaces. HanaMinA covers the BMP extensions,
# HanaMinB the supplementary planes; listing both lets fontconfig pick per glyph.
FONT_STACK = "'HanaMinA', 'HanaMinB', 'Noto Serif CJK JP', serif"
GLYPH_COLOR = "#f0c060"   # --kanji-color
CANVAS = 256              # 4x .detail-char-img's 4rem, so it stays crisp scaled down

# The canvas is exactly one em, and the glyph is set at exactly that font size, so the
# PNG's box *is* the em square. That matters: the CSS sizes these with max-width /
# max-height + object-fit (1.4rem on a part chip, 4rem on the detail header), so an
# image whose canvas is bigger than its em square renders visibly smaller than the real
# glyph next to it. Matching them one-to-one makes an image chip and a text chip occupy
# the same space with the same internal proportions — including for a short primitive
# like 𭕄, which correctly stays a shallow crown near the top of its box.


def needs_image(character: str | None) -> bool:
    if not character or len(character) != 1:
        return False
    cp = ord(character)
    return any(lo <= cp <= hi for lo, hi in UNRENDERABLE_RANGES)


def system_primitives(conn):
    """(id, character) for every system row whose glyph needs a picture."""
    rows = conn.execute(
        "SELECT id, character FROM kanji WHERE owner_id = 1 AND character IS NOT NULL "
        "ORDER BY id"
    ).fetchall()
    return [(r["id"], r["character"]) for r in rows if needs_image(r["character"])]


def _page(character: str) -> str:
    """One glyph, centred on a transparent canvas, no chrome of any kind."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; background: transparent; }}
  .glyph {{
    width: {CANVAS}px; height: {CANVAS}px;
    font-family: {FONT_STACK};
    font-size: {CANVAS}px;
    line-height: {CANVAS}px;
    text-align: center;
    color: {GLYPH_COLOR};
  }}
</style></head>
<body><div class="glyph">{html.escape(character)}</div></body></html>
"""


def render_one(character: str, out_path: Path) -> None:
    chrome = find_chrome()
    with tempfile.TemporaryDirectory() as tmpdir:
        page = Path(tmpdir) / "glyph.html"
        page.write_text(_page(character), encoding="utf-8")
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-sandbox",
             "--default-background-color=00000000",   # keep the PNG's alpha
             f"--screenshot={out_path}",
             f"--window-size={CANVAS},{CANVAS}",
             f"file://{page}"],
            capture_output=True, check=True, timeout=60,
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="list the primitives that need a picture, render nothing")
    ap.add_argument("--only", nargs="*", help="restrict to these kanji ids")
    args = ap.parse_args()

    conn = database.get_db()
    targets = system_primitives(conn)
    if args.only:
        wanted = set(args.only)
        targets = [t for t in targets if t[0] in wanted]

    if not targets:
        print("No system primitive needs a picture — every glyph is in a well-supported block.")
        return

    print(f"{len(targets)} primitive(s) whose glyph needs a picture:")
    for kid, ch in targets:
        print(f"  {kid:24s} {ch}  U+{ord(ch):04X}")
    if args.dry_run:
        return

    IMAGE_DIR.mkdir(exist_ok=True)
    for kid, ch in targets:
        out = IMAGE_DIR / f"{kid}.png"
        render_one(ch, out)
        if not out.exists() or out.stat().st_size == 0:
            print(f"FAILED to render {kid} ({ch})", file=sys.stderr)
            sys.exit(1)
        print(f"  wrote {out.relative_to(Path(__file__).parent)} ({out.stat().st_size} bytes)")

    print("\nRendered. Now LOOK at them — a missing font silently produces a blank or a "
          "tofu box, and this script cannot tell the difference from a correct glyph.")


if __name__ == "__main__":
    main()
