#!/usr/bin/env python3
"""
check_kanji.py — runs on YOUR OWN computer (not the server) to look up a handful of
kanji per run via a normal, visible Google search and save whatever AI Overview (or
top result) Google shows, so it can be cross-checked against this project's database
later.

Why this runs locally instead of on the server: Google immediately CAPTCHA-blocked
the very first automated request from the project's server IP (a shared AWS address
Google already treats as a data-center/bot IP) -- not a rate limit, a reputation
block. Your home computer's IP and a real, visible browser window don't have that
problem. See docs/2026-08-search-quality-audit.md's 2026-08-29 entry for the full
story of what was tried first and why.

What this does NOT do: it doesn't try to defeat CAPTCHAs, spoof a browser
fingerprint, or hide that it's automated. It opens a real, visible Chrome window
(via Playwright, using a persistent profile so it behaves like a normal returning
visitor across days) with a short randomized pause between queries (--delay MIN MAX
to change it, --no-delay for none). If Google ever shows a CAPTCHA, the script
pauses and waits for you to solve it in the visible window before continuing.

Reading the AI Overview: Google truncates it behind a "Show more" toggle and its
markup drifts, so instead of hunting for one button selector the script runs a JS
pass over the whole AI Overview region that clicks every expander it finds AND
strips the CSS that clamps height (line-clamp / max-height / overflow) -- so the
full text is recovered even when the click target has moved. extracted_text is the
region's complete innerText.

Setup (one-time):
    python3 -m venv venv
    venv/bin/pip install playwright      (Windows: venv\\Scripts\\pip install playwright)
    venv/bin/playwright install chromium (Windows: venv\\Scripts\\playwright install chromium)

Usage:
    venv/bin/python3 check_kanji.py                 # check 10 random not-yet-done kanji
    venv/bin/python3 check_kanji.py --count 20       # check 20 instead
    venv/bin/python3 check_kanji.py --id rtk523      # check one specific kanji by id
    venv/bin/python3 check_kanji.py --resume-only    # don't pick new random ones, just
                                                      # retry any that failed/were skipped
    venv/bin/python3 check_kanji.py --from-list need_rerun.json   # re-check exactly the
                                                      # ids in that file, even ones already
                                                      # in progress.json (for when a past
                                                      # run got no/truncated Google text)
    venv/bin/python3 check_kanji.py --from-list need_rerun.json --no-delay   # ...as fast
                                                      # as possible (higher CAPTCHA risk)

Run it once a day (or whenever) -- it remembers what's already been checked in
progress.json and won't repeat kanji. Sending results back: either paste the
contents of results.jsonl into a message, or (if this checkout has git access)
`git add docs/heisig-google-check/results.jsonl && git commit && git push` -- either
way, a future session can read it and do the actual comparison against data.txt.

Output:
    results.jsonl   -- one JSON object per kanji checked: id, character, keyword,
                       current_parts (what the DB currently has), extracted_text
                       (the full AI Overview text, or null), expand_clicks
                       (expander controls clicked inside the overview),
                       unclamped_nodes (nodes whose truncation CSS was force-
                       stripped), found_overview (whether the AI Overview region
                       was located at all), and a path to a saved screenshot for
                       manual review either way.
    screenshots/    -- one PNG per kanji checked, full page, so nothing is lost even
                       if the text extraction below picks the wrong element (Google
                       changes its markup periodically -- if extracted_text keeps
                       coming back empty/wrong, open a screenshot and see what
                       actually rendered, then fix the SELECTORS list below to match).
    progress.json   -- {"done": [...ids already checked...]} so re-runs advance
                       instead of repeating.
"""
import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
KANJI_LIST_PATH = HERE / "unreviewed_kanji.json"
RESULTS_PATH = HERE / "results.jsonl"
PROGRESS_PATH = HERE / "progress.json"
SCREENSHOTS_DIR = HERE / "screenshots"
PROFILE_DIR = HERE / "browser-profile"  # persistent so you look like a returning visitor

