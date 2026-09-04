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
    # rad2.8 ("animal legs") was an orphaned legacy placeholder (character='?', never
    # linked to its real glyph) that duplicated prim-katakana-ha (ハ) -- session
    # 2026-08-30 re-homed rtk6's part onto prim-katakana-ha and retired rad2.8, same
    # consolidation pattern as kangxi94/kangxi122 earlier in the audit.
    "rtk6": {"character": "六", "keyword": "six",
             "expected_part_ids": {"kangxi8", "prim-katakana-ha"}},
    # Was ｜,一,日,木,田 -- redundant flattening (｜+一 = 日's own strokes double-counted)
    # plus an erroneous, unrelated 田 -- CSV lists 東 as just "sun; day; tree; wood"
    # (session 2026-08-30, found via cross-checking tools/heisig-google-check/results.jsonl).
    "rtk543": {"character": "東", "keyword": "east",
               "expected_part_ids": {"rtk12", "rtk207"}},
    # The same ｜,一,日,木,田-style corrupted flatten as rtk543 had propagated to every
    # 東-containing compound in data.txt (found by grepping for the literal pattern
    # once rtk543 itself was fixed) -- collapsed each back to referencing 東/由 (or,
    # for 欄, 木+門+東 per CSV's "tree; wood; gates; east") as a whole part instead of
    # re-flattening its strokes. Session 2026-08-30.
    "rtk544": {"character": "棟", "keyword": "ridgepole",
               "expected_part_ids": {"rtk207", "rtk543"}},
    "rtk545": {"character": "凍", "keyword": "frozen",
               "expected_part_ids": {"kangxi15", "rtk543"}},
    "rtk2186": {"character": "錬", "keyword": "tempering",
                "expected_part_ids": {"rtk287", "rtk543"}},
    "rtk2549": {"character": "柚", "keyword": "citron",
                "expected_part_ids": {"rtk207", "rtk1186"}},
    "rtk2745": {"character": "諌", "keyword": "admonish",
                "expected_part_ids": {"rtk357", "rtk543"}},
    "rtk1756": {"character": "欄", "keyword": "column",
                "expected_part_ids": {"rtk207", "rtk1743", "rtk543"}},
    # 由/甲/申 all carried identical copy-pasted parts (｜,日,田) despite being
    # CSV-distinct glyphs; render_glyphs.py (Chromium+Noto Sans CJK JP installed this
    # session) confirmed all three really are 田 plus one added stroke -- Heisig's own
    # prim-pipe (｜) primitive -- just positioned differently (top/bottom/both), which
    # this flattened parts-list model can't capture. Dropped the erroneous 日. Session
    # 2026-08-30.
    "rtk1186": {"character": "由", "keyword": "wherefore",
                "expected_part_ids": {"rtk14", "prim-pipe"}},
    "rtk1194": {"character": "甲", "keyword": "armor",
                "expected_part_ids": {"rtk14", "prim-pipe"}},
    "rtk1198": {"character": "申", "keyword": "speaketh",
                "expected_part_ids": {"rtk14", "prim-pipe"}},
    # 曹 was ｜,一,日 (missing 曲/"bend" entirely, despite CSV and the independent
    # data_from_pdf.txt extraction both saying "one, bend, sun") -- confirmed via
    # render that the top really is 曲-shaped. 動/糟 both reference 曹-family parts as
    # whole compounds (重+力, 米+曹 respectively) per IDS, confirmed via render.
    "rtk1257": {"character": "曹", "keyword": "cadet",
                "expected_part_ids": {"rtk1", "rtk1256", "rtk12"}},
    # 重 was ｜,ノ,一,日,里 -- IDS says 重 is actually Unicode-atomic, but render
    # confirms the standard Heisig mnemonic 千("thousand")+里("village") holds up
    # visually (top matches 千 exactly, bottom matches 里 exactly); CSV's "thousand;
    # computer; rice field; brains; soil; dirt; ground" is 千's and 里's own
    # sub-component gloss fragments bleeding through, not 重's real parts.
    "rtk1805": {"character": "重", "keyword": "heavy",
                "expected_part_ids": {"rtk40", "rtk185"}},
    "rtk1806": {"character": "動", "keyword": "move",
                "expected_part_ids": {"rtk1805", "rtk922"}},
    "rtk2691": {"character": "糟", "keyword": "lees",
                "expected_part_ids": {"rtk987", "rtk1257"}},
    "rtk2014": {"character": "航", "keyword": "navigate",
                "expected_part_ids": {"rtk2012", "kangxi8", "kangxi16"}},
    "rtk580": {"character": "家", "keyword": "house",
               "expected_part_ids": {"kangxi40", "kangxi152"}},
    # "sun" used to resolve to hanzi-5b6b (孫, grandchild) via an unrelated pinyin
    # collision, since rtk12 (日) had no "sun" alias at all -- fixed as a side effect
    # of session 25's alias restoration (rtk12 got "sun" back), so "sun" and "day"
    # now both correctly resolve to rtk12 and collapse to one chip.
    # Fixed 2026-08-31: was 宀,primitive_roof,span,one,ceiling,sun,day,one,
    # floor,one -- corrupted/bloated (rad1.1, an orphaned legacy placeholder
    # colliding with "ceiling"/"floor"/"minus" aliases that really belong on
    # rtk1/一, plus "one"/"sun"/"day" duplicating 亘's own already-taught
    # parts). cjkvi-ids confirms 宣 = 宀+亘 exactly. rad1.1 itself deleted
    # (its aliases moved onto rtk1, its only other reference); see the 更/
    # 梗/典/暢/亘 cluster fixed the same session for the rest of this batch.
    "rtk200": {"character": "宣", "keyword": "proclaim",
               "expected_part_ids": {"kangxi40", "rtk32"}},
    "rtk1809": {"character": "働", "keyword": "work",
                "expected_part_ids": {"kangxi9", "rtk1806"}},
    "rtk688": {"character": "看", "keyword": "watch over",
               "expected_part_ids": {"prim-katakana-no", "rtk1", "rtk687", "rtk2", "rtk15"}},
    "rtk1049": {"character": "側", "keyword": "side",
                "expected_part_ids": {"kangxi9", "rtk92"}},  # 亻 + 則 (person radical added 2026-09-05)
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
    # Was 扌,𠂊,央 (rtk1877, "center") -- render-confirmed 換's right side is the
    # SAME 奐 shape as 喚(rtk1121)'s own right side (they're siblings, ⿰口奐 vs
    # ⿰扌奐), not remotely 央-shaped; the pre-fix pin baked the bug in. Fixed
    # 2026-09-05 to match 喚's own 奐 treatment (四,大,冂,勹).
    "rtk1122": {"character": "換", "keyword": "interchange",
                "expected_part_ids": {"kangxi64", "kangxi13", "kangxi20", "rtk4", "rtk112"}},
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
    # Corrected 2026-09-01 (owner-reported 口 audit): was kangxi170,rtk10,
    # rtk11,prim-pipe -- wrong on two counts (阝 doesn't belong on the
    # standalone 阜 itself, and 口/｜ were standing in for a completely
    # missing primitive). cjkvi-ids: 阜 = ⿱𠂤十. Added prim-maestro (𠂤,
    # Heisig's own "maestro", CSV-confirmed across the whole 追/師/帥/官
    # cluster) since it had never been added to this dataset at all.
    "rtk1360": {"character": "阜", "keyword": "large hill",
                "expected_part_ids": {"prim-maestro", "rtk10"}},
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
                "expected_part_ids": {"kangxi9", "rtk2067"}},  # 亻 + 為 (person radical added 2026-09-05)
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
                "expected_part_ids": {"rtk1503", "rtk64"}},
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
    # Corrected 2026-09-01 (owner-reported): the original sweep-batch-1 fix
    # (way earlier this audit) matched 椅 against 丁(rtk95, "street") --
    # a real but *partial* match (丁 only accounts for 一,亅) that left 口,大
    # sitting there unexplained and, worse, made the real bug invisible to
    # audit_flattening.py's own detector (丁's own sub-parts absorbed the
    # 一/亅 tokens, so the remaining top-level set no longer matched anything
    # as a contiguous run). cjkvi-ids confirms 椅 = ⿰木奇 -- 奇(rtk133,
    # "strange") is the correct, *maximal* match, fully consuming 一,口,大,亅
    # at once. Lesson: always prefer the longest/most-complete compound
    # match, not the first one found.
    "rtk218": {"character": "椅", "keyword": "chair",
                "expected_part_ids": {"rtk207", "rtk133"}},
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
                "expected_part_ids": {"rtk518", "rtk59"}},
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
                "expected_part_ids": {"kangxi9", "rtk691"}},  # 亻 + 義 (person radical added 2026-09-05)
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
                "expected_part_ids": {"rtk1372", "rtk250"}},
    "rtk1385": {"character": "髄", "keyword": "marrow",
                "expected_part_ids": {"kangxi14", "rtk1383", "rtk83", "rtk843"}},
    "rtk1390": {"character": "阪", "keyword": "heights",
                "expected_part_ids": {"kangxi170", "rtk779"}},
    "rtk1393": {"character": "障", "keyword": "hinder",
                "expected_part_ids": {"kangxi170", "rtk464"}},
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
                "expected_part_ids": {"rtk1070", "rtk1431"}},
    "rtk1435": {"character": "繁", "keyword": "luxuriant",
                "expected_part_ids": {"rtk1431", "rtk498"}},
    "rtk1436": {"character": "縦", "keyword": "vertical",
                "expected_part_ids": {"rtk1431", "rtk942"}},
    "rtk1438": {"character": "線", "keyword": "line",
                "expected_part_ids": {"rtk140", "rtk1431"}},
    "rtk1439": {"character": "綻", "keyword": "come apart at the seams",
                "expected_part_ids": {"rtk1431", "rtk408"}},
    "rtk1444": {"character": "緒", "keyword": "thong",
                "expected_part_ids": {"rtk1345", "rtk1431"}},
    "rtk1448": {"character": "絞", "keyword": "strangle",
                "expected_part_ids": {"rtk1368", "rtk1431"}},
    "rtk1476": {"character": "縛", "keyword": "truss",
                "expected_part_ids": {"kangxi3", "rtk1431", "rtk47"}},
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
                "expected_part_ids": {"rtk1719", "rtk505", "rtk64"}},
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
                "expected_part_ids": {"kangxi9", "prim-pipe", "rtk1767"}},  # 亻 added 2026-09-05
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
                "expected_part_ids": {"kangxi59", "rtk464"}},
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
    # 更/梗/典/暢/亘 cluster fixed 2026-08-31, continuing the previous
    # session's flagged "next session priorities". All confirmed via
    # cjkvi-ids + render, not just CSV, since CSV is blank or only
    # loosely worded for several of these.
    #
    # 亘 (rtk32) was 一,二,日 -- wrong: cjkvi-ids says 亘 = 一 + 旦
    # (already-taught rtk30, itself 日+一), not "一,二,日" flattened with a
    # 二 that isn't even part of the real glyph. Fixed to 一,旦.
    "rtk32": {"character": "亘", "keyword": "span",
              "expected_part_ids": {"rtk1", "rtk30"}},
    # 更 (rtk749) was ノ,一,日,田 -- 田 has no connection to "grow late" at
    # all. cjkvi-ids: 更 = ⿱一⿻日乂 (一 on top, 乂 overlapping 日 below).
    # data_from_pdf.txt's 4th-edition extraction independently names the
    # same three primitives Heisig actually teaches here: "ceiling"
    # (rtk1/一 -- see the rad1.1 cleanup below), "sun" (rtk12/日), and
    # "tucked under the arm" -- a real Unicode character (乂, U+4E42) with
    # no existing entry, added as prim-tucked-under-the-arm.
    "rtk749": {"character": "更", "keyword": "grow late",
               "expected_part_ids": {"rtk1", "rtk12", "prim-tucked-under-the-arm"}},
    # 梗 (rtk751) re-flattened 更's stale strokes instead of referencing it;
    # cjkvi-ids: 梗 = ⿰木更. Fixed to 木,更.
    "rtk751": {"character": "梗", "keyword": "spiny",
               "expected_part_ids": {"rtk207", "rtk749"}},
    # 典 (rtk1969) was ｜,一,日,ハ -- render confirms the top is unmistakably
    # 曲 (bend, already-taught rtk1256), matching CSV's "bend; tool"
    # component gloss; bottom is 八. Fixed to 曲,八.
    "rtk1969": {"character": "典", "keyword": "code",
                "expected_part_ids": {"rtk1256", "rtk8"}},
    # 暢 (rtk2895) was ｜,一,日,田,勿 -- the 田/｜/一 tokens don't belong at
    # all. cjkvi-ids: 暢 = ⿰申昜, 昜 = ⿱旦勿. Flattened one level past 昜
    # (skipped adding it as its own primitive -- 昜/U+661C and 易/U+6613
    # render near-identically in this font, and this session already found
    # that exact mix-up once; safer to reference only the three
    # already-taught, unambiguous primitives it resolves to). Fixed to
    # 申,旦,勿 (rtk1198/rtk30/rtk1128, all pre-existing).
    "rtk2895": {"character": "暢", "keyword": "carefree",
                "expected_part_ids": {"rtk1198", "rtk30", "rtk1128"}},
    # Batch fixed 2026-09-01, continuing the IDS-atomic-but-has-parts review
    # (67-item list from the Google-cross-check session). All confirmed via CSV
    # components + render, not just CSV wording alone.
    # 世 was ｜,一 -- render confirms the top matches 廿 ("twenty", rtk1274, itself
    # fixed below) exactly, plus a bottom horizontal stroke; CSV says "ten; twenty".
    "rtk28": {"character": "世", "keyword": "generation",
              "expected_part_ids": {"rtk1274", "rtk1"}},
    # 廿 was ｜,一,凵 -- the lone ｜ was redundant, both verticals already come from
    # 凵; render confirms 廿 = 凵 + a top horizontal stroke exactly.
    "rtk1274": {"character": "廿", "keyword": "twenty",
                "expected_part_ids": {"kangxi17", "rtk1"}},
    # 自 was missing the top dot entirely; CSV: "drop; eye" = 丶+目.
    "rtk36": {"character": "自", "keyword": "oneself",
              "expected_part_ids": {"kangxi3", "rtk15"}},
    # 頁 was missing its top horizontal stroke; render confirms 頁 = 一 + 貝
    # (matching CSV's "one; ceiling; ...(貝's own sub-components)").
    "rtk64": {"character": "頁", "keyword": "page",
              "expected_part_ids": {"rtk1", "rtk56"}},
    # 州 had a redundant extra ｜ alongside 川+丶; CSV: "stream; flood; drops".
    "rtk135": {"character": "州", "keyword": "state",
               "expected_part_ids": {"rtk134", "kangxi3"}},
    # 及 had a redundant extra ノ alongside 丶+乃; CSV: "fist; from; drop" -- render
    # confirms 及 visually matches 乃 (whose own CSV components gloss is literally
    # "fist") plus one added dot, not a separate ノ stroke.
    "rtk743": {"character": "及", "keyword": "reach out",
               "expected_part_ids": {"kangxi3", "rtk741"}},
    # 丈 was ノ,一,丶 -- none of which reflect CSV's "stick; tucked under the arm".
    # Render confirms the bottom matches prim-tucked-under-the-arm (乂) exactly.
    "rtk746": {"character": "丈", "keyword": "length",
               "expected_part_ids": {"rtk1", "prim-tucked-under-the-arm"}},
    # 史 was ノ,口 -- CSV: "mouth; tucked under the arm" = 口+乂, confirmed by render.
    "rtk747": {"character": "史", "keyword": "history",
               "expected_part_ids": {"rtk11", "prim-tucked-under-the-arm"}},
    # 吏 was re-flattening 史's parts instead of referencing it; render confirms
    # 吏 = 一 + 史 (whole compound) exactly, matching CSV's overlapping gloss terms.
    "rtk748": {"character": "吏", "keyword": "officer",
               "expected_part_ids": {"rtk1", "rtk747"}},
    # 久 was ノ,入 -- render confirms the top matches prim-hooked-hand (𠂊, "bound
    # up") exactly and the bottom matches 人; CSV: "bound up; person; mummy".
    "rtk1092": {"character": "久", "keyword": "long time",
                "expected_part_ids": {"prim-hooked-hand", "rtk1023"}},
    # 肉 was 冂,人 -- render confirms 肉 and 内 ("inside", rtk1095) share almost the
    # same outer contour; CSV: "person; inside; belt; person" -- fixed to reference
    # 内 as a whole compound plus the extra internal stroke (人) 肉 adds over 内.
    "rtk1098": {"character": "肉", "keyword": "meat",
                "expected_part_ids": {"rtk1095", "rtk1023"}},
    # 年 was ノ,一,干 -- render confirms 年 and 午 ("noon", rtk610) are nearly
    # identical, differing only by one added short stroke on top; CSV: "sign of
    # the horse; sunglasses" (午 is the zodiac "horse" hour). Fixed to reference
    # 午 as a whole compound plus that one extra stroke.
    "rtk1114": {"character": "年", "keyword": "year",
                "expected_part_ids": {"prim-katakana-no", "rtk610"}},
    # 己/已/巳 host-by-host review (2026-09-01): 18 hosts wrongly used 已("stop")
    # where cjkvi-ids's Japanese-standard variant calls for 己 (11 hosts) or
    # 巳 (1 host, 祀); the other 6 needed a real re-decomposition, not just a
    # character swap (see each entry's own comment). Also added prim-southeast
    # (巽 = 己+共), a real 5th-edition-only Heisig frame (id_5th_ed=2861,
    # dropped from the 6th) needed by 選/撰, since it's a genuine, citable
    # compound shared by both rather than repeating 己+共 twice.
    "rtk565": {"character": "起", "keyword": "rouse",
               "expected_part_ids": {"rtk410", "rtk564"}},
    "rtk566": {"character": "妃", "keyword": "queen",
               "expected_part_ids": {"rtk102", "rtk564"}},
    "rtk567": {"character": "改", "keyword": "reformation",
               "expected_part_ids": {"rtk564", "kangxi66"}},
    "rtk568": {"character": "記", "keyword": "scribe",
               "expected_part_ids": {"rtk357", "rtk564"}},
    "rtk569": {"character": "包", "keyword": "wrap",
               "expected_part_ids": {"kangxi20", "rtk564"}},
    "rtk644": {"character": "忌", "keyword": "mourning",
               "expected_part_ids": {"rtk564", "rtk639"}},
    "rtk1292": {"character": "巻", "keyword": "scroll",
                "expected_part_ids": {"rtk112", "rtk2", "kangxi12", "rtk564"}},
    "rtk1454": {"character": "紀", "keyword": "chronicle",
                "expected_part_ids": {"rtk1431", "rtk564"}},
    "rtk1544": {"character": "配", "keyword": "distribute",
                "expected_part_ids": {"rtk1534", "rtk564"}},
    "rtk1737": {"character": "遷", "keyword": "transition",
                "expected_part_ids": {"rtk843", "rtk1728", "rtk112", "rtk564"}},
    # 港 was 水,ハ,已,井 -- neither ハ nor 井 have any connection to the real
    # glyph. cjkvi-ids: 港 = 氵+巷, 巷 = 共+己 (Japanese variant); flattened
    # past 巷 (not itself a taught frame, no Heisig citation for it) straight
    # to its two real components.
    "rtk1940": {"character": "港", "keyword": "harbor",
                "expected_part_ids": {"rtk137", "rtk1934", "rtk564"}},
    # 選 was ｜,込,二,ハ,已 -- cjkvi-ids: 選 = 込+巽. Fixed to reference the new
    # prim-southeast primitive.
    "rtk1944": {"character": "選", "keyword": "elect",
                "expected_part_ids": {"rtk843", "prim-southeast"}},
    # 倦 was 已,大,二,丷,卩,ハ -- a flattened mess re-copying 巻's own sub-parts
    # (大,二,丷) plus stray tokens. cjkvi-ids: 倦 = 亻+巻(J variant). Fixed to
    # reference the already-taught 巻 (rtk1292) directly.
    "rtk2246": {"character": "倦", "keyword": "fed up",
                "expected_part_ids": {"kangxi9", "rtk1292"}},
    # 庖 was 勹,已,广 -- cjkvi-ids: 庖 = 广+包. Fixed to reference 包 (rtk569).
    "rtk2341": {"character": "庖", "keyword": "cleaver",
                "expected_part_ids": {"kangxi53", "rtk569"}},
    # 撰 was ｜,二,ハ,已,扌 -- cjkvi-ids: 撰 = 扌+巽. Fixed to reference
    # prim-southeast, same as 選 above.
    "rtk2357": {"character": "撰", "keyword": "assortment",
                "expected_part_ids": {"kangxi64", "prim-southeast"}},
    # 鞄 was 革,勹,已 -- cjkvi-ids: 鞄 = 革+包. Fixed to reference 包 (rtk569).
    "rtk2806": {"character": "鞄", "keyword": "briefcase",
                "expected_part_ids": {"rtk2041", "rtk569"}},
    # 祀 was 礼,已 -- two bugs at once: 礼 (the whole "salute" kanji, rtk1168)
    # was standing in for 礻 (altar) again, the same bug class kangxi113's
    # fix addressed dataset-wide but missed this one host; and cjkvi-ids's
    # JK variant confirms the right side is 巳, not 已. Fixed to 礻,巳.
    "rtk2993": {"character": "祀", "keyword": "enshrine",
                "expected_part_ids": {"kangxi113", "rtk2200"}},
    # 匚/巨 redundancy (2026-09-01, flagged alongside the 己/已/巳 review): 拒
    # and 距 both listed 匚 alongside 巨, but cjkvi-ids gives 拒=⿰扌巨 and
    # 距=⿰𧾷巨 -- no 匚 in either. Render confirmed 拒/距's right side matches
    # 巨 exactly with no separate box shape. 距 also re-listed 足's own parts
    # (口,止) instead of referencing 足 (rtk1372, already taught as 口+止) as
    # a whole compound -- fixed to reference it directly.
    "rtk921": {"character": "拒", "keyword": "repel",
               "expected_part_ids": {"kangxi64", "rtk920"}},
    "rtk1375": {"character": "距", "keyword": "long-distance",
                "expected_part_ids": {"rtk1372", "rtk920"}},
    # Owner-reported batch (2026-09-01), all the same redundant-flattening
    # pattern audit_flattening.py's contiguous-run check *should* have
    # caught but didn't -- each compound's own parts were present but not
    # adjacent (something sitting in between), which the detector's
    # deliberately strict contiguity requirement misses. Confirmed via
    # cjkvi-ids + render before fixing, per usual.
    # 格 was 口,木,夂 -- 各(each, rtk311)'s own parts are 口,夂, with 木
    # sitting between them, so never adjacent. cjkvi-ids: 格 = ⿰木各.
    "rtk312": {"character": "格", "keyword": "status",
               "expected_part_ids": {"rtk207", "rtk311"}},
    # 燥 was 火,口,木,品 -- the 口 duplicated what 品(goods, rtk23, itself
    # already just 口) already covers; cjkvi-ids: 燥 = ⿰火喿, 喿 = 品+木
    # (喿 itself not independently taught, flattened one level).
    "rtk228": {"character": "燥", "keyword": "parch",
               "expected_part_ids": {"rtk173", "rtk23", "rtk207"}},
    # 礎 was 口,石,疋,木 -- a stray 口 plus an incomplete 木 standing in for
    # 林(grove, rtk208, itself 木+木). cjkvi-ids: 礎 = ⿰石楚, 楚 = 林+疋
    # (楚 not independently taught, flattened one level; 疋="critters",
    # rtk2238).
    "rtk421": {"character": "礎", "keyword": "cornerstone",
               "expected_part_ids": {"rtk118", "rtk208", "rtk2238"}},
    # 磨 was 口,石,木,广,麻 -- listed 麻(hemp, rtk637) *and* its own already-
    # flattened parts (木,广) side by side, plus a stray 口. cjkvi-ids:
    # 磨 = ⿸麻石, cleanly referencing 麻 as a whole compound.
    "rtk638": {"character": "磨", "keyword": "grind",
               "expected_part_ids": {"rtk637", "rtk118"}},
    # Large systematic batch (2026-09-01), triggered by an owner bug report on
    # 5 kanji (椅/格/燥/礎/磨, pinned above) that all shared one root cause:
    # audit_flattening.py's contiguous-run check missed cases where a
    # compound's own parts are present in order but NOT adjacent (something
    # else sits between them). Wrote audit_flattening_subsequence.py to catch
    # this class specifically, CSV-cross-checked its output (222 candidates),
    # and applied 206 of them after spot-rendering a diverse sample. Iterated
    # the detector two more rounds after applying the batch to catch second-
    # order matches the first pass could only partially collapse (e.g. 苛/阿
    # both partially matched 丁 first, then fully matched 可=丁+口 once 丁 was
    # a literal token; 柄 similarly converged to 丙 after an intermediate 内
    # step; 陳 was a fresh find in the same pass, not previously flattened).
    # See docs/2026-08-search-quality-audit.md for the full methodology and
    # candidate list.
    "rtk31": {"character": "胆", "keyword": "gall bladder",
                "expected_part_ids": {"rtk13", "rtk30"}},
    "rtk42": {"character": "升", "keyword": "measuring box",
                "expected_part_ids": {"kangxi55", "rtk40"}},
    "rtk43": {"character": "昇", "keyword": "rise up",
                "expected_part_ids": {"rtk12", "rtk42"}},
    "rtk79": {"character": "真", "keyword": "true",
                "expected_part_ids": {"rtk10", "rtk78"}},
    "rtk84": {"character": "賄", "keyword": "bribe",
                "expected_part_ids": {"rtk56", "rtk83"}},
    "rtk130": {"character": "妙", "keyword": "exquisite",
                "expected_part_ids": {"rtk102", "rtk111"}},
    "rtk133": {"character": "奇", "keyword": "strange",
                "expected_part_ids": {"rtk112", "rtk97"}},
    "rtk133": {"character": "奇", "keyword": "strange",
                "expected_part_ids": {"rtk112", "rtk97"}},
    "rtk145": {"character": "沼", "keyword": "marsh",
                "expected_part_ids": {"rtk137", "rtk90"}},
    "rtk146": {"character": "沖", "keyword": "open sea",
                "expected_part_ids": {"rtk137", "rtk39"}},
    "rtk151": {"character": "沙", "keyword": "grains of sand",
                "expected_part_ids": {"rtk111", "rtk137"}},
    "rtk152": {"character": "潮", "keyword": "tide",
                "expected_part_ids": {"rtk13", "rtk137", "rtk26"}},
    "rtk155": {"character": "消", "keyword": "extinguish",
                "expected_part_ids": {"rtk119", "rtk137"}},
    "rtk156": {"character": "況", "keyword": "but of course",
                "expected_part_ids": {"rtk107", "rtk137"}},
    "rtk203": {"character": "宴", "keyword": "banquet",
                "expected_part_ids": {"rtk12", "rtk202"}},
    "rtk206": {"character": "貯", "keyword": "savings",
                "expected_part_ids": {"kangxi40", "rtk56", "rtk95"}},
    "rtk227": {"character": "案", "keyword": "plan",
                "expected_part_ids": {"rtk202", "rtk207"}},
    "rtk240": {"character": "苛", "keyword": "bullying",
                "expected_part_ids": {"prim-mugwort", "rtk97"}},
    "rtk240": {"character": "苛", "keyword": "bullying",
                "expected_part_ids": {"prim-mugwort", "rtk97"}},
    "rtk242": {"character": "薄", "keyword": "dilute",
                "expected_part_ids": {"kangxi3", "prim-mugwort", "rtk137", "rtk47"}},
    "rtk264": {"character": "洗", "keyword": "wash",
                "expected_part_ids": {"rtk137", "rtk263"}},
    "rtk270": {"character": "塔", "keyword": "pagoda",
                "expected_part_ids": {"prim-mugwort", "rtk161", "rtk269"}},
    "rtk273": {"character": "宝", "keyword": "treasure",
                "expected_part_ids": {"kangxi40", "rtk272"}},
    "rtk285": {"character": "注", "keyword": "pour",
                "expected_part_ids": {"rtk137", "rtk272"}},
    "rtk286": {"character": "柱", "keyword": "pillar",
                "expected_part_ids": {"rtk207", "rtk272"}},
    "rtk288": {"character": "銑", "keyword": "pig iron",
                "expected_part_ids": {"rtk263", "rtk287"}},
    "rtk289": {"character": "鉢", "keyword": "bowl",
                "expected_part_ids": {"rtk224", "rtk287"}},
    "rtk314": {"character": "略", "keyword": "abbreviation",
                "expected_part_ids": {"rtk14", "rtk311"}},
    "rtk316": {"character": "額", "keyword": "forehead",
                "expected_part_ids": {"kangxi40", "rtk311", "rtk64"}},
    "rtk324": {"character": "輝", "keyword": "radiance",
                "expected_part_ids": {"kangxi10", "rtk1", "rtk196", "rtk323"}},
    "rtk331": {"character": "塾", "keyword": "cram school",
                "expected_part_ids": {"kangxi3", "rtk161", "rtk330", "rtk9"}},
    "rtk336": {"character": "景", "keyword": "scenery",
                "expected_part_ids": {"rtk12", "rtk334"}},
    "rtk340": {"character": "週", "keyword": "week",
                "expected_part_ids": {"rtk339", "rtk843"}},
    "rtk397": {"character": "歩", "keyword": "walk",
                "expected_part_ids": {"rtk111", "rtk396"}},
    "rtk398": {"character": "渉", "keyword": "ford",
                "expected_part_ids": {"rtk137", "rtk397"}},
    "rtk399": {"character": "頻", "keyword": "repeatedly",
                "expected_part_ids": {"rtk397", "rtk64"}},
    "rtk406": {"character": "証", "keyword": "evidence",
                "expected_part_ids": {"rtk357", "rtk405"}},
    "rtk411": {"character": "超", "keyword": "transcend",
                "expected_part_ids": {"rtk161", "rtk410", "rtk90"}},
    "rtk441": {"character": "柿", "keyword": "persimmon",
                "expected_part_ids": {"kangxi13", "prim-pipe", "rtk207", "rtk440"}},
    "rtk442": {"character": "姉", "keyword": "elder sister",
                "expected_part_ids": {"rtk102", "rtk440"}},
    "rtk443": {"character": "肺", "keyword": "lungs",
                "expected_part_ids": {"rtk13", "rtk440"}},
    "rtk465": {"character": "競", "keyword": "vie",
                "expected_part_ids": {"rtk107", "rtk462"}},
    "rtk498": {"character": "敏", "keyword": "cleverness",
                "expected_part_ids": {"kangxi66", "rtk497"}},
    "rtk499": {"character": "梅", "keyword": "plum",
                "expected_part_ids": {"rtk207", "rtk497"}},
    "rtk508": {"character": "歌", "keyword": "song",
                "expected_part_ids": {"rtk11", "rtk505", "rtk95"}},
    "rtk513": {"character": "姿", "keyword": "figure",
                "expected_part_ids": {"rtk102", "rtk510"}},
    "rtk514": {"character": "諮", "keyword": "consult with",
                "expected_part_ids": {"rtk11", "rtk357", "rtk510"}},
    "rtk537": {"character": "脱", "keyword": "undress",
                "expected_part_ids": {"kangxi12", "rtk107", "rtk13"}},
    "rtk538": {"character": "説", "keyword": "explanation",
                "expected_part_ids": {"kangxi12", "rtk107", "rtk357"}},
    "rtk539": {"character": "鋭", "keyword": "pointed",
                "expected_part_ids": {"kangxi12", "prim-umbrella", "rtk107", "rtk287"}},
    "rtk541": {"character": "増", "keyword": "increase",
                "expected_part_ids": {"rtk161", "rtk540"}},
    "rtk550": {"character": "賓", "keyword": "v.i.p.",
                "expected_part_ids": {"kangxi40", "rtk1", "rtk111", "rtk56"}},
    "rtk562": {"character": "蚕", "keyword": "silkworm",
                "expected_part_ids": {"rtk457", "rtk556"}},
    "rtk611": {"character": "許", "keyword": "permit",
                "expected_part_ids": {"rtk357", "rtk610"}},
    "rtk624": {"character": "国", "keyword": "country",
                "expected_part_ids": {"kangxi31", "rtk272"}},
    "rtk631": {"character": "壇", "keyword": "podium",
                "expected_part_ids": {"kangxi31", "kangxi8", "rtk11", "rtk161", "rtk30"}},
    "rtk655": {"character": "臆", "keyword": "cowardice",
                "expected_part_ids": {"rtk13", "rtk654"}},
    "rtk666": {"character": "悦", "keyword": "ecstasy",
                "expected_part_ids": {"kangxi12", "kangxi61", "rtk107"}},
    "rtk671": {"character": "慌", "keyword": "disconcerted",
                "expected_part_ids": {"kangxi61", "rtk527"}},
    "rtk672": {"character": "悔", "keyword": "repent",
                "expected_part_ids": {"kangxi61", "prim-katakana-no", "rtk1", "rtk1023", "rtk497"}},
    "rtk676": {"character": "惰", "keyword": "lazy",
                "expected_part_ids": {"kangxi61", "rtk13", "rtk81"}},
    "rtk677": {"character": "慎", "keyword": "humility",
                "expected_part_ids": {"kangxi61", "rtk79"}},
    "rtk678": {"character": "憾", "keyword": "remorse",
                "expected_part_ids": {"kangxi61", "rtk662"}},
    "rtk679": {"character": "憶", "keyword": "recollection",
                "expected_part_ids": {"kangxi61", "rtk654"}},
    "rtk686": {"character": "泌", "keyword": "ooze",
                "expected_part_ids": {"kangxi3", "rtk137", "rtk685"}},
    "rtk698": {"character": "搭", "keyword": "board",
                "expected_part_ids": {"kangxi64", "prim-mugwort", "rtk269"}},
    "rtk714": {"character": "括", "keyword": "fasten",
                "expected_part_ids": {"kangxi64", "rtk11", "rtk40", "rtk41"}},
    "rtk720": {"character": "拾", "keyword": "pick up",
                "expected_part_ids": {"kangxi64", "rtk269"}},
    "rtk756": {"character": "護", "keyword": "safeguard",
                "expected_part_ids": {"prim-mugwort", "rtk357", "rtk755"}},
    "rtk759": {"character": "怒", "keyword": "angry",
                "expected_part_ids": {"rtk639", "rtk758"}},
    "rtk767": {"character": "殻", "keyword": "husk",
                "expected_part_ids": {"kangxi79", "rtk321", "rtk341", "rtk752"}},
    "rtk781": {"character": "板", "keyword": "plank",
                "expected_part_ids": {"rtk207", "rtk779"}},
    "rtk790": {"character": "奨", "keyword": "exhort",
                "expected_part_ids": {"rtk112", "rtk789"}},
    "rtk797": {"character": "曖", "keyword": "unclear",
                "expected_part_ids": {"rtk12", "rtk796"}},
    "rtk806": {"character": "怠", "keyword": "neglect",
                "expected_part_ids": {"rtk639", "rtk805"}},
    "rtk807": {"character": "治", "keyword": "reign",
                "expected_part_ids": {"rtk137", "rtk805"}},
    "rtk808": {"character": "冶", "keyword": "metallurgy",
                "expected_part_ids": {"kangxi15", "rtk805"}},
    "rtk809": {"character": "始", "keyword": "commence",
                "expected_part_ids": {"rtk102", "rtk805"}},
    "rtk831": {"character": "拙", "keyword": "bungling",
                "expected_part_ids": {"kangxi64", "rtk829"}},
    "rtk833": {"character": "炭", "keyword": "charcoal",
                "expected_part_ids": {"rtk180", "rtk830"}},
    "rtk835": {"character": "峠", "keyword": "mountain pass",
                "expected_part_ids": {"rtk51", "rtk830"}},
    "rtk837": {"character": "密", "keyword": "secrecy",
                "expected_part_ids": {"kangxi3", "kangxi40", "rtk685", "rtk830"}},
    "rtk848": {"character": "松", "keyword": "pine tree",
                "expected_part_ids": {"rtk207", "rtk847"}},
    "rtk849": {"character": "翁", "keyword": "venerable old man",
                "expected_part_ids": {"rtk615", "rtk847"}},
    "rtk854": {"character": "溶", "keyword": "melt",
                "expected_part_ids": {"rtk137", "rtk853"}},
    "rtk883": {"character": "趣", "keyword": "gist",
                "expected_part_ids": {"rtk161", "rtk410", "rtk882"}},
    "rtk884": {"character": "最", "keyword": "utmost",
                "expected_part_ids": {"rtk1", "rtk12", "rtk882"}},
    "rtk885": {"character": "撮", "keyword": "snapshot",
                "expected_part_ids": {"kangxi64", "rtk12", "rtk882"}},
    "rtk892": {"character": "慢", "keyword": "ridicule",
                "expected_part_ids": {"kangxi61", "rtk2240"}},
    "rtk897": {"character": "寧", "keyword": "rather",
                "expected_part_ids": {"kangxi40", "rtk1555", "rtk639", "rtk95"}},
    "rtk914": {"character": "臓", "keyword": "entrails",
                "expected_part_ids": {"rtk13", "rtk913"}},
    "rtk934": {"character": "架", "keyword": "erect",
                "expected_part_ids": {"rtk207", "rtk932"}},
    "rtk953": {"character": "懲", "keyword": "penal",
                "expected_part_ids": {"rtk639", "rtk952"}},
    "rtk960": {"character": "程", "keyword": "extent",
                "expected_part_ids": {"kangxi115", "rtk280"}},
    "rtk961": {"character": "税", "keyword": "tax",
                "expected_part_ids": {"kangxi115", "kangxi12", "rtk107"}},
    "rtk965": {"character": "秒", "keyword": "second",
                "expected_part_ids": {"kangxi115", "rtk111"}},
    # Corrected 2026-09-05 (results.jsonl PARTIAL mining): cjkvi-ids
    # confirms 秘 = ⿰禾必 exactly -- the extra "丶"(kangxi3) was
    # redundant with 必(rtk685)'s own structure.
    "rtk970": {"character": "秘", "keyword": "secret",
                "expected_part_ids": {"kangxi115", "rtk685"}},
    "rtk974": {"character": "穫", "keyword": "harvest",
                "expected_part_ids": {"kangxi115", "prim-mugwort", "rtk755"}},
    "rtk976": {"character": "稲", "keyword": "rice plant",
                "expected_part_ids": {"kangxi115", "rtk35", "rtk784"}},
    "rtk982": {"character": "誘", "keyword": "entice",
                "expected_part_ids": {"rtk357", "rtk980"}},
    "rtk989": {"character": "粘", "keyword": "sticky",
                "expected_part_ids": {"rtk49", "rtk987"}},
    "rtk991": {"character": "粧", "keyword": "cosmetics",
                "expected_part_ids": {"rtk2345", "rtk987"}},
    "rtk1005": {"character": "球", "keyword": "ball",
                "expected_part_ids": {"rtk137", "rtk272"}},
    "rtk1015": {"character": "筒", "keyword": "cylinder",
                "expected_part_ids": {"rtk1007", "rtk192"}},
    "rtk1016": {"character": "等", "keyword": "etc.",
                "expected_part_ids": {"rtk1007", "rtk170"}},
    "rtk1018": {"character": "答", "keyword": "solution",
                "expected_part_ids": {"rtk1007", "rtk269"}},
    "rtk1020": {"character": "簿", "keyword": "register",
                "expected_part_ids": {"kangxi3", "rtk1007", "rtk137", "rtk47"}},
    "rtk1088": {"character": "荷", "keyword": "baggage",
                "expected_part_ids": {"prim-mugwort", "rtk1087"}},
    "rtk1097": {"character": "柄", "keyword": "design",
                "expected_part_ids": {"rtk1096", "rtk207"}},
    "rtk1097": {"character": "柄", "keyword": "design",
                "expected_part_ids": {"rtk1096", "rtk207"}},
    "rtk1099": {"character": "腐", "keyword": "rot",
                "expected_part_ids": {"rtk1077", "rtk1098"}},
    "rtk1100": {"character": "座", "keyword": "sit",
                "expected_part_ids": {"prim-pipe", "rtk1023", "rtk2345"}},
    "rtk1110": {"character": "宮", "keyword": "shinto shrine",
                "expected_part_ids": {"kangxi40", "rtk24"}},
    "rtk1111": {"character": "営", "keyword": "occupation",
                "expected_part_ids": {"kangxi14", "rtk196", "rtk24"}},
    "rtk1113": {"character": "膳", "keyword": "dining tray",
                "expected_part_ids": {"rtk1112", "rtk13"}},
    "rtk1121": {"character": "喚", "keyword": "yell",
                "expected_part_ids": {"kangxi13", "kangxi20", "rtk112", "rtk4"}},
    "rtk1140": {"character": "屈", "keyword": "yield",
                "expected_part_ids": {"kangxi44", "rtk829"}},
    "rtk1141": {"character": "掘", "keyword": "dig",
                "expected_part_ids": {"kangxi64", "rtk1140"}},
    "rtk1142": {"character": "堀", "keyword": "ditch",
                "expected_part_ids": {"rtk1140", "rtk161"}},
    "rtk1163": {"character": "涙", "keyword": "tears",
                "expected_part_ids": {"rtk1162", "rtk137"}},
    "rtk1165": {"character": "顧", "keyword": "look back",
                "expected_part_ids": {"rtk1164", "rtk64"}},
    "rtk1177": {"character": "慰", "keyword": "consolation",
                "expected_part_ids": {"rtk1176", "rtk639"}},
    "rtk1185": {"character": "擦", "keyword": "grate",
                "expected_part_ids": {"kangxi64", "rtk1184"}},
    "rtk1212": {"character": "哲", "keyword": "philosophy",
                "expected_part_ids": {"rtk11", "rtk1211"}},
    "rtk1213": {"character": "逝", "keyword": "departed",
                "expected_part_ids": {"rtk1211", "rtk843"}},
    "rtk1214": {"character": "誓", "keyword": "vow",
                "expected_part_ids": {"rtk1211", "rtk357"}},
    "rtk1221": {"character": "訴", "keyword": "accusation",
                "expected_part_ids": {"rtk1220", "rtk357"}},
    "rtk1247": {"character": "群", "keyword": "flock",
                "expected_part_ids": {"rtk1246", "rtk586"}},
    "rtk1253": {"character": "満", "keyword": "full",
                "expected_part_ids": {"prim-mugwort", "rtk1252", "rtk137", "rtk2"}},
    "rtk1258": {"character": "遭", "keyword": "encounter",
                "expected_part_ids": {"rtk1", "rtk1256", "rtk843"}},
    "rtk1259": {"character": "漕", "keyword": "rowing",
                "expected_part_ids": {"rtk1", "rtk1256", "rtk137"}},
    "rtk1309": {"character": "智", "keyword": "wisdom",
                "expected_part_ids": {"rtk12", "rtk1308"}},
    "rtk1324": {"character": "溺", "keyword": "drowning",
                "expected_part_ids": {"rtk1323", "rtk137"}},
    "rtk1364": {"character": "棺", "keyword": "coffin",
                "expected_part_ids": {"rtk1363", "rtk207"}},
    "rtk1365": {"character": "管", "keyword": "pipe",
                "expected_part_ids": {"rtk1007", "rtk1363"}},
    "rtk1369": {"character": "効", "keyword": "merit",
                "expected_part_ids": {"rtk1368", "rtk922"}},
    "rtk1371": {"character": "校", "keyword": "exam",
                "expected_part_ids": {"rtk1368", "rtk207"}},
    "rtk1376": {"character": "路", "keyword": "path",
                "expected_part_ids": {"rtk1372", "rtk311"}},
    "rtk1391": {"character": "阿", "keyword": "africa",
                "expected_part_ids": {"kangxi170", "rtk97"}},
    "rtk1391": {"character": "阿", "keyword": "africa",
                "expected_part_ids": {"kangxi170", "rtk97"}},
    "rtk1398": {"character": "陳", "keyword": "line up",
                "expected_part_ids": {"kangxi170", "rtk543"}},
    "rtk1401": {"character": "院", "keyword": "inst.",
                "expected_part_ids": {"kangxi10", "kangxi170", "rtk199", "rtk2"}},
    "rtk1419": {"character": "窃", "keyword": "stealth",
                "expected_part_ids": {"rtk1413", "rtk89"}},
    "rtk1433": {"character": "繕", "keyword": "darning",
                "expected_part_ids": {"rtk1112", "rtk1431"}},
    "rtk1443": {"character": "練", "keyword": "practice",
                "expected_part_ids": {"prim-katakana-ha", "prim-pipe", "rtk14", "rtk1431", "rtk543"}},
    "rtk1445": {"character": "続", "keyword": "continue",
                "expected_part_ids": {"rtk1431", "rtk345"}},
    "rtk1449": {"character": "給", "keyword": "salary",
                "expected_part_ids": {"rtk1431", "rtk269"}},
    "rtk1450": {"character": "絡", "keyword": "entwine",
                "expected_part_ids": {"rtk1431", "rtk311"}},
    "rtk1459": {"character": "紹", "keyword": "introduce",
                "expected_part_ids": {"rtk1431", "rtk90"}},
    "rtk1475": {"character": "紫", "keyword": "purple",
                "expected_part_ids": {"rtk1431", "rtk2201"}},
    "rtk1494": {"character": "孫", "keyword": "grandchild",
                "expected_part_ids": {"rtk1492", "rtk99"}},
    "rtk1496": {"character": "遜", "keyword": "modest",
                "expected_part_ids": {"rtk1494", "rtk843"}},
    "rtk1497": {"character": "却", "keyword": "instead",
                "expected_part_ids": {"kangxi26", "rtk812"}},
    "rtk1502": {"character": "命", "keyword": "fate",
                "expected_part_ids": {"kangxi26", "rtk269"}},
    "rtk1505": {"character": "齢", "keyword": "age",
                "expected_part_ids": {"kangxi17", "rtk1255", "rtk1503", "rtk396", "rtk987"}},
    "rtk1506": {"character": "冷", "keyword": "cool",
                "expected_part_ids": {"kangxi15", "rtk1503"}},
    "rtk1514": {"character": "擬", "keyword": "mimic",
                "expected_part_ids": {"kangxi64", "rtk1513"}},
    "rtk1533": {"character": "興", "keyword": "entertain",
                "expected_part_ids": {"prim-katakana-ha", "rtk1531", "rtk192"}},
    "rtk1538": {"character": "酵", "keyword": "fermentation",
                "expected_part_ids": {"rtk1342", "rtk1534"}},
    "rtk1540": {"character": "酬", "keyword": "repay",
                "expected_part_ids": {"prim-pipe", "rtk135", "rtk1534"}},
    "rtk1541": {"character": "酪", "keyword": "dairy products",
                "expected_part_ids": {"rtk1534", "rtk311"}},
    "rtk1559": {"character": "盗", "keyword": "steal",
                "expected_part_ids": {"rtk1555", "rtk510"}},
    "rtk1563": {"character": "濫", "keyword": "overflow",
                "expected_part_ids": {"prim-katakana-no", "rtk137", "rtk1562"}},
    "rtk1567": {"character": "盛", "keyword": "boom",
                "expected_part_ids": {"rtk1555", "rtk386"}},
    "rtk1574": {"character": "節", "keyword": "node",
                "expected_part_ids": {"rtk1007", "rtk1572"}},
    "rtk1589": {"character": "館", "keyword": "bldg.",
                "expected_part_ids": {"rtk1363", "rtk1582"}},
    # Corrected 2026-09-04 (owner-reported "stone, mouth" search bug --
    # see the big pin block below): the redundant "口"(rtk11) this pin was
    # keying off of is exactly the bug — 石(rtk118) already contains its
    # own 口 recursively, and 碑's real cjkvi-ids structure (⿰石卑) has no
    # separate mouth stroke.
    "rtk1630": {"character": "碑", "keyword": "tombstone",
                "expected_part_ids": {"rtk118", "rtk1629"}},
    "rtk1638": {"character": "核", "keyword": "nucleus",
                "expected_part_ids": {"rtk1637", "rtk207"}},
    "rtk1641": {"character": "骸", "keyword": "remains",
                "expected_part_ids": {"kangxi13", "kangxi14", "rtk13", "rtk1383", "rtk1637"}},
    "rtk1642": {"character": "劾", "keyword": "censure",
                "expected_part_ids": {"rtk1637", "rtk922"}},
    "rtk1662": {"character": "績", "keyword": "exploits",
                "expected_part_ids": {"rtk1431", "rtk1661"}},
    "rtk1665": {"character": "漬", "keyword": "pickling",
                "expected_part_ids": {"rtk137", "rtk1661"}},
    "rtk1672": {"character": "轄", "keyword": "control",
                "expected_part_ids": {"rtk1671", "rtk304"}},
    "rtk1677": {"character": "醒", "keyword": "awakening",
                "expected_part_ids": {"rtk1534", "rtk1676"}},
    "rtk1691": {"character": "椿", "keyword": "camellia",
                "expected_part_ids": {"rtk1690", "rtk207"}},
    "rtk1693": {"character": "奏", "keyword": "play music",
                "expected_part_ids": {"kangxi115", "rtk1023", "rtk457"}},
    "rtk1718": {"character": "陰", "keyword": "shade",
                "expected_part_ids": {"kangxi170", "kangxi28", "rtk1711", "rtk2"}},
    "rtk1745": {"character": "閲", "keyword": "review",
                "expected_part_ids": {"kangxi12", "rtk107", "rtk1743"}},
    "rtk1752": {"character": "閣", "keyword": "tower",
                "expected_part_ids": {"rtk1743", "rtk311"}},
    "rtk1799": {"character": "速", "keyword": "quick",
                "expected_part_ids": {"rtk1793", "rtk843"}},
    "rtk1800": {"character": "整", "keyword": "organize",
                "expected_part_ids": {"kangxi66", "rtk1793", "rtk405"}},
    # Was 合,人 (人 not 亻, and 合/"fit" is a wrong reference -- render-confirmed
    # the right side is the same 僉 shape as 剣/険, not 合-shaped) -- 2026-09-05
    "rtk1804": {"character": "倹", "keyword": "frugal",
                "expected_part_ids": {"kangxi9", "rtk11", "rtk1023", "prim-umbrella"}},
    "rtk1857": {"character": "惨", "keyword": "wretched",
                "expected_part_ids": {"kangxi61", "rtk1856"}},
    "rtk1897": {"character": "謀", "keyword": "conspire",
                "expected_part_ids": {"rtk1896", "rtk357"}},
    "rtk1898": {"character": "媒", "keyword": "mediator",
                "expected_part_ids": {"rtk102", "rtk1896"}},
    "rtk1908": {"character": "貴", "keyword": "precious",
                "expected_part_ids": {"rtk1", "rtk39", "rtk56"}},
    "rtk1910": {"character": "遣", "keyword": "dispatch",
                "expected_part_ids": {"rtk1", "rtk39", "rtk843"}},
    "rtk1937": {"character": "翼", "keyword": "wing",
                "expected_part_ids": {"prim-pipe", "rtk1936", "rtk2", "rtk615"}},
    "rtk1972": {"character": "婚", "keyword": "marriage",
                "expected_part_ids": {"rtk102", "rtk2526"}},
    "rtk1977": {"character": "眠", "keyword": "sleep",
                "expected_part_ids": {"rtk15", "rtk1976"}},
    "rtk1982": {"character": "舗", "keyword": "shop",
                "expected_part_ids": {"kangxi3", "rtk10", "rtk1265", "rtk338"}},
    "rtk1986": {"character": "郡", "keyword": "county",
                "expected_part_ids": {"rtk1246", "rtk1991"}},
    "rtk1987": {"character": "郊", "keyword": "outskirts",
                "expected_part_ids": {"rtk1368", "rtk1991"}},
    "rtk1989": {"character": "都", "keyword": "metropolis",
                "expected_part_ids": {"rtk1345", "rtk1991"}},
    "rtk2018": {"character": "搬", "keyword": "conveyor",
                "expected_part_ids": {"kangxi64", "rtk2016"}},
    "rtk2020": {"character": "艦", "keyword": "warship",
                "expected_part_ids": {"rtk1562", "rtk2012"}},
    "rtk2047": {"character": "娯", "keyword": "recreation",
                "expected_part_ids": {"rtk102", "rtk2046"}},
    "rtk2086": {"character": "厳", "keyword": "stern",
                "expected_part_ids": {"kangxi27", "rtk196", "rtk889"}},
    "rtk2099": {"character": "暖", "keyword": "warmth",
                "expected_part_ids": {"rtk12", "rtk760", "rtk784"}},
    "rtk2101": {"character": "援", "keyword": "abet",
                "expected_part_ids": {"kangxi64", "rtk760", "rtk784"}},
    "rtk2110": {"character": "塑", "keyword": "model",
                "expected_part_ids": {"rtk161", "rtk2862"}},
    "rtk2111": {"character": "遡", "keyword": "go upstream",
                "expected_part_ids": {"rtk2862", "rtk843"}},
    "rtk2121": {"character": "就", "keyword": "concerning",
                "expected_part_ids": {"kangxi3", "kangxi43", "rtk2232", "rtk334"}},
    "rtk2122": {"character": "蹴", "keyword": "kick",
                "expected_part_ids": {"rtk1372", "rtk2121"}},
    "rtk2133": {"character": "駒", "keyword": "pony",
                "expected_part_ids": {"prim-fire-radical", "rtk2132", "rtk69"}},
    "rtk2136": {"character": "駐", "keyword": "parking",
                "expected_part_ids": {"prim-fire-radical", "rtk2132", "rtk272"}},
    "rtk2140": {"character": "駄", "keyword": "burdensome",
                "expected_part_ids": {"prim-fire-radical", "rtk126", "rtk2132"}},
    "rtk2161": {"character": "態", "keyword": "attitude",
                "expected_part_ids": {"rtk2160", "rtk639"}},
    # Corrected 2026-09-01 (common-primitive audit): further converged now
    # that 辰(rtk2164) itself is fixed -- cjkvi-ids: 農 = 曲+辰 exactly.
    "rtk2170": {"character": "農", "keyword": "agriculture",
                "expected_part_ids": {"rtk1256", "rtk2164"}},
    "rtk2171": {"character": "濃", "keyword": "concentrated",
                "expected_part_ids": {"rtk137", "rtk2170"}},
    "rtk2194": {"character": "璽", "keyword": "imperial seal",
                "expected_part_ids": {"rtk271", "rtk2867"}},
    # 口("mouth") audit (2026-09-01, owner-requested): checked every kanji
    # currently listing rtk11(口) as a part against cjkvi-ids's real,
    # recursively-expanded structure -- 40 candidates where 口 doesn't appear
    # anywhere in the real glyph at all. Most turned out to be legitimate
    # (谷/事/豆/亜/民/革/束/史 are all CSV-confirmed Heisig mnemonics for an
    # otherwise Unicode-atomic glyph, the same pattern as 東=日+木 elsewhere in
    # this dataset) -- only fixed the ones with no CSV support at all, plus
    # two clusters that shared one missing primitive: 𠂤("maestro", CSV-
    # confirmed across 追/阜/師/帥/官) and the already-existing 束("bundle")
    # compound, both of which several hosts had approximated with a spurious
    # 口/｜ instead of ever having a real primitive/compound reference. 壷
    # deliberately left unfixed -- genuinely ambiguous at render resolution,
    # not worth guessing on one rare kanji.
    "rtk4": {"character": "四", "keyword": "four",
                "expected_part_ids": {"kangxi10", "kangxi31"}},
    "rtk1065": {"character": "使", "keyword": "use",
                "expected_part_ids": {"kangxi9", "rtk748"}},
    "rtk1359": {"character": "追", "keyword": "chase",
                "expected_part_ids": {"prim-maestro", "rtk843"}},
    "rtk1361": {"character": "師", "keyword": "expert",
                "expected_part_ids": {"prim-maestro", "prim-noren"}},
    "rtk1362": {"character": "帥", "keyword": "commander",
                "expected_part_ids": {"prim-maestro", "rtk432"}},
    "rtk1363": {"character": "官", "keyword": "bureaucrat",
                "expected_part_ids": {"kangxi40", "prim-maestro"}},
    "rtk1794": {"character": "頼", "keyword": "trust",
                "expected_part_ids": {"rtk1793", "rtk64"}},
    "rtk1795": {"character": "瀬", "keyword": "rapids",
                "expected_part_ids": {"rtk137", "rtk1794"}},
    "rtk1796": {"character": "勅", "keyword": "imperial order",
                "expected_part_ids": {"rtk1793", "rtk922"}},
    "rtk1797": {"character": "疎", "keyword": "alienate",
                "expected_part_ids": {"rtk1793", "rtk2238"}},
    "rtk1798": {"character": "辣", "keyword": "bitter",
                "expected_part_ids": {"rtk1612", "rtk1793"}},
    "rtk1800": {"character": "整", "keyword": "organize",
                "expected_part_ids": {"kangxi66", "rtk1793", "rtk405"}},
    "rtk2126": {"character": "免", "keyword": "excuse",
                "expected_part_ids": {"kangxi10", "kangxi20", "prim-pipe", "rtk1"}},
    "rtk2130": {"character": "象", "keyword": "elephant",
                "expected_part_ids": {"kangxi152", "kangxi20", "rtk1"}},
    "rtk2131": {"character": "像", "keyword": "statue",
                "expected_part_ids": {"kangxi9", "rtk2130"}},
    "rtk2235": {"character": "兎", "keyword": "rabbit",
                "expected_part_ids": {"kangxi10", "kangxi3", "prim-katakana-no", "prim-pipe"}},
    "rtk2304": {"character": "埠", "keyword": "wharf",
                "expected_part_ids": {"rtk1360", "rtk161"}},
    "rtk2385": {"character": "漱", "keyword": "gargle",
                "expected_part_ids": {"rtk137", "rtk1793", "rtk505"}},
    "rtk2433": {"character": "獅", "keyword": "lion",
                "expected_part_ids": {"kangxi94", "rtk1361"}},
    "rtk2490": {"character": "菅", "keyword": "sedge",
                "expected_part_ids": {"prim-mugwort", "rtk1363"}},
    "rtk2543": {"character": "槌", "keyword": "wooden hammer",
                "expected_part_ids": {"rtk1359", "rtk207"}},
    "rtk2728": {"character": "蝦", "keyword": "shrimp",
                "expected_part_ids": {"rtk556", "rtk752"}},
    "rtk2791": {"character": "鎚", "keyword": "hammer",
                "expected_part_ids": {"rtk1359", "rtk287"}},
    # 羽("feathers") owner-reported (2026-09-01): 羽 itself was wrongly defined
    # with kangxi15("ice", 冫) as its own part -- cjkvi-ids confirms 羽 = 习+习
    # (two mirrored strokes), no ice anywhere; render confirms too. That one
    # bug had been copy-pasted as a literal extra token into all 13 kanji
    # using 羽 as a part, since each host's own data.txt line listed 冫
    # explicitly rather than just referencing 羽. Fixed 羽 to atomic and
    # removed the redundant 冫 from every host.
    "rtk616": {"character": "習", "keyword": "learn",
               "expected_part_ids": {"rtk37", "rtk615"}},
    "rtk617": {"character": "翌", "keyword": "the following",
               "expected_part_ids": {"rtk462", "rtk615"}},
    "rtk1160": {"character": "扇", "keyword": "fan",
               "expected_part_ids": {"rtk1157", "rtk615"}},
    "rtk2060": {"character": "翻", "keyword": "flip",
               "expected_part_ids": {"kangxi165", "rtk14", "rtk615", "rtk987"}},
    "rtk2371": {"character": "摺", "keyword": "rubbing",
               "expected_part_ids": {"kangxi64", "rtk37", "rtk615"}},
    "rtk2599": {"character": "煽", "keyword": "fanning",
               "expected_part_ids": {"rtk1160", "rtk173"}},
    "rtk2752": {"character": "謬", "keyword": "fallible",
               "expected_part_ids": {"kangxi59", "prim-umbrella", "rtk357", "rtk615"}},
    "rtk2801": {"character": "翰", "keyword": "quill",
               "expected_part_ids": {"prim-umbrella", "rtk10", "rtk12", "rtk615"}},
    "rtk2876": {"character": "翠", "keyword": "jade green",
               "expected_part_ids": {"kangxi8", "rtk10", "rtk1023", "rtk615"}},
    "rtk2908": {"character": "翫", "keyword": "fiddle with",
               "expected_part_ids": {"kangxi10", "rtk37", "rtk615", "rtk63"}},
    "rtk2940": {"character": "翔", "keyword": "soar",
               "expected_part_ids": {"rtk586", "rtk615"}},
    # Common-primitive audit (2026-09-01, daily check-in): systematically
    # checked every primitive used >=5 times as a part against CSV/cjkvi-ids,
    # the same methodology that caught 羽 above, applied proactively rather
    # than waiting for another owner report. Two more clusters found:
    # 邦("home country") was ノ,二 -- doesn't match CSV's "bushes; city walls"
    # at all; cjkvi-ids: 邦 = 丰+阝. Added prim-bushes (丰, IDS-atomic, not a
    # taught frame). 辰("sign of the dragon") was 衣,厂 -- 衣("clothing") has
    # no connection to the glyph (render confirmed); cjkvi-ids's real
    # structure is fine-stroke-level with no clean citable primitive for the
    # remainder, so fixed to what's confirmed correct (厂,二) and stopped
    # there rather than invent a shaky primitive for the last stroke detail.
    # That wrong 衣 had been redundantly copy-pasted into all 9 hosts
    # alongside a correct reference to 辰 itself -- dropped 衣 (and 厂, also
    # redundant once 辰 is referenced directly) from all of them.
    "rtk1991": {"character": "邦", "keyword": "home country",
               "expected_part_ids": {"kangxi170", "prim-bushes"}},
    "rtk2164": {"character": "辰", "keyword": "sign of the dragon",
               "expected_part_ids": {"kangxi27", "rtk2"}},
    "rtk2165": {"character": "辱", "keyword": "embarrass",
               "expected_part_ids": {"rtk2164", "rtk45"}},
    "rtk2166": {"character": "震", "keyword": "quake",
               "expected_part_ids": {"rtk2164", "rtk451"}},
    "rtk2167": {"character": "振", "keyword": "shake",
               "expected_part_ids": {"kangxi64", "rtk2164"}},
    "rtk2168": {"character": "娠", "keyword": "with child",
               "expected_part_ids": {"rtk102", "rtk2164"}},
    "rtk2169": {"character": "唇", "keyword": "lips",
               "expected_part_ids": {"rtk11", "rtk2164"}},
    "rtk2520": {"character": "晨", "keyword": "morrow",
               "expected_part_ids": {"rtk12", "rtk2164"}},
    "rtk2528": {"character": "膿", "keyword": "pus",
               "expected_part_ids": {"prim-pipe", "rtk1", "rtk12", "rtk13", "rtk2164"}},
    "rtk2767": {"character": "賑", "keyword": "bustling",
               "expected_part_ids": {"rtk2164", "rtk56"}},
    # Same audit, same session: 尚(rtk196, "esteem") used 49x as a component --
    # was missing a real component entirely (口,冂 only). cjkvi-ids: 尚 =
    # small-variant + 冂 + 口 (尚 = ⿱⺌冋, 冋 = ⿵冂口). Render-confirmed 尚's
    # top two strokes match 小's top portion closely enough to reuse 小
    # directly (same pragmatic-approximation precedent as 个 for "person").
    # The "small" alias had been pointing at an orphaned rad3.13:?  row
    # instead of rtk110 -- same orphaned-placeholder bug class as rad1.1/
    # rad2.8/rad4.17 fixed earlier in this audit. Retargeted "small" to
    # rtk110 and deleted the orphan.
    "rtk196": {"character": "尚", "keyword": "esteem",
               "expected_part_ids": {"kangxi13", "rtk11", "rtk110"}},
    # Continuing the common-primitive audit (2026-09-02, interactive
    # follow-up): 天(rtk457, "heavens") itself had a stray "二"("two") that
    # doesn't appear anywhere in cjkvi-ids's ⿱一大 or the render -- 天 is
    # just 一+大. That in turn revealed 矢(rtk1305, "dart") was flattening
    # 天's own (now-corrected) parts instead of referencing 天 directly --
    # CSV's components for 矢 are exactly "drop; heavens", and a render
    # comparison confirms 矢 = ノ("drop", the extra stroke) sitting on 天.
    "rtk457": {"character": "天", "keyword": "heavens",
               "expected_part_ids": {"rtk1", "rtk112"}},
    "rtk1305": {"character": "矢", "keyword": "dart",
                "expected_part_ids": {"prim-katakana-no", "rtk457"}},
    # Separately, found the same "个 has an extra stroke the real shape
    # doesn't have" anti-pattern documented elsewhere in this project
    # (CLAUDE.md's own 个/"umbrella" case) recurring for a *different*
    # shape: 个 (umbrella, cjkvi-ids ⿱人丨, WITH a vertical stroke through
    # the roof) had been used as a stand-in for 亼 ("meeting", cjkvi-ids
    # ⿱人一, no vertical stroke -- just a roof over a floor-line) in every
    # kanji where CSV's components column names "meeting" as a distinct,
    # real component: 合, 令 (already fixed above), 今, 倉. Render-confirmed
    # (合/命's peaks lack the umbrella's vertical descender) and added
    # prim-meeting (亼, IDS-atomic, not a taught RTK frame, referenced by
    # its own character like every other prim-* per convention -- not by
    # its id string, an early mistake in this same edit caught before
    # commit). Left 余 alone even though cjkvi-ids also shows 亼 there --
    # its own CSV components list "umbrella", not "meeting", unlike the
    # other four, so there isn't the same clear signal Heisig taught it
    # via the same primitive there. Also left 会/金/介/全/傘/舎/禽 alone --
    # their cjkvi-ids tops are plain 人 (person), a separate, lower-
    # confidence question not examined closely enough this session to act
    # on. 命(rtk1502) needed no direct edit -- it already referenced 合
    # itself rather than flattening, so the fix cascades automatically.
    "rtk269": {"character": "合", "keyword": "fit",
               "expected_part_ids": {"rtk11", "prim-meeting"}},
    "rtk1503": {"character": "令", "keyword": "orders",
                "expected_part_ids": {"prim-meeting", "kangxi26"}},
    "rtk1711": {"character": "今", "keyword": "now",
                "expected_part_ids": {"prim-meeting", "rtk1"}},
    "rtk1758": {"character": "倉", "keyword": "godown",
                "expected_part_ids": {"prim-katakana-no", "rtk11", "prim-meeting", "kangxi44", "rtk1"}},
    # Re-running audit_flattening.py after the 天 fix above surfaced 3 more
    # hosts sharing 天's exact old bug signature (a stray "二" alongside
    # "一,大") -- the classic iterative-convergence pattern: fixing one
    # compound reveals identical bugs elsewhere that were previously
    # indistinguishable from noise. 夫(rtk901, "husband") itself was 人,二,
    # 大,亠 -- none of which except 大 has any visual relation to the glyph;
    # CSV/cjkvi-ids agree it's exactly "one; large" (一,大), rendering
    # confirms it's 大 with one extra stroke on top, same shape family as
    # 天. That cascaded to two more: 漢("Sino-", CSV names "husband" as a
    # real component, was flattening 夫's old wrong parts) and, one level
    # deeper, 規(rtk904, "standard", cjkvi-ids ⿰夫見, CSV "husband; see")
    # which was 見,土,人,二,大 -- fixed to 夫,見 -- which in turn fixed
    # 窺("peep", cjkvi-ids ⿱穴規) which was flattening 規's old wrong parts
    # under a 9-token pile. 央(rtk1877, "center") was a separate render-only
    # finding (cjkvi-ids has no decomposition for it at all, so no CSV/IDS
    # component list to cross-check): was ノ,一,大,冖 but a render comparison
    # against 大/冖 alone shows only two real visual chunks -- a box (冖)
    # over 大 -- with no room for the extra ノ/一 strokes.
    "rtk901": {"character": "夫", "keyword": "husband",
               "expected_part_ids": {"rtk1", "rtk112"}},
    "rtk904": {"character": "規", "keyword": "standard",
               "expected_part_ids": {"rtk901", "rtk61"}},
    "rtk1701": {"character": "漢", "keyword": "sino-",
                "expected_part_ids": {"rtk137", "prim-mugwort", "rtk11", "rtk901"}},
    "rtk1877": {"character": "央", "keyword": "center",
                "expected_part_ids": {"kangxi14", "rtk112"}},
    "rtk2659": {"character": "窺", "keyword": "lie in wait",
                "expected_part_ids": {"rtk1413", "rtk904"}},
    # Same daily check-in (2026-09-03), picking up last session's flagged
    # "鹿/比 stayed inconclusive" item with fresh eyes: 比(rtk482, "compare")
    # was atomic (no parts) despite CSV explicitly listing "spoon; sitting
    # on the ground" as its real components -- exactly the same pair
    # already used correctly for 北(rtk480, "north"), whose own CSV row is
    # identical. Decomposed 比 the same way: 匕,prim-sitting-on-the-ground.
    # That in turn made 鹿(rtk2154, "deer")'s bug provable: CSV's "cave;
    # antlers; compare; spoon; sitting on the ground" is [cave] + [antlers]
    # + [compare, redundantly re-expanded into its own spoon/sitting-on-
    # the-ground parts] -- "antlers" was the one real component missing
    # entirely (confirmed via cjkvi-ids, which shows a ⿻コ⿰丨丨 shape between
    # 广 and 比 with no standalone citable character anywhere in cjkvi-ids,
    # so added prim-antlers the same glyph-less way as prim-sitting-on-
    # the-ground). Fixed 鹿 to 广,prim-antlers,比. That in turn exposed
    # redundant-flattening in 6 more kanji that all separately re-listed
    # 比 and/or 广 alongside 鹿 itself once cjkvi-ids confirmed 鹿 is a
    # single clean top-level component of each: 麓(⿱林鹿, CSV also
    # separately names "grove"=林), 麗(⿱丽鹿, kept the existing 一,冂
    # approximation of 丽 since CSV independently confirms "one; ceiling;
    # mediocre"), 麟(⿰鹿粦, 粦=米+舛 per cjkvi-ids, dropped a stray "夕" that
    # didn't belong), 漉(⿰氵鹿), 塵(⿸鹿土), 麒(⿰鹿其, kept the existing 甘,ハ
    # approximation of 其). 慶(rtk2157) shows the same top shape as 鹿 in
    # cjkvi-ids but its own bottom differs enough from 比 in a render
    # comparison that it wasn't touched -- left as a separate, still-open
    # question rather than guess.
    "rtk482": {"character": "比", "keyword": "compare",
               "expected_part_ids": {"rtk476", "prim-sitting-on-the-ground"}},
    "rtk2154": {"character": "鹿", "keyword": "deer",
                "expected_part_ids": {"kangxi53", "prim-antlers", "rtk482"}},
    "rtk2155": {"character": "麓", "keyword": "foot of a mountain",
                "expected_part_ids": {"rtk208", "rtk2154"}},
    "rtk2158": {"character": "麗", "keyword": "lovely",
                "expected_part_ids": {"rtk1", "kangxi13", "rtk2154"}},
    "rtk2210": {"character": "麟", "keyword": "chinese unicorn",
                "expected_part_ids": {"rtk2154", "rtk987", "kangxi136"}},
    "rtk2398": {"character": "漉", "keyword": "manufacture paper",
                "expected_part_ids": {"rtk137", "rtk2154"}},
    "rtk2853": {"character": "塵", "keyword": "dust",
                "expected_part_ids": {"rtk2154", "rtk161"}},
    "rtk2854": {"character": "麒", "keyword": "chinese unicorn",
                "expected_part_ids": {"rtk1894", "prim-katakana-ha", "rtk2154"}},
    # Owner report (2026-09-04): searching "tree, mouth" surfaced wrong
    # results, and 保("protect") specifically was "missing left part".
    # 保 was 口,木 -- entirely missing 亻("person"), the literal left
    # radical the owner pointed at; cjkvi-ids confirms 保 = ⿰亻呆, and CSV
    # names "person" as a real component alongside 呆(rtk2297,"dumbfounded",
    # itself already correctly 口,木)'s own redundantly-restated subparts.
    # Fixed to 亻,呆. The other two reported false positives were
    # redundant-flattening, not missing components: 操("maneuver") listed
    # a bare "口" alongside "品"(rtk23, "goods") even though 品 already
    # implies a mouth-shape recursively -- the extra literal "口" was what
    # made a depth-1 "mouth" search wrongly match it; cjkvi-ids confirms
    # 操 = 扌+喿(=品+木) with no separate mouth stroke, so dropped the
    # redundant "口". 藁("straw") similarly re-listed 高(rtk329,"tall")'s
    # own subparts (口,亠,冂) alongside 高 itself; cjkvi-ids confirms
    # 藁 = 艹+槀(=高+木), so fixed to 艾,高,木.
    "rtk1072": {"character": "保", "keyword": "protect",
                "expected_part_ids": {"kangxi9", "rtk2297"}},
    "rtk724": {"character": "操", "keyword": "maneuver",
               "expected_part_ids": {"kangxi64", "rtk23", "rtk207"}},
    "rtk2480": {"character": "藁", "keyword": "straw",
                "expected_part_ids": {"prim-mugwort", "rtk329", "rtk207"}},
    # Owner report (2026-09-04): "search for stone+mouth brings mistakes".
    # Checked all 23 non-atomic 石("stone")-family kanji at once (every
    # host currently listing 石) rather than one at a time, since the
    # pattern turned out to be near-universal: 石 itself is correctly
    # 厂,口 (cliff, mouth) -- but essentially every host built on top of it
    # was ALSO separately re-listing a bare "口" alongside "石", even
    # though cjkvi-ids confirms every single one of these 23 characters is
    # cleanly [石 + exactly one other real component] with no independent
    # mouth stroke anywhere (e.g. 岩=⿱山石, 破=⿰石皮, 碑=⿰石卑, ...). That
    # stray "口" is exactly what made a depth-1 "mouth" search wrongly
    # match all of them. Beyond dropping the universal redundant "口",
    # several also needed their *other* component fixed, following the
    # same two established patterns:
    #  - reference an already-taught compound directly instead of
    #    re-flattening its own parts: 硬(更, rtk749), 砦(此, rtk2201),
    #    磐(般, rtk2016), 碇(定, rtk408), 碗(宛, rtk1521),
    #    碩(頁, rtk64 -- also dropped a redundant "貝", 頁's own part),
    #    磯(幾, rtk1481), 碍(旦, rtk30, kept the separate "寸"),
    #    砺(万, rtk68, kept the separate "厂", dropped a stray "斤"
    #    that didn't belong at all).
    #  - trust cjkvi-ids's real structure over a previous rough guess:
    #    確(⿰石隺, 隺=⿻冖隹 -- render-confirmed the top is 冖("cover"),
    #    not the previously-used 宀("roof"), which has an extra dot);
    #    研(⿰石开, 开=⿱一廾 exactly -- dropped 4 unrelated stray tokens);
    #    砕(⿰石卆, 卆=⿱九十 exactly, dropped a stray "ノ").
    #  - the rest needed only the redundant "口" dropped, their other
    #    parts were already correct: 拓, 硫, 岩, 磁, 碑(also referenced
    #    卑, rtk1629, directly already), 碁(其≈甘,ハ per the established
    #    approximation from the 麒 fix, also dropped a stray "一"), 柘,
    #    碧, 硯, 碓.
    "rtk121": {"character": "砕", "keyword": "smash",
               "expected_part_ids": {"rtk118", "rtk9", "rtk10"}},
    "rtk609": {"character": "確", "keyword": "assurance",
               "expected_part_ids": {"rtk118", "kangxi14", "kangxi172"}},
    "rtk703": {"character": "拓", "keyword": "clear (the land)",
               "expected_part_ids": {"rtk118", "kangxi64"}},
    "rtk729": {"character": "研", "keyword": "polish",
               "expected_part_ids": {"rtk118", "rtk1", "kangxi55"}},
    "rtk750": {"character": "硬", "keyword": "stiff",
               "expected_part_ids": {"rtk118", "rtk749"}},
    "rtk825": {"character": "硫", "keyword": "sulphur",
               "expected_part_ids": {"rtk118", "rtk134", "kangxi8", "kangxi28"}},
    "rtk832": {"character": "岩", "keyword": "boulder",
               "expected_part_ids": {"rtk830", "rtk118"}},
    "rtk869": {"character": "破", "keyword": "rend",
               "expected_part_ids": {"rtk118", "rtk865"}},
    "rtk1491": {"character": "磁", "keyword": "magnet",
                "expected_part_ids": {"rtk118", "rtk1", "kangxi12", "kangxi52"}},
    "rtk1903": {"character": "碁", "keyword": "go",
                "expected_part_ids": {"rtk118", "rtk1894", "prim-katakana-ha"}},
    "rtk2204": {"character": "砦", "keyword": "fort",
                "expected_part_ids": {"rtk118", "rtk2201"}},
    "rtk2577": {"character": "柘", "keyword": "wild mulberry",
                "expected_part_ids": {"rtk118", "rtk207"}},
    "rtk2632": {"character": "磐", "keyword": "rock",
                "expected_part_ids": {"rtk118", "rtk2016"}},
    "rtk2633": {"character": "碇", "keyword": "anchor",
                "expected_part_ids": {"rtk118", "rtk408"}},
    "rtk2634": {"character": "碧", "keyword": "blue",
                "expected_part_ids": {"rtk271", "rtk118", "rtk37"}},
    "rtk2635": {"character": "硯", "keyword": "inkstone",
                "expected_part_ids": {"rtk61", "rtk118"}},
    "rtk2637": {"character": "碗", "keyword": "porcelain bowl",
                "expected_part_ids": {"rtk118", "rtk1521"}},
    "rtk2638": {"character": "碍", "keyword": "obstacle",
                "expected_part_ids": {"rtk118", "rtk30", "rtk45"}},
    "rtk2639": {"character": "碩", "keyword": "large",
                "expected_part_ids": {"rtk118", "rtk64"}},
    "rtk2640": {"character": "磯", "keyword": "seashore",
                "expected_part_ids": {"rtk118", "rtk1481"}},
    "rtk2641": {"character": "砺", "keyword": "whetstone",
                "expected_part_ids": {"rtk118", "kangxi27", "rtk68"}},
    "rtk2642": {"character": "碓", "keyword": "pestle",
                "expected_part_ids": {"rtk118", "kangxi172"}},
    # Proactive spot-check (2026-09-04, same session as the 石-family fix):
    # owner asked to check other common two-part primitives the same way.
    # Built audit_direct_ref_overlap.py to search systematically (a host
    # directly references a taught primitive AND also separately re-lists
    # one of that primitive's own parts) rather than eyeballing more
    # candidates by hand. It found the exact same bug, at even larger
    # scale, in four more primitive families -- all confirmed via
    # cjkvi-ids before fixing, same as every other fix in this audit:
    #  - 糸("thread", rtk1431=幺,小; 77 hosts) -- every kanji in the whole
    #    silk/thread radical family (織,繕,縮,...) correctly referenced 糸
    #    but also separately carried its own "幺,小" redundantly.
    #  - 頁("page", rtk64=一,貝; 26 hosts) -- the "he-page" radical family
    #    (頑,項,額,...) all redundantly re-listed "貝". 領(rtk1507) needed
    #    the same fix, which in turn let 嶺(rtk2336, "peak", cjkvi-ids
    #    ⿱山領) be corrected to reference 領 directly instead of a stale
    #    flatten still using pre-fix 令 tokens.
    #  - 魚("fish", rtk183=田,杰(fire-radical); 20 hosts) -- the entire
    #    fish-radical family (鮮,鱗,鮭,...) redundantly re-listed both.
    #  - 足("leg", rtk1372=口,止; 19 hosts) -- while fixing this family,
    #    also found 促(rtk1373) was entirely missing its "person"(亻)
    #    component (same missing-component class as 保 earlier today,
    #    cjkvi-ids ⿰亻足), a few stray-token mistakes (践's "二"->"一"
    #    matching 戋=⿻戈一; 踊's "マ"->"卩", 跡's "赤"->"亦", both
    #    render-confirmed), and more of the same "reference the taught
    #    compound directly" pattern (踪->足,宗; 蕗->艾,路; 鷺->路,鳥;
    #    躇->艾,者,足).
    "rtk65": {"character": "頑", "keyword": "stubborn",
               "expected_part_ids": {"kangxi10", "rtk2", "rtk63", "rtk64"}},
    "rtk86": {"character": "項", "keyword": "paragraph",
               "expected_part_ids": {"rtk64", "rtk80"}},
    "rtk415": {"character": "題", "keyword": "topic",
               "expected_part_ids": {"rtk414", "rtk64"}},
    "rtk479": {"character": "頃", "keyword": "about that time",
               "expected_part_ids": {"rtk476", "rtk64"}},
    "rtk590": {"character": "鮮", "keyword": "fresh",
               "expected_part_ids": {"rtk183", "rtk586"}},
    "rtk846": {"character": "頒", "keyword": "partition",
               "expected_part_ids": {"rtk64", "rtk87"}},
    "rtk1000": {"character": "類", "keyword": "sort",
               "expected_part_ids": {"rtk112", "rtk64", "rtk987"}},
    "rtk1086": {"character": "傾", "keyword": "lean",
               "expected_part_ids": {"kangxi9", "rtk479"}},  # 亻 + 頃 (person radical added 2026-09-05)
    "rtk1333": {"character": "顎", "keyword": "chin",
               "expected_part_ids": {"kangxi20", "rtk11", "rtk2", "rtk64"}},
    "rtk1358": {"character": "頬", "keyword": "cheek",
               "expected_part_ids": {"kangxi12", "rtk1023", "rtk112", "rtk2", "rtk64"}},
    "rtk1373": {"character": "促", "keyword": "stimulate",
               "expected_part_ids": {"kangxi9", "rtk1372"}},
    "rtk1374": {"character": "捉", "keyword": "nab",
               "expected_part_ids": {"kangxi64", "rtk1372"}},
    "rtk1379": {"character": "躍", "keyword": "leap",
               "expected_part_ids": {"kangxi172", "rtk1372", "rtk615"}},
    "rtk1380": {"character": "践", "keyword": "tread",
               "expected_part_ids": {"kangxi62", "rtk1", "rtk1372"}},
    "rtk1381": {"character": "踏", "keyword": "step",
               "expected_part_ids": {"rtk12", "rtk137", "rtk1372"}},
    "rtk1382": {"character": "踪", "keyword": "trail",
               "expected_part_ids": {"rtk1181", "rtk1372"}},
    "rtk1432": {"character": "織", "keyword": "weave",
               "expected_part_ids": {"kangxi62", "rtk1431", "rtk518"}},
    "rtk1437": {"character": "緻", "keyword": "fine",
               "expected_part_ids": {"rtk1431", "rtk818"}},
    "rtk1440": {"character": "締", "keyword": "tighten",
               "expected_part_ids": {"rtk1431", "rtk466"}},
    "rtk1441": {"character": "維", "keyword": "fiber",
               "expected_part_ids": {"kangxi172", "rtk1431"}},
    "rtk1442": {"character": "羅", "keyword": "gauze",  # was missing 罒 (net radical) entirely — 2026-09-05
               "expected_part_ids": {"kangxi122", "kangxi172", "rtk1431"}},
    "rtk1453": {"character": "級", "keyword": "class",
               "expected_part_ids": {"prim-katakana-no", "rtk1431", "rtk743"}},
    "rtk1455": {"character": "紅", "keyword": "crimson",
               "expected_part_ids": {"rtk1431", "rtk80"}},
    "rtk1457": {"character": "紡", "keyword": "spinning",
               "expected_part_ids": {"rtk1431", "rtk529"}},
    "rtk1460": {"character": "経", "keyword": "sutra",
               "expected_part_ids": {"rtk1431", "rtk161", "rtk752"}},
    "rtk1461": {"character": "紳", "keyword": "sire",
               "expected_part_ids": {"prim-pipe", "rtk12", "rtk14", "rtk1431"}},
    "rtk1463": {"character": "細", "keyword": "dainty",
               "expected_part_ids": {"rtk14", "rtk1431"}},
    "rtk1464": {"character": "累", "keyword": "accumulate",
               "expected_part_ids": {"rtk14", "rtk1431"}},
    "rtk1465": {"character": "索", "keyword": "cord",
               "expected_part_ids": {"kangxi14", "rtk10", "rtk1431"}},
    "rtk1467": {"character": "綿", "keyword": "cotton",
               "expected_part_ids": {"rtk1431", "rtk37", "rtk432"}},
    "rtk1468": {"character": "絹", "keyword": "silk",
               "expected_part_ids": {"rtk11", "rtk13", "rtk1431"}},
    # Owner asked to search "goods" (2026-09-04) -- checked all 8 results
    # against cjkvi-ids. 品(rtk23, "goods") itself is correctly just "口"
    # (one mouth, per the established no-duplicate-token convention for
    # its own 3-mouth shape). 燥/操/嘔 already correctly referenced 品
    # directly with no issue. But 臨/繰/藻/癌 all redundantly repeated a
    # bare "口" alongside "品" -- the same overlap bug as everything else
    # in this audit today, just not caught until asked directly. Dropped
    # the redundant "口" from all three (臨's remaining ノ,臣,一,人
    # approximates 臣+𠂉 per cjkvi-ids ⿰臣⿱𠂉品; 癌's "疔" is an existing
    # alias for kangxi104/疒, not a separate error).
    "rtk1469": {"character": "繰", "keyword": "winding",
               "expected_part_ids": {"rtk1431", "rtk207", "rtk23"}},
    "rtk918": {"character": "臨", "keyword": "look to",
               "expected_part_ids": {"prim-katakana-no", "rtk1", "rtk1023", "rtk23", "rtk911"}},
    "rtk2191": {"character": "藻", "keyword": "seaweed",
                "expected_part_ids": {"prim-mugwort", "rtk137", "rtk207", "rtk23"}},
    "rtk2626": {"character": "癌", "keyword": "cancer",
                "expected_part_ids": {"kangxi104", "rtk23", "rtk830"}},
    "rtk1470": {"character": "継", "keyword": "inherit",
               "expected_part_ids": {"prim-pipe", "rtk1431", "rtk987"}},
    "rtk1471": {"character": "緑", "keyword": "green",
               "expected_part_ids": {"kangxi171", "prim-katakana-yo", "rtk137", "rtk1431"}},
    "rtk1472": {"character": "縁", "keyword": "affinity",
               "expected_part_ids": {"kangxi152", "prim-katakana-yo", "rtk1431"}},
    "rtk1473": {"character": "網", "keyword": "netting",
               "expected_part_ids": {"kangxi12", "kangxi13", "rtk1431", "rtk524"}},
    "rtk1474": {"character": "緊", "keyword": "tense",
               "expected_part_ids": {"rtk1431", "rtk752", "rtk911"}},
    "rtk1477": {"character": "縄", "keyword": "straw rope",
               "expected_part_ids": {"kangxi20", "rtk14", "rtk1431", "rtk573", "rtk75"}},
    "rtk1492": {"character": "系", "keyword": "lineage",
               "expected_part_ids": {"prim-katakana-no", "rtk1431"}},
    "rtk1493": {"character": "係", "keyword": "person in charge",
               "expected_part_ids": {"kangxi9", "rtk1492"}},  # 亻 + 系 (person radical added 2026-09-05)
    "rtk1512": {"character": "踊", "keyword": "jump",
               "expected_part_ids": {"kangxi26", "rtk1265", "rtk1372"}},
    "rtk1609": {"character": "純", "keyword": "genuine",
               "expected_part_ids": {"rtk1431", "rtk2189"}},
    "rtk1610": {"character": "頓", "keyword": "immediate",
               "expected_part_ids": {"rtk2189", "rtk64"}},
    "rtk1627": {"character": "糾", "keyword": "twist",
               "expected_part_ids": {"prim-pipe", "rtk10", "rtk1431"}},
    "rtk1652": {"character": "素", "keyword": "elementary",
               "expected_part_ids": {"kangxi8", "rtk1431", "rtk161", "rtk2"}},
    "rtk1668": {"character": "潔", "keyword": "undefiled",
               "expected_part_ids": {"kangxi8", "rtk137", "rtk1431", "rtk161", "rtk2", "rtk87"}},
    "rtk1685": {"character": "縫", "keyword": "sew",
               "expected_part_ids": {"kangxi34", "prim-pipe", "rtk1", "rtk1431", "rtk843"}},
    "rtk1774": {"character": "緯", "keyword": "horizontal",
               "expected_part_ids": {"kangxi178", "rtk11", "rtk1431"}},
    "rtk1853": {"character": "顔", "keyword": "face",
               "expected_part_ids": {"kangxi27", "kangxi59", "kangxi8", "rtk462", "rtk64"}},
    "rtk1854": {"character": "須", "keyword": "ought",
               "expected_part_ids": {"kangxi59", "rtk64"}},
    "rtk1863": {"character": "紋", "keyword": "family crest",
               "expected_part_ids": {"rtk1431", "rtk1861"}},
    "rtk1883": {"character": "跡", "keyword": "tracks",
               "expected_part_ids": {"kangxi8", "rtk1372"}},
    "rtk1891": {"character": "絶", "keyword": "discontinue",
               "expected_part_ids": {"rtk1431", "rtk1890"}},
    "rtk1895": {"character": "紺", "keyword": "navy blue",
               "expected_part_ids": {"rtk1431", "rtk1894"}},
    "rtk1914": {"character": "組", "keyword": "association",
               "expected_part_ids": {"rtk1", "rtk1431", "rtk15"}},
    "rtk1928": {"character": "顕", "keyword": "appear",
               "expected_part_ids": {"rtk12", "rtk64"}},
    "rtk1929": {"character": "繊", "keyword": "slender",
               "expected_part_ids": {"kangxi62", "rtk1431", "rtk161", "rtk1880"}},
    "rtk1966": {"character": "編", "keyword": "compilation",
               "expected_part_ids": {"prim-fishfinger", "rtk1431"}},
    "rtk1971": {"character": "紙", "keyword": "paper",
               "expected_part_ids": {"rtk1431", "rtk1970"}},
    "rtk2025": {"character": "繭", "keyword": "cocoon",
               "expected_part_ids": {"kangxi13", "prim-mugwort", "rtk1431", "rtk556", "rtk563"}},
    "rtk2102": {"character": "緩", "keyword": "slacken",
               "expected_part_ids": {"prim-katakana-no", "rtk1", "rtk1431", "rtk752", "rtk784"}},
    "rtk2114": {"character": "綱", "keyword": "hawser",
               "expected_part_ids": {"rtk1431", "rtk2112"}},
    "rtk2211": {"character": "鱗", "keyword": "scaled",
               "expected_part_ids": {"kangxi136", "rtk114", "rtk183", "rtk987"}},
    "rtk2222": {"character": "綴", "keyword": "mend",
               "expected_part_ids": {"rtk1431", "rtk752"}},
    "rtk2336": {"character": "嶺", "keyword": "mountaintop",
               "expected_part_ids": {"rtk1507", "rtk830"}},
    "rtk2399": {"character": "瀕", "keyword": "on the verge of",
               "expected_part_ids": {"prim-katakana-no", "rtk110", "rtk137", "rtk396", "rtk64"}},
    "rtk2455": {"character": "蕗", "keyword": "butterbur",
               "expected_part_ids": {"prim-mugwort", "rtk1376"}},
    "rtk2463": {"character": "蘇", "keyword": "resurrect",
               "expected_part_ids": {"kangxi115", "prim-mugwort", "rtk183"}},
    "rtk2568": {"character": "櫓", "keyword": "turret",
               "expected_part_ids": {"rtk12", "rtk183", "rtk207"}},
    "rtk2683": {"character": "纂", "keyword": "redaction",
               "expected_part_ids": {"rtk1007", "rtk1431", "rtk15"}},
    "rtk2697": {"character": "繋", "keyword": "link up",
               "expected_part_ids": {"kangxi16", "kangxi79", "rtk1431", "rtk304", "rtk752"}},
    "rtk2698": {"character": "綸", "keyword": "twine",
               "expected_part_ids": {"kangxi55", "prim-pipe", "prim-umbrella", "rtk1", "rtk1431", "rtk1967"}},
    "rtk2699": {"character": "絨", "keyword": "carpet yarn",
               "expected_part_ids": {"kangxi62", "prim-katakana-no", "rtk1", "rtk1431"}},
    "rtk2700": {"character": "絆", "keyword": "ties",
               "expected_part_ids": {"rtk1286", "rtk1431"}},
    "rtk2701": {"character": "緋", "keyword": "scarlet",
               "expected_part_ids": {"rtk1431", "rtk1760"}},
    "rtk2702": {"character": "綜", "keyword": "synthesis",
               "expected_part_ids": {"rtk1181", "rtk1431"}},
    "rtk2703": {"character": "紐", "keyword": "string",
               "expected_part_ids": {"prim-pipe", "rtk1", "rtk1431"}},
    "rtk2704": {"character": "紘", "keyword": "chinstrap",
               "expected_part_ids": {"kangxi28", "prim-katakana-no", "rtk1", "rtk1431"}},
    "rtk2705": {"character": "纏", "keyword": "summarize",
               "expected_part_ids": {"kangxi10", "kangxi53", "rtk1431", "rtk161", "rtk185"}},
    "rtk2706": {"character": "絢", "keyword": "gorgeous",
               "expected_part_ids": {"kangxi20", "rtk12", "rtk1431"}},
    "rtk2707": {"character": "繍", "keyword": "embroidery",
               "expected_part_ids": {"kangxi171", "prim-katakana-no", "prim-katakana-yo", "prim-pipe", "rtk137", "rtk1431"}},
    "rtk2708": {"character": "紬", "keyword": "pongee",
               "expected_part_ids": {"prim-pipe", "rtk12", "rtk14", "rtk1431"}},
    "rtk2709": {"character": "綺", "keyword": "ornate",
               "expected_part_ids": {"kangxi6", "rtk1", "rtk11", "rtk112", "rtk1431"}},
    "rtk2710": {"character": "綾", "keyword": "damask",
               "expected_part_ids": {"kangxi10", "kangxi34", "rtk1431", "rtk161"}},
    "rtk2711": {"character": "絃", "keyword": "catgut",
               "expected_part_ids": {"kangxi8", "rtk1431", "rtk1484"}},
    "rtk2712": {"character": "縞", "keyword": "stripe",
               "expected_part_ids": {"kangxi13", "kangxi8", "rtk11", "rtk1431", "rtk329"}},
    "rtk2713": {"character": "綬", "keyword": "gimp",
               "expected_part_ids": {"kangxi14", "rtk1431", "rtk752", "rtk784"}},
    "rtk2714": {"character": "紗", "keyword": "gossamer",
               "expected_part_ids": {"prim-katakana-no", "rtk1431"}},
    "rtk2730": {"character": "螺", "keyword": "screw",
               "expected_part_ids": {"rtk14", "rtk1431", "rtk556"}},
    "rtk2769": {"character": "躓", "keyword": "stumble",
               "expected_part_ids": {"rtk1206", "rtk1372", "rtk56"}},
    "rtk2771": {"character": "蹟", "keyword": "vestiges",
               "expected_part_ids": {"kangxi8", "rtk1372", "rtk161", "rtk2", "rtk56"}},
    "rtk2772": {"character": "跨", "keyword": "straddle",
               "expected_part_ids": {"kangxi20", "rtk112", "rtk1372", "rtk2"}},
    "rtk2773": {"character": "跪", "keyword": "kneel",
               "expected_part_ids": {"kangxi20", "kangxi26", "kangxi27", "rtk1372"}},
    "rtk2809": {"character": "顛", "keyword": "overturn",
               "expected_part_ids": {"rtk10", "rtk64"}},
    "rtk2810": {"character": "穎", "keyword": "brush tip",
               "expected_part_ids": {"kangxi115", "rtk476", "rtk64"}},
    "rtk2811": {"character": "頗", "keyword": "exceedingly",
               "expected_part_ids": {"rtk64", "rtk865"}},
    "rtk2812": {"character": "頌", "keyword": "accolade",
               "expected_part_ids": {"kangxi28", "rtk64"}},
    "rtk2813": {"character": "頚", "keyword": "neck and throat",
               "expected_part_ids": {"rtk161", "rtk64", "rtk752"}},
    "rtk2826": {"character": "鰻", "keyword": "eel",
               "expected_part_ids": {"rtk12", "rtk183", "rtk752"}},
    "rtk2827": {"character": "鯛", "keyword": "sea bream",
               "expected_part_ids": {"kangxi13", "rtk11", "rtk161", "rtk183"}},
    "rtk2828": {"character": "鰯", "keyword": "sardine",
               "expected_part_ids": {"kangxi15", "rtk1317", "rtk183"}},
    "rtk2830": {"character": "鮭", "keyword": "salmon",
               "expected_part_ids": {"rtk161", "rtk183"}},
    "rtk2831": {"character": "鮪", "keyword": "tuna",
               "expected_part_ids": {"prim-katakana-no", "rtk1", "rtk13", "rtk183"}},
    "rtk2832": {"character": "鮎", "keyword": "sweet smelt",
               "expected_part_ids": {"kangxi25", "rtk11", "rtk183"}},
    "rtk2833": {"character": "鯵", "keyword": "horse mackerel",
               "expected_part_ids": {"kangxi28", "kangxi59", "rtk112", "rtk183"}},
    "rtk2834": {"character": "鱈", "keyword": "cod",
               "expected_part_ids": {"prim-katakana-yo", "rtk183", "rtk451"}},
    "rtk2835": {"character": "鯖", "keyword": "mackerel",
               "expected_part_ids": {"rtk1654", "rtk183"}},
    "rtk2836": {"character": "鮫", "keyword": "shark",
               "expected_part_ids": {"kangxi8", "rtk1366", "rtk183"}},
    "rtk2837": {"character": "鰹", "keyword": "bonito",
               "expected_part_ids": {"rtk161", "rtk183", "rtk752", "rtk911"}},
    "rtk2838": {"character": "鰍", "keyword": "bullhead",
               "expected_part_ids": {"kangxi115", "rtk173", "rtk183"}},
    "rtk2839": {"character": "鰐", "keyword": "alligator",
               "expected_part_ids": {"kangxi20", "rtk11", "rtk183", "rtk2"}},
    "rtk2840": {"character": "鮒", "keyword": "crucian carp",
               "expected_part_ids": {"rtk183", "rtk45"}},
    "rtk2841": {"character": "鮨", "keyword": "sushi",
               "expected_part_ids": {"rtk12", "rtk183", "rtk476"}},
    "rtk2842": {"character": "鰭", "keyword": "fish fin",
               "expected_part_ids": {"rtk12", "rtk1340", "rtk183", "rtk476"}},
    "rtk2848": {"character": "鷺", "keyword": "heron",
               "expected_part_ids": {"rtk1376", "rtk2091"}},
    "rtk2956": {"character": "噸", "keyword": "ton",
               "expected_part_ids": {"rtk11", "rtk2189", "rtk64"}},
    "rtk2970": {"character": "轡", "keyword": "tinkling bell",
               "expected_part_ids": {"rtk11", "rtk1431", "rtk304"}},
    "rtk2995": {"character": "躇", "keyword": "dither",
               "expected_part_ids": {"prim-mugwort", "rtk1345", "rtk1372"}},
    "rtk2997": {"character": "躊", "keyword": "hesitate",
               "expected_part_ids": {"rtk1372", "rtk341", "rtk45", "rtk80"}},
    # Continuing the proactive spot-check further (2026-09-04): five more
    # primitive families from audit_direct_ref_overlap.py, same discipline:
    #  - 青(rtk1654=月,土,二,亠; used 10x) -- the whole "clear/blue" family
    #    (精,請,情,晴,清,静,靖,錆,鯖) correctly referenced 青 but redundantly
    #    repeated its own parts. 瀞 was flattening 静 instead of
    #    referencing it directly (cjkvi-ids ⿰氵静).
    #  - 示(rtk1167=二,小; used 10x) -- several hosts (剽,捺,禦,綜,瓢,祟) were
    #    flattening an already-taught second-level compound (票, 奈, 御,
    #    宗, 出) instead of referencing it; 剽 also turned out to be
    #    entirely missing "刀"(sword) -- and while fixing it, caught a
    #    latent bug in my own edit: "刂"(the radical form) isn't a
    #    registered alias in this system (only "刀" is; same silent-drop
    #    behavior as the already-known-dead "primitive_roof" token) --
    #    corrected both this and 到(rtk817) to use "刀". 蔚 doesn't
    #    contain 示 at all (real cjkvi-ids ⿱艹尉, unrelated) -- dropped it
    #    rather than force an approximation.
    #  - 至(rtk815=土,厶; used 9x) -- 到 was missing "刀" (see above) and
    #    倒/緻/渥 were flattening second-level compounds (到, 致, 屋)
    #    instead of referencing them.
    #  - 巾(rtk432; used 9x) -- only the one clean case fixed (凧=几+巾);
    #    left 刺/策/棘 (real cjkvi-ids 朿-family) and 幣/蔽/弊/瞥/逓 (敝-
    #    family, already flagged as an open question) for another
    #    session rather than force an uncertain call.
    #  - 自(rtk36=丶,目; used 9x) -- most hosts correctly referenced 自 but
    #    redundantly repeated its own "目". 嗅/榎/鼾 were flattening
    #    already-taught compounds (臭, 夏, 鼻) instead of referencing them.
    "rtk74": {"character": "首", "keyword": "neck",
               "expected_part_ids": {"kangxi12", "rtk36"}},
    "rtk128": {"character": "臭", "keyword": "stinking",
               "expected_part_ids": {"rtk112", "rtk36"}},
    "rtk129": {"character": "嗅", "keyword": "sniff",
               "expected_part_ids": {"rtk11", "rtk128"}},
    "rtk317": {"character": "夏", "keyword": "summer",
               "expected_part_ids": {"kangxi34", "rtk1", "rtk36"}},
    "rtk657": {"character": "息", "keyword": "breath",
               "expected_part_ids": {"rtk36", "rtk639"}},
    "rtk658": {"character": "憩", "keyword": "recess",
               "expected_part_ids": {"rtk36", "rtk41", "rtk639"}},
    "rtk733": {"character": "鼻", "keyword": "nose",
               "expected_part_ids": {"kangxi55", "rtk14", "rtk36"}},
    "rtk816": {"character": "室", "keyword": "room",
               "expected_part_ids": {"kangxi40", "rtk815"}},
    "rtk817": {"character": "到", "keyword": "arrival",
               "expected_part_ids": {"rtk815", "rtk87"}},
    "rtk818": {"character": "致", "keyword": "doth",
               "expected_part_ids": {"kangxi66", "rtk815"}},
    "rtk1055": {"character": "倒", "keyword": "overthrow",
               "expected_part_ids": {"kangxi9", "rtk817"}},
    "rtk1138": {"character": "屋", "keyword": "roof",
               "expected_part_ids": {"kangxi44", "rtk815"}},
    "rtk1655": {"character": "精", "keyword": "refined",
               "expected_part_ids": {"rtk1654", "rtk987"}},
    "rtk1656": {"character": "請", "keyword": "solicit",
               "expected_part_ids": {"rtk1654", "rtk357"}},
    "rtk1657": {"character": "情", "keyword": "feelings",
               "expected_part_ids": {"kangxi61", "rtk1654"}},
    "rtk1658": {"character": "晴", "keyword": "clear up",
               "expected_part_ids": {"rtk12", "rtk1654"}},
    "rtk1659": {"character": "清", "keyword": "pure",
               "expected_part_ids": {"rtk137", "rtk1654"}},
    "rtk1660": {"character": "静", "keyword": "quiet",
               "expected_part_ids": {"kangxi20", "kangxi6", "prim-katakana-yo", "rtk1654"}},
    "rtk2264": {"character": "凛", "keyword": "stately",
               "expected_part_ids": {"kangxi15", "kangxi31", "kangxi8", "rtk11", "rtk1167"}},
    "rtk2265": {"character": "凧", "keyword": "kite",
               "expected_part_ids": {"kangxi16", "rtk432"}},
    "rtk2269": {"character": "剽", "keyword": "menace",
               "expected_part_ids": {"rtk1732", "rtk87"}},
    "rtk2314": {"character": "姪", "keyword": "niece",
               "expected_part_ids": {"rtk102", "rtk815"}},
    "rtk2355": {"character": "捺", "keyword": "impress",
               "expected_part_ids": {"kangxi64", "rtk1175"}},
    "rtk2411": {"character": "渥", "keyword": "moisten",
               "expected_part_ids": {"rtk1138", "rtk137"}},
    "rtk2414": {"character": "瀞", "keyword": "river pool",
               "expected_part_ids": {"rtk137", "rtk1660"}},
    "rtk2484": {"character": "蒜", "keyword": "garlic",
               "expected_part_ids": {"prim-mugwort", "rtk1167"}},
    "rtk2486": {"character": "蔚", "keyword": "grow plentiful",
               "expected_part_ids": {"kangxi44", "prim-mugwort", "rtk45"}},
    "rtk2574": {"character": "榎", "keyword": "hackberry",
               "expected_part_ids": {"rtk207", "rtk317"}},
    "rtk2643": {"character": "禦", "keyword": "fend off",
               "expected_part_ids": {"rtk1167", "rtk1500"}},
    "rtk2666": {"character": "靖", "keyword": "repose",
               "expected_part_ids": {"rtk1654", "rtk462"}},
    "rtk2735": {"character": "蛭", "keyword": "leech",
               "expected_part_ids": {"rtk556", "rtk815"}},
    "rtk2793": {"character": "錆", "keyword": "rust",
               "expected_part_ids": {"rtk1654", "rtk287"}},
    "rtk2920": {"character": "瓢", "keyword": "gourd",
               "expected_part_ids": {"rtk1732", "rtk2022"}},
    "rtk2946": {"character": "祟", "keyword": "haunt",
               "expected_part_ids": {"rtk1167", "rtk829"}},
    "rtk2951": {"character": "鼾", "keyword": "snore",
               "expected_part_ids": {"rtk1777", "rtk733"}},
    # Continuing the proactive spot-check (2026-09-04, same session):
    # audit_direct_ref_overlap.py's next four families, same discipline
    # (every fix confirmed via cjkvi-ids, several needed deeper attention
    # beyond a simple redundant-token drop):
    #  - 尚(rtk196, used 14x) -- 賞/堂/常/裳/掌/嘗 all correctly reference
    #    尚 but redundantly repeat its own "口"; also carried a stray
    #    "冖" nowhere in cjkvi-ids's real ⿱𫩠X tops. 償(rtk1060) was
    #    entirely missing "亻" (same missing-component class as 保/促
    #    today) and should reference 賞 directly (cjkvi-ids ⿰亻賞). 党
    #    (⿱龸兄) and 哨(⿰口肖) were using 尚 outright where the real
    #    top is a plainer "小" shape -- fixed 肖(rtk119) itself (was
    #    wrongly 月,尚; cjkvi-ids ⿱⺌月) and referenced 兄/肖 directly.
    #    Left 蔽/弊/瞥/鼈/獣 (all real cjkvi-ids 敝-family or otherwise
    #    unrelated to 尚) unexamined -- a different, more involved
    #    question for another session.
    #  - 戸(rtk1157, used 17x) -- 肩/房/扇/炉/戻/雇/所/扉/芦 all
    #    correctly reference 戸 but redundantly repeat its own "一,尸".
    #    偏/遍/編/篇/騙 were flattening a *second-level* compound (扁,
    #    CSV: "fishfinger") into 7-8 tokens each instead of referencing
    #    it -- added prim-fishfinger. 偏 was also entirely missing "亻"
    #    (cjkvi-ids ⿰亻扁). 啓/肇 use a different compound (𢼄=戸+攵) and
    #    had two stray tokens each dropped. 煽 was flattening 戸+羽
    #    instead of referencing 扇(rtk1160) directly (cjkvi-ids ⿰火扇).
    #  - 穴(rtk1413, used 16x) -- most hosts correctly reference 穴 but
    #    redundantly repeat its own "儿,宀". 容/蓉 don't contain 穴 at
    #    all (cjkvi-ids ⿱宀谷) -- they'd wrongly picked up 穴 because 宀
    #    happens to be one of 穴's own parts too, a sharper version of
    #    the same overlap bug. 窒 and 腔 were flattening already-taught
    #    compounds (至, 空) instead of referencing them directly.
    #  - 音(rtk518, used 14x) -- most hosts correctly reference 音 but
    #    redundantly repeat its own "日,立" (though 暗 needed *only*
    #    "立" dropped, since cjkvi-ids ⿰日音 means its own "日" token
    #    does double duty as 音's real external neighbor, not just an
    #    internal duplicate -- not a blind "drop the whole overlap"
    #    case). 章(rtk464) doesn't contain 音 at all (cjkvi-ids ⿱立早,
    #    same "picked up the primitive via one shared sub-part" trap as
    #    容/蓉 above) -- fixing it let 障/彰 correctly reference 章
    #    directly instead of flattening its pre-fix wrong parts. 識/職/
    #    織/幟 were flattening 戠(=音+戈, not separately taught) instead
    #    of referencing 音 + 戈 directly. 億 was entirely missing "亻"
    #    and should reference 意 directly (cjkvi-ids ⿰亻意, same
    #    missing-component class again).
    "rtk119": {"character": "肖", "keyword": "resemblance",
               "expected_part_ids": {"rtk110", "rtk13"}},
    "rtk464": {"character": "章", "keyword": "badge",
               "expected_part_ids": {"rtk26", "rtk462"}},
    "rtk519": {"character": "暗", "keyword": "darkness",
               "expected_part_ids": {"rtk12", "rtk518"}},
    "rtk521": {"character": "識", "keyword": "discriminating",
               "expected_part_ids": {"kangxi62", "rtk357", "rtk518"}},
    "rtk522": {"character": "鏡", "keyword": "mirror",
               "expected_part_ids": {"kangxi10", "rtk287", "rtk518"}},
    "rtk654": {"character": "意", "keyword": "idea",
               "expected_part_ids": {"rtk518", "rtk639"}},
    "rtk811": {"character": "窓", "keyword": "window",
               "expected_part_ids": {"kangxi28", "rtk1413", "rtk639"}},
    "rtk853": {"character": "容", "keyword": "contain",
               "expected_part_ids": {"kangxi40", "rtk851"}},
    "rtk859": {"character": "賞", "keyword": "prize",
               "expected_part_ids": {"rtk196", "rtk56"}},
    "rtk860": {"character": "党", "keyword": "party",
               "expected_part_ids": {"rtk107", "rtk110"}},
    "rtk861": {"character": "堂", "keyword": "hall",
               "expected_part_ids": {"rtk161", "rtk196"}},
    "rtk862": {"character": "常", "keyword": "usual",
               "expected_part_ids": {"rtk196", "rtk432"}},
    "rtk863": {"character": "裳", "keyword": "skirt",
               "expected_part_ids": {"rtk196", "rtk423"}},
    "rtk864": {"character": "掌", "keyword": "manipulate",
               "expected_part_ids": {"rtk196", "rtk687"}},
    "rtk887": {"character": "職", "keyword": "post",
               "expected_part_ids": {"kangxi62", "rtk518", "rtk881"}},
    "rtk1058": {"character": "億", "keyword": "hundred million",
               "expected_part_ids": {"kangxi9", "rtk654"}},
    "rtk1060": {"character": "償", "keyword": "reparation",
               "expected_part_ids": {"kangxi9", "rtk859"}},
    "rtk1158": {"character": "肩", "keyword": "shoulder",
               "expected_part_ids": {"rtk1157", "rtk13"}},
    "rtk1159": {"character": "房", "keyword": "tassel",
               "expected_part_ids": {"rtk1157", "rtk529"}},
    "rtk1161": {"character": "炉", "keyword": "hearth",
               "expected_part_ids": {"rtk1157", "rtk173"}},
    "rtk1162": {"character": "戻", "keyword": "re-",
               "expected_part_ids": {"rtk112", "rtk1157"}},
    "rtk1164": {"character": "雇", "keyword": "employ",
               "expected_part_ids": {"kangxi172", "rtk1157"}},
    "rtk1166": {"character": "啓", "keyword": "disclose",
               "expected_part_ids": {"kangxi66", "rtk11", "rtk1157"}},
    "rtk1208": {"character": "所", "keyword": "place",
               "expected_part_ids": {"rtk1157", "rtk1206"}},
    "rtk1414": {"character": "空", "keyword": "empty",
               "expected_part_ids": {"rtk1413", "rtk80"}},
    "rtk1416": {"character": "突", "keyword": "stab",
               "expected_part_ids": {"rtk112", "rtk1413"}},
    "rtk1417": {"character": "究", "keyword": "research",
               "expected_part_ids": {"rtk1413", "rtk9"}},
    "rtk1418": {"character": "窒", "keyword": "plug up",
               "expected_part_ids": {"rtk1413", "rtk815"}},
    "rtk1420": {"character": "窟", "keyword": "cavern",
               "expected_part_ids": {"kangxi44", "prim-pipe", "rtk1413", "rtk830"}},
    "rtk1421": {"character": "窪", "keyword": "depression",
               "expected_part_ids": {"rtk137", "rtk1413", "rtk161"}},
    "rtk1423": {"character": "窯", "keyword": "kiln",
               "expected_part_ids": {"prim-fire-radical", "rtk1413", "rtk586"}},
    "rtk1424": {"character": "窮", "keyword": "hard up",
               "expected_part_ids": {"rtk1317", "rtk1337", "rtk1413"}},
    "rtk1748": {"character": "闇", "keyword": "pitch dark",
               "expected_part_ids": {"rtk1743", "rtk518"}},
    "rtk1766": {"character": "扉", "keyword": "front door",
               "expected_part_ids": {"rtk1157", "rtk1760"}},
    "rtk1964": {"character": "偏", "keyword": "partial",
               "expected_part_ids": {"kangxi9", "prim-fishfinger"}},
    "rtk1965": {"character": "遍", "keyword": "everywhere",
               "expected_part_ids": {"prim-fishfinger", "rtk843"}},
    "rtk1994": {"character": "響", "keyword": "echo",
               "expected_part_ids": {"kangxi138", "kangxi52", "rtk1991", "rtk518"}},
    "rtk2277": {"character": "哨", "keyword": "scout",
               "expected_part_ids": {"rtk11", "rtk119"}},
    "rtk2340": {"character": "幟", "keyword": "pennant",
               "expected_part_ids": {"kangxi62", "rtk432", "rtk518"}},
    "rtk2448": {"character": "蓉", "keyword": "lotus blossom",
               "expected_part_ids": {"kangxi40", "prim-mugwort", "rtk851"}},
    "rtk2450": {"character": "芦", "keyword": "hollow reed",
               "expected_part_ids": {"prim-mugwort", "rtk1157"}},
    "rtk2535": {"character": "腔", "keyword": "body cavity",
               "expected_part_ids": {"rtk13", "rtk1414"}},
    "rtk2660": {"character": "窄", "keyword": "tight",
               "expected_part_ids": {"prim-katakana-no", "prim-pipe", "rtk1413"}},
    "rtk2661": {"character": "穿", "keyword": "drill",
               "expected_part_ids": {"rtk1413", "rtk2053"}},
    "rtk2662": {"character": "竃", "keyword": "kitchen stove",
               "expected_part_ids": {"kangxi20", "rtk14", "rtk1413", "rtk161", "rtk573", "rtk75"}},
    "rtk2687": {"character": "篇", "keyword": "livraison",
               "expected_part_ids": {"prim-fishfinger", "rtk1007"}},
    "rtk2821": {"character": "騙", "keyword": "cheat",
               "expected_part_ids": {"prim-fishfinger", "rtk2132"}},
    "rtk2883": {"character": "嘗", "keyword": "lick",
               "expected_part_ids": {"rtk196", "rtk493"}},
    "rtk2902": {"character": "肇", "keyword": "founding",
               "expected_part_ids": {"kangxi129", "kangxi66", "rtk1157"}},
    # Owner asked to cross-check the live DB against the owner's own Google
    # AI Overview results (tools/heisig-google-check/results.jsonl) via
    # triage_google_check.py, which flags 651 kanji where our decomposition
    # and Google's mentioned characters don't line up. Worked through the
    # 43 "DISJOINT" (zero overlap -- the strongest signal) entries first,
    # cjkvi-ids/CSV/render-verified as always; most turned out to be false
    # positives (the heuristic doesn't distinguish Google mentioning a real
    # component from mentioning an unrelated example kanji), but 19 were
    # real bugs:
    #  - missing components (same class as 保/促/偏 earlier): 良 missing
    #    "丶" (cjkvi-ids ⿱丶艮); 爽 missing "大" entirely (cjkvi-ids shows
    #    大 overlaid with a doubled-cross shape, approximated with the
    #    already-established 乂).
    #  - wrong box shape (同"石/砕" family's 田-vs-something confusion,
    #    but the OTHER direction this time): 亀 had 田(rice field) where
    #    render confirms a 2-cell 日(sun/day) box, not a 4-cell one.
    #  - reference an already-taught compound directly instead of
    #    flattening: 渓→夫, 尽→尺, 芝→之, 浜→兵, 浪→良, 英→央, 汀→丁,
    #    茉→末, 芥→介, 迪→由, 邁→萬(rtk2974), 慾→欲, 添→天(+心), and
    #    芸→云 (which needed 云 itself fixed first -- was 一,二,厶 but
    #    cjkvi-ids ⿱二厶 has no "一"). 歪(cjkvi-ids ⿱不正) now references
    #    both 不 and 正 directly instead of a flattened mash of both.
    # Deliberately left many more DISJOINT hits alone after checking them:
    # some were already fixed earlier this same session (梗, 党, 邦--
    # Google's results.jsonl was scraped before those fixes landed), some
    # are confirmed-correct existing approximations once rendered (申's
    # real 田 box, 競, 追, 師, 沸, 鳥/馬's 杰-for-灬 stand-in), and several
    # stayed genuinely inconclusive (壷's already-standing ambiguous top,
    # 単/脳's shared "𭕄" marker, 之's own atomic breakdown, 斡, 華, 予,
    # 共, 蒲, 汚, 之, 了, 袖, 浄) -- left unfixed rather than force a
    # low-confidence call, matching this audit's standing discipline.
    # The 608 "PARTIAL" hits (something in ours not echoed in Google's
    # text -- much noisier, most likely just Google's text omitting a
    # real part rather than us having a wrong one) are still unmined.
    "rtk450": {"character": "芸", "keyword": "technique",
               "expected_part_ids": {"prim-mugwort", "rtk2241"}},
    "rtk573": {"character": "亀", "keyword": "tortoise",
               "expected_part_ids": {"kangxi20", "rtk12", "rtk75"}},
    "rtk684": {"character": "添", "keyword": "annexed",
               "expected_part_ids": {"rtk137", "rtk457", "rtk639"}},
    "rtk903": {"character": "渓", "keyword": "mountain stream",
               "expected_part_ids": {"rtk137", "rtk784", "rtk901"}},
    "rtk1152": {"character": "尽", "keyword": "exhaust",
               "expected_part_ids": {"kangxi3", "rtk1151"}},
    "rtk1301": {"character": "芝", "keyword": "turf",
               "expected_part_ids": {"prim-mugwort", "rtk1299"}},
    "rtk1430": {"character": "浜", "keyword": "seacoast",
               "expected_part_ids": {"rtk137", "rtk1429"}},
    "rtk1578": {"character": "良", "keyword": "good",
               "expected_part_ids": {"kangxi138", "kangxi3"}},
    "rtk1580": {"character": "浪", "keyword": "wandering",
               "expected_part_ids": {"rtk137", "rtk1578"}},
    "rtk1608": {"character": "爽", "keyword": "bracing",
               "expected_part_ids": {"prim-tucked-under-the-arm", "rtk112"}},
    "rtk1878": {"character": "英", "keyword": "england",
               "expected_part_ids": {"prim-mugwort", "rtk1877"}},
    "rtk2241": {"character": "云", "keyword": "quote",
               "expected_part_ids": {"kangxi28", "rtk2"}},
    "rtk2405": {"character": "汀", "keyword": "water’s edge",
               "expected_part_ids": {"rtk137", "rtk95"}},
    "rtk2436": {"character": "茉", "keyword": "jasmine",
               "expected_part_ids": {"prim-mugwort", "rtk230"}},
    "rtk2459": {"character": "芥", "keyword": "mustard",
               "expected_part_ids": {"prim-mugwort", "rtk265"}},
    "rtk2492": {"character": "迪", "keyword": "way",
               "expected_part_ids": {"rtk1186", "rtk843"}},
    "rtk2875": {"character": "歪", "keyword": "warped",
               "expected_part_ids": {"rtk1302", "rtk405"}},
    "rtk2975": {"character": "邁", "keyword": "pass through",
               "expected_part_ids": {"rtk2974", "rtk843"}},
    "rtk2988": {"character": "慾", "keyword": "longing (old)",
               "expected_part_ids": {"rtk639", "rtk855"}},
    # Continuing the results.jsonl mining into the noisier 622 "PARTIAL"
    # flags (2026-09-05, daily check-in): filtered for the highest-signal
    # subset first -- exactly one of our tokens missing from Google's
    # text, no kana noise in Google's mentions, and Google's own mentions
    # short/clean -- then cjkvi-ids/CSV-verified each survivor as usual.
    # Most PARTIAL hits are the water/氵, 込/辶, ハ/八, 艾/艹 radical-
    # variant false positives this audit already knows about (Google's
    # text uses the compound-radical form, ours uses the standalone
    # character -- both correct), or 个("umbrella") cases already
    # resolved earlier this session -- skipped all of those. Real bugs
    # found in the filtered subset:
    #  - 忘/忙/盲/妄 all redundantly repeated 亡(rtk524)'s own "亠" part
    #    alongside referencing 亡 directly (this audit's most common bug
    #    shape); 忙 was additionally missing "忄" entirely (cjkvi-ids
    #    ⿰忄亡) where it had "亠" doing nothing useful in its place.
    #  - 朗 was flattening 良's pre-fix parts instead of referencing it
    #    (cjkvi-ids K variant ⿰良月); 島 had a stray extra "白" cjkvi-ids
    #    doesn't call for (⿹⑦山, confirmed by render: 鳥 sits cleanly on
    #    山 with nothing else); 烏 was using the wrong reference entirely
    #    -- it's missing a stroke 鳥 has (render-confirmed), so CSV's
    #    real component list ("drop; mouth; one; tail feathers") was
    #    used instead of flattening via the too-similar 鳥.
    #  - 能 was missing "prim-sitting-on-the-ground" (the same
    #    spoon/sitting-on-the-ground pair from 北/比 found earlier this
    #    audit -- CSV confirms "spoon; sitting on the ground" for 能 too).
    #  - 雲/腸/恵 were each flattening an already-taught compound's own
    #    parts (云, 旦, and a stray "一" instead of "十" respectively --
    #    CSV explicitly names "ten" for 恵, not "one").
    #  - 双/彼/秘 each carried one redundant extra stroke duplicating
    #    part of an already-referenced compound (双=又+又 per cjkvi-ids,
    #    "no duplicate token" convention collapses to one; 彼's 又 is
    #    already inside 皮 per the established rtk865 fix; 秘's 丶 is
    #    already inside 必).
    "rtk452": {"character": "雲", "keyword": "cloud",
               "expected_part_ids": {"rtk2241", "rtk451"}},
    "rtk525": {"character": "盲", "keyword": "blind",
               "expected_part_ids": {"rtk15", "rtk524"}},
    "rtk526": {"character": "妄", "keyword": "delusion",
               "expected_part_ids": {"rtk102", "rtk524"}},
    "rtk583": {"character": "腸", "keyword": "intestines",
               "expected_part_ids": {"rtk1128", "rtk13", "rtk30"}},
    "rtk640": {"character": "忘", "keyword": "forget",
               "expected_part_ids": {"rtk524", "rtk639"}},
    "rtk659": {"character": "恵", "keyword": "favor",
               "expected_part_ids": {"rtk10", "rtk14", "rtk639"}},
    "rtk665": {"character": "忙", "keyword": "busy",
               "expected_part_ids": {"kangxi61", "rtk524"}},
    "rtk753": {"character": "双", "keyword": "pair",
               "expected_part_ids": {"rtk752"}},
    "rtk948": {"character": "彼", "keyword": "he",
               "expected_part_ids": {"kangxi60", "rtk865"}},
    "rtk1579": {"character": "朗", "keyword": "melodious",
               "expected_part_ids": {"rtk13", "rtk1578"}},
    "rtk2094": {"character": "烏", "keyword": "crow",
               "expected_part_ids": {"kangxi3", "prim-fire-radical", "rtk1", "rtk11"}},
    "rtk2098": {"character": "島", "keyword": "island",
               "expected_part_ids": {"rtk2091", "rtk830"}},
    "rtk2160": {"character": "能", "keyword": "ability",
               "expected_part_ids": {"kangxi28", "prim-sitting-on-the-ground", "rtk13", "rtk476"}},
    # Five owner-disputed decompositions (review_queue.py #9-13, 2026-09-04), all
    # KRADFILE over-fragmentation from the original import_rtk.py pass: a whole RTK
    # primitive shattered into stray strokes because heisig-kanjis.csv had no
    # components for these rare N1/uncommon frames (so the KRADFILE guess in data.txt
    # won the merge by default). Fixed 2026-09-05 to reference the real compound.
    "rtk2540": {"character": "椋", "keyword": "type of deciduous tree",  # was 口,小,木,亠 (亠+口+小 = shattered 京)
               "expected_part_ids": {"rtk207", "rtk334"}},              # 木 + 京
    "rtk2561": {"character": "桔", "keyword": "used in plant names",     # was 口,士,木 (士+口 = shattered 吉)
               "expected_part_ids": {"rtk207", "rtk342"}},              # 木 + 吉
    "rtk460": {"character": "橋", "keyword": "bridge",                   # was ノ,口,木,冂 — missing 大 + a 口 vs siblings 嬌/矯
               "expected_part_ids": {"kangxi13", "prim-katakana-no", "rtk11", "rtk112", "rtk207"}},
    "rtk2903": {"character": "麿", "keyword": "i",                       # was 口,木,广,麻,ノ — 麻 double-counted w/ its own 广,木; spurious ノ
               "expected_part_ids": {"rtk24", "rtk637"}},               # 麻 + 呂
    "rtk24": {"character": "呂", "keyword": "spine",                     # was 口,ノ — missing the second 口 entirely (ノ = KRADFILE proxy)
               "expected_part_ids": {"rtk11"}},                          # 口,口 (dedupes to one id, order-independent)
    # Six more single-instance radical-omission bugs found via the same cjkvi-ids
    # presence check (2026-09-05, continued), each real (confirmed the old value
    # didn't carry the radical even transitively, unlike two other candidates —
    # 擁/rtk1488 and 祐-family/rtk1168-referencing kanji — that were false positives
    # from the shallow single-level parts_detail check and were left alone).
    "rtk150": {"character": "汁", "keyword": "soup",       # was 十 alone — missing 水 (soup is water + ten)
               "expected_part_ids": {"rtk10", "rtk137"}},
    "rtk2720": {"character": "耶", "keyword": "question mark",  # was 耳,邦 — 邦("home country") is a semantically-bogus
               "expected_part_ids": {"kangxi170", "rtk881"}},   # whole-kanji stand-in for a bare 阝; now 耳,阝 directly
    "rtk2980": {"character": "薗", "keyword": "garden",    # was 衣,口,土,囗,艾 — flattened 園's own parts instead of
               "expected_part_ids": {"prim-mugwort", "rtk629"}},  # referencing it; now 艾,園
    "rtk2434": {"character": "狒", "keyword": "baboon",     # was ｜,ノ,弓 — missing 犭 entirely, plus a botched 弗
               "expected_part_ids": {"kangxi94", "prim-katakana-no", "prim-pipe", "rtk1317"}},
    "rtk2994": {"character": "祓", "keyword": "exorcise",   # was ノ,一,礼,丶 — a byte-level flatten of 礼's strokes,
               "expected_part_ids": {"kangxi113", "rtk253"}},   # not a real reference; render shows 犬, not 礼-shaped
    "rtk431": {"character": "初", "keyword": "first time",  # was 刀 alone — missing 衣 (the clothing radical 衤), which
               "expected_part_ids": {"rtk423", "rtk87"}},   # then silently propagated through every kanji that
                                                              # correctly *referenced* 初 (裕/被/裾/襟/袖/裸/補/... — 15
                                                              # kanji total, all auto-fixed by this one root fix)
    "rtk1073": {"character": "褒", "keyword": "praise",  # was 衣,口,小,亠 -- flattened 保(rtk1072)'s own 呆 with a
               "expected_part_ids": {"kangxi8", "rtk1072", "rtk423"}},  # wrong 小 for 木; CSV names "protect" directly
    "rtk1304": {"character": "杯", "keyword": "counter for cupfuls",  # was ｜,ノ,一,木,礼 -- render-confirmed the
               "expected_part_ids": {"rtk1302", "rtk207"}},  # right side is 不(rtk1302)-shaped, not remotely 礼-shaped
    "rtk1349": {"character": "署", "keyword": "signature",  # was 日,老 -- an exact copy-paste of 暑(rtk1350)'s own
               "expected_part_ids": {"kangxi122", "rtk1345"}},  # value; IDS/render confirm the top is 罒 (net), not 日
    "rtk1696": {"character": "俸", "keyword": "stipend",  # was ｜,一,人,大,二 -- a literal stroke flatten instead of
               "expected_part_ids": {"kangxi9", "rtk1695"}},   # referencing 奉(rtk1695), which is already taught
    "rtk1697": {"character": "棒", "keyword": "rod",  # was ｜,一,人,木,二,大 -- same flatten-instead-of-reference bug
               "expected_part_ids": {"rtk1695", "rtk207"}},
    "rtk1768": {"character": "喉", "keyword": "throat",  # was 口,矢 -- dropped ユ(ktakana-yu) entirely instead of
               "expected_part_ids": {"rtk11", "rtk1767"}},  # referencing 侯(rtk1767), which is already taught
    "rtk1883": {"character": "跡", "keyword": "tracks",  # was 亦,足,亠 -- 亦 has no defining row anywhere in
               "expected_part_ids": {"kangxi8", "rtk1372"}},  # data.txt, silently dropped; aligned with its own
                                                                # siblings (変/蛮/恋/湾), which all use 亠 for this same
                                                                # primitive. Closed the last single-glyph gap in
                                                                # audit_radicals.py's undefined-terms check.
    # These 9 (found continuing the sequential sweep, 2026-09-05) are a DIFFERENT bug
    # shape than PERSON_RADICAL_HOSTS below: each already had a person-concept token,
    # just the WRONG one -- bare 人(rtk1023, the standalone "person" kanji) instead of
    # the compressed left-radical 亻(kangxi9) cjkvi-ids actually calls for. Both
    # resolve fine (no missing-part search miss), so check_person_radical_present's
    # "does any part resolve to kangxi9" test can't catch this class -- it takes the
    # bare id/character text literally correct-looking 人 as satisfying "has a
    # person," which is wrong for a decomposition, if not for search. Every one
    # confirmed by rendering the left-side shape before fixing (matches 保's 亻, not
    # standalone 人). 倹 additionally had a wrong non-亻 reference (合/"fit" instead
    # of the real 僉 shape shared with 剣/険) found the same way.
    "rtk2245": {"character": "侠", "keyword": "tomboy",
               "expected_part_ids": {"kangxi12", "kangxi8", "kangxi9", "rtk112", "rtk2"}},
    "rtk2259": {"character": "倅", "keyword": "son",
               "expected_part_ids": {"kangxi8", "kangxi9", "rtk10"}},
    "rtk1036": {"character": "伝", "keyword": "transmit",
               "expected_part_ids": {"kangxi9", "rtk2241"}},
    "rtk1045": {"character": "依", "keyword": "reliant",
               "expected_part_ids": {"kangxi9", "rtk423"}},
    "rtk1047": {"character": "個", "keyword": "individual",
               "expected_part_ids": {"kangxi9", "rtk622"}},
    "rtk1071": {"character": "傷", "keyword": "wound",
               "expected_part_ids": {"kangxi20", "kangxi9", "prim-katakana-no", "rtk1", "rtk1128", "rtk12"}},
    "rtk1106": {"character": "似", "keyword": "becoming",
               "expected_part_ids": {"kangxi3", "kangxi9"}},
    "rtk2260": {"character": "做", "keyword": "make",
               "expected_part_ids": {"kangxi9", "rtk355"}},
    "rtk212": {"character": "枠", "keyword": "frame",  # had NO data.txt override at all -- fell through to
               "expected_part_ids": {"rtk9", "rtk10", "rtk207"}},  # heisig-kanjis.csv's raw components text
                                                                     # verbatim, which includes "ninety" (a dead,
                                                                     # alias-less term -- CSV's own gloss for 卆's
                                                                     # 九+十 combination, not a real primitive
                                                                     # name) plus a legacy orphaned rad4.16 row.
                                                                     # Added an override: render-confirmed 枠 =
                                                                     # 木 + 卆(=九,十). Closed the last multi-char
                                                                     # gap in the same check -- 0 undefined terms
                                                                     # dataset-wide as of 2026-09-05.
}

