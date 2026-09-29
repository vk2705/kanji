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

## The render can lie, and now it says so

Added 2026-09-29, after chunk 87 found that a font may claim a codepoint in its
charset and still have no distinct outline for it, quietly drawing something
else. That is the worst possible failure for this tool: two glyphs come out
pixel-identical and the comparison reads as "these are the same shape" — a
confident, wrong conclusion rather than a visibly missing one. fontconfig does
not help; `fc-list :charset=864D` lists Noto for 虍 because the charset table
claims it.

So every run now ends with a relative check: each pair of distinct requested
codepoints is hashed in each face of the stack separately. If a pair is
identical in one face and different in another, the first face is substituting
and the run says so loudly, naming a face to re-render with. If a pair is
identical in *every* face, they are simply near-identical shapes and it says
that instead of crying wolf. Silence means nothing suspicious was found.

Demonstrated on 者 U+8005 vs 者 U+FA5B: identical in WenQuanYi Zen Hei and
HanaMinB, distinct in Noto Sans CJK JP and HanaMinA.
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]

# Fall back to whatever Chromium `playwright install` put in the default cache dir
# (versioned subdirectory, e.g. ~/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome)
# if none of the fixed CHROME_CANDIDATES paths above exist.
_PW_CACHE = Path.home() / ".cache" / "ms-playwright"
if _PW_CACHE.is_dir():
    for _entry in sorted(_PW_CACHE.glob("chromium-*")):
        _bin = _entry / "chrome-linux64" / "chrome"
        if _bin.exists():
            CHROME_CANDIDATES.append(str(_bin))

# HanaMin sits ahead of Unifont deliberately. Unifont covers almost everything, but
# it is a 16px *bitmap* face: enlarged for comparison, a CJK Ext B/G glyph like 𠂉 or
# 𢦏 comes out as a staircase, which is a poor basis for "look at it and decide" —
# this tool's whole purpose. HanaMin (`apt-get install fonts-hanazono`) has real
# outlines for Ext A–G. It is Mincho, so it stays *after* the gothic faces: common
# kanji keep the gothic look, and only the rare glyphs those faces lack fall through
# to it. Unifont remains the last resort for anything even HanaMin misses.
FONT_STACK = ("'Noto Sans CJK JP', 'WenQuanYi Zen Hei', "
              "'HanaMinA', 'HanaMinB', 'Unifont-JP', sans-serif")


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


# The individual faces of FONT_STACK, for the substitution check below. Kept
# separate from FONT_STACK itself so the picture the tool draws is unchanged.
CHECK_FONTS = ("Noto Sans CJK JP", "WenQuanYi Zen Hei", "HanaMinA", "HanaMinB")

_CHECK_JS = """
function hashGlyph(ch, font) {
  const c = document.createElement('canvas');
  c.width = c.height = 72;
  const g = c.getContext('2d');
  g.fillStyle = '#fff'; g.fillRect(0, 0, 72, 72);
  g.fillStyle = '#000';
  g.font = '56px "' + font + '"';
  g.textBaseline = 'top';
  g.fillText(ch, 6, 6);
  const d = g.getImageData(0, 0, 72, 72).data;
  let h = 2166136261;
  for (let i = 0; i < d.length; i += 4) { h ^= d[i]; h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(16);
}
const chars = CHARS, fonts = FONTS, out = [];
for (let i = 0; i < chars.length; i++) {
  for (let j = i + 1; j < chars.length; j++) {
    if (chars[i] === chars[j]) continue;
    const same = [], diff = [];
    for (const f of fonts) {
      (hashGlyph(chars[i], f) === hashGlyph(chars[j], f) ? same : diff).push(f);
    }
    if (same.length) out.push([chars[i], chars[j], same, diff]);
  }
}
document.title = JSON.stringify(out);
"""


def check_substitution(chars: list[str]) -> list[tuple]:
    """Pairs of distinct characters that render identically in some font.

    The failure this exists for: a font that claims a codepoint in its charset
    but has no distinct outline for it quietly draws something else. Noto Sans
    CJK JP does this for 虍 (U+864D) — it draws the full 虎, legs and all — so
    a render of 虍 beside 虎 came out pixel-identical and was read as "the
    comparison is inconclusive" rather than "the font is lying". fontconfig is
    no help: `fc-list :charset=864D` lists Noto, because the charset table does
    claim it.

    Relative comparison catches it. If two *different* codepoints hash the same
    in one face and differ in another, the first face is substituting. If they
    hash the same in every face, they are simply near-identical shapes and the
    tool says so instead of crying wolf.
    """
    script = (_CHECK_JS
              .replace("CHARS", json.dumps(sorted({c for s in chars for c in s})))
              .replace("FONTS", json.dumps(list(CHECK_FONTS))))
    page = ("<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>"
            f"<script>{script}</script></body></html>")
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "check.html"
        html_path.write_text(page, encoding="utf-8")
        result = subprocess.run(
            [find_chrome(), "--headless", "--disable-gpu", "--no-sandbox",
             "--dump-dom", f"file://{html_path}"],
            capture_output=True, text=True, timeout=60,
        )
    match = re.search(r"<title>(.*?)</title>", result.stdout, re.S)
    if not match:
        return []
    return [tuple(row) for row in json.loads(html.unescape(match.group(1)) or "[]")]


def report_substitution(chars: list[str]) -> None:
    try:
        pairs = check_substitution(chars)
    except Exception as error:  # noqa: BLE001 - a broken check must not break the render
        print(f"  (substitution check skipped: {type(error).__name__}: {error})")
        return
    if not pairs:
        return
    print()
    for a, b, same, diff in pairs:
        if diff:
            print(f"  !! FONT SUBSTITUTION: {a} (U+{ord(a):04X}) and {b} (U+{ord(b):04X}) "
                  f"render IDENTICALLY in {', '.join(same)} but differ in {', '.join(diff)}.")
            print(f"     The first face has no distinct outline for one of them and is drawing "
                  f"the other. Do not compare these two in this PNG — re-render forcing "
                  f"{diff[0]}.")
        else:
            print(f"  note: {a} and {b} render identically in every face checked "
                  f"({', '.join(same)}) — near-identical shapes, not a substitution.")


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
    report_substitution([char for char, _label in entries])


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