# Query template -- {char} is replaced with the kanji glyph. Tweak this if you find a
# phrasing that reliably triggers Google's AI Overview for these searches.
QUERY_TEMPLATE = "heisig kanji {char} primitives meaning breakdown"

# Google's AI Overview markup changes periodically and isn't a stable public API --
# these are best-guess CSS selectors as of 2026-08. If extracted_text comes back
# empty/wrong for everything, open a screenshot, right-click the AI Overview box in
# a real browser -> Inspect, and add/update a selector here. Ordered most- to
# least- specific; the last few are broad structural guesses.
AI_OVERVIEW_SELECTORS = [
    "[data-attrid='wa:/description']",
    "div.LT6Xte",  # a historically-used AI Overview container class; likely stale
    "div[data-md]",
    "#Odp5De",
    "#m-x-content",              # AI Overview mount point seen 2026-09
    "div[jsname='I4bIT']",
    "[aria-label='AI Overview']",
    "[aria-label*='AI Overview']",
    "div.WaaZC",                 # inner text block of the overview
    "c-wiz[data-node-index] div[data-content-feature]",
]

# Pause between queries. Short by default -- long enough to not look like a
# scripted flood, short enough to get through the list quickly. Override with
# --delay MIN MAX, or --no-delay for zero (fastest, but a few hundred back-to-back
# Google searches from one IP is the surest way to get CAPTCHA'd -- see module
# docstring; if that happens, the script pauses for you to solve it).
DEFAULT_MIN_DELAY_SECONDS = 2.0
DEFAULT_MAX_DELAY_SECONDS = 4.0


def load_kanji_list() -> list[dict]:
    if not KANJI_LIST_PATH.exists():
        raise SystemExit(
            f"{KANJI_LIST_PATH} not found -- this should have been provided alongside "
            f"this script. Ask for a refreshed copy if the database has changed since."
        )
    return json.loads(KANJI_LIST_PATH.read_text(encoding="utf-8"))


def load_progress() -> set[str]:
    if PROGRESS_PATH.exists():
        return set(json.loads(PROGRESS_PATH.read_text(encoding="utf-8")).get("done", []))
    return set()


def save_progress(done: set[str]):
    PROGRESS_PATH.write_text(json.dumps({"done": sorted(done)}, ensure_ascii=False, indent=1), encoding="utf-8")