# character -> hanzi id, spot-checking the 429-character Unihan self-reference backfill
# (2026-08-22) rather than re-verifying every one.
EXPECTED_HANZI_PRESENT = {
    "报": "hanzi-62a5", "万": "hanzi-4e07", "个": "hanzi-4e2a", "丰": "hanzi-4e30",
}

# kanji_id -> character, for kanji that are truly Unicode-IDS-atomic (no structural
# decomposition exists at all -- character maps to itself in cjkvi-ids) and whose
# live decomposition should therefore be empty. rtk11 (口) previously listed an
# unrelated 囗 as a "part"; CSV and cjkvi-ids both agree 口 is atomic (session
# 2026-08-30, found via cross-checking tools/heisig-google-check/results.jsonl).
# Most of the 67-item IDS-atomic-but-has-parts candidates found in that session are
# legitimate Heisig teachings (e.g. 東=日+木 despite Unicode treating 東 as atomic) and
# are deliberately NOT pinned here -- only genuinely-fixed bugs belong in this set.
EXPECTED_ATOMIC = {
    "rtk11": "口",
    # All confirmed atomic 2026-09-01: CSV components column is a single word that
    # names the whole glyph's traditional gloss (turtle/yawn/genie/snake), not a
    # parts list, and each is used elsewhere in data.txt as a whole-compound
    # reference already -- not touching those downstream hosts, just this row's
    # own stale parts.
    "rtk33": "凹",   # concave -- CSV components blank; a simple atomic pictograph
    "rtk34": "凸",   # convex -- CSV components blank; a simple atomic pictograph
    "rtk250": "兆",  # portent -- CSV: "turtle" (a single gloss word, not parts)
    "rtk505": "欠",  # lack -- CSV: "yawn" (a single gloss word, not parts)
    "rtk564": "己",  # self -- CSV: "snake"; visually distinct from 已/巳, not the same glyph
    "rtk736": "才",  # genius -- CSV: "genie" (a single gloss word, not parts)
    "rtk911": "臣",  # retainer -- CSV: "slave" (a single gloss word, not parts);
                     # render confirms it does not match kangxi171/隶 (also "slave")
    "rtk920": "巨",  # gigantic -- CSV: "Fafner" (a single gloss word, not parts)
    # 己/已/巳 host-by-host review (2026-09-01, daily check-in): confirmed via
    # cjkvi-ids that Japanese-standard glyphs consistently use 己 (not 已)
    # for what CSV calls "snake; self" across 11 hosts (see EXPECTED_DECOMPOSITIONS
    # below), and 巳 for the two that specifically call for the "snake" reading
    # (祀's JK variant, and 巳/rtk2200 itself). 已(rtk2944, "stop") had been
    # wrongly substituted into all of them -- it now has zero hosts left, which
    # surfaced a separate, pre-existing bug: 已's own keyword "stop" collides
    # with rtk396(止)'s identical keyword, so 已 doesn't resolve via its own
    # primary keyword at all (rtk396 wins the tie) -- flagged in the audit doc,
    # not fixed this session (out of scope for today's specific investigation).
    "rtk2200": "巳",  # sign of the snake -- was wrongly defined as "已" (a
                      # different character); genuinely atomic, confirmed distinct
                      # from 己/已 via render (top-right corner fully closed).
    "rtk2237": "巴",  # comma-design -- was 乙,已 (fabricated); Unicode-atomic,
                      # CSV components blank, render shows one continuous stroke.
    "rtk615": "羽",   # feathers -- was wrongly kangxi15("ice"); cjkvi-ids
                      # confirms 羽 = 习+习 (two mirrored strokes), no ice.
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


def check_atomic(conn) -> list[str]:
    failures = []
    for kid, char in EXPECTED_ATOMIC.items():
        row = conn.execute("SELECT character FROM kanji WHERE id = ?", (kid,)).fetchone()
        if row is None:
            failures.append(f"{kid} ({char}): kanji row no longer exists")
            continue
        if row["character"] != char:
            failures.append(f"{kid}: character changed from {char!r} to {row['character']!r}")
        detail = database.get_kanji_detail(conn, kid, viewer_id=None)
        for decomp in detail["decompositions"]:
            if decomp["parts_detail"]:
                got = [p["id"] for p in decomp["parts_detail"]]
                failures.append(f"{kid} ({char}): expected atomic (no parts) but "
                                 f"decomposition {decomp.get('label')!r} has {got}")
    return failures


# Every rtk* kanji whose cjkvi-ids decomposition has the standing person radical 亻
# as a direct top-level component (⿰亻X and friends) must carry a person-resolving
# part. 86 of them didn't (2026-09-05): the whole single-亻-radical family — 佐 侶 但
# 住 位 仲 体 件 仕 他 伏 仏 休 …  — came in from import_rtk.py's KRADFILE pass with
# 亻 dropped entirely, usually replaced by a stray ノ ("katakana no") proxy, so a
# "person" search missed every one of them. Same bug shape as 保 (rtk1072, fixed
# 2026-09-04) but dataset-wide. Structural rather than 86 individual pins, matching
# the KRADFILE-proxy invariant's philosophy for bulk fixes.
PERSON_RADICAL_HOSTS = [
    "rtk1024", "rtk1025", "rtk1026", "rtk1027", "rtk1028", "rtk1029", "rtk1030",
    "rtk1032", "rtk1033", "rtk1034", "rtk1035", "rtk1037", "rtk1038", "rtk1039",
    "rtk1040", "rtk1041", "rtk1042", "rtk1043", "rtk1044", "rtk1046", "rtk1048",
    "rtk1049", "rtk1050", "rtk1052", "rtk1053", "rtk1054", "rtk1056", "rtk1057",
    "rtk1059", "rtk1061", "rtk1062", "rtk1063", "rtk1064", "rtk1067", "rtk1068",
    "rtk1069", "rtk1074", "rtk1075", "rtk1078", "rtk1080", "rtk1083", "rtk1086",
    "rtk1087", "rtk1089", "rtk1090", "rtk1091", "rtk1107", "rtk1199", "rtk1224",
    "rtk1231", "rtk1245", "rtk1250", "rtk1267", "rtk1270", "rtk1493", "rtk1664",
    "rtk1667", "rtk1699", "rtk1729", "rtk1761", "rtk1769", "rtk1772", "rtk1836",
    "rtk1842", "rtk1858", "rtk1935", "rtk1962", "rtk1973", "rtk2008", "rtk2068",
    "rtk2105", "rtk2244", "rtk2247", "rtk2248", "rtk2249", "rtk2250", "rtk2251",
    "rtk2252", "rtk2253", "rtk2254", "rtk2255", "rtk2256", "rtk2257", "rtk2258",
    "rtk2972", "rtk2973",
]

_PERSON_PART_IDS = {"kangxi9"}  # 亻/⺅/人 all resolve here


def check_person_radical_present(conn) -> list[str]:
    failures = []
    for kid in PERSON_RADICAL_HOSTS:
        detail = database.get_kanji_detail(conn, kid, viewer_id=None)
        if not detail["decompositions"]:
            failures.append(f"{kid}: no decomposition at all (person radical fix regressed)")
            continue
        part_ids = {p["id"] for p in detail["decompositions"][0]["parts_detail"]}
        if not (part_ids & _PERSON_PART_IDS):
            failures.append(f"{kid} ({detail['character']}): missing the person radical "
                            f"亻 again (got {sorted(part_ids)})")
    return failures


# Same bug shape as PERSON_RADICAL_HOSTS, found 2026-09-05 continuing the sequential
# sweep: 12 kanji whose cjkvi-ids decomposition has 罒 (net/eye radical, kangxi122) as
# a top-level component but whose data.txt parts list dropped it entirely (買 was just
# 貝, 罰 just 言, etc. — the mnemonic component that actually makes them "net over X"
# was silently missing). Found via the same recursive-aware presence check built for
# the 亻 family, this time checking actual resolved part ids (not just literal token
# text) to avoid the false-positive trap that check_person_radical_present's sibling
# investigation hit with 擁/rtk1488 (a radical present transitively through a
# referenced compound isn't a bug).
NET_RADICAL_HOSTS = [
    "rtk894", "rtk895", "rtk896", "rtk950", "rtk1442", "rtk1573", "rtk1674",
    "rtk1764", "rtk2143", "rtk2188", "rtk2240", "rtk2737",
]

_NET_PART_IDS = {"kangxi122"}  # 罒/网 resolve here


def check_net_radical_present(conn) -> list[str]:
    failures = []
    for kid in NET_RADICAL_HOSTS:
        detail = database.get_kanji_detail(conn, kid, viewer_id=None)
        if not detail["decompositions"]:
            failures.append(f"{kid}: no decomposition at all (net radical fix regressed)")
            continue
        part_ids = {p["id"] for p in detail["decompositions"][0]["parts_detail"]}
        if not (part_ids & _NET_PART_IDS):
            failures.append(f"{kid} ({detail['character']}): missing the net radical "
                            f"罒 again (got {sorted(part_ids)})")
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


def check_alias_visibility_boundary(conn) -> list[str]:
    """Regression test for the 2026-08-31 resolve_alias() privacy leak: a public
    alias on someone else's private kanji must not let an unrelated viewer resolve,
    read, or (via contributions.py's _visible_kanji_id) write to that kanji. Inserts
    a throwaway private kanji + public alias inside an explicit transaction and rolls
    it back unconditionally, so this never leaves test data in the live DB regardless
    of outcome."""
    import contributions

    failures = []
    test_id = "usr-test-alias-boundary"
    test_alias = "zzz-regression-test-alias-boundary"
    owner_id, attacker_id = 8999001, 8999002

    conn.isolation_level = None
    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
            "VALUES (?, '?', ?, ?, 'private', 'ja-kanji')",
            (test_id, test_alias, owner_id)
        )
        conn.execute(
            "INSERT INTO aliases (kanji_id, alias, owner_id, visibility) VALUES (?, ?, ?, 'public')",
            (test_id, test_alias, owner_id)
        )

        leaked = database.resolve_alias(conn, test_alias, viewer_id=attacker_id)
        if leaked is not None:
            failures.append(f"resolve_alias leaked {leaked!r} to an unrelated viewer via a "
                             f"public alias on a private kanji")

        anon_leaked = database.resolve_alias(conn, test_alias, viewer_id=None)
        if anon_leaked is not None:
            failures.append(f"resolve_alias leaked {anon_leaked!r} to an anonymous viewer via a "
                             f"public alias on a private kanji")

        try:
            contributions._visible_kanji_id(conn, test_alias, attacker_id)
            failures.append("_visible_kanji_id let an unrelated viewer write to a private "
                             "kanji via its public alias (expected a 404)")
        except Exception:
            pass  # expected: raises (404) for an unrelated viewer

        owner_cid = database.resolve_alias(conn, test_alias, viewer_id=owner_id)
        if owner_cid != test_id:
            failures.append(f"resolve_alias broke the owner's own access: got {owner_cid!r}, "
                             f"expected {test_id!r}")
    finally:
        conn.execute("ROLLBACK")
        conn.isolation_level = ""

    return failures


