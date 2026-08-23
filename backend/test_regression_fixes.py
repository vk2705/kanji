#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
test_regression_fixes.py — pins every kanji-decomposition bug fixed and owner-approved
in the 2026-08-19/22 sessions to its now-correct state, so a future data.txt edit or
sync can't silently reintroduce the same corruption without a loud, specific failure.

There is no traditional test suite in this repo (see CLAUDE.md); this follows the
existing audit_*.py convention instead — a standalone script against the live
kanji.db, pass/fail via exit code, human-readable diagnostics on stdout.

## What it checks

1. EXPECTED_DECOMPOSITIONS — exact-match pins for every individually discussed and
   owner-approved kanji fix: the resolved top-level part ids (via
   database.get_kanji_detail, i.e. exactly what the app itself would render) must
   equal the recorded-correct set, in any order. A change here means either a real
   regression, or a legitimate future improvement that should update this file
   alongside the data.txt change that caused it — never silently.

2. Structural invariants for the *bulk* fixes, where pinning every individual kanji
   would be both impractical and brittle (hundreds of rows each):
   - No ja-kanji decomposition may use 扎 (a real, unrelated kanji "pull up") as a
     literal part_term — it was a KRADFILE JIS-substitution proxy standing in for
     the 扌 hand radical across 114 kanji (session 2026-08-22); its reappearance
     means someone re-typed the proxy instead of the real 扌.
   - No kanji.variant_of may equal its own id (the self-referencing-Unihan-variant
     bug that skipped 429 hanzi entirely, fixed in import_hanzi.py 2026-08-22).
   - No kanji's own decomposition may resolve a part back to itself (the general
     "kanji as part of itself" class this whole test file exists to catch, per
     audit_self_reference.py's more exhaustive but much slower full-database scan
     — this test only re-checks the specific ids fixed this session, as a fast
     smoke test; run audit_self_reference.py for a full sweep).

Usage:
    python3 test_regression_fixes.py

Exits non-zero on any failure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402


# kanji_id -> {"character": ..., "expected_part_ids": [...]} — the resolved top-level
# parts_detail ids from get_kanji_detail's first (system) decomposition, order-independent.
EXPECTED_DECOMPOSITIONS = {
    "rtk1209": {"character": "祈", "keyword": "pray",
                "expected_part_ids": {"rtk1206", "rad4.36"}},
    "rtk6": {"character": "六", "keyword": "six",
             "expected_part_ids": {"rad1001", "rad2.8"}},
    "rtk2014": {"character": "航", "keyword": "navigate",
                "expected_part_ids": {"rtk2012", "rad1001", "rad1011"}},
    "rtk580": {"character": "家", "keyword": "house",
               "expected_part_ids": {"rad1041", "rad1019"}},
    # "sun" used to resolve to hanzi-5b6b (孫, grandchild) via an unrelated pinyin
    # collision, since rtk12 (日) had no "sun" alias at all -- fixed as a side effect
    # of session 25's alias restoration (rtk12 got "sun" back), so "sun" and "day"
    # now both correctly resolve to rtk12 and collapse to one chip.
    "rtk200": {"character": "宣", "keyword": "proclaim",
               "expected_part_ids": {"rad1041", "rtk32", "rtk1", "rad1.1", "rtk12"}},
    "rtk1809": {"character": "働", "keyword": "work",
                "expected_part_ids": {"rad2.3", "rtk1806"}},
    "rtk1806": {"character": "動", "keyword": "move",
                "expected_part_ids": {"rad1.2", "rtk1", "rtk12", "rtk922", "rtk185", "rad1050"}},
    "rtk688": {"character": "看", "keyword": "watch over",
               "expected_part_ids": {"rad1050", "rtk1", "rtk687", "rtk2", "rtk15"}},
    "rtk1049": {"character": "側", "keyword": "side",
                "expected_part_ids": {"rtk56"}},
    "rtk2087": {"character": "鎖", "keyword": "chain",
                "expected_part_ids": {"rtk56", "rtk287", "rtk196"}},
    "rtk1909": {"character": "遺", "keyword": "bequeath",
                "expected_part_ids": {"rtk1908", "rad3.1"}},
    "rtk407": {"character": "政", "keyword": "politics",
               "expected_part_ids": {"rad1009", "rtk405"}},
    "rtk409": {"character": "錠", "keyword": "lock",
               "expected_part_ids": {"rtk287", "rtk408"}},
    "rtk549": {"character": "燃", "keyword": "burn",
               "expected_part_ids": {"rtk173", "rtk256"}},
    "rtk1115": {"character": "夜", "keyword": "night",
                "expected_part_ids": {"rad1001", "rad2.3", "rad3.6", "rtk114"}},
    "rtk1122": {"character": "換", "keyword": "interchange",
                "expected_part_ids": {"rad3.34", "rad2.31", "rtk1877"}},
    "rtk711": {"character": "指", "keyword": "finger",
               "expected_part_ids": {"rtk12", "rtk476", "rad3.34"}},
    "rtk705": {"character": "打", "keyword": "strike",
               "expected_part_ids": {"rad1004", "rad3.34"}},
    "rtk1405": {"character": "降", "keyword": "descend",
                "expected_part_ids": {"rad3.6", "rad3.40", "rad3.41"}},
    "rtk1397": {"character": "陽", "keyword": "sunshine",
                "expected_part_ids": {"rtk1", "rtk12", "rad3.40", "rtk1128"}},
    "rtk1360": {"character": "阜", "keyword": "large hill",
                "expected_part_ids": {"rad3.40", "rtk10", "rtk11", "rad1.2"}},
    "rtk1549": {"character": "頭", "keyword": "head",
                "expected_part_ids": {"rtk1548", "rtk64"}},
    "rtk1548": {"character": "豆", "keyword": "beans",
                "expected_part_ids": {"rad1011", "rtk1", "rtk11"}},
}

