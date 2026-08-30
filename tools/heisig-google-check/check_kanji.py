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
visitor across days) and paces itself with random delays between queries -- the
same as a person doing this by hand, just less tedious. If Google ever shows a
CAPTCHA, the script pauses and waits for you to solve it in the visible window
before continuing.

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

Run it once a day (or whenever) -- it remembers what's already been checked in
progress.json and won't repeat kanji. Sending results back: either paste the
contents of results.jsonl into a message, or (if this checkout has git access)
`git add docs/heisig-google-check/results.jsonl && git commit && git push` -- either
way, a future session can read it and do the actual comparison against data.txt.

Output:
    results.jsonl   -- one JSON object per kanji checked: id, character, keyword,
                       current_parts (what the DB currently has), the extracted AI
                       Overview text (or null if none was found), and a path to a
                       saved screenshot for manual review either way.
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
# a real browser -> Inspect, and add/update a selector here.
AI_OVERVIEW_SELECTORS = [
    "[data-attrid='wa:/description']",
    "div.LT6Xte",  # a historically-used AI Overview container class; likely stale
    "div[data-md]",
    "#Odp5De",
]

MIN_DELAY_SECONDS = 20
MAX_DELAY_SECONDS = 60


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


def expand_ai_overview(page):
    """AI Overview often truncates behind a 'Show more' toggle -- click it so both the
    extracted text and the screenshot capture the full answer, not just the preview.
    Best-effort: some overviews have nothing to expand, so a missing/unclickable
    button is not an error."""
    try:
        button = page.get_by_role("button", name="Show more").first
        if button.is_visible(timeout=2000):
            button.click()
            page.wait_for_timeout(800)
    except Exception:
        pass


def extract_ai_overview(page) -> str | None:
    for selector in AI_OVERVIEW_SELECTORS:
        try:
            el = page.query_selector(selector)
            if el:
                text = el.inner_text().strip()
                if text:
                    return text
        except Exception:
            continue
    return None


def check_one(page, entry: dict) -> dict:
    query = QUERY_TEMPLATE.format(char=entry["character"])
    page.goto(f"https://www.google.com/search?q={query}", timeout=30000)
    page.wait_for_timeout(2500)

    if looks_like_captcha(page):
        print(f"\n  !! CAPTCHA shown for {entry['id']} ({entry['character']}).")
        print("     Solve it in the browser window, then press Enter here to continue...")
        input()
        page.wait_for_timeout(1500)

    expand_ai_overview(page)

    screenshot_path = SCREENSHOTS_DIR / f"{entry['id']}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)

    extracted = extract_ai_overview(page)

    return {
        "id": entry["id"],
        "character": entry["character"],
        "keyword": entry["keyword"],
        "current_parts": entry["current_parts"],
        "query": query,
        "extracted_text": extracted,
        "screenshot": str(screenshot_path.relative_to(HERE)),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=10, help="How many kanji to check this run (default 10)")
    parser.add_argument("--all", action="store_true",
                         help="Check every not-yet-done kanji in one run, in order, instead of --count random ones. "
                              "Safe to Ctrl+C and re-run later -- progress is saved after each kanji, so it picks "
                              "up where it left off. With ~1800 kanji and a 20-60s delay between each, expect this "
                              "to take roughly 10-30 hours of wall-clock time (it doesn't need to be unattended --"
                              "the browser window can just sit in the background between runs).")
    parser.add_argument("--id", help="Check one specific kanji id instead of random ones")
    parser.add_argument("--resume-only", action="store_true",
                         help="Don't pick new kanji, just re-run this many from the not-yet-done pool in order")
    args = parser.parse_args()

    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    all_kanji = load_kanji_list()
    done = load_progress()
    by_id = {e["id"]: e for e in all_kanji}

    if args.id:
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
                    record = check_one(page, entry)
                except Exception as exc:
                    print(f"FAILED: {exc}")
                    continue
                append_result(record)
                done.add(entry["id"])
                save_progress(done)
                found = "found AI overview" if record["extracted_text"] else "no overview extracted (check screenshot)"
                print(found)

                if i < len(batch):
                    delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
                    time.sleep(delay)
        except KeyboardInterrupt:
            print(f"\nStopped early at [{i}/{len(batch)}]. Progress is saved -- "
                  f"just re-run the same command later to pick up where you left off.")
        finally:
            context.close()

    print(f"\nDone. Results appended to {RESULTS_PATH.name}. "
          f"{len(done)}/{len(all_kanji)} kanji checked so far overall.")


if __name__ == "__main__":
    main()