def check_migration_atomicity() -> list[str]:
    """Regression test for the 2026-08-31 migration-atomicity fix (architecture
    review finding #2): a crash partway through a schema migration must not leave
    PRAGMA user_version pointing at a version whose schema changes are only
    partially applied (which would make the next startup fail on a duplicate
    ALTER TABLE / CREATE TABLE). Runs entirely against a throwaway temp-file DB —
    never touches the live kanji.db."""
    import tempfile
    import os

    failures = []
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        saved_migrations = list(database._MIGRATIONS)
        saved_db_path = database.DB_PATH
        try:
            database.DB_PATH = Path(path)
            database.init_db()
            conn = database.get_db()

            def faulty_v1(c):
                c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
                c.execute("CREATE TABLE sessions (token TEXT PRIMARY KEY)")
                raise RuntimeError("simulated crash mid-migration")

            database._MIGRATIONS[:] = [
                (v, faulty_v1 if v == 1 else fn) for v, fn in saved_migrations
            ]

            try:
                database.migrate_schema(conn)
                failures.append("migrate_schema() did not propagate the simulated "
                                 "mid-migration crash (a real crash would be silently "
                                 "swallowed)")
            except RuntimeError:
                pass  # expected

            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version != 0:
                failures.append(f"after a crash partway through migration v1, "
                                 f"user_version is {version}, expected 0 (unrolled-back "
                                 f"PRAGMA user_version bump)")
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            leaked = tables & {"users", "sessions"}
            if leaked:
                failures.append(f"after a crash partway through migration v1, "
                                 f"{sorted(leaked)} still exist -- the transaction "
                                 f"didn't roll back the partial schema change")

            # Restore the real migrations and confirm a retry (simulating a service
            # restart after the crash) completes cleanly with no duplicate-table error.
            database._MIGRATIONS[:] = saved_migrations
            try:
                database.migrate_schema(conn)
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version != max(v for v, _ in saved_migrations):
                    failures.append(f"retry after the simulated crash left "
                                     f"user_version at {version}, expected "
                                     f"{max(v for v, _ in saved_migrations)}")
            except Exception as e:
                failures.append(f"retry after the simulated crash raised {e!r} "
                                 f"instead of migrating cleanly from scratch")

            conn.close()
        finally:
            database._MIGRATIONS[:] = saved_migrations
            database.DB_PATH = saved_db_path
    finally:
        os.remove(path)

    return failures


