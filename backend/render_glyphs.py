"""
render_glyphs.py — render kanji/primitive glyphs to a PNG for visual comparison.

## Why this exists

This audit had already been burned once by trusting Unicode codepoint reasoning
alone (script_group ambiguity, KRADFILE JIS-substitution proxies) — but on
2026-08-23, investigating whether `个` (data.txt's "person radical" stand-in,
101 host kanji) duplicated `亻`/kangxi9, *codepoint and text-based* reasoning
was independently wrong twice in a row: first guessing it duplicated `亻`
(actually a different positional variant, 𠆢), then guessing it stood in for
that variant `𠆢` specifically (also wrong). Only actually *rendering* `个`
next to the real top-of-会/谷/令 shape settled it: `个` has an extra vertical
stroke through the middle (looks like an arrow / an umbrella's pole) that the
real host shape doesn't have — a visual difference no amount of codepoint- or
keyword-matching would have caught, confirmed once cross-checked against
heisig-kanjis.csv's own component list (the shape is Heisig's "umbrella", a
concept with nothing to do with "person" at all).

Owner's explicit standing instruction after that: use this method — actually
render and look, don't reason from codepoints/keywords alone — as the final
verification step before believing two primitives are the same or different,
eventually across the whole dataset.

## How it works

Writes an HTML file with each requested character/string rendered large,
labelled, then screenshots it with the pre-installed headless Chromium
(PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers — no `playwright` package needed,
this shells out to the chrome binary directly with --headless --screenshot).
Uses WenQuanYi Zen Hei (broad CJK Unified coverage) with Unifont-JP as a
fallback for rare/Extension-B characters it doesn't cover — both already
installed in this environment; if that stops being true elsewhere, install
`fonts-wqy-zenhei` (or any full CJK font) first.

## Usage

    python3 render_glyphs.py 個 亻 人 "𠆢" 会 谷 令 --out /tmp/compare.png
    python3 render_glyphs.py --labelled 個:"个 (proxy)" 会:"top of 会" --out /tmp/compare.png

Then Read the PNG (or send it) to actually look at it — this script only
produces the image, it doesn't replace looking.
"""
import argparse
import html
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]

FONT_STACK = "'WenQuanYi Zen Hei', 'Unifont-JP', sans-serif"


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    found = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if found:
        return found
    raise RuntimeError(
        "No Chromium binary found. Checked " + ", ".join(CHROME_CANDIDATES) +
        " and PATH. Install one, or update CHROME_CANDIDATES."
    )


def build_html(entries: list[tuple[str, str]]) -> str:
    rows = []
    for char, label in entries:
        rows.append(
            f'<div class="row"><div class="label">{html.escape(label)}</div>'
            f'<div class="glyph">{html.escape(char)}</div></div>'
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ background: white; font-family: {FONT_STACK}; margin: 0; }}
  .row {{ display: flex; align-items: center; border-bottom: 1px solid #ddd; }}
  .label {{ width: 320px; font-size: 20px; padding: 8px; font-family: sans-serif; }}
  .glyph {{ font-size: 110px; padding: 4px 24px; line-height: 1.1; }}
</style></head>
<body>
{"".join(rows)}
</body></html>
"""


def render(entries: list[tuple[str, str]], out_path: Path, width: int = 900):
    height = max(200, 140 * len(entries) + 40)
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "compare.html"
        html_path.write_text(build_html(entries), encoding="utf-8")
        chrome = find_chrome()
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-sandbox",
             f"--screenshot={out_path}", f"--window-size={width},{height}",
             f"file://{html_path}"],
            capture_output=True, check=True, timeout=60,
        )
    print(f"Wrote {out_path} ({len(entries)} glyphs). Read it to actually compare — "
          f"this script only renders, it doesn't verify anything by itself.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("chars", nargs="*", help="Characters/strings to render, each its own row, "
                                                   "auto-labelled by codepoint. Use --labelled for custom labels.")
    parser.add_argument("--labelled", nargs="*", default=[],
                         help='char:label pairs, e.g. 個:"proxy in data.txt"')
    parser.add_argument("--out", type=Path, default=Path("/tmp/glyph_compare.png"))
    args = parser.parse_args()

    entries = []
    for c in args.chars:
        cps = ", ".join(f"U+{ord(ch):04X}" for ch in c)
        entries.append((c, f"{c}  ({cps})"))
    for pair in args.labelled:
        char, _, label = pair.partition(":")
        entries.append((char, label or char))

    if not entries:
        print("No characters given.", file=sys.stderr)
        sys.exit(1)

    render(entries, args.out)


if __name__ == "__main__":
    main()