# character -> hanzi id, spot-checking the 429-character Unihan self-reference backfill
# (2026-08-22) rather than re-verifying every one.
EXPECTED_HANZI_PRESENT = {
    "报": "hanzi-62a5", "万": "hanzi-4e07", "个": "hanzi-4e2a", "丰": "hanzi-4e30",
}


def check_decompositions(conn) -> list[str]:
    failures = []
    for kid, spec in EXPECTED_DECOMPOSITIONS.items():
        row = conn.execute("SELECT character, keyword FROM kanji WHERE id = ?", (kid,)).fetchone()
        if row is None:
            failures.append(f"{kid} ({spec['character']}): kanji row no longer exists")
            continue
        if row["character"] != spec["character"]:
            failures.append(f"{kid}: character changed from {spec['character']!r} to {row['character']!r}")

        detail = database.get_kanji_detail(conn, kid, viewer_id=None)
        if not detail["decompositions"]:
            failures.append(f"{kid} ({spec['character']}/{spec['keyword']}): "
                             f"has no decompositions at all (expected {sorted(spec['expected_part_ids'])})")
            continue
        actual = {p["id"] for p in detail["decompositions"][0]["parts_detail"]}
        if actual != spec["expected_part_ids"]:
            missing = spec["expected_part_ids"] - actual
            extra = actual - spec["expected_part_ids"]
            detail_msg = []
            if missing:
                detail_msg.append(f"missing {sorted(missing)}")
            if extra:
                detail_msg.append(f"unexpected {sorted(extra)}")
            failures.append(f"{kid} ({spec['character']}/{spec['keyword']}): "
                             f"{', '.join(detail_msg)} (expected {sorted(spec['expected_part_ids'])}, "
                             f"got {sorted(actual)})")
    return failures


def check_hanzi_present(conn) -> list[str]:
    failures = []
    for ch, expected_id in EXPECTED_HANZI_PRESENT.items():
        row = conn.execute("SELECT id FROM kanji WHERE id = ?", (expected_id,)).fetchone()
        if row is None:
            failures.append(f"{ch} ({expected_id}) missing again — the Unihan "
                             f"self-reference backfill regressed")
    return failures


# (proxy character, real radical it was standing in for) -- each pair was a KRADFILE
# JIS-substitution artifact (a real, unrelated kanji used as a stand-in glyph because
# the actual radical has no JIS X 0208 codepoint of its own) bulk-fixed across many
# kanji at once; see fix_kradfile_proxies.py for the original five (乞化刈買犯).
KRADFILE_PROXY_PAIRS = [
    ("扎", "扌"),  # "pull up" standing in for the hand radical (114 kanji, 2026-08-22)
    ("阡", "阝"),  # "footpaths between fields" standing in for the mound radical (40 kanji, 2026-08-22)
]


def check_no_kradfile_proxy(conn) -> list[str]:
    failures = []
    for proxy, real in KRADFILE_PROXY_PAIRS:
        rows = conn.execute("""
            SELECT DISTINCT k.id, k.character FROM parts p
            JOIN decompositions d ON d.id = p.decomposition_id
            JOIN kanji k ON k.id = p.kanji_id
            WHERE p.part_term = ? AND k.script = 'ja-kanji' AND d.owner_id = 1
        """, (proxy,)).fetchall()
        failures += [f"{r['id']} ({r['character']}) uses the {proxy} KRADFILE proxy again instead of {real}"
                     for r in rows]
    return failures


def check_no_self_reference(conn) -> list[str]:
    failures = []
    variant_rows = conn.execute("SELECT id, character FROM kanji WHERE variant_of = id").fetchall()
    for r in variant_rows:
        failures.append(f"{r['id']} ({r['character']}): variant_of points at itself")

    for kid in EXPECTED_DECOMPOSITIONS:
        detail = database.get_kanji_detail(conn, kid, viewer_id=None)
        for decomp in detail["decompositions"]:
            for p in decomp["parts_detail"]:
                if p["id"] == kid:
                    failures.append(f"{kid}: decomposition lists itself as one of its own parts")
    return failures


def main():
    conn = database.sqlite3.connect(database.DB_PATH)
    conn.row_factory = database.sqlite3.Row

    all_failures = []
    all_failures += check_decompositions(conn)
    all_failures += check_hanzi_present(conn)
    all_failures += check_no_kradfile_proxy(conn)
    all_failures += check_no_self_reference(conn)
    conn.close()

    total_checks = len(EXPECTED_DECOMPOSITIONS) + len(EXPECTED_HANZI_PRESENT) + 2
    if all_failures:
        print(f"FAILED: {len(all_failures)} problem(s) found across {total_checks} checks:\n")
        for f in all_failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"PASSED: all {total_checks} regression checks OK "
              f"({len(EXPECTED_DECOMPOSITIONS)} pinned decompositions, "
              f"{len(EXPECTED_HANZI_PRESENT)} hanzi presence spot-checks, "
              f"KRADFILE-proxy + self-reference invariants).")
        sys.exit(0)


if __name__ == "__main__":
    main()
