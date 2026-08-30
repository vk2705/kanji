#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
triage_google_check.py — cross-checks tools/heisig-google-check/results.jsonl (the
owner's local Google AI Overview lookups) against the LIVE database's current
resolved decomposition for each kanji, and flags disagreements for manual review.

This is a heuristic pre-filter, not a verdict: it extracts CJK characters mentioned
in the AI Overview text that look like they're part of the *primitive breakdown*
itself (cutting off at "Examples of X as a Primitive" / "Would you like" / "Show all"
markers, which introduce unrelated example kanji or follow-up chatter, not X's own
parts) and diffs that set against what get_kanji_detail actually resolves today.
Google's AI Overview is itself just another LLM's guess (see this project's own
audit doc for why that's not treated as authoritative) -- cjkvi-ids remains the
tiebreaker for anything flagged here, same as every other fix this session.

Usage:
    ./triage_google_check.py                 # print a summary + flagged list
    ./triage_google_check.py --show-text ID   # print one entry's full extracted_text
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

RESULTS_PATH = Path(__file__).parent.parent / "tools" / "heisig-google-check" / "results.jsonl"

# Text after any of these markers is examples/chatter about OTHER kanji, not the
# primitive breakdown of the kanji being asked about -- cut before extracting chars.
CUTOFF_MARKERS = [
    "Examples of", "You will see this primitive", "Would you like",
    "If you are currently studying", "Note on the Heisig Method",
]

CJK_RE = re.compile(r"[㐀-鿿぀-ヿ]")


def load_results() -> list[dict]:
    if not RESULTS_PATH.exists():
        raise SystemExit(f"{RESULTS_PATH} not found -- has it been pulled from the owner's push?")
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def extracted_chars(text: str, own_char: str) -> set[str]:
    for marker in CUTOFF_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    chars = set(CJK_RE.findall(text))
    chars.discard(own_char)
    return chars


def live_chars(conn, kid: str) -> set[str] | None:
    """Current live top-level resolved part characters, or None if the kanji id
    doesn't exist / has no decomposition (both worth flagging separately)."""
    row = conn.execute("SELECT id FROM kanji WHERE id = ?", (kid,)).fetchone()
    if not row:
        return None
    d = database.get_kanji_detail(conn, kid, viewer_id=None)
    if not d["decompositions"]:
        return set()
    return {p["character"] for p in d["decompositions"][0]["parts_detail"] if p["character"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--show-text", help="Print one entry's full extracted_text and exit")
    args = parser.parse_args()

    results = load_results()

    if args.show_text:
        rec = next((r for r in results if r["id"] == args.show_text), None)
        if not rec:
            raise SystemExit(f"{args.show_text} not found in results")
        print(rec["extracted_text"])
        return

    conn = database.sqlite3.connect(database.DB_PATH)
    conn.row_factory = database.sqlite3.Row

    agree, flagged, missing = [], [], []
    for rec in results:
        lchars = live_chars(conn, rec["id"])
        if lchars is None:
            missing.append(rec)
            continue
        echars = extracted_chars(rec["extracted_text"], rec["character"])
        # "Agree" if every extracted char is either already one of our parts, or IS
        # itself a further breakdown the AI gave beyond our (possibly atomic) parts --
        # so only flag when our own parts contain something the AI text never
        # mentions at all (a likely-missing or likely-wrong component on our side),
        # since the AI's text often adds MORE granularity than our flattened set does.
        missing_from_ai = lchars - echars if echars else set()
        if lchars and echars and missing_from_ai == lchars:
            # Complete disjoint sets -- strongest signal of a real disagreement.
            flagged.append((rec, lchars, echars, "disjoint"))
        elif lchars and echars and missing_from_ai:
            flagged.append((rec, lchars, echars, "partial"))
        else:
            agree.append(rec)

    conn.close()

    print(f"{len(results)} total results, {len(missing)} kanji not found live "
          f"(likely renamed/migrated ids), {len(agree)} look consistent, "
          f"{len(flagged)} flagged for review.\n")

    disjoint = [f for f in flagged if f[3] == "disjoint"]
    partial = [f for f in flagged if f[3] == "partial"]
    print(f"-- {len(disjoint)} DISJOINT (our parts and Google's text share nothing) --")
    for rec, lchars, echars, _ in disjoint:
        print(f"  {rec['id']} {rec['character']} ({rec['keyword']}): "
              f"ours={sorted(lchars)} google-mentions={sorted(echars)}")

    print(f"\n-- {len(partial)} PARTIAL (something in ours not echoed in Google's text) --")
    for rec, lchars, echars, _ in partial:
        print(f"  {rec['id']} {rec['character']} ({rec['keyword']}): "
              f"ours={sorted(lchars)} google-mentions={sorted(echars)}")

    if missing:
        print(f"\n-- {len(missing)} NOT FOUND live (id may have been renamed since the export) --")
        for rec in missing:
            print(f"  {rec['id']} {rec['character']} ({rec['keyword']})")


if __name__ == "__main__":
    main()
