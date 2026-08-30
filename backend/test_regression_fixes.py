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
                "expected_part_ids": {"rtk1206", "kangxi113"}},
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
    # Further-collapsed 2026-08-29 (sweep batch 3 follow-up): 指's old
    # 日,匕,扌 flattened 旨 (delicious, rtk493 = 日,匕) in place instead of
    # referencing it -- found because fixing other frames made
    # audit_flattening.py newly flag this one (iterative convergence).
    "rtk711": {"character": "指", "keyword": "finger",
               "expected_part_ids": {"rtk493", "kangxi64"}},
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
    # Further-collapsed 2026-08-29 (sweep batch 3 follow-up): 薪's old
    # 艾,立,木,斤 flattened 新 (new, rtk1619) in place instead of
    # referencing it -- same iterative-convergence discovery as rtk711.
    "rtk1620": {"character": "薪", "keyword": "fuel",
                "expected_part_ids": {"prim-mugwort", "rtk1619"}},
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
    # Further-collapsed 2026-08-29 (sweep batch 3 follow-up): the 犭-family
    # fix only added the missing dog radical, it didn't also clean up the
    # remainder -- 狩's 寸,宀 flattened 守 (guard, rtk198) in place.
    "rtk258": {"character": "狩", "keyword": "hunt",
               "expected_part_ids": {"kangxi94", "rtk198"}},
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
    # Further-collapsed 2026-08-29 (sweep batch 3 follow-up), same as 狩
    # above: 猪's 日,老 flattened 者 (someone, rtk1345) in place.
    "rtk1352": {"character": "猪", "keyword": "boar",
                "expected_part_ids": {"kangxi94", "rtk1345"}},
    "rtk1356": {"character": "狭", "keyword": "cramped",
                "expected_part_ids": {"kangxi94", "rtk1023", "rtk112", "rtk2", "kangxi12", "kangxi3", "kangxi8"}},
    "rtk1517": {"character": "犯", "keyword": "crime",
                "expected_part_ids": {"kangxi94", "rtk75", "kangxi26"}},
    # Further-collapsed 2026-08-29 (sweep batch 3 follow-up), same as 狩
    # above: 猶's 酉,丷 flattened 酋 (chieftain, rtk2915) in place.
    "rtk1546": {"character": "猶", "keyword": "furthermore",
                "expected_part_ids": {"kangxi94", "rtk2915"}},
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
    # kangxi113 (礻, altar radical) fix (2026-08-28): found via a systematic census
    # cross-checking every uncharactered rad{N}.{M} primitive's CSV-confirmed hosts
    # against what data.txt actually uses -- same method that surfaced 犭/罒 two
    # sessions ago. Two distinct sub-bugs on the same missing radical: 礼/祥/祝/福/
    # 祉/社/視/神/禍/祖/禅 used the whole kanji 礼 (rtk1168, "salute") as a wrong
    # stand-in for just its own left radical (confirmed via render: none of these
    # hosts show 礼's extra 乙 hook); 奈/尉/慰/款/禁/襟/宗/崇/祭/察/擦/際/票/漂/標/
    # 斎/隷 had the *different*, already-taught standalone 示 (rtk1167, "show" --
    # the same shape at full width, not the narrow 礻 form) redundantly re-flattened
    # into its own 二/小 parts alongside the reference, plus 斎 had a second nested
    # redundant flatten of 斉. A representative sample of each:
    "rtk1168": {"character": "礼", "keyword": "salute",
                "expected_part_ids": {"kangxi113", "rtk75"}},
    "rtk1169": {"character": "祥", "keyword": "auspicious",
                "expected_part_ids": {"kangxi113", "rtk586"}},
    "rtk1200": {"character": "神", "keyword": "gods",
                "expected_part_ids": {"kangxi113", "rtk1198"}},
    "rtk1918": {"character": "祖", "keyword": "ancestor",
                "expected_part_ids": {"kangxi113", "rtk2190"}},
    "rtk1175": {"character": "奈", "keyword": "nara",
                "expected_part_ids": {"rtk1167", "rtk112"}},
    "rtk1179": {"character": "禁", "keyword": "prohibition",
                "expected_part_ids": {"rtk207", "rtk1167"}},
    "rtk1869": {"character": "斎", "keyword": "purification",
                "expected_part_ids": {"rtk1866", "rtk1167"}},
    "rtk1732": {"character": "票", "keyword": "ballot",
                "expected_part_ids": {"rtk1167", "rtk1728"}},
    # 北/rtk480 fix (2026-08-28): 爿 (turtle, kangxi90) was wrong -- flagged by the
    # owner while double-checking 爿's own identity the previous session. cjkvi-ids
    # gives 北 = a mirrored/backward 匕-shaped element (no Unicode codepoint of its
    # own) + a real 匕, and heisig-kanjis.csv agrees ("spoon; sitting on the
    # ground", never "turtle"). New prim-sitting-on-the-ground added (same
    # "name it even without a real glyph" convention as the many other
    # uncharactered primitives already in data.txt) for the mirrored element.
    "rtk480": {"character": "北", "keyword": "north",
               "expected_part_ids": {"rtk476", "prim-sitting-on-the-ground"}},
    # Final 5 并 hosts (2026-08-29), closing out the multi-session 并 investigation:
    # none of these five relate to 丷/horns at all (unlike everywhere else 并 turned
    # out to be), each was its own distinct bug. 為/偽's 并 was pure unexplained
    # noise, same as the 豆/弟-family pattern. 誉's 尚 was a wrong stand-in for its
    # real top shape (matches 興's own 臼+ハ+一, confirmed by rendering next to 興).
    # 糞 had 井(well) instead of 共(together) -- another wrong-character mix-up like
    # 噂's 西/酉 and 鄭's 邦/阝 two sessions ago -- plus the same redundant-flattening
    # pattern once corrected to reference 共 directly. 粉 simply re-flattened 分
    # (part, rtk844) instead of referencing it. search_by_parts(['eight radical'])
    # is down to exactly 1 host now: 屏 (rtk2333), confirmed genuinely correct via
    # cjkvi-ids two sessions ago -- 并 the character really is present there.
    "rtk988": {"character": "粉", "keyword": "flour",
               "expected_part_ids": {"rtk987", "rtk844"}},
    "rtk2067": {"character": "為", "keyword": "do",
                "expected_part_ids": {"prim-katakana-no", "prim-fire-radical",
                                       "prim-katakana-yu", "kangxi3", "kangxi20"}},
    "rtk2068": {"character": "偽", "keyword": "falsehood",
                "expected_part_ids": {"kangxi3", "prim-fire-radical",
                                       "prim-katakana-yu", "prim-katakana-no", "kangxi20"}},
    "rtk2089": {"character": "誉", "keyword": "reputation",
                "expected_part_ids": {"rtk357", "rtk1531", "prim-katakana-ha", "rtk1"}},
    "rtk2695": {"character": "糞", "keyword": "shit",
                "expected_part_ids": {"rtk987", "rtk14", "rtk1934"}},
    # Frame-ordered sweep (2026-08-29): with the 并 investigation closed, started
    # working through audit_flattening.py's candidate list (1728 raw, cross-checked
    # against heisig-kanjis.csv's own components down to 231 plausible ones) --
    # the same "contains kanji X's own full flattened parts" redundant-flattening
    # pattern found throughout this whole audit, just not yet swept dataset-wide.
    # A first confirmed batch, one per host:
    "rtk48": {"character": "博", "keyword": "dr.",
              "expected_part_ids": {"rtk10", "rtk47", "kangxi3"}},
    "rtk60": {"character": "貼", "keyword": "stick",
              "expected_part_ids": {"rtk56", "rtk49"}},
    "rtk171": {"character": "時", "keyword": "time",
               "expected_part_ids": {"rtk170", "rtk12"}},
    "rtk291": {"character": "釣", "keyword": "angling",
               "expected_part_ids": {"rtk287", "rtk72"}},
    "rtk293": {"character": "銘", "keyword": "inscription",
               "expected_part_ids": {"rtk287", "rtk117"}},
    "rtk366": {"character": "詔", "keyword": "imperial edict",
               "expected_part_ids": {"rtk357", "rtk90"}},
    "rtk370": {"character": "詩", "keyword": "poem",
               "expected_part_ids": {"rtk357", "rtk170"}},
    "rtk373": {"character": "調", "keyword": "tune",
               "expected_part_ids": {"rtk357", "rtk339"}},
    "rtk628": {"character": "咽", "keyword": "throat",
               "expected_part_ids": {"rtk11", "rtk626"}},
    # Frame-ordered sweep, batch 2 (2026-08-29). Same redundant-flattening pattern
    # throughout, except 停 -- that one was a real missing-component bug (the
    # person radical was absent entirely, replaced by a stray 一 that didn't
    # belong anywhere in the glyph; confirmed by rendering 停 next to 亭 and 亻).
    "rtk290": {"character": "銅", "keyword": "copper",
               "expected_part_ids": {"rtk287", "rtk192"}},
    "rtk313": {"character": "賂", "keyword": "bribe",
               "expected_part_ids": {"rtk56", "rtk311"}},
    "rtk315": {"character": "客", "keyword": "guest",
               "expected_part_ids": {"rtk311", "kangxi40"}},
    "rtk369": {"character": "詠", "keyword": "recitation",
               "expected_part_ids": {"rtk357", "rtk139"}},
    "rtk418": {"character": "鍵", "keyword": "key",
               "expected_part_ids": {"rtk287", "rtk417"}},
    "rtk500": {"character": "海", "keyword": "sea",
               "expected_part_ids": {"rtk137", "rtk497"}},
    "rtk542": {"character": "贈", "keyword": "presents",
               "expected_part_ids": {"rtk56", "rtk540"}},
    "rtk581": {"character": "嫁", "keyword": "marry into",
               "expected_part_ids": {"rtk102", "rtk580"}},
    "rtk780": {"character": "坂", "keyword": "slope",
               "expected_part_ids": {"rtk161", "rtk779"}},
    "rtk782": {"character": "返", "keyword": "return",
               "expected_part_ids": {"rtk843", "rtk779"}},
    "rtk783": {"character": "販", "keyword": "marketing",
               "expected_part_ids": {"rtk56", "rtk779"}},
    "rtk933": {"character": "賀", "keyword": "congratulations",
               "expected_part_ids": {"rtk56", "rtk932"}},
    "rtk1051": {"character": "停", "keyword": "halt",
                "expected_part_ids": {"kangxi9", "rtk333"}},
    "rtk1096": {"character": "丙", "keyword": "third class",
                "expected_part_ids": {"rtk1", "rtk1095"}},
    "rtk1216": {"character": "暫", "keyword": "temporarily",
                "expected_part_ids": {"rtk1215", "rtk12"}},
    "rtk1217": {"character": "漸", "keyword": "steadily",
                "expected_part_ids": {"rtk1215", "rtk137"}},
    "rtk1260": {"character": "槽", "keyword": "vat",
                "expected_part_ids": {"rtk1257", "rtk207"}},
    "rtk1507": {"character": "領", "keyword": "jurisdiction",
                "expected_part_ids": {"rtk56", "rtk64", "rtk1503"}},
    "rtk1508": {"character": "鈴", "keyword": "small bell",
                "expected_part_ids": {"rtk287", "rtk1503"}},
    "rtk1594": {"character": "概", "keyword": "outline",
                "expected_part_ids": {"rtk1593", "rtk207"}},
    "rtk1712": {"character": "含", "keyword": "contain",
                "expected_part_ids": {"rtk11", "rtk1711"}},
    "rtk1717": {"character": "琴", "keyword": "harp",
                "expected_part_ids": {"rtk271", "rtk1711"}},
    "rtk2048": {"character": "誤", "keyword": "mistake",
                "expected_part_ids": {"rtk357", "rtk2046"}},
    # Sweep batch 3 (2026-08-29): large-scale frame-ordered sweep, CSV-filtered
    # audit_flattening.py candidates resolved by matching contiguous RESOLVED part-id
    # runs (not raw text) -- see docs/2026-08-search-quality-audit.md for methodology.
    # Same redundant-flattening pattern throughout, except three real bugs caught by
    # the mandatory render/CSV spot-check: 便 (rtk1066) was missing its person radical
    # entirely (｜ was a wrong stand-in, like 停 in the previous batch); 侯 (rtk1767,
    # not part of the original candidate list) was missing its person radical too,
    # found by cross-checking CSV components while verifying 候 (rtk1769), which
    # references it.
    "rtk62": {"character": "児", "keyword": "newborn babe",
                "expected_part_ids": {"kangxi10", "rtk35"}},
    "rtk73": {"character": "的", "keyword": "bull's eye",
                "expected_part_ids": {"rtk37", "rtk72"}},
    "rtk131": {"character": "省", "keyword": "focus",
                "expected_part_ids": {"rtk111", "rtk15"}},
    "rtk141": {"character": "腺", "keyword": "gland",
                "expected_part_ids": {"rtk13", "rtk140"}},
    "rtk147": {"character": "汎", "keyword": "pan-",
                "expected_part_ids": {"rtk137", "rtk66"}},
    "rtk149": {"character": "汰", "keyword": "cleanse",
                "expected_part_ids": {"rtk126", "rtk137"}},
    "rtk154": {"character": "活", "keyword": "lively",
                "expected_part_ids": {"prim-katakana-no", "rtk137", "rtk16", "rtk41"}},
    "rtk204": {"character": "寄", "keyword": "draw near",
                "expected_part_ids": {"kangxi40", "rtk133"}},
    "rtk213": {"character": "梢", "keyword": "treetops",
                "expected_part_ids": {"rtk119", "rtk207"}},
    "rtk218": {"character": "椅", "keyword": "chair",
                "expected_part_ids": {"rtk11", "rtk112", "rtk207", "rtk95"}},
    "rtk237": {"character": "若", "keyword": "young",
                "expected_part_ids": {"prim-mugwort", "rtk82"}},
    "rtk238": {"character": "草", "keyword": "grass",
                "expected_part_ids": {"prim-mugwort", "rtk26"}},
    "rtk251": {"character": "桃", "keyword": "peach tree",
                "expected_part_ids": {"rtk207", "rtk250"}},
    "rtk252": {"character": "眺", "keyword": "stare",
                "expected_part_ids": {"rtk15", "rtk250"}},
    "rtk294": {"character": "鎮", "keyword": "tranquillize",
                "expected_part_ids": {"prim-katakana-ha", "rtk1", "rtk15", "rtk292"}},
    "rtk301": {"character": "逃", "keyword": "escape",
                "expected_part_ids": {"rtk250", "rtk843"}},
    "rtk310": {"character": "煎", "keyword": "roast",
                "expected_part_ids": {"prim-fire-radical", "rtk309"}},
    "rtk325": {"character": "運", "keyword": "carry",
                "expected_part_ids": {"rtk323", "rtk843"}},
    "rtk332": {"character": "熟", "keyword": "mellow",
                "expected_part_ids": {"kangxi3", "prim-fire-radical", "rtk330", "rtk9"}},
    "rtk356": {"character": "敬", "keyword": "awe",
                "expected_part_ids": {"kangxi66", "prim-mugwort", "rtk69"}},
    "rtk488": {"character": "渇", "keyword": "thirst",
                "expected_part_ids": {"rtk12", "rtk137", "rtk478"}},
    "rtk489": {"character": "謁", "keyword": "audience",
                "expected_part_ids": {"rtk12", "rtk357", "rtk478"}},
    "rtk490": {"character": "褐", "keyword": "brown",
                "expected_part_ids": {"rtk12", "rtk431", "rtk478"}},
    "rtk491": {"character": "喝", "keyword": "hoarse",
                "expected_part_ids": {"rtk11", "rtk12", "rtk478"}},
    "rtk492": {"character": "葛", "keyword": "kudzu",
                "expected_part_ids": {"prim-mugwort", "rtk12", "rtk478"}},
    "rtk502": {"character": "乾", "keyword": "drought",
                "expected_part_ids": {"prim-katakana-no", "rtk1", "rtk1023", "rtk26", "rtk75"}},
    "rtk520": {"character": "韻", "keyword": "rhyme",
                "expected_part_ids": {"rtk12", "rtk462", "rtk518", "rtk59"}},
    "rtk635": {"character": "庁", "keyword": "government office",
                "expected_part_ids": {"kangxi53", "rtk95"}},
    # Further-collapsed 2026-08-29, same day as the batch above: fixing
    # 刀,丶 -> 刃 left 心,刃 in place, which itself fully matches 忍
    # (endure, rtk642)'s own parts -- audit_flattening.py caught this as a
    # brand-new candidate right after the batch landed (iterative
    # convergence: a fix can make the next redundancy visible).
    "rtk643": {"character": "認", "keyword": "acknowledge",
                "expected_part_ids": {"rtk357", "rtk642"}},
    "rtk648": {"character": "忠", "keyword": "loyalty",
                "expected_part_ids": {"rtk39", "rtk639"}},
    "rtk650": {"character": "患", "keyword": "afflicted",
                "expected_part_ids": {"rtk39", "rtk639"}},
    "rtk670": {"character": "怖", "keyword": "dreadful",
                "expected_part_ids": {"kangxi61", "rtk433"}},
    "rtk673": {"character": "憎", "keyword": "hate",
                "expected_part_ids": {"kangxi61", "rtk540"}},
    "rtk692": {"character": "議", "keyword": "deliberation",
                "expected_part_ids": {"rtk1", "rtk357", "rtk586", "rtk690"}},
    "rtk693": {"character": "犠", "keyword": "sacrifice",
                "expected_part_ids": {"rtk1", "rtk260", "rtk586", "rtk690"}},
    "rtk695": {"character": "拭", "keyword": "wipe",
                "expected_part_ids": {"kangxi64", "rtk377"}},
    "rtk697": {"character": "抱", "keyword": "embrace",
                "expected_part_ids": {"kangxi64", "rtk569"}},
    "rtk699": {"character": "抄", "keyword": "extract",
                "expected_part_ids": {"kangxi64", "rtk111"}},
    "rtk702": {"character": "招", "keyword": "beckon",
                "expected_part_ids": {"kangxi64", "rtk90"}},
    "rtk706": {"character": "拘", "keyword": "arrest",
                "expected_part_ids": {"kangxi64", "rtk69"}},
    "rtk707": {"character": "捨", "keyword": "discard",
                "expected_part_ids": {"kangxi64", "rtk338"}},
    "rtk710": {"character": "挑", "keyword": "challenge",
                "expected_part_ids": {"kangxi64", "rtk250"}},
    "rtk712": {"character": "持", "keyword": "hold",
                "expected_part_ids": {"kangxi64", "rtk170"}},
    "rtk715": {"character": "揮", "keyword": "brandish",
                "expected_part_ids": {"kangxi64", "rtk323"}},
    "rtk718": {"character": "提", "keyword": "propose",
                "expected_part_ids": {"kangxi64", "rtk414"}},
    "rtk719": {"character": "損", "keyword": "damage",
                "expected_part_ids": {"kangxi64", "rtk59"}},
    "rtk721": {"character": "担", "keyword": "shouldering",
                "expected_part_ids": {"kangxi64", "rtk30"}},
    "rtk722": {"character": "拠", "keyword": "foothold",
                "expected_part_ids": {"kangxi64", "rtk318"}},
    "rtk725": {"character": "接", "keyword": "touch",
                "expected_part_ids": {"kangxi64", "rtk2667"}},
    "rtk726": {"character": "掲", "keyword": "put up a notice",
                "expected_part_ids": {"kangxi64", "rtk12", "rtk478"}},
    "rtk728": {"character": "捗", "keyword": "make headway",
                "expected_part_ids": {"kangxi64", "rtk397"}},
    "rtk735": {"character": "型", "keyword": "mould",
                "expected_part_ids": {"rtk161", "rtk734"}},
    "rtk776": {"character": "督", "keyword": "coach",
                "expected_part_ids": {"rtk15", "rtk775"}},
    "rtk777": {"character": "寂", "keyword": "loneliness",
                "expected_part_ids": {"kangxi40", "rtk775"}},
    "rtk778": {"character": "淑", "keyword": "graceful",
                "expected_part_ids": {"rtk137", "rtk775"}},
    "rtk792": {"character": "採", "keyword": "pick",
                "expected_part_ids": {"kangxi64", "rtk791"}},
    "rtk793": {"character": "菜", "keyword": "vegetable",
                "expected_part_ids": {"prim-mugwort", "rtk791"}},
    "rtk795": {"character": "授", "keyword": "impart",
                "expected_part_ids": {"kangxi64", "rtk794"}},
    "rtk801": {"character": "拡", "keyword": "broaden",
                "expected_part_ids": {"kangxi64", "rtk799"}},
    "rtk802": {"character": "鉱", "keyword": "mineral",
                "expected_part_ids": {"rtk287", "rtk799"}},
    "rtk810": {"character": "胎", "keyword": "womb",
                "expected_part_ids": {"rtk13", "rtk805"}},
    "rtk813": {"character": "法", "keyword": "method",
                "expected_part_ids": {"rtk137", "rtk812"}},
    "rtk822": {"character": "撤", "keyword": "remove",
                "expected_part_ids": {"kangxi64", "kangxi66", "rtk821"}},
    "rtk824": {"character": "銃", "keyword": "gun",
                "expected_part_ids": {"rtk287", "rtk823"}},
    "rtk838": {"character": "蜜", "keyword": "honey",
                "expected_part_ids": {"kangxi3", "kangxi40", "rtk556", "rtk685"}},
    "rtk850": {"character": "訟", "keyword": "sue",
                "expected_part_ids": {"rtk357", "rtk847"}},
    "rtk872": {"character": "殉", "keyword": "martyrdom",
                "expected_part_ids": {"kangxi78", "rtk71"}},
    "rtk893": {"character": "漫", "keyword": "loose",
                "expected_part_ids": {"rtk137", "rtk2240"}},
    "rtk926": {"character": "劣", "keyword": "inferiority",
                "expected_part_ids": {"rtk111", "rtk922"}},
    "rtk929": {"character": "努", "keyword": "toil",
                "expected_part_ids": {"rtk758", "rtk922"}},
    "rtk944": {"character": "待", "keyword": "wait",
                "expected_part_ids": {"kangxi60", "rtk170"}},
    "rtk945": {"character": "往", "keyword": "journey",
                "expected_part_ids": {"kangxi60", "rtk284"}},
    "rtk946": {"character": "征", "keyword": "subjugate",
                "expected_part_ids": {"kangxi60", "rtk405"}},
    "rtk951": {"character": "徹", "keyword": "penetrate",
                "expected_part_ids": {"kangxi60", "kangxi66", "rtk821"}},
    "rtk959": {"character": "稼", "keyword": "earnings",
                "expected_part_ids": {"kangxi115", "rtk580"}},
    "rtk967": {"character": "愁", "keyword": "distress",
                "expected_part_ids": {"rtk639", "rtk966"}},
    "rtk983": {"character": "稽", "keyword": "training",
                "expected_part_ids": {"kangxi115", "rtk2232", "rtk493"}},
    "rtk986": {"character": "萎", "keyword": "numb",
                "expected_part_ids": {"prim-mugwort", "rtk979"}},
    "rtk994": {"character": "謎", "keyword": "riddle",
                "expected_part_ids": {"rtk357", "rtk992"}},
    "rtk995": {"character": "糧", "keyword": "provisions",
                "expected_part_ids": {"rtk185", "rtk30", "rtk987"}},
    "rtk1021": {"character": "築", "keyword": "fabricate",
                "expected_part_ids": {"rtk1007", "rtk207", "rtk66", "rtk80"}},
    "rtk1059": {"character": "儀", "keyword": "ceremony",
                "expected_part_ids": {"rtk1", "rtk586", "rtk690"}},
    "rtk1066": {"character": "便", "keyword": "convenience",
                "expected_part_ids": {"kangxi9", "rtk749"}},
    "rtk1101": {"character": "挫", "keyword": "sprain",
                "expected_part_ids": {"kangxi64", "rtk2861"}},
    "rtk1135": {"character": "泥", "keyword": "mud",
                "expected_part_ids": {"rtk1133", "rtk137"}},
    "rtk1139": {"character": "握", "keyword": "grip",
                "expected_part_ids": {"kangxi64", "rtk1138"}},
    "rtk1146": {"character": "層", "keyword": "stratum",
                "expected_part_ids": {"kangxi44", "rtk540"}},
    "rtk1156": {"character": "昼", "keyword": "daytime",
                "expected_part_ids": {"kangxi3", "kangxi44", "rtk30"}},
    "rtk1170": {"character": "祝", "keyword": "celebrate",
                "expected_part_ids": {"kangxi113", "rtk107"}},
    "rtk1180": {"character": "襟", "keyword": "collar",
                "expected_part_ids": {"rtk1179", "rtk431"}},
    "rtk1182": {"character": "崇", "keyword": "adore",
                "expected_part_ids": {"rtk1181", "rtk830"}},
    "rtk1197": {"character": "挿", "keyword": "insert",
                "expected_part_ids": {"kangxi64", "prim-pipe", "rtk12", "rtk14", "rtk40"}},
    "rtk1271": {"character": "惜", "keyword": "pity",
                "expected_part_ids": {"kangxi61", "rtk1268"}},
    "rtk1272": {"character": "措", "keyword": "set aside",
                "expected_part_ids": {"kangxi64", "rtk1268"}},
    "rtk1276": {"character": "遮", "keyword": "intercept",
                "expected_part_ids": {"rtk1", "rtk1275", "rtk843"}},
    "rtk1298": {"character": "版", "keyword": "printing block",
                "expected_part_ids": {"rtk1297", "rtk779"}},
    "rtk1300": {"character": "乏", "keyword": "destitution",
                "expected_part_ids": {"prim-katakana-no", "rtk1299"}},
    "rtk1314": {"character": "霧", "keyword": "fog",
                "expected_part_ids": {"rtk1313", "rtk451"}},
    "rtk1339": {"character": "謝", "keyword": "apologize",
                "expected_part_ids": {"rtk1338", "rtk357"}},
    "rtk1343": {"character": "教", "keyword": "teach",
                "expected_part_ids": {"kangxi66", "rtk1342"}},
    "rtk1346": {"character": "煮", "keyword": "boil",
                "expected_part_ids": {"prim-fire-radical", "rtk1345"}},
    "rtk1347": {"character": "著", "keyword": "renowned",
                "expected_part_ids": {"prim-mugwort", "rtk1345"}},
    "rtk1348": {"character": "箸", "keyword": "chopsticks",
                "expected_part_ids": {"rtk1007", "rtk1345"}},
    "rtk1351": {"character": "諸", "keyword": "various",
                "expected_part_ids": {"rtk1345", "rtk357"}},
    "rtk1353": {"character": "渚", "keyword": "strand",
                "expected_part_ids": {"rtk1345", "rtk137"}},
    "rtk1354": {"character": "賭", "keyword": "gamble",
                "expected_part_ids": {"rtk1345", "rtk56"}},
    "rtk1370": {"character": "較", "keyword": "contrast",
                "expected_part_ids": {"rtk1368", "rtk304"}},
    "rtk1377": {"character": "露", "keyword": "dew",
                "expected_part_ids": {"rtk1376", "rtk451"}},
    "rtk1378": {"character": "跳", "keyword": "hop",
                "expected_part_ids": {"rtk11", "rtk1372", "rtk250", "rtk396"}},
    "rtk1385": {"character": "髄", "keyword": "marrow",
                "expected_part_ids": {"kangxi14", "rtk1383", "rtk83", "rtk843"}},
    "rtk1390": {"character": "阪", "keyword": "heights",
                "expected_part_ids": {"kangxi170", "rtk779"}},
    "rtk1393": {"character": "障", "keyword": "hinder",
                "expected_part_ids": {"kangxi170", "rtk26", "rtk462", "rtk518"}},
    "rtk1395": {"character": "随", "keyword": "follow",
                "expected_part_ids": {"kangxi170", "rtk83", "rtk843"}},
    "rtk1404": {"character": "墜", "keyword": "crash",
                "expected_part_ids": {"rtk1403", "rtk161"}},
    "rtk1406": {"character": "階", "keyword": "story",
                "expected_part_ids": {"kangxi170", "rtk484"}},
    "rtk1411": {"character": "堕", "keyword": "degenerate",
                "expected_part_ids": {"kangxi170", "rtk161", "rtk83"}},
    "rtk1412": {"character": "陥", "keyword": "collapse",
                "expected_part_ids": {"kangxi170", "kangxi20", "rtk35"}},
    "rtk1415": {"character": "控", "keyword": "withdraw",
                "expected_part_ids": {"kangxi64", "rtk1414"}},
    "rtk1422": {"character": "搾", "keyword": "squeeze",
                "expected_part_ids": {"kangxi64", "rtk2660"}},
    "rtk1429": {"character": "兵", "keyword": "soldier",
                "expected_part_ids": {"prim-katakana-ha", "rtk1427"}},
    "rtk1434": {"character": "縮", "keyword": "shrink",
                "expected_part_ids": {"kangxi52", "rtk1070", "rtk110", "rtk1431"}},
    "rtk1435": {"character": "繁", "keyword": "luxuriant",
                "expected_part_ids": {"kangxi52", "rtk110", "rtk1431", "rtk498"}},
    "rtk1436": {"character": "縦", "keyword": "vertical",
                "expected_part_ids": {"kangxi52", "rtk110", "rtk1431", "rtk942"}},
    "rtk1438": {"character": "線", "keyword": "line",
                "expected_part_ids": {"kangxi52", "rtk110", "rtk140", "rtk1431"}},
    "rtk1439": {"character": "綻", "keyword": "come apart at the seams",
                "expected_part_ids": {"kangxi52", "rtk110", "rtk1431", "rtk408"}},
    "rtk1444": {"character": "緒", "keyword": "thong",
                "expected_part_ids": {"kangxi52", "rtk110", "rtk1345", "rtk1431"}},
    "rtk1448": {"character": "絞", "keyword": "strangle",
                "expected_part_ids": {"kangxi52", "rtk110", "rtk1368", "rtk1431"}},
    "rtk1476": {"character": "縛", "keyword": "truss",
                "expected_part_ids": {"kangxi3", "kangxi52", "rtk110", "rtk1431", "rtk47"}},
    "rtk1488": {"character": "擁", "keyword": "hug",
                "expected_part_ids": {"rtk1484", "rtk716"}},
    "rtk1498": {"character": "脚", "keyword": "shins",
                "expected_part_ids": {"rtk13", "rtk1497"}},
    "rtk1500": {"character": "御", "keyword": "honorable",
                "expected_part_ids": {"kangxi60", "rtk1499"}},
    "rtk1504": {"character": "零", "keyword": "zero",
                "expected_part_ids": {"rtk1503", "rtk451"}},
    "rtk1522": {"character": "腕", "keyword": "arm",
                "expected_part_ids": {"rtk13", "rtk1521"}},
    "rtk1528": {"character": "瑠", "keyword": "marine blue",
                "expected_part_ids": {"rtk1527", "rtk271"}},
    "rtk1536": {"character": "酌", "keyword": "bartending",
                "expected_part_ids": {"rtk1534", "rtk72"}},
    "rtk1547": {"character": "尊", "keyword": "revered",
                "expected_part_ids": {"rtk2915", "rtk45"}},
    "rtk1557": {"character": "盆", "keyword": "basin",
                "expected_part_ids": {"rtk1555", "rtk844"}},
    "rtk1561": {"character": "蓋", "keyword": "lid",
                "expected_part_ids": {"prim-mugwort", "rtk1555", "rtk812"}},
    "rtk1564": {"character": "鑑", "keyword": "specimen",
                "expected_part_ids": {"rtk1562", "rtk287"}},
    "rtk1565": {"character": "藍", "keyword": "indigo",
                "expected_part_ids": {"prim-katakana-no", "prim-mugwort", "rtk1562"}},
    "rtk1583": {"character": "飯", "keyword": "meal",
                "expected_part_ids": {"rtk1582", "rtk779"}},
    "rtk1586": {"character": "餓", "keyword": "starve",
                "expected_part_ids": {"rtk1582", "rtk690"}},
    "rtk1592": {"character": "飽", "keyword": "sated",
                "expected_part_ids": {"rtk1582", "rtk569"}},
    "rtk1595": {"character": "慨", "keyword": "rue",
                "expected_part_ids": {"kangxi61", "rtk1593"}},
    "rtk1634": {"character": "熱", "keyword": "heat",
                "expected_part_ids": {"kangxi10", "prim-fire-radical", "rtk161", "rtk44"}},
    "rtk1640": {"character": "該", "keyword": "above-stated",
                "expected_part_ids": {"rtk1637", "rtk357"}},
    "rtk1663": {"character": "積", "keyword": "volume",
                "expected_part_ids": {"kangxi115", "rtk1661"}},
    "rtk1670": {"character": "喫", "keyword": "consume",
                "expected_part_ids": {"rtk11", "rtk1669"}},
    "rtk1706": {"character": "唾", "keyword": "saliva",
                "expected_part_ids": {"rtk11", "rtk1705"}},
    "rtk1707": {"character": "睡", "keyword": "drowsy",
                "expected_part_ids": {"rtk15", "rtk1705"}},
    "rtk1708": {"character": "錘", "keyword": "spindle",
                "expected_part_ids": {"rtk1705", "rtk287"}},
    "rtk1716": {"character": "捻", "keyword": "wrench",
                "expected_part_ids": {"kangxi64", "rtk1715"}},
    "rtk1721": {"character": "預", "keyword": "deposit",
                "expected_part_ids": {"rtk1719", "rtk505", "rtk56", "rtk64"}},
    "rtk1731": {"character": "腰", "keyword": "loins",
                "expected_part_ids": {"rtk13", "rtk1730"}},
    "rtk1733": {"character": "漂", "keyword": "drift",
                "expected_part_ids": {"rtk137", "rtk1732"}},
    "rtk1734": {"character": "標", "keyword": "signpost",
                "expected_part_ids": {"rtk1732", "rtk207"}},
    "rtk1749": {"character": "簡", "keyword": "simplicity",
                "expected_part_ids": {"rtk1007", "rtk1747"}},
    "rtk1767": {"character": "侯", "keyword": "marquis",
                "expected_part_ids": {"kangxi9", "prim-katakana-yu", "rtk1305"}},
    "rtk1769": {"character": "候", "keyword": "climate",
                "expected_part_ids": {"prim-pipe", "rtk1767"}},
    "rtk1776": {"character": "韓", "keyword": "korea",
                "expected_part_ids": {"kangxi178", "rtk11", "rtk26"}},
    "rtk1783": {"character": "幹", "keyword": "tree trunk",
                "expected_part_ids": {"prim-umbrella", "rtk1777", "rtk26"}},
    # Further-collapsed 2026-08-29, same iterative-convergence discovery
    # as rtk643 above: fixing 人,冂 -> 内 left 一,内 in place, which fully
    # matches 丙 (third class, rtk1096)'s own parts.
    "rtk1813": {"character": "病", "keyword": "ill",
                "expected_part_ids": {"kangxi104", "rtk1096"}},
    "rtk1816": {"character": "症", "keyword": "symptoms",
                "expected_part_ids": {"kangxi104", "rtk405"}},
    "rtk1820": {"character": "嫉", "keyword": "envy",
                "expected_part_ids": {"rtk102", "rtk1819"}},
    "rtk1846": {"character": "彫", "keyword": "carve",
                "expected_part_ids": {"kangxi59", "rtk339"}},
    "rtk1848": {"character": "影", "keyword": "shadow",
                "expected_part_ids": {"kangxi59", "rtk336"}},
    "rtk1850": {"character": "彩", "keyword": "coloring",
                "expected_part_ids": {"kangxi59", "rtk791"}},
    "rtk1851": {"character": "彰", "keyword": "patent",
                "expected_part_ids": {"kangxi59", "rtk26", "rtk462", "rtk518"}},
    "rtk1907": {"character": "堪", "keyword": "withstand",
                "expected_part_ids": {"rtk161", "rtk1830", "rtk1894"}},
    "rtk1951": {"character": "悪", "keyword": "bad",
                "expected_part_ids": {"rtk1950", "rtk639"}},
    "rtk1990": {"character": "郵", "keyword": "mail",
                "expected_part_ids": {"rtk1705", "rtk1991"}},
    "rtk1996": {"character": "廊", "keyword": "corridor",
                "expected_part_ids": {"kangxi53", "rtk1995"}},
    "rtk1998": {"character": "循", "keyword": "sequential",
                "expected_part_ids": {"kangxi60", "rtk1997"}},
    "rtk2011": {"character": "嗣", "keyword": "heir",
                "expected_part_ids": {"kangxi13", "prim-pipe", "rtk2007"}},
    "rtk2017": {"character": "盤", "keyword": "tray",
                "expected_part_ids": {"rtk1555", "rtk2016"}},
    "rtk2049": {"character": "蒸", "keyword": "steam",
                "expected_part_ids": {"prim-fire-radical", "prim-mugwort", "rtk2927"}},
    "rtk2079": {"character": "戦", "keyword": "war",
                "expected_part_ids": {"kangxi62", "rtk2078"}},
    "rtk2081": {"character": "弾", "keyword": "bullet",
                "expected_part_ids": {"rtk1317", "rtk2078"}},
    "rtk2137": {"character": "駆", "keyword": "drive",
                "expected_part_ids": {"prim-fire-radical", "rtk1831", "rtk2132"}},
    "rtk2147": {"character": "膚", "keyword": "skin",
                "expected_part_ids": {"kangxi141", "kangxi25", "kangxi27", "rtk29", "rtk476"}},
    "rtk2150": {"character": "虞", "keyword": "uneasiness",
                "expected_part_ids": {"kangxi141", "kangxi25", "kangxi27", "rtk2046", "rtk476"}},
    "rtk2151": {"character": "慮", "keyword": "prudence",
                "expected_part_ids": {"kangxi141", "kangxi25", "kangxi27", "rtk476", "rtk651"}},
    "rtk2159": {"character": "熊", "keyword": "bear",
                "expected_part_ids": {"prim-fire-radical", "rtk2160"}},
    "rtk2163": {"character": "演", "keyword": "performance",
                "expected_part_ids": {"rtk137", "rtk2162"}},
    "rtk2182": {"character": "嚇", "keyword": "upbraid",
                "expected_part_ids": {"rtk11", "rtk2917"}},
    "rtk2184": {"character": "雰", "keyword": "atmosphere",
                "expected_part_ids": {"rtk451", "rtk844"}},
    "rtk2187": {"character": "遵", "keyword": "abide by",
                "expected_part_ids": {"rtk1547", "rtk843"}},
    # 境 fixed (2026-08-29, owner-reported): old 音,土,日,立,儿 redundantly
    # listed 音 alongside its own already-flattened 日,立 sub-parts side by
    # side. cjkvi-ids confirms 境 = 土+竟, 竟 = 音+儿 -- added 竟 as a new
    # primitive (prim-finally, with its own 音,儿 sub-decomposition) per
    # owner request, rather than just deduplicating the flat list.
    "rtk523": {"character": "境", "keyword": "boundary",
               "expected_part_ids": {"rtk161", "prim-finally"}},
    # 唱 fixed (2026-08-30, audit_csv_regressions.py rarity-filtered pass):
    # old 口,日 was missing a whole second 日 -- cjkvi-ids confirms
    # 唱 = 口+昌, 昌 = 日+日 (two suns stacked), and CSV's components list
    # ("mouth; prosperous; sun; day; tongue wagging") independently names
    # 昌 ("prosperous") as the real compound. Fixed to reference 昌
    # (rtk25) directly rather than reproducing only one of its two suns.
    "rtk21": {"character": "唱", "keyword": "chant",
              "expected_part_ids": {"rtk11", "rtk25"}},
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
