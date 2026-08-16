"""
audit_csv_regressions.py — flag data.txt/data_from_pdf.txt overrides that
irrecoverably dropped a concept heisig-kanjis.csv's own baseline had.

Background: sessions 10 and 11 (docs/2026-08-search-quality-audit.md) found
the same bug shape three times in a row by hand — 告/産/報/執/熱 all had a
data.txt override that discarded heisig-kanjis.csv's own already-correct
component list (e.g. 告's CSV baseline is "cow; mouth", but a data.txt
override replaced it with a flattened "ノ,口,土" that drops 牛/"cow"
entirely). Each time, the CSV baseline was right there in the repo the
whole time; nobody had compared overrides against it systematically before
these fixes were reported by the owner one at a time.

This script automates that comparison, deterministic and no API key needed
(same style as audit_radicals.py).

## What counts as "dropped" — and why a naive diff doesn't work

heisig-kanjis.csv's `components` field is already fully recursively
pre-expanded (CLAUDE.md: "no recursive expansion needed at query time") —
so it lists both a compound primitive AND that primitive's own sub-pieces
side by side, e.g. 舌's CSV baseline includes "thousand" *and*
"drop, ten, needle" (thousand's own components), redundantly, by design.
Now that query-time recursive resolution exists (session 2/3), a *good*
override can legitimately reference just the top-level compound and rely on
recursion for the rest — a naive "is every CSV term present in the final
flat parts list" comparison flags that as a false-positive "regression". A
first version of this script did exactly that and flagged 1729/3000 kanji,
almost all noise.

The fix: a CSV term is only "dropped" if its canonical id is unreachable
from the override's parts even after following recursive decomposition —
i.e. not just "is X literally in the override's parts list" but "is X
somewhere in the transitive closure of what the override's parts recursively
expand to" (same MAX_DECOMPOSITION_DEPTH/cycle-guard semantics
_resolve_parts_detail already uses for the UI's expandable chips). This
matches every one of sessions 10/11's confirmed bugs (each dropped a
concept that genuinely doesn't appear anywhere in the override, at any
depth) while treating "the override just correctly relies on recursion" as
the non-issue it now architecturally is.

This still deliberately only catches *loss* of a resolvable concept — it
does NOT flag overrides that only *add* extra terms beyond the CSV baseline
(session 11's 産 bug was exactly that shape — padded with three extra terms,
nothing dropped — needs eyeballing by hand). An override that explicitly
sets a kanji's parts to empty (the documented "this primitive is atomic"
convention, e.g. rtk1743 門) is never flagged.

## Usage

    python3 audit_csv_regressions.py [--max-depth N]

Prints one block per flagged kanji: id, character, keyword, the CSV
baseline, the current (overridden) parts, and which specific CSV concepts
are unreachable. Read each one before touching data.txt — some overrides
are legitimate corrections of a CSV bug (heisig-kanjis.csv has its own
known duplicate-component issues, e.g. rtk1261 斗 in Finding 3) or a
deliberate re-grouping the CSV's flat expansion can't represent, so
"flagged" means "needs a human/agent judgement call", not "definitely
wrong".
"""
import argparse
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402

DEFAULT_MAX_DEPTH = 4


def build_shadow_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="kanji_csv_audit_"))
    tmp_db = tmp_dir / "shadow.db"
    database.DB_PATH = tmp_db
    database.init_db()
    conn = database.get_db()
    database.migrate_schema(conn)
    conn.close()
    database.import_data()
    return tmp_db


def load_csv_baseline() -> dict[str, list[str]]:
    """id -> raw CSV component terms (lowercased), before any override."""
    baseline: dict[str, list[str]] = {}
    with open(database.CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            frame = (row.get("id_6th_ed") or "").strip()
            if not frame.isdigit():
                continue
            comp_str = row.get("components", "").strip()
            terms = [t.strip().lower() for t in comp_str.split(";") if t.strip()]
            baseline[f"rtk{frame}"] = terms
    return baseline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    args = parser.parse_args()

    print("Building shadow database from source files...", flush=True)
    shadow_db = build_shadow_db()
    conn = database.sqlite3.connect(shadow_db)
    conn.row_factory = database.sqlite3.Row

    baseline = load_csv_baseline()
    pdf_parts = database._load_parts_file(database.PDF_PATH)
    prim_parts = database._load_parts_file(database.PRIM_PATH)
    merged_overrides = {**pdf_parts, **prim_parts}

    def resolve(term: str) -> str | None:
        row = conn.execute(
            "SELECT kanji_id FROM aliases WHERE alias = ? "
            "UNION SELECT id FROM kanji WHERE id = ? OR character = ? LIMIT 1",
            (term, term, term)
        ).fetchone()
        return row[0] if row else None

    own_parts_cache: dict[str, list[str]] = {}

    def own_parts(kid: str) -> list[str]:
        if kid not in own_parts_cache:
            own_parts_cache[kid] = [
                r["part_term"] for r in conn.execute(
                    "SELECT p.part_term FROM parts p JOIN decompositions d ON d.id = p.decomposition_id "
                    "WHERE p.kanji_id = ? AND d.owner_id = 1 ORDER BY p.position", (kid,)
                ).fetchall()
            ]
        return own_parts_cache[kid]

    def transitive_closure(kid: str) -> set[str]:
        """Every canonical id reachable from kid's own decomposition, recursively,
        bounded by --max-depth and a cycle guard (same shape as the app's own
        _resolve_parts_detail, reimplemented here against the shadow DB directly)."""
        seen: set[str] = set()
        frontier = [(kid, 0)]
        while frontier:
            cur, depth = frontier.pop()
            if depth > args.max_depth:
                continue
            for term in own_parts(cur):
                cid = resolve(term)
                if cid is None or cid == cur or cid in seen:
                    continue
                seen.add(cid)
                frontier.append((cid, depth + 1))
        return seen

    flagged = []
    for kid, csv_terms in baseline.items():
        if kid not in merged_overrides:
            continue  # no override at all -> CSV baseline is used as-is, nothing to compare
        override_terms = merged_overrides[kid]
        if not override_terms:
            continue  # explicit "atomic" override -- deliberate, not a regression

        final_terms = own_parts(kid)
        reachable = {resolve(t) for t in final_terms} - {None}
        reachable |= transitive_closure(kid)

        dropped = []
        for t in csv_terms:
            cid = resolve(t)
            if cid is not None and cid not in reachable and cid != kid:
                dropped.append((t, cid))

        if dropped:
            row = conn.execute("SELECT character, keyword FROM kanji WHERE id = ?", (kid,)).fetchone()
            flagged.append({
                "id": kid, "character": row["character"], "keyword": row["keyword"],
                "csv_terms": csv_terms, "final_terms": final_terms, "dropped": dropped,
            })

    conn.close()

    print(f"\n{len(flagged)} kanji flagged (dropped a concept unreachable even via recursion):\n")
    for f in flagged:
        dropped_str = ", ".join(f"{t} (-> {cid})" for t, cid in f["dropped"])
        print(f"- {f['id']} {f['character']} ({f['keyword']})")
        print(f"    CSV baseline:  {', '.join(f['csv_terms'])}")
        print(f"    current parts: {', '.join(f['final_terms']) or '(empty)'}")
        print(f"    dropped:       {dropped_str}")


if __name__ == "__main__":
    main()
