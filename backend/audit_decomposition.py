"""
audit_decomposition.py — LLM sanity-check of RTK kanji decompositions.

Rebuilds a throwaway copy of the database from the real source files
(heisig-kanjis.csv, data_from_pdf.txt, data.txt) using the actual import
pipeline in database.py — so this sees exactly the merged/expanded parts
list production would use for search, warts and all (data.txt overrides
winning over data_from_pdf.txt, expand_part_terms() appending a part's
keyword when a listed part is itself a kanji character, etc). Never
touches backend/kanji.db.

For each rtk{n} kanji, asks an LLM whether its final parts list is a
sensible Heisig-style primitive decomposition, and writes a markdown
report of anything flagged, with a pointer to the source file/line that
produced the current value so it's fast to go fix.

Usage:
    pip install openai   # not in requirements.txt — this script isn't part of the app runtime
    export OPENAI_API_KEY=...
    python3 audit_decomposition.py [--limit N] [--model MODEL] [--force]

Results are cached in audit_results.jsonl (gitignored) as they come in,
so a killed/interrupted run can be resumed by just running again; --force
clears the cache and re-audits everything. The report is regenerated from
the cache on every run, so `python3 audit_decomposition.py --limit 0` (no
new audit calls, just point at an existing cache) is free.
"""
import argparse
import csv
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

from openai import OpenAI

ROOT_DIR      = Path(__file__).parent
CSV_PATH      = ROOT_DIR / "heisig-kanjis.csv"
PDF_PATH      = ROOT_DIR / "data_from_pdf.txt"
PRIM_PATH     = ROOT_DIR / "data.txt"
RESULTS_PATH  = ROOT_DIR.parent / "audit_results.jsonl"
REPORT_PATH   = ROOT_DIR.parent / "audit_report.md"

BATCH_SIZE    = 25
DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """\
You are auditing a Heisig-style ("Remembering the Kanji") primitive decomposition \
database for a Japanese kanji-learning app. Each kanji has a keyword and a list of \
"part" terms meant to be the primitives a learner recognizes when looking at the \
character: named visual building blocks, roughly matching how Heisig's method \
breaks a character down (not just any literal stroke group, and not the \
dictionary radical).

For each kanji, judge whether its listed parts are a sensible decomposition:

- "wrong": parts are clearly incorrect for this character — components that don't \
visually appear in the glyph at all, or terms that make no sense for it.
- "suspicious": parts are technically related but look like a bad decomposition — \
duplicated/redundant terms, a primitive standing in as a proxy for something whose \
own meaning is unrelated (e.g. using a character purely because it happens to \
contain the right radical, without the part being aliased to that meaning), an \
obviously missing major visible component, or a breakdown that doesn't read like a \
usable Heisig-style primitive story.
- "ok": a reasonable, useful decomposition for a learner, even if it's not \
verbatim what Heisig's book uses.

An empty parts list is "ok" if the character is a genuinely atomic Heisig primitive \
with no visible sub-components (e.g. 一, 二, 八, 目) — not a bug in that case. It's \
"wrong" or "suspicious" if the character is visually composed of recognizable \
sub-parts that just aren't listed.

Respond with strict JSON only, no prose:
{"results": [{"id": "<kanji id>", "verdict": "ok"|"suspicious"|"wrong", \
"issue": "<short reason, empty string if ok>", "suggested_parts": [...] or null}]}
Include one result object per kanji given, in any order.
"""


