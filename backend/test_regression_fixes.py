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
             "expected_part_ids": {"kangxi8", "rad2.8"}},
    "rtk2014": {"character": "航", "keyword": "navigate",
                "expected_part_ids": {"rtk2012", "kangxi8", "kangxi16"}},
    "rtk580": {"character": "家", "keyword": "house",
               "expected_part_ids": {"kangxi40", "kangxi152"}},
    # "sun" used to resolve to hanzi-5b6b (孫, grandchild) via an unrelated pinyin
    # collision, since rtk12 (日) had no "sun" alias at all -- fixed as a side effect
    # of session 25's alias restoration (rtk12 got "sun" back), so "sun" and "day"
    # now both correctly resolve to rtk12 and collapse to one chip.
    "rtk200": {"character": "宣", "keyword": "proclaim",
               "expected_part_ids": {"kangxi40", "rtk32", "rtk1", "rad1.1", "rtk12"}},
    "rtk1809": {"character": "働", "keyword": "work",
                "expected_part_ids": {"kangxi9", "rtk1806"}},
    "rtk1806": {"character": "動", "keyword": "move",
                "expected_part_ids": {"prim-pipe", "rtk1", "rtk12", "rtk922", "rtk185", "prim-katakana-no"}},
    "rtk688": {"character": "看", "keyword": "watch over",
               "expected_part_ids": {"prim-katakana-no", "rtk1", "rtk687", "rtk2", "rtk15"}},
    "rtk1049": {"character": "側", "keyword": "side",
                "expected_part_ids": {"rtk56"}},
    "rtk2087": {"character": "鎖", "keyword": "chain",
                "expected_part_ids": {"rtk56", "rtk287", "rtk196"}},
    "rtk1909": {"character": "遺", "keyword": "bequeath",
                "expected_part_ids": {"rtk1908", "kangxi162"}},
    "rtk407": {"character": "政", "keyword": "politics",
               "expected_part_ids": {"kangxi66", "rtk405"}},
    "rtk409": {"character": "錠", "keyword": "lock",
               "expected_part_ids": {"rtk287", "rtk408"}},
    "rtk549": {"character": "燃", "keyword": "burn",
               "expected_part_ids": {"rtk173", "rtk256"}},
    "rtk1115": {"character": "夜", "keyword": "night",
                "expected_part_ids": {"kangxi8", "kangxi9", "kangxi34", "rtk114"}},
    "rtk1122": {"character": "換", "keyword": "interchange",
                "expected_part_ids": {"kangxi64", "prim-hooked-hand", "rtk1877"}},
    "rtk711": {"character": "指", "keyword": "finger",
               "expected_part_ids": {"rtk12", "rtk476", "kangxi64"}},
    "rtk705": {"character": "打", "keyword": "strike",
               "expected_part_ids": {"kangxi6", "kangxi64"}},
    "rtk1405": {"character": "降", "keyword": "descend",
                "expected_part_ids": {"kangxi34", "kangxi170", "prim-winter-cow"}},
    "rtk1397": {"character": "陽", "keyword": "sunshine",
                "expected_part_ids": {"rtk1", "rtk12", "kangxi170", "rtk1128"}},
    "rtk1360": {"character": "阜", "keyword": "large hill",
                "expected_part_ids": {"kangxi170", "rtk10", "rtk11", "prim-pipe"}},
    "rtk1549": {"character": "頭", "keyword": "head",
                "expected_part_ids": {"rtk1548", "rtk64"}},
    "rtk1548": {"character": "豆", "keyword": "beans",
                "expected_part_ids": {"kangxi16", "rtk1", "rtk11"}},
    # 羊-family redundant-flattening fix (2026-08-24): these used to list both
    # 羊's own flattened parts (王,并) AND 羊 itself in the same line. rtk586
    # (羊) already correctly resolves to {kangxi40's cousin kangxi12, rtk...}
    # -- see its own line in data.txt (王,丷) -- so re-listing 王/并 here was
    # pure redundancy, not a second distinct concept.
    "rtk587": {"character": "美", "keyword": "beauty",
               "expected_part_ids": {"rtk112", "rtk586"}},
    "rtk588": {"character": "洋", "keyword": "ocean",
               "expected_part_ids": {"rtk137", "rtk586"}},
    "rtk691": {"character": "義", "keyword": "righteousness",
               "expected_part_ids": {"rtk1", "rtk586", "kangxi6", "kangxi62", "rtk687"}},
    "rtk1591": {"character": "養", "keyword": "foster",
                "expected_part_ids": {"rtk1582", "rtk586"}},
    "rtk2622": {"character": "痒", "keyword": "itch",
                "expected_part_ids": {"rtk586", "kangxi104"}},
    # 半-family fix (2026-08-25): these three re-flattened 半's own parts
    # instead of referencing 半 (rtk1286) directly, and in doing so silently
    # dropped their own actually-distinguishing part entirely (伴 had no
    # "person", 判 had no "sword") -- worse than the usual redundant-
    # flattening pattern, this one lost information, not just duplicated it.
    "rtk1287": {"character": "伴", "keyword": "consort",
                "expected_part_ids": {"kangxi9", "rtk1286"}},
    "rtk1288": {"character": "畔", "keyword": "paddy ridge",
                "expected_part_ids": {"rtk14", "rtk1286"}},
    "rtk1289": {"character": "判", "keyword": "judgement",
                "expected_part_ids": {"rtk1286", "rtk87"}},
    # "quarter"-family missing-component fix (2026-08-25): data_from_pdf.txt's
    # original entries for these two used "quarter" (now correctly kangxi12,
    # the same 丷/horns primitive as everywhere else in this cluster — see
    # the audit doc's IDS-based investigation) as one of their parts,
    # matching heisig-kanjis.csv's own components list, but data.txt's
    # override silently dropped it while keeping the sibling frames
    # 1290-1294 (拳/券/巻/圏/勝) correct.
    "rtk1295": {"character": "藤", "keyword": "wisteria",
                "expected_part_ids": {"prim-pipe", "rtk1", "rtk13", "rtk137",
                                       "prim-mugwort", "rtk2", "rtk112", "kangxi12"}},
    "rtk1296": {"character": "謄", "keyword": "mimeograph",
                "expected_part_ids": {"prim-pipe", "rtk1", "rtk13", "rtk357",
                                       "rtk2", "rtk112", "kangxi12"}},
    # 豆-family fix (2026-08-25): 17 kanji re-flattened 豆 (and, for the
    # drum/bend/ascend sub-cluster, 鼓/曲/登) into their own already-atomic
    # parts alongside a stray, unexplained 并 token that no CSV or PDF
    # source ever corroborated for this whole cluster (unlike the
    # sheep/quarter/horns families, where 并 did map to something real).
    # Collapsed each to reference the already-taught compound directly.
    "rtk1550": {"character": "短", "keyword": "short",
                "expected_part_ids": {"rtk1305", "rtk1548"}},
    "rtk1551": {"character": "豊", "keyword": "bountiful",
                "expected_part_ids": {"rtk1256", "rtk1548"}},
    "rtk1552": {"character": "鼓", "keyword": "drum",
                "expected_part_ids": {"rtk341", "rtk1548", "rtk768"}},
    "rtk1553": {"character": "喜", "keyword": "rejoice",
                "expected_part_ids": {"rtk1552", "rtk11"}},
    "rtk1554": {"character": "樹", "keyword": "timber",
                "expected_part_ids": {"rtk207", "rtk1552", "rtk45"}},
    "rtk1757": {"character": "闘", "keyword": "fight",
                "expected_part_ids": {"rtk1743", "rtk1548", "rtk45"}},
    "rtk1815": {"character": "痘", "keyword": "pox",
                "expected_part_ids": {"rtk1548", "kangxi104"}},
    "rtk1838": {"character": "登", "keyword": "ascend",
                "expected_part_ids": {"kangxi105", "rtk1548"}},
    "rtk1839": {"character": "澄", "keyword": "lucidity",
                "expected_part_ids": {"rtk137", "rtk1838"}},
    "rtk1855": {"character": "膨", "keyword": "swell",
                "expected_part_ids": {"rtk13", "rtk1552", "kangxi59"}},
    "rtk1892": {"character": "艶", "keyword": "glossy",
                "expected_part_ids": {"rtk1551", "rtk1890", "kangxi20"}},
    "rtk2223": {"character": "鎧", "keyword": "put on armor",
                "expected_part_ids": {"rtk287", "rtk830", "rtk1548"}},
    "rtk2224": {"character": "凱", "keyword": "victory song",
                "expected_part_ids": {"rtk830", "rtk1548", "kangxi16"}},
    "rtk2275": {"character": "厨", "keyword": "kitchen",
                "expected_part_ids": {"rtk1548", "rtk45", "kangxi27"}},
    "rtk2319": {"character": "嬉", "keyword": "glad",
                "expected_part_ids": {"rtk102", "rtk1553"}},
    "rtk2502": {"character": "逗", "keyword": "stop",
                "expected_part_ids": {"rtk843", "rtk1548"}},
    "rtk2978": {"character": "燈", "keyword": "lamp",
                "expected_part_ids": {"rtk173", "rtk1838"}},
    # 新-family fix (2026-08-25): heisig-kanjis.csv wording ("red pepper;
    # stand up; vase") looked like it belonged to the still-open 帝-family
    # "vase" cluster, but rendering showed 新's left side is 立+木, not
    # 辛(spicy)+并 -- CSV's wording was noise here, not a real shared
    # concept; see docs/2026-08-search-quality-audit.md for the full story.
    "rtk1619": {"character": "新", "keyword": "new",
                "expected_part_ids": {"rtk462", "rtk207", "rtk1206"}},
    "rtk1620": {"character": "薪", "keyword": "fuel",
                "expected_part_ids": {"prim-mugwort", "rtk462", "rtk207", "rtk1206"}},
    "rtk1621": {"character": "親", "keyword": "parent",
                "expected_part_ids": {"rtk61", "rtk462", "rtk207"}},
    # 弟-family fix (2026-08-25): all four re-flattened 弟 (younger brother,
    # rtk1328) into its own raw strokes using the stale 并 token instead of
    # referencing 弟 directly (which itself already correctly uses 丷, from
    # the horns fix two sessions ago) -- 剃 additionally dropped its knife
    # (刀) entirely, a missing-component bug like 伴/判 two sessions ago.
    "rtk2271": {"character": "剃", "keyword": "shave",
                "expected_part_ids": {"rtk1328", "rtk87"}},
    "rtk2381": {"character": "悌", "keyword": "serving our elders",
                "expected_part_ids": {"rtk1328", "kangxi61"}},
    "rtk2545": {"character": "梯", "keyword": "ladder",
                "expected_part_ids": {"rtk207", "rtk1328"}},
    "rtk2847": {"character": "鵜", "keyword": "cormorant",
                "expected_part_ids": {"rtk1328", "rtk2091"}},
    # 平-family fix (2026-08-25): data_from_pdf.txt's originals for these
    # three used "water lily" as a single reference to 平 (even) itself,
    # matching this session's dominant pattern -- data.txt's override had
    # re-flattened 平 into 干+并 (plus other stray fragments) instead.
    # 平's own "干,并" -> "干,?" question (what "并" really is at the top
    # of 平 itself) is left open, same bucket as vase/quarter.
    "rtk1597": {"character": "呼", "keyword": "call",
                "expected_part_ids": {"rtk11", "rtk1596"}},
    "rtk1598": {"character": "坪", "keyword": "two-mat area",
                "expected_part_ids": {"rtk161", "rtk1596"}},
    "rtk1599": {"character": "評", "keyword": "evaluate",
                "expected_part_ids": {"rtk357", "rtk1596"}},
    # 并's real identity resolved (2026-08-26): fetched cjkvi-ids's IDS data
    # (the same authoritative decomposition source import_hanzi.py already
    # uses) for every remaining 并 host and found 并 itself decomposes to
    # 丷+开 -- meaning almost every remaining host only ever showed the 丷
    # top-part, never the full 并 glyph with 开 below it, so the token was
    # wrong throughout: it's the same kangxi12/丷 primitive as the original
    # horns-cluster fix, just several structural layers deeper (e.g. 拳's
    # 龹 = 丷+夫, 帝's own shape = 亠+丷+冖+巾). Fixed ~66 kanji: a direct
    # 并->丷 swap where the host's own glyph shows 丷 with nothing else
    # already covering it, or a reference to an already-taught compound
    # (帝/南/半/並/巻/平/前/岡/尊/酋) where that compound's own flattened
    # parts were being redundantly (and, for 剛/伴/判-style cases,
    # incompletely) repeated instead of just citing it. Only one host
    # (屏, rtk2333) turned out to genuinely contain the full 并 character
    # itself and was left untouched. 業/撲/僕/為/偽/誉/糞/粉 remain open —
    # see docs/2026-08-search-quality-audit.md for the full breakdown and
    # per-kanji reasoning. A representative sample, one per sub-pattern:
    "rtk466": {"character": "帝", "keyword": "sovereign",
               "expected_part_ids": {"rtk432", "kangxi12", "rtk462", "kangxi8", "kangxi14"}},
    "rtk1286": {"character": "半", "keyword": "half",
                "expected_part_ids": {"prim-pipe", "rtk2", "kangxi12", "rtk10"}},
    "rtk1596": {"character": "平", "keyword": "even",
                "expected_part_ids": {"rtk1777", "kangxi12"}},
    "rtk287": {"character": "金", "keyword": "gold",
               "expected_part_ids": {"rtk271", "prim-katakana-ha", "prim-umbrella", "kangxi12"}},
    "rtk467": {"character": "諦", "keyword": "truth",
               "expected_part_ids": {"rtk357", "rtk466"}},
    "rtk1741": {"character": "楠", "keyword": "camphor tree",
                "expected_part_ids": {"rtk207", "rtk1740"}},
    "rtk1293": {"character": "圏", "keyword": "sphere",
                "expected_part_ids": {"kangxi31", "rtk1292"}},
    "rtk2113": {"character": "鋼", "keyword": "steel",
                "expected_part_ids": {"rtk287", "rtk2112"}},
    "rtk2115": {"character": "剛", "keyword": "sturdy",
                "expected_part_ids": {"rtk2112", "rtk87"}},
    "rtk2282": {"character": "噂", "keyword": "rumor",
                "expected_part_ids": {"rtk11", "rtk1547"}},
    "rtk2503": {"character": "鄭", "keyword": "an ancient chinese province",
                "expected_part_ids": {"rtk2915", "rtk112", "kangxi170"}},
    "rtk2911": {"character": "叛", "keyword": "disobey",
                "expected_part_ids": {"rtk1286", "rtk779"}},
    "rtk473": {"character": "適", "keyword": "suitable",
               "expected_part_ids": {"rtk843", "prim-teki"}},
    # 業/撲/僕 reconstruction (2026-08-27): flagged three sessions ago as
    # needing more than a 并->丷 token swap -- their old 王/羊 tokens don't
    # match either character's real IDS structure at all. Rebuilt around
    # a new prim-upside-down-row (业, Heisig's own "upside down in a row",
    # per heisig-kanjis.csv) + kangxi12 (丷, confirmed via IDS: 業's 𦍎 =
    # 䒑(丷+一)+未, 撲/僕's 菐 = 业+䒑+夫) + already-taught 木/夫, confirmed
    # via render that 撲/僕's bottom-right clearly matches 夫 (husband,
    # rtk901), not 木.
    "rtk1931": {"character": "業", "keyword": "business",
                "expected_part_ids": {"prim-upside-down-row", "kangxi12", "rtk1", "rtk207"}},
    "rtk1932": {"character": "撲", "keyword": "slap",
                "expected_part_ids": {"kangxi64", "prim-upside-down-row", "kangxi12", "rtk901"}},
    "rtk1933": {"character": "僕", "keyword": "me",
                "expected_part_ids": {"kangxi9", "prim-upside-down-row", "kangxi12", "rtk901"}},
    # "pack of wild dogs" (犭) family missing-component bug (2026-08-27):
    # flagged by the owner disputing 猫's in-app review (rtk259 had no dog
    # radical at all). Turned out all 15 CSV-confirmed hosts of "pack of
    # wild dogs" were missing it, not just 猫 -- confirmed each against
    # cjkvi-ids. Root cause: the placeholder primitive (character "?",
    # skipped by the 2026-08-23 id migration for exactly that reason) had
    # "dog" as its own first alias/keyword, colliding with rtk253/犬's own
    # "dog" keyword -- same same-script collision class as the 个/umbrella
    # bug fixed earlier this session. Linked it to the real glyph 犭 as
    # kangxi94, keyword "pack of wild dogs" (Heisig's own term, matches
    # CSV, no collision), and added it to all 15 hosts.
    "rtk259": {"character": "猫", "keyword": "cat",
               "expected_part_ids": {"kangxi94", "rtk14", "prim-mugwort"}},
    "rtk890": {"character": "聴", "keyword": "listen",
               "expected_part_ids": {"rtk881", "rtk10", "kangxi122", "rtk639"}},
    "rtk1754": {"character": "聞", "keyword": "hear",
                "expected_part_ids": {"rtk881", "rtk1743"}},
    "rtk257": {"character": "荻", "keyword": "reed",
               "expected_part_ids": {"prim-mugwort", "kangxi94", "rtk173"}},
    "rtk258": {"character": "狩", "keyword": "hunt",
               "expected_part_ids": {"kangxi94", "rtk45", "kangxi40"}},
    "rtk277": {"character": "狂", "keyword": "lunatic",
               "expected_part_ids": {"kangxi94", "rtk271"}},
    "rtk361": {"character": "獄", "keyword": "prison",
               "expected_part_ids": {"kangxi94", "rtk357", "rtk253"}},
    "rtk430": {"character": "猿", "keyword": "monkey",
               "expected_part_ids": {"kangxi94", "rtk423", "rtk11", "rtk161"}},
    "rtk561": {"character": "独", "keyword": "single",
               "expected_part_ids": {"kangxi94", "rtk556"}},
    "rtk757": {"character": "獲", "keyword": "seize",
               "expected_part_ids": {"kangxi94", "rtk752", "prim-mugwort", "kangxi172"}},
    "rtk1352": {"character": "猪", "keyword": "boar",
                "expected_part_ids": {"kangxi94", "rtk12", "rtk1340"}},
    "rtk1356": {"character": "狭", "keyword": "cramped",
                "expected_part_ids": {"kangxi94", "rtk1023", "rtk112", "rtk2", "kangxi12", "kangxi3", "kangxi8"}},
    "rtk1517": {"character": "犯", "keyword": "crime",
                "expected_part_ids": {"kangxi94", "rtk75", "kangxi26"}},
    "rtk1546": {"character": "猶", "keyword": "furthermore",
                "expected_part_ids": {"kangxi94", "rtk1534", "kangxi12"}},
    "rtk1566": {"character": "猛", "keyword": "fierce",
                "expected_part_ids": {"kangxi94", "rtk1555", "rtk99"}},
    "rtk1917": {"character": "狙", "keyword": "aim at",
                "expected_part_ids": {"kangxi94", "rtk1", "rtk15"}},
    "rtk2090": {"character": "猟", "keyword": "game-hunting",
                "expected_part_ids": {"kangxi94", "rtk196", "rtk1265", "kangxi16"}},
    # Owner-approved via the review queue (2026-08-27), confirmed correct
    # against cjkvi-ids before pinning: 警 = ⿱敬言, 特 = ⿰牛寺 (寺 already
    # flattened to 土,寸 elsewhere in data.txt).
    "rtk358": {"character": "警", "keyword": "admonish",
               "expected_part_ids": {"rtk356", "rtk357"}},
    "rtk261": {"character": "特", "keyword": "special",
               "expected_part_ids": {"rtk260", "rtk45", "rtk161"}},
    # kangxi90 (爿) renamed "radical 90" -> "turtle" (2026-08-27), Heisig's
    # own name per heisig-kanjis.csv (consistent across all 5 CSV-covered
    # hosts: 状/壮/将/奨/寝). Pinning 状 to confirm the rename didn't touch
    # its own resolved id, just its keyword.
    "rtk254": {"character": "状", "keyword": "status quo",
               "expected_part_ids": {"rtk253", "kangxi90"}},
    # 帯 fixed from its old ｜,一,巾,冖 flattening to 丗,冖,巾 (2026-08-27),
    # matching cjkvi-ids's 帯 = ⿳丗冖巾 directly -- new prim-thirty (丗)
    # primitive added for this. Also the case that surfaced the
    # _resolve_parts_detail visibility-scoping bug (see that function's
    # own docstring) -- pinning this doubles as a regression guard for
    # that fix, since the bug's symptom was exactly a duplicate/wrong
    # chip on this kanji.
    "rtk444": {"character": "帯", "keyword": "sash",
               "expected_part_ids": {"prim-thirty", "kangxi14", "rtk432"}},
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
