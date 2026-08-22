"""
audit_self_reference.py — deterministic detector for "kanji resolves to itself"
bugs: a kanji whose own decomposition lists itself as one of its own parts, or a
hanzi row whose variant_of points at itself.

## Why this exists

Both shapes have actually happened:
  - variant_of self-reference: import_hanzi.py's Unihan-variant parsing treated a
    self-referencing kSimplifiedVariant/kTraditionalVariant (Unihan's way of saying
    "this char already IS that form", e.g. 报's kSimplifiedVariant points to 报
    itself) as a genuine second variant direction, wrongly flagging 430 characters
    as both-directions-ambiguous and skipping them entirely (found 2026-08-22,
    fixed in import_hanzi.py + backfill_missing_hanzi.py). A self-reference that
    slips through a future data source would show up here as kanji.variant_of ==
    kanji.id.
  - decomposition self-reference: a data.txt/data_from_pdf.txt line whose parts
    list, once resolved through alias matching, includes the kanji's own id — i.e.
    "X decomposes into ... X ...". Nothing in the codebase currently produces this,
    but nothing guards against it either, and it is exactly the class of "obviously
    nonsensical if you looked at it" bug that has recurred all session in different
    forms (orphaned-alias id-clobbering, keyword-collision decomposition hijacking).
    Better to check for it deterministically than rely on spotting it by eye.

## How it works

Checks the *live* kanji.db directly (not a shadow rebuild) since the variant_of bug
is hanzi-only data, not reproducible via import_data()'s rtk pipeline. Read-only —
never writes.

  1. variant_of self-reference: trivial, `variant_of = id`.
  2. Decomposition self-reference: for every visible decomposition of every kanji K,
     resolve each part_term via database.resolve_alias (same script-scoped
     resolution the app's own detail view uses, via K's own script) and flag any
     part_term that resolves back to K itself.

Usage:
    python3 audit_self_reference.py

Exits non-zero if any self-reference is found, so it can be used as a pass/fail
gate (e.g. before a deploy or after a data.txt edit) as well as an interactive report.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402


def find_variant_self_references(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, character, keyword FROM kanji WHERE variant_of = id"
    ).fetchall()
    return [dict(r) for r in rows]


def _resolve_top_level_ids(conn, cid: str, decomposition_id: int, char_lookup) -> dict[str, str]:
    """{part_term: resolved_kanji_id} for one decomposition, replicating exactly the
    synthetic char+keyword pairing detection and script-scoped alias tie-break
    database._resolve_parts_detail uses — WITHOUT its final `pid != cid` self-exclusion,
    since that's precisely the thing this audit needs to see. Kept in lockstep with
    _resolve_parts_detail by design; a naive per-term resolve_alias check (this
    script's first version) flags every radical that happens to share a keyword with
    an unrelated whole kanji built from it (e.g. 虍/"tiger" the radical vs 虎/"tiger"
    the kanji it appears in) as a false-positive self-reference, because it doesn't
    know those are a synthetic pair the real display logic already drops before ever
    resolving the keyword half independently."""
    part_terms = [
        r["part_term"] for r in conn.execute(
            "SELECT part_term FROM parts WHERE decomposition_id = ? ORDER BY position",
            (decomposition_id,)
        ).fetchall()
    ]
    if not part_terms:
        return {}

    parent = conn.execute("SELECT script FROM kanji WHERE id = ?", (cid,)).fetchone()
    parent_group = database._script_group(parent["script"]) if parent else None

    char_to_candidates, id_to_keyword = char_lookup
    synthetic_positions: set[int] = set()
    for i, term in enumerate(part_terms[:-1]):
        candidates = char_to_candidates.get(term)
        if not candidates:
            continue
        chosen_id = None
        if parent_group:
            chosen_id = next((kid for kid, script in candidates if database._script_group(script) == parent_group), None)
        if chosen_id is None:
            chosen_id = candidates[0][0]
        kw = id_to_keyword.get(chosen_id)
        if kw and part_terms[i + 1] == kw:
            synthetic_positions.add(i + 1)
    if synthetic_positions:
        part_terms = [t for i, t in enumerate(part_terms) if i not in synthetic_positions]

    term_to_id: dict[str, str] = {}
    for t in part_terms:
        row = conn.execute("SELECT id FROM kanji WHERE id = ?", (t,)).fetchone()
        if row:
            term_to_id[t] = row["id"]

    alias_candidates: dict[str, list[tuple[str, str]]] = {}
    for t in part_terms:
        if t in term_to_id:
            continue
        for r in conn.execute(
            "SELECT a.kanji_id, k.script FROM aliases a JOIN kanji k ON k.id = a.kanji_id WHERE a.alias = ?", (t,)
        ).fetchall():
            alias_candidates.setdefault(t, []).append((r["kanji_id"], r["script"]))

    for term, candidates in alias_candidates.items():
        preferred = None
        if parent_group:
            preferred = next((kid for kid, script in candidates if database._script_group(script) == parent_group), None)
        term_to_id[term] = preferred or candidates[0][0]

    return term_to_id


def find_decomposition_self_references(conn) -> list[dict]:
    findings = []
    char_lookup = database._build_char_lookup(conn)
    kanji_rows = conn.execute("SELECT id, character, keyword FROM kanji").fetchall()

    for k in kanji_rows:
        kid, kchar, kkeyword = k["id"], k["character"], k["keyword"]
        decomps = conn.execute(
            "SELECT id, owner_id FROM decompositions WHERE kanji_id = ?", (kid,)
        ).fetchall()
        for d in decomps:
            term_to_id = _resolve_top_level_ids(conn, kid, d["id"], char_lookup)
            for term, resolved_id in term_to_id.items():
                if resolved_id == kid:
                    findings.append({
                        "kanji_id": kid, "character": kchar, "keyword": kkeyword,
                        "decomposition_id": d["id"], "decomposition_owner": d["owner_id"],
                        "part_term": term,
                    })
    return findings


def main():
    conn = database.sqlite3.connect(database.DB_PATH)
    conn.row_factory = database.sqlite3.Row

    variant_hits = find_variant_self_references(conn)
    decomp_hits = find_decomposition_self_references(conn)
    conn.close()

    print(f"variant_of self-references: {len(variant_hits)}")
    for h in variant_hits:
        print(f"  {h['id']} {h['character']} ({h['keyword']}) — variant_of points at itself")

    print(f"\ndecomposition self-references: {len(decomp_hits)}")
    for h in decomp_hits:
        print(f"  {h['kanji_id']} {h['character']} ({h['keyword']}) decomposition "
              f"#{h['decomposition_id']} (owner_id={h['decomposition_owner']}) "
              f"lists part_term {h['part_term']!r}, which resolves back to itself")

    total = len(variant_hits) + len(decomp_hits)
    print(f"\n{total} total self-reference(s) found.")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