def main():
    conn = database.sqlite3.connect(database.DB_PATH)
    conn.row_factory = database.sqlite3.Row

    all_failures = []
    all_failures += check_decompositions(conn)
    all_failures += check_hanzi_present(conn)
    all_failures += check_no_kradfile_proxy(conn)
    all_failures += check_atomic(conn)
    all_failures += check_no_self_reference(conn)
    all_failures += check_person_radical_present(conn)
    all_failures += check_net_radical_present(conn)
    all_failures += check_alias_visibility_boundary(conn)
    conn.close()

    all_failures += check_migration_atomicity()

    total_checks = (len(EXPECTED_DECOMPOSITIONS) + len(EXPECTED_HANZI_PRESENT)
                    + len(EXPECTED_ATOMIC) + len(PERSON_RADICAL_HOSTS)
                    + len(NET_RADICAL_HOSTS) + 4)
    if all_failures:
        print(f"FAILED: {len(all_failures)} problem(s) found across {total_checks} checks:\n")
        for f in all_failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"PASSED: all {total_checks} regression checks OK "
              f"({len(EXPECTED_DECOMPOSITIONS)} pinned decompositions, "
              f"{len(EXPECTED_HANZI_PRESENT)} hanzi presence spot-checks, "
              f"KRADFILE-proxy + self-reference + alias-visibility-boundary + "
              f"migration-atomicity invariants).")
        sys.exit(0)


if __name__ == "__main__":
    main()
