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

## One name, several rows (fixed 2026-09-21)

The version above resolved each CSV term to **one** id — a `UNION ... LIMIT 1`,
whose row order SQLite does not even define — and then asked whether that one id
was reachable. Names are not one-to-one with rows and never have been: 貝 is
"shellfish" *and* "clam" *and* "oyster", and 蛤 and 蛎 are kanji whose keywords
are "clam" and "oyster". Pick the wrong claimant and a perfectly good
decomposition looks like it dropped a concept.

That is not hypothetical. After 2026-09-20's chunk 22 put twenty of Heisig's
synonym names onto the primitives they belong to, this script reported **926 of
3,000 kanji** — nearly all of them because "clam" now resolves to 蛤, or "drop"
to something other than 丶, rather than because anything was dropped.

So a term is satisfied if **any** row answering to it is reachable, and a term
that names the host itself is satisfied outright. Same rule
`audit_phantom_parts.py` uses (`claimants()`), and for the same reason: for
*evidence*, every claimant counts, even when search has to canonicalise to one.
**926 flagged → 718**, and two data fixes the corrected report then made visible
(deleting the `prim28.2` orphan, which answered to "drop" with an ASCII
apostrophe for a glyph, and putting "drop" on ノ as well as 丶, which is how
Heisig uses it in 千 呂 頁) took it to **661**.

661 is still not a clean report, and the largest single cause is worth naming:
**言 is atomic here** while the CSV reads "words; keitai; mouth", so every one of
its ~90 hosts is recorded as having dropped 口. Whether 言 should decompose is a
judgement call about search noise, not a bug this script can settle.

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

    claim_cache: dict[str, frozenset[str]] = {}

    def claimants(term: str) -> frozenset[str]:
        """Every row that answers to `term` — not one canonical pick.

        See "One name, several rows" in the docstring: 貝 answers to "clam" and
        so does 蛤, and which one a `LIMIT 1` returned decided whether this
        script called a correct decomposition a regression.
        """
        if term not in claim_cache:
            rows = conn.execute(
                "SELECT kanji_id AS id FROM aliases WHERE alias = ? "
                "UNION SELECT id FROM kanji WHERE id = ? OR character = ?",
                (term, term, term)
            ).fetchall()
            claim_cache[term] = frozenset(r["id"] for r in rows)
        return claim_cache[term]

    def resolve(term: str) -> str | None:
        """One id, for walking the decomposition tree — any claimant will do
        there, since the walk is about structure rather than about naming."""
        ids = claimants(term)
        return min(ids) if ids else None

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
            cids = claimants(t)
            if not cids:
                continue  # suggest_heisig_aliases.py owns the unnameable class
            if cids & reachable or kid in cids:
                continue  # some row answering to this name is in there, or is it
            dropped.append((t, "/".join(sorted(cids))))

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
