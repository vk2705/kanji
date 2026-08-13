"""
audit_radicals.py — deterministic "unnamed primitive" check, no API key needed.

Rebuilds a throwaway copy of the database via the real import pipeline
(same approach as audit_decomposition.py's build_shadow_db) and reports every
part_term used in an rtk* decomposition that never resolves to any kanji row
or alias visible in the system — i.e. a primitive a user could never search
for by name. This is the free, deterministic half of the search-quality
audit (docs/2026-08-search-quality-audit.md, Finding 1); the LLM-based
plausibility check in audit_decomposition.py is a separate, paid pass.

Usage:
    python3 audit_radicals.py

Never touches backend/kanji.db.
"""
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402


def build_shadow_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="kanji_audit_"))
    tmp_db = tmp_dir / "shadow.db"
    database.DB_PATH = tmp_db
    database.init_db()
    conn = database.get_db()
    database.migrate_schema(conn)
    conn.close()
    database.import_data()
    return tmp_db


def find_undefined_terms(shadow_db: Path) -> Counter:
    conn = database.sqlite3.connect(shadow_db)
    conn.row_factory = database.sqlite3.Row

    known = set()
    for r in conn.execute("SELECT alias FROM aliases"):
        known.add(r[0])
    for r in conn.execute("SELECT id, character FROM kanji"):
        known.add(r["id"])
        if r["character"] and r["character"] not in ("?", "??", ""):
            known.add(r["character"])

    cnt = Counter()
    rows = conn.execute("""
        SELECT p.part_term FROM parts p
        JOIN decompositions d ON d.id = p.decomposition_id
        JOIN kanji k ON k.id = p.kanji_id
        WHERE k.id LIKE 'rtk%' AND d.owner_id = 1
    """).fetchall()
    for r in rows:
        term = r["part_term"]
        if term not in known:
            cnt[term] += 1

    conn.close()
    return cnt


def main():
    print("Building shadow database from source files...", flush=True)
    shadow_db = build_shadow_db()
    cnt = find_undefined_terms(shadow_db)

    single_glyph = sorted(
        (t for t in cnt if len(t) == 1 and not t.isascii()),
        key=lambda t: -cnt[t]
    )
    other = sorted((t for t in cnt if t not in single_glyph), key=lambda t: -cnt[t])

    total_hits = sum(cnt.values())
    print(f"\n{len(cnt)} distinct undefined part terms "
          f"({len(single_glyph)} single glyphs, {len(other)} multi-char), "
          f"{total_hits} total occurrences across rtk* decompositions.\n")

    print(f"-- Single-glyph (likely unnamed radicals), {len(single_glyph)} --")
    for t in single_glyph:
        print(f"  {t}\t{cnt[t]}")

    print(f"\n-- Multi-char / descriptive phrases, {len(other)} --")
    for t in other:
        print(f"  {t!r}\t{cnt[t]}")


if __name__ == "__main__":
    main()