def build_shadow_db() -> Path:
    """Run the real import pipeline against a throwaway sqlite file so the audit
    sees production's actual merged/expanded parts, not a hand-reimplemented guess
    at the merge logic."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="kanji_audit_"))
    tmp_db = tmp_dir / "shadow.db"
    database.DB_PATH = tmp_db
    database.init_db()
    conn = database.get_db()
    database.migrate_schema(conn)
    conn.close()
    database.import_data()
    return tmp_db


def load_rtk_entries(shadow_db: Path) -> list[dict]:
    conn = database.sqlite3.connect(shadow_db)
    conn.row_factory = database.sqlite3.Row
    rows = conn.execute(
        "SELECT id, character, keyword, frame FROM kanji "
        "WHERE id LIKE 'rtk%' AND owner_id = 1 ORDER BY frame"
    ).fetchall()
    entries = []
    for r in rows:
        parts = [
            p["part_term"] for p in conn.execute(
                "SELECT part_term FROM parts p "
                "JOIN decompositions d ON d.id = p.decomposition_id "
                "WHERE p.kanji_id = ? AND d.owner_id = 1 ORDER BY p.position",
                (r["id"],)
            ).fetchall()
        ]
        entries.append({
            "id": r["id"], "character": r["character"],
            "keyword": r["keyword"], "frame": r["frame"], "parts": parts,
        })
    conn.close()
    return entries


def trace_origins() -> dict[str, tuple[str, int]]:
    """Map kanji id -> (source_file, line_number) for whichever source actually
    supplied its current parts list, mirroring the priority data.txt > \
    data_from_pdf.txt > heisig-kanjis.csv used by database.py's import_data()."""
    origins: dict[str, tuple[str, int]] = {}

    if CSV_PATH.exists():
        with open(CSV_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                frame = (row.get("id_6th_ed") or "").strip()
                if frame.isdigit():
                    origins[f"rtk{frame}"] = ("heisig-kanjis.csv", reader.line_num)

    for path in (PDF_PATH, PRIM_PATH):
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                cols = line.split(":")
                pid = cols[0].strip().lower()
                parts_str = cols[3].strip() if len(cols) > 3 else ""
                if pid and parts_str:
                    origins[pid] = (path.name, lineno)

    return origins


def load_cache() -> dict[str, dict]:
    cache = {}
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    cache[rec["id"]] = rec
    return cache


def append_cache(records: list[dict]):
    with open(RESULTS_PATH, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def audit_batch(client: OpenAI, model: str, batch: list[dict]) -> list[dict]:
    payload = [
        {"id": e["id"], "character": e["character"], "keyword": e["keyword"], "parts": e["parts"]}
        for e in batch
    ]
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    parsed = json.loads(resp.choices[0].message.content)
    return parsed.get("results", [])


def run_audit(entries: list[dict], model: str, limit: int | None):
    cache = load_cache()
    pending = [e for e in entries if e["id"] not in cache]
    if limit is not None:
        pending = pending[:limit]

    if not pending:
        print(f"Nothing new to audit ({len(cache)} cached results).", flush=True)
        return

    client = OpenAI()
    print(f"Auditing {len(pending)} kanji in batches of {BATCH_SIZE} with {model}...", flush=True)

    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        try:
            results = audit_batch(client, model, batch)
        except Exception as exc:
            print(f"  batch {i // BATCH_SIZE + 1}: FAILED ({exc}), retrying once...", flush=True)
            time.sleep(3)
            try:
                results = audit_batch(client, model, batch)
            except Exception as exc2:
                print(f"  batch {i // BATCH_SIZE + 1}: failed again, skipping ({exc2})", flush=True)
                continue

        by_id = {r["id"]: r for r in results if "id" in r}
        records = []
        for e in batch:
            r = by_id.get(e["id"])
            if not r:
                continue
            records.append({
                "id": e["id"], "character": e["character"], "keyword": e["keyword"],
                "parts": e["parts"], "verdict": r.get("verdict", "ok"),
                "issue": r.get("issue", ""), "suggested_parts": r.get("suggested_parts"),
            })
        append_cache(records)
        print(f"  batch {i // BATCH_SIZE + 1}/{(len(pending) - 1) // BATCH_SIZE + 1} done "
              f"({len(records)} results)", flush=True)


def write_report(entries: list[dict], origins: dict[str, tuple[str, int]]):
    cache = load_cache()
    # Empty parts is deliberately NOT flagged here — it's correct for a genuinely
    # atomic primitive (一, 二, 八, ...) and wrong for anything else, and telling
    # those apart needs judgement, so it goes through the LLM pass instead.
    structural = []  # cheap checks, no LLM needed
    for e in entries:
        if e["parts"] and len(e["parts"]) != len(set(e["parts"])):
            dupes = sorted({p for p in e["parts"] if e["parts"].count(p) > 1})
            structural.append((e, f"duplicate part term(s): {', '.join(dupes)}"))

    wrong = [cache[e["id"]] for e in entries if cache.get(e["id"], {}).get("verdict") == "wrong"]
    suspicious = [cache[e["id"]] for e in entries if cache.get(e["id"], {}).get("verdict") == "suspicious"]
    audited = sum(1 for e in entries if e["id"] in cache)

    def origin_str(eid):
        origin = origins.get(eid)
        return f"`{origin[0]}:{origin[1]}`" if origin else "unknown"

    def fmt_llm(rec):
        line = (f"- **{rec['id']}** {rec['character']} ({rec['keyword']}) — "
                f"parts: `{', '.join(rec['parts']) or '(none)'}`\n"
                f"  - issue: {rec['issue']}\n  - source: {origin_str(rec['id'])}")
        if rec.get("suggested_parts"):
            line += f"\n  - suggested: `{', '.join(rec['suggested_parts'])}`"
        return line

    def fmt_structural(e, issue):
        return (f"- **{e['id']}** {e['character']} ({e['keyword']}) — "
                f"parts: `{', '.join(e['parts']) or '(none)'}`\n"
                f"  - issue: {issue}\n  - source: {origin_str(e['id'])}")

    lines = [
        "# RTK decomposition audit report",
        "",
        f"Audited {audited}/{len(entries)} kanji. "
        f"{len(wrong)} wrong, {len(suspicious)} suspicious, {len(structural)} structural issues.",
        "",
        "## Wrong",
        "",
    ]
    lines += [fmt_llm(r) for r in wrong] or ["(none)"]
    lines += ["", "## Suspicious", ""]
    lines += [fmt_llm(r) for r in suspicious] or ["(none)"]
    lines += ["", "## Structural (no LLM judgement needed)", ""]
    lines += [fmt_structural(e, issue) for e, issue in structural] or ["(none)"]

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to {REPORT_PATH} "
          f"({len(wrong)} wrong, {len(suspicious)} suspicious, {len(structural)} structural)", flush=True)


def main():
    parser = argparse.ArgumentParser(description="LLM-audit RTK kanji decompositions")
    parser.add_argument("--limit", type=int, default=None, help="Only audit the first N un-cached kanji")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--force", action="store_true", help="Clear the results cache and re-audit everything")
    args = parser.parse_args()

    if args.force and RESULTS_PATH.exists():
        RESULTS_PATH.unlink()

    print("Building shadow database from source files...", flush=True)
    shadow_db = build_shadow_db()
    entries = load_rtk_entries(shadow_db)
    print(f"  {len(entries)} rtk kanji loaded", flush=True)

    origins = trace_origins()

    run_audit(entries, args.model, args.limit)
    write_report(entries, origins)


if __name__ == "__main__":
    main()