def append_result(record: dict):
    with open(RESULTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def looks_like_captcha(page) -> bool:
    text = page.content().lower()
    return "unusual traffic" in text or "recaptcha" in text or "detected unusual traffic" in text


# Whole-string (trimmed, lowercased) label / aria-label of a "Show more" control.
# Matched exactly, not as a substring, so "more results" / "learn more" don't fire.
# Add your browser locale's wording if a screenshot shows the button unclicked.
SHOW_MORE_LABELS = [
    "show more", "show all", "see more", "show more ai overview", "expand",
    "показать больше", "ещё", "еще", "развернуть", "показать всё", "показать все",
]

# One JS pass that (a) finds the AI Overview region, (b) forces every truncation
# mechanism Google is known to use inside it OPEN -- clicking expander controls,
# setting aria-expanded, opening <details>, and stripping the CSS that clamps
# height (line-clamp / -webkit-box / max-height / overflow) -- and (c) returns the
# region's full innerText. This is deliberately not dependent on one button
# selector: even if the click target has changed, killing the clamp CSS still
# reveals the text that was hidden below the fold.
_EXPAND_AND_READ_JS = r"""
(labels) => {
  const norm = s => (s || "").replace(/\s+/g, " ").trim().toLowerCase();

  // 1. Locate the AI Overview region.
  let root = null;
  const bySel = [
    "[aria-label='AI Overview']", "[aria-label*='AI Overview' i]",
    "#m-x-content", "#Odp5De", "div[data-attrid='wa:/description']",
    "div[jsname='I4bIT']",
  ];
  for (const sel of bySel) { const e = document.querySelector(sel); if (e) { root = e; break; } }
  if (!root) {
    // Fall back: find a heading whose text is "AI Overview" and walk up to a
    // container that holds a meaningful amount of text.
    const heads = [...document.querySelectorAll("h1,h2,h3,div[role='heading'],span")]
      .filter(e => norm(e.textContent) === "ai overview");
    if (heads.length) {
      let n = heads[0];
      for (let i = 0; i < 6 && n && n.parentElement; i++) {
        n = n.parentElement;
        if ((n.innerText || "").length > 400) { root = n; break; }
      }
      if (!root) root = heads[0].parentElement;
    }
  }
  if (!root) return { text: null, clicked: 0, unclamped: 0, foundRoot: false };

  let clicked = 0, unclamped = 0;

  // 2. Click expander controls inside the region, a few rounds (a "Show more"
  //    can reveal another one). Never click the same element twice -- some of
  //    these toggle, so a second click would re-collapse. The marker attribute
  //    persists across this function's repeated calls from the poll loop.
  for (let round = 0; round < 4; round++) {
    let any = false;
    const ctrls = root.querySelectorAll(
      "button, [role='button'], a[jsaction], [jsaction*='click'], summary"
    );
    for (const c of ctrls) {
      if (c.hasAttribute("data-ck-clicked")) continue;
      const lab = norm(c.getAttribute("aria-label")) || norm(c.textContent);
      const isMore = labels.includes(lab) || c.getAttribute("aria-expanded") === "false";
      if (!isMore) continue;
      c.setAttribute("data-ck-clicked", "1");
      try {
        c.scrollIntoView({ block: "center" });
        c.click();
        clicked++; any = true;
      } catch (e) {}
    }
    if (!any) break;
  }

  // 3. Open <details>, set aria-expanded, and strip clamp styles everywhere in root.
  root.querySelectorAll("details:not([open])").forEach(d => { d.open = true; unclamped++; });
  root.querySelectorAll("[aria-expanded='false']").forEach(e => e.setAttribute("aria-expanded", "true"));
  const all = root.querySelectorAll("*");
  for (const el of all) {
    const cs = getComputedStyle(el);
    const clamped =
      cs.webkitLineClamp && cs.webkitLineClamp !== "none" ||
      cs.display === "-webkit-box" ||
      (cs.maxHeight && cs.maxHeight !== "none" && parseFloat(cs.maxHeight) < el.scrollHeight - 4) ||
      ((cs.overflow === "hidden" || cs.overflowY === "hidden") && el.scrollHeight > el.clientHeight + 4);
    if (clamped) {
      el.style.setProperty("-webkit-line-clamp", "unset", "important");
      el.style.setProperty("max-height", "none", "important");
      el.style.setProperty("height", "auto", "important");
      el.style.setProperty("overflow", "visible", "important");
      el.style.setProperty("display", "block", "important");
      unclamped++;
    }
  }

  const text = (root.innerText || "").trim();
  // "Generating" = the overview box exists but Google is still streaming it in
  // ("Searching...", a lone "AI Overview" heading, a bare loading dot). Treat a
  // short body that is basically just the heading / a spinner word as not-ready.
  const body = norm(text).replace(/^ai overview/, "").trim();
  const generating =
    body.length < 40 ||
    /^(searching|generating|loading|thinking)\b/.test(body) ||
    body === "…" || body === "...";

  return { text: text || null, clicked, unclamped, foundRoot: true, generating };
}
"""

# How long to keep polling once the AI Overview box has appeared but is still
# "Searching..." -- Google can take a while to finish generating one.
GENERATING_BUDGET_S = 25
# How long to wait for ANY AI Overview box to show up before giving up on this
# query having one at all.
APPEAR_BUDGET_S = 12


def expand_and_read(page) -> dict:
    """Poll for the AI Overview, run a JS pass that forces it fully open, and
    return its text. Handles the three states seen in practice:
      - no overview box ever appears  -> give up after APPEAR_BUDGET_S
      - box appears but says "Searching..." -> keep polling to GENERATING_BUDGET_S
      - box has real text             -> expand it, return once it stops growing
    Returns {text, clicked, unclamped, found_root, generating}."""
    start = time.monotonic()
    best = {"text": None, "clicked": 0, "unclamped": 0, "found_root": False, "generating": False}
    stable = 0
    first_real_text_at = None
    while True:
        now = time.monotonic()
        try:
            r = page.evaluate(_EXPAND_AND_READ_JS, SHOW_MORE_LABELS)
        except Exception:
            if now - start > APPEAR_BUDGET_S:
                break
            page.wait_for_timeout(400)
            continue

        found = bool(r.get("found_root"))
        generating = bool(r.get("generating"))
        cur_len = len(r.get("text") or "")
        best_len = len(best["text"] or "")

        if found:
            best["found_root"] = True
        best["generating"] = generating
        if cur_len >= best_len and not (generating and best_len > 0):
            best["text"] = r.get("text") or best["text"]
        best["clicked"] = max(best["clicked"], r.get("clicked", 0))
        best["unclamped"] = max(best["unclamped"], r.get("unclamped", 0))
        best_len = len(best["text"] or "")

        # Terminal conditions.
        if not found and now - start > APPEAR_BUDGET_S:
            break  # no overview on this page
        if found and generating:
            if now - start > GENERATING_BUDGET_S:
                break  # gave it a fair chance; still spinning
            stable = 0
            page.wait_for_timeout(700)
            continue
        if found and not generating and cur_len > 0:
            if first_real_text_at is None:
                first_real_text_at = now
            # Done once real text stopped growing for two polls, or we've been
            # reading real text for 10s (chained expansions settled).
            if cur_len <= best_len:
                stable += 1
                if stable >= 2 and best_len > 120:
                    break
            else:
                stable = 0
            if now - first_real_text_at > 10:
                break
        page.wait_for_timeout(500)
    return best


def dump_debug(page, entry: dict):
    """Save everything about the current page so we can see why the AI Overview
    isn't coming through: full HTML, visible text, and a list of every button /
    role=button with its label. Written next to the script."""
    stem = HERE / f"debug_{entry['id']}"
    try:
        (stem.with_suffix(".html")).write_text(page.content(), encoding="utf-8")
    except Exception as e:
        print(f"  (couldn't save HTML: {e})")
    try:
        body_text = page.evaluate("() => document.body.innerText")
        (stem.with_suffix(".txt")).write_text(body_text, encoding="utf-8")
    except Exception:
        body_text = ""
    try:
        controls = page.evaluate("""() => {
          const out = [];
          for (const c of document.querySelectorAll("button, [role='button'], a[jsaction], summary")) {
            const t = (c.getAttribute("aria-label") || c.innerText || "").replace(/\\s+/g," ").trim();
            if (t) out.push(t.slice(0, 80));
          }
          return out;
        }""")
    except Exception:
        controls = []
    print(f"\n  === DEBUG {entry['id']} {entry['character']} ===")
    print(f"  page title: {page.title()!r}")
    print(f"  body text length: {len(body_text)}")
    low = body_text.lower()
    for probe in ("ai overview", "ai-powered overview", "sign in", "unusual traffic",
                  "generative ai is experimental", "show more", "search labs"):
        if probe in low:
            i = low.index(probe)
            print(f"  found {probe!r}: ...{body_text[max(0,i-40):i+80]!r}...")
    print(f"  {len(controls)} clickable controls; labels containing 'overview'/'more'/'ai':")
    for c in controls:
        cl = c.lower()
        if any(k in cl for k in ("overview", "more", "ai ", "generat", "show", "expand")):
            print(f"    - {c!r}")
    print(f"  full HTML -> {stem.with_suffix('.html').name}, text -> {stem.with_suffix('.txt').name}")
    print(f"  === end debug ===\n")


def check_one(page, entry: dict, debug: bool = False) -> dict:
    query = QUERY_TEMPLATE.format(char=entry["character"])
    page.goto(f"https://www.google.com/search?q={query}", timeout=30000)
    # No fixed sleep here -- expand_and_read() polls for the AI Overview itself
    # (it streams in after the page settles) and returns as soon as the text
    # stops growing, so a static wait would only ever be dead time.
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass

    if looks_like_captcha(page):
        print(f"\n  !! CAPTCHA shown for {entry['id']} ({entry['character']}).")
        print("     Solve it in the browser window, then press Enter here to continue...")
        input()

    if debug:
        page.wait_for_timeout(3000)
        dump_debug(page, entry)

    r = expand_and_read(page)

    screenshot_path = SCREENSHOTS_DIR / f"{entry['id']}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)

    text = r["text"]
    if r["generating"]:
        # Box appeared but Google never finished generating -- the text is just
        # "Searching..."/the heading. Store null so a re-run picks it up rather
        # than a useless partial.
        text = None

    return {
        "id": entry["id"],
        "character": entry["character"],
        "keyword": entry["keyword"],
        "current_parts": entry["current_parts"],
        "query": query,
        "extracted_text": text,
        "still_generating": r["generating"],  # box appeared but never finished
        "expand_clicks": r["clicked"],       # expander controls clicked inside the overview
        "unclamped_nodes": r["unclamped"],   # nodes whose truncation CSS was stripped
        "found_overview": r["found_root"],   # the AI Overview region was located at all
        "screenshot": str(screenshot_path.relative_to(HERE)),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=10, help="How many kanji to check this run (default 10)")
    parser.add_argument("--all", action="store_true",
                         help="Check every not-yet-done kanji in one run, in order, instead of --count random ones. "
                              "Safe to Ctrl+C and re-run later -- progress is saved after each kanji, so it picks "
                              "up where it left off. At the default ~3s delay, budget very roughly 10-15s per "
                              "kanji including page load and extraction. The browser window can sit in the "
                              "background between runs.")
    parser.add_argument("--id", help="Check one specific kanji id instead of random ones")
    parser.add_argument("--resume-only", action="store_true",
                         help="Don't pick new kanji, just re-run this many from the not-yet-done pool in order")
    parser.add_argument("--from-list", metavar="FILE",
                         help="Re-check exactly the ids listed in FILE (a JSON list of {\"id\": ...} "
                              "objects or a bare JSON list of id strings), in order, ignoring progress.json. "
                              "Use this to redo kanji whose earlier run produced no/truncated Google text. "
                              "results.jsonl gets a fresh appended record for each; the newest wins when the "
                              "file is read later.")
    parser.add_argument("--delay", nargs=2, type=float, metavar=("MIN", "MAX"),
                         default=[DEFAULT_MIN_DELAY_SECONDS, DEFAULT_MAX_DELAY_SECONDS],
                         help=f"Random pause (seconds) between queries "
                              f"(default {DEFAULT_MIN_DELAY_SECONDS} {DEFAULT_MAX_DELAY_SECONDS})")
    parser.add_argument("--no-delay", action="store_true",
                         help="No pause between queries at all -- fastest, but hammering Google from one "
                              "IP is the surest way to get CAPTCHA-blocked. The script will pause for you "
                              "to solve a CAPTCHA if one appears, so this is recoverable, just slower when "
                              "it goes wrong.")
    parser.add_argument("--debug", action="store_true",
                         help="For each kanji, dump the full page HTML + visible text + a list of every "
                              "clickable control (debug_<id>.html / .txt) and print what markers are on "
                              "the page. Use this when the AI Overview isn't coming through -- it shows "
                              "whether Google is serving one at all, asking for sign-in, showing a CAPTCHA, "
                              "or just needs a control clicked that the script isn't finding. Also keeps "
                              "the browser open at the end so you can look. Pair with --id or a 1-item list.")
    args = parser.parse_args()

    delay_min, delay_max = (0.0, 0.0) if args.no_delay else (args.delay[0], args.delay[1])

    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    all_kanji = load_kanji_list()
    done = load_progress()
    by_id = {e["id"]: e for e in all_kanji}

    if args.from_list:
        raw = json.loads(Path(args.from_list).read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not raw:
            raise SystemExit(f"{args.from_list}: expected a non-empty JSON list")
        batch = []
        for x in raw:
            entry = x if isinstance(x, dict) else {"id": x}
            eid = entry.get("id")
            if not eid:
                continue
            # Prefer the full record from the kanji list (has current_parts); fall back
            # to whatever fields the list file itself carries -- need_rerun.json has
            # id/character/keyword but not current_parts, and ~half its ids are no
            # longer in unreviewed_kanji.json because they've since been reviewed.
            base = dict(by_id.get(eid, {}))
            base.setdefault("id", eid)
            base.setdefault("character", entry.get("character", ""))
            base.setdefault("keyword", entry.get("keyword", ""))
            base.setdefault("current_parts", entry.get("current_parts", []))
            if not base["character"]:
                print(f"  skipping {eid}: no character glyph available")
                continue
            batch.append(base)
        if not batch:
            raise SystemExit("Nothing to check -- no usable entries in the list.")
    elif args.id:
        if args.id not in by_id:
            raise SystemExit(f"{args.id} not found in {KANJI_LIST_PATH.name}")
        batch = [by_id[args.id]]
    else:
        pending = [e for e in all_kanji if e["id"] not in done]
        if not pending:
            print("Nothing left to check -- every kanji in the list has been done.")
            return
        if args.all:
            batch = pending
        elif args.resume_only:
            batch = pending[:args.count]
        else:
            batch = random.sample(pending, min(args.count, len(pending)))

    if args.from_list:
        print(f"Re-checking {len(batch)} kanji from {args.from_list} "
              f"(ignoring progress.json for this run)...")
    else:
        print(f"Checking {len(batch)} kanji ({len(done)} already done, "
              f"{len(all_kanji) - len(done)} remaining before this run)...")
    print("A browser window will open. Leave it alone unless a CAPTCHA appears.\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for i, entry in enumerate(batch, 1):
                print(f"[{i}/{len(batch)}] {entry['id']} {entry['character']} ({entry['keyword']})...", end=" ", flush=True)
                try:
                    record = check_one(page, entry, debug=args.debug)
                except Exception as exc:
                    print(f"FAILED: {exc}")
                    continue
                append_result(record)
                done.add(entry["id"])
                save_progress(done)
                if record["extracted_text"]:
                    found = f"OK  {len(record['extracted_text'])} chars"
                    if record.get("expand_clicks"):
                        found += f", {record['expand_clicks']} expand-clicks"
                    if record.get("unclamped_nodes"):
                        found += f", {record['unclamped_nodes']} unclamped"
                elif record.get("still_generating"):
                    found = "SKIP  overview still 'Searching...' after 25s (stored null; re-run later)"
                elif record.get("found_overview"):
                    found = "SKIP  overview box found but empty (check screenshot)"
                else:
                    found = "SKIP  no AI overview for this query (check screenshot)"
                print(found)

                if i < len(batch) and delay_max > 0:
                    time.sleep(random.uniform(delay_min, delay_max))
        except KeyboardInterrupt:
            print(f"\nStopped early at [{i}/{len(batch)}]. Progress is saved -- "
                  f"just re-run the same command later to pick up where you left off.")
        finally:
            if args.debug:
                input("\n--debug: browser left open. Look at the page, then press Enter to close...")
            context.close()

    print(f"\nDone. Results appended to {RESULTS_PATH.name}. "
          f"{len(done)}/{len(all_kanji)} kanji checked so far overall.")


if __name__ == "__main__":
    main()
