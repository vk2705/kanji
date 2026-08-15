# Search quality audit — August 2026

Record of a conversation-driven investigation into why parts-search sometimes
finds unexpected kanji or misses expected ones. Kept here (rather than only in
chat) because the next conversation is going to use this as the basis for a
"how should this project have been run from the start" discussion, and that
needs the actual findings and reasoning, not just a summary.

## How this started

User-reported symptom: "поиск находит странное и не находит ожидаемое" — the
data sources feel questionable and the matching algorithm produces surprising
results. Motivating example demanded on the spot: **cat (猫)**.

`backend/data.txt:530`: `rtk259:猫:cat:田,犯,艾`

- Real structure: 猫 = 犭(quadruped/dog) + 苗(seedling). 苗 is *already* a
  separate, correctly-decomposed entry: `rtk249:苗:seedling:田,艾`.
- Whoever wrote the cat override flattened 苗's own two parts (田 "field", 艾
  "mugwort") directly into cat's list instead of just referencing 苗/"seedling",
  and used 犯 (a real kanji meaning "crime") as an unlabelled stand-in for the
  dog-radical stroke — 犯 is never aliased to "dog" anywhere.
- Net effect: searching "dog" never finds 猫 (nothing is named "dog"), while
  searching "field" or "mugwort" does find it, unexpectedly, because of the
  flattening. Both reported symptoms, same root cause, one entry.

That single example turned out to be representative of two systemic patterns
across the whole dataset, found by building a throwaway copy of the database
through the *real* import pipeline (`backend/database.py::import_data()`, via
a new script, `backend/audit_decomposition.py`) and analyzing the actual
merged/expanded parts lists production search would use — not a
hand-reconstructed guess at the merge logic.

## Aside: is the underlying goal even sound?

Before going further into data quality, it was worth checking the premise
wasn't already confused. Restated goal: a user meets an unfamiliar kanji,
recognizes a piece of it (official radical name, Heisig primitive name, or
their own personal mnemonic), and searches by that remembered name to find
the character.

Conclusion: the goal is sound and is literally the app's headline feature
(README: "search by primitives"). The schema already has reasonable building
blocks for it — kanji glyphs are self-aliased so typing a recognized
character works, and the contributions API lets a user attach a personal
alias to any visible kanji or decomposition part. The gap is that
official-name / Heisig-name / personal-name currently all live in one flat,
untagged `aliases` synonym set with no record of which vocabulary a given
alias came from — flagged as **worth addressing but is a separate, larger
task** (schema change + backfill classification + UI), not folded into this
audit. Deferred, not resolved.

## Finding 1 — 66 radicals have no name anywhere in the system

**2,262 of 3,000 `rtk*` kanji (75%)** list at least one part term that never
resolves to any kanji row or alias — a bare glyph nobody can search for by
name, in any vocabulary. Full list and per-radical counts were captured in
the audit report sent to the user (`ノ`×321, `｜`×314, `ハ`×235, `亠`×222, down
to single-digit tails like `黽`×1 — 66 distinct glyphs total). Almost all are
standard Kangxi radical forms.

This is a structural gap, not a per-entry mistake: for these 66 radicals, the
"user remembers the official/Heisig name" search flow described above simply
cannot work, because no name was ever recorded for them in any layer
(`heisig-kanjis.csv`, `data_from_pdf.txt`, or `data.txt`).

### Lead: this data already half-exists, twice, unused

`backend/data.txt` contains **252 `radN.M` entries** (e.g.
`rad2.17:?:power,muscle`, `rad2.24:?:cliff`) that are clearly an attempt at
exactly this — naming glyph-less primitives — but **250 of 252 have
`character` left as the placeholder `?`**, so they never resolve to anything
(`prim_chars` in `database.py::import_data()` only registers a primitive's
glyph if the character field isn't `?`/`??`/empty). One of the two that *is*
set is wrong: `rad1.2` uses ASCII `|` (U+007C) while every actual
decomposition uses the fullwidth `｜` (U+FF5C) — different codepoints, never
matches.

These 252 entries are a **verbatim copy of `cgi-bin/data`** — the data file
of the legacy Perl app (`cgi-bin/` + `html/kanji/`, kept in this repo as
"reference only, not part of the active stack" per `CLAUDE.md`). The
migration to the FastAPI/React stack carried this file forward byte-for-byte,
placeholders and all, rather than resolving it.

`html/kanji/pics/` (25 images: `cliff.PNG`, `divining-rod.PNG`,
`walking-legs.PNG`, `turtle.PNG`, `lidded-crock.PNG`, `zoo.PNG`, `mist.PNG`,
etc.) appears to be the legacy app's illustrations for glyph-less primitives
— several names correspond directly to aliases already sitting in the `rad*`
entries above (`cliff`, `divining rod`, `human/animal legs`). The current
schema already has `kanji.image_url` for exactly this purpose (pictures
standing in for primitives with no Unicode glyph) — these images were never
attached to anything in the new app.

**Caveat for later**: several of those image/alias names (`lidded-crock`,
`thanksgiving`, `zoo`, `breasts`) read like distinctive Heisig-book primitive
names rather than generic radical names — the same copyright concern
`CLAUDE.md` already flags for mnemonic story text ("The Heisig mnemonic
story text from the book is still not stored (copyright)") may apply here
too. Not resolved — needs a decision before reusing these verbatim.

## Finding 2 — real kanji misused as unaliased visual proxies

A different, smaller class: part terms that *do* resolve, but only because
the glyph coincidentally matches an unrelated, fully-fledged kanji entry — so
`expand_part_terms()` (in `database.py`) silently appends that kanji's own
irrelevant keyword to the decomposition, and it becomes an accidental search
hit for the host character.

| Glyph | Its own (irrelevant) keyword | Hosts | Confirmed via |
|---|---|---|---|
| 乞 | "beg" | 167 kanji (牧 breed, 攻 aggression, 敗 failure, 故 happenstance, ...) | pattern review |
| 化 | "change" | 137 kanji (佐 assistant, 侶 partner, 但 however, ...) | pattern review |
| 刈 | "reap" | 54 kanji (則 rule, 別 separate, 測 fathom, ...) | rtk2359 捌 (deal with) — "hand" missing entirely, 刈 stands in unaliased |
| 買 | "buy" | 31 kanji (夢 dream, 蔑 revile, 聴 listen, ...) | rtk897 寧 (rather) — 買 doesn't match any visible component |
| 犯 | "crime" | 27 kanji (荻 reed, 狩 hunt, 猫 cat, 獄 prison, ...) | rtk259 猫 — the original example |

Lower-confidence, not independently verified this pass: 忙 ("busy", 41),
込 ("crowded", 77 — may be legitimate, 込 is a real common Heisig primitive),
邦 ("home country", 19), 礼 ("salutation", 21).

Checked and rejected one hypothesis: that 乞 is simply a synonym/stand-in for
攵 (also independently undefined, Finding 1). If so they'd never co-occur in
one decomposition, but 50 entries contain *both* 乞 and 攵 — they're not a
clean 1:1 substitution, so each proxy needs its own investigation into what
it's actually standing in for, not a bulk assumption.

## Finding 3 — mechanical/structural bugs (small, unambiguous)

- **rtk91 昭** (shining): parts `?, ?, pipe, minus` — the unidentified-glyph
  placeholder `?` listed twice. `data.txt:281`.
- **rtk1261 斗** (big dipper): parts `big dipper, measuring cup, big dipper,
  the plough, drop, ten, needle` — the kanji's own keyword is listed as one
  of its own parts, twice.
- **rtk1743 門** (gates): empty parts despite 8 strokes, initially flagged by
  an automated stroke-count heuristic — on review this is **not** a bug: 門
  is legitimately treated as an atomic Heisig primitive (used whole inside
  間/聞/開/etc.). Noted so a future automated pass doesn't re-flag it.

## Sample individual verdicts (spot-review, not exhaustive)

| Kanji | Verdict | Note |
|---|---|---|
| rtk259 猫 (cat) | suspicious | Finding 2 |
| rtk2359 捌 (deal with) | suspicious | Finding 2 |
| rtk897 寧 (rather) | suspicious | Finding 2; 一+亅 correctly spell 丁, that part is fine |
| rtk612 歓 (delight) | ok | 欠 correctly matches the right-side radical |

A full row-by-row LLM verdict pass over the ~700 kanji untouched by either
finding is possible via `backend/audit_decomposition.py` (committed, needs
`OPENAI_API_KEY`) but was deprioritized — Findings 1 and 2 already explain
the bulk of the reported symptoms and are cheaper to fix first.

## Fix plan (as discussed, not yet executed)

**Finding 1**
1. Reconcile the 66 undefined glyphs against the 252 existing `rad*` ghost
   entries (and the legacy `html/kanji/pics/` images) — fill in `character`
   (and `image_url` where a legacy picture exists and the copyright question
   above is resolved) instead of writing from scratch where a match exists.
2. For glyphs with no existing entry, add new `radN.M` lines with an
   official Kangxi radical name as the primary alias (public-domain,
   sidesteps the Heisig-text copyright concern).
3. Rebuild `kanji.db` locally (delete + restart, per `CLAUDE.md`), spot-check
   via `rtk.py parts <name>`, and re-run the undefined-glyph check to confirm
   the 2,262-kanji count drops.

**Finding 2** (depends on Finding 1 being done first, so a correctly-named
primitive exists to redirect to)
1. Per proxy character, determine what it's actually standing in for by
   looking at what its hosts visually share — case by case, not assumed
   uniform (see the 乞/攵 co-occurrence check above).
2. Scripted find/replace of the proxy term with the correct primitive
   reference across affected `data.txt` lines (~416 individual occurrences
   across the 5 confirmed proxies alone) — not hand-edited one by one.
3. Rebuild + spot-check that the proxy's own irrelevant keyword no longer
   surfaces as a search hit for its former hosts.

**Risks noted**: no test suite exists for this repo; verification is manual
(`rtk.py` + rebuild) only. The 252 ghost entries vary wildly in reliability
(some aliases are clearly personal jokes, e.g. `"obama,data, Mister T."`) so
Phase 1 needs actual review, not a blind bulk-fill.

## Architecture decision (agreed after this doc was written, 2026-08-13)

Not yet executed when this doc was first written; recorded here as soon as
the decision was made so it survives context resets. Owner + agent agreed
the fix plan below should be implemented on top of a redesigned storage
model, not by continuing to patch the flat `data.txt` → single
`owner_id=1` decomposition pipeline as-is:

1. **Sources become multiple decomposition/alias owners, not one flat
   `owner_id=1`.** The `decompositions`/`aliases` tables already support
   multiple owners per kanji (built for user contributions). Reuse that
   machinery for system data too: introduce source pseudo-owners (e.g.
   `heisig4`, `heisig6`, `official-radicals`, `krad`) instead of collapsing
   every source into one system decomposition at import time. This directly
   fixes the *class* of bug Finding 2 describes (a decomposition silently
   flattening another entry's parts into itself), not just the specific
   instances found so far — once each source is its own decomposition
   owner, "flattening 苗's parts into 猫's own list" isn't something import
   would ever do.
2. **Hierarchy is resolved at query time, not flattened at import time.** A
   decomposition stores one level of parts; if a part itself has its own
   decomposition, search/detail code resolves it recursively at query time.
   This is a deliberate departure from current `import_data()` behavior
   (CSV components arrive pre-expanded). Performance is a non-issue at this
   dataset's scale (single user, ~3000 rows) — correctness and
   maintainability win over the micro-optimization the old pre-expansion
   was never actually needed for.
3. **User control over source scope**: search endpoints get a `sources`
   filter analogous to the existing `script` filter, so a user can restrict
   matching to e.g. "Heisig only" or "official radicals only".
4. **Personal/user-invented primitives are unaffected** — they're just
   another value on the same source axis (owned by a real user id, not a
   source pseudo-owner), already fully supported by the existing
   contributions API. This redesign must compose with that flow, not route
   around it.
5. **Copyright is explicitly not a concern** for Heisig-derived primitive
   names, per the owner. Do not self-censor on that basis anywhere in this
   fix (including radical/primitive naming below).

This is a bigger structural change than either Finding's original fix plan
assumed (both were written against the old flat-import model). It has not
been executed yet as of this entry — see the progress log below for what's
actually been done vs. still pending. Treat the "Fix plan" section above as
superseded in *mechanism* (system data will end up multi-owner, not more
`data.txt` overrides) even though the *content* work it describes (name the
66 radicals, fix the 5 proxy characters) is still exactly the right content
work to do — it's the storage that changes, not which radicals need names.

## Progress log

Update this section every working session: what got done, what's next, any
judgment calls and why. Read it first before starting new work.

### 2026-08-13 — session 1

- Recorded the architecture decision above (agreed in conversation, not
  written down until now).
- **Finding 1, Phase 1 (partial)**: wrote `backend/audit_radicals.py` — a
  deterministic (no API key), committed version of the "undefined part
  term" check used to produce this doc's Finding 1 numbers. Re-running it
  found **69** single-glyph undefined terms (not 66 — small drift from
  whatever ad hoc query produced the original number; not investigated
  further, the discrepancy doesn't change the shape of the problem).
  - Reconciled **16** of those 69 against existing `data.txt` `radN.M`
    ghost entries with confident, non-joke semantic matches: fixed their
    `character` field from the `?` placeholder to the real glyph (`rad1.2`
    → `｜` fullwidth, fixing the exact U+007C/U+FF5C bug flagged above;
    `rad1.3`→丶, `rad2.6`→儿, `rad2.12`→冫, `rad2.22`→卜, `rad2.23`→卩,
    `rad2.24`→厂, `rad2.25`→ヨ, `rad3.6`→夂, `rad3.15`→尢, `rad3.17`→屮,
    `rad3.20`→巛, `rad3.27`→廾, `rad3.31`→彑, `rad4.32`→爿, `rad4.45`→毋).
    Kept each entry's existing legacy aliases (including jokes like
    `rad3.15`'s "chihuahua with one human leg" — harmless once the entry
    also resolves, and it's genuinely funny) and added an official/plain
    name alongside where the legacy alias alone wasn't a search-friendly
    term.
  - Added **42 new** `rad{n}` entries (ids `rad1001`–`rad1042`, a plain
    integer scheme per `CLAUDE.md`'s documented `rad{n}` format — the
    legacy `radN.M` dotted scheme was the *old Perl app's* convention, not
    this project's) for glyphs with no usable existing ghost entry. Named
    them with the standard, public-domain Kangxi radical English name
    (亠 lid, 冂 border, 冖 cover, 亅 hook, 尸 corpse, 戈 spear, 禾 grain, 隹
    short-tailed bird, 攵 rap, 广 dotted cliff, 几 table, 凵 container, 彳
    step, 囗 enclosure, 艮 stopping, 彡 bristle, 殳 weapon, 匚 box, 豕 pig,
    歹 death, 弋 stake, 廴 long stride, 虍 tiger, 癶 footsteps, 釆
    distinguish, 隶 reach, 聿 brush, 舛 oppose, 韋 tanned leather, 耒 plow,
    豸 badger, 爻 trigrams, 韭 leek, 鬲 cauldron, 气 steam, 髟 long hair, 鬯
    sacrificial wine, 黽 frog, 幺 tiny, 宀 roof), plus two non-Kangxi-radical
    real characters that were legitimate primitive parts with no registered
    name at all: 艾 "mugwort" (the exact one from this doc's own 猫/苗
    example — it was never itself resolvable even though it's a correct
    part) and 厶 "cocoon" (well-established informal primitive name, not a
    top-level Kangxi radical but a common decomposition component).
  - **Result**: single-glyph undefined terms dropped 69 → **11**
    (`ノ ハ 并 扎 杰 个 阡 疔 マ 禹 ユ`), and kanji with ≥1 unresolved part
    dropped **2,262 → 1,043** (rebuilt DB, recount via the same query
    Finding 1 used).
  - **Deliberately deferred, not fixed** — the remaining 11: `ノ ハ ヨ`-style
    katakana primitives (`ノ` slash, `ハ`, `マ`, `ユ`) are primitives Heisig's
    book does name explicitly, but I don't have high enough confidence in
    the exact book terminology to assign names without risking new
    Finding-2/3-style bugs (a wrong name is worse than no name — it looks
    resolved but misleads). `并 扎 杰 个 阡 疔 禹` are all real CJK
    characters (阡="path between fields", 疔="boil/carbuncle", 禹="Yu, the
    mythical emperor", etc.) that read as visual-proxy misuse similar to
    Finding 2, not straightforward unnamed radicals — each needs the same
    "what is this actually standing in for" investigation Finding 2's fix
    plan already calls for, so deferring them there rather than guessing.
    **Open question for the owner**: if you have the RTK book (or PDF)
    handy, the katakana primitives' exact Heisig names would resolve 4 of
    these 11 immediately and safely.
  - Verified: rebuilt `kanji.db` from scratch, `python3 rtk.py detail
    rtk259/rtk2359/rtk897` still show the exact Finding 2 symptoms
    described above (untouched, as expected — Finding 2 not started yet),
    `rtk.py parts cliff/roof/lid/mugwort` all return results now (0 before),
    `audit_radicals.py` count matches the 69→11 drop.
- **Not started**: Finding 1 Phase (image reconciliation against
  `html/kanji/pics/`, deferred — needs the copyright-flavor judgment call
  noted in Finding 1 above, plus it's lower value than the name gap itself
  which is now mostly closed), Finding 2 (proxy character fix — explicitly
  gated on Finding 1 being far enough along that a correctly-named target
  exists to redirect to, which is now true for 4 of 5 proxies: 乞/化/刈/犯
  all have named replacements available or need the same "what does this
  stand in for" pass; 買 already resolves as itself, same as before), and
  the full multi-owner-decomposition/query-time-resolution architecture
  migration described above (this session's fix stayed inside the existing
  flat `data.txt` → `owner_id=1` pipeline since that's what Finding 1's
  concrete task needed; the architecture migration is a separate, larger
  piece of work for a future session).
- **Next session should**: either (a) start the actual architecture
  migration (source pseudo-owners + query-time recursive resolution +
  `sources` filter — this is the big one, budget multiple sessions), or
  (b) continue content work first (Finding 2's proxy-character fixes, now
  partially unblocked) and defer the storage migration until more content
  fixes are queued up behind it. Not yet decided which order is better;
  whoever picks this up next should make that call and record it here.

### 2026-08-13 — session 2

- Prompted by the owner googling "rtk1495 kanji" and finding Heisig's book
  groups it as prefecture(県) + thread(糸) + heart(心), while our data had
  flattened it to raw strokes (`ノ,糸,幺,小,心,目`, from a `data.txt`
  override — see the file, this predates both sessions). Fixed by hand as a
  worked example, not a scripted pass:
  - `backend/data.txt` rtk1495 line and the live local `kanji.db`
    (`decomposition_id=547`) now both list `県,prefecture,糸,thread,心,heart`.
  - Along the way, found that `expand_part_terms`'s char→keyword
    auto-lookup (`_build_char_lookup`) is **not script-scoped**: for a
    glyph that exists as both an `ja-kanji` row and a `zh-*` row (~2,628 of
    them, see `CLAUDE.md`), it can silently resolve to the Chinese keyword
    instead of the Heisig one, non-deterministically (dict-insertion-order
    dependent). Worked around it for rtk1495 by writing terms explicitly
    instead of relying on auto-expansion; **not fixed at the source**.
  - Added a pseudo-user account `ai-mnemonics` (id 9 in the local DB, no
    password/`auth_provider='ai'`, can never log in) and wrote one
    original (not book-derived) mnemonic story for rtk1495 under it,
    public. Deliberately not `owner_id=1` — system/Heisig-sourced data and
    AI-generated content should stay visibly distinct, same reasoning as
    Finding 1's copyright note above. This is a new precedent, not yet
    applied anywhere else.
  - Owner also asked, separately, for decomposition *display* to stop
    flattening to only atomic primitives — e.g. show "prefecture" as a
    chip on 懸's decomposition, but also let the user drill into
    prefecture's own parts (目 eye + ...), rather than only ever showing
    the fully-flattened `県,prefecture,糸,thread,心,heart` list. This is
    exactly the "hierarchy resolved at query time, not flattened at
    import time" item in the architecture decision above — it's no longer
    just a nice-to-have, it's a concrete product requirement, which
    answers session 1's open "which order is better" question: the
    recursive-resolution piece of the migration needs to happen for this,
    specifically (doesn't require the full source-pseudo-owner piece too,
    but the two were designed together).

**Queued for a future session (not started, as of end of session 2)**:
1. ~~Hierarchical decomposition display~~ — **done, same session**: this
   list was written slightly ahead of the commit that closed it out
   (`6cdf7b9`, same day) and never got updated to say so. Correcting the
   record here rather than editing session 2's text above: `database.py`'s
   `_resolve_parts_detail` (recursive, depth-capped, cycle-guarded) plus
   `main.py`'s detail endpoint and `KanjiDetail.jsx`'s `PartChip` all
   shipped in that commit. Verified as actually present by reading the
   current code at the start of session 3, not just trusting this log —
   worth remembering that a log entry can be stale even within the same
   day if written before the commit that finishes the work.
2. ~~Script-scope bug in `expand_part_terms`/`_build_char_lookup`~~ —
   **done, session 3** (see below).
3. **Bulk decomposition audit** — extend the rtk1495 fix (flattened
   strokes → book-style primitive grouping) across the dataset instead of
   one kanji at a time. `audit_decomposition.py` (LLM-based, needs
   `OPENAI_API_KEY`) is built for exactly this but has never been run
   against the real API; running it is the natural first step. Now
   unblocked (item 2 was the correctness prerequisite for this).
4. **Bulk original-mnemonic generation** under the `ai-mnemonics` pseudo
   account for kanji that have no story yet — same "one kanji at a time,
   by hand" caveat as #3; needs a scoping decision (all ~2,900? JLPT
   levels first? something else) before running it at scale.

### 2026-08-14 — session 3

- Pulled latest, found session 2's log listed item 1 above as "not started"
  when the code (and that session's own commit message) showed it was
  actually shipped — see the strikethrough correction above. Lesson for
  future sessions: trust the code over the log when they disagree, and
  write the log entry *after* the commit that does the work, not before.
- **Fixed the script-scope bug in `expand_part_terms`/`_build_char_lookup`**
  (queued item 2, found in session 2): `_build_char_lookup` now returns
  `character -> [(kanji_id, script), ...]` (a list of candidates) instead
  of collapsing straight to a single winning id, and `expand_part_terms`
  takes a new optional `script_group` ("ja"/"zh"/`None`, same values as
  `_script_group()`) to pick the candidate matching the decomposition's
  own script when a glyph is ambiguous — falling back to the first
  candidate when `script_group` is unset or matches nothing, same
  disambiguation `_resolve_parts_detail` already does at read time. Threaded
  through all three call sites: `import_data()` now passes
  `script_group="ja"` (it only ever writes ja-kanji rows), `import_hanzi.py`
  now passes `script_group="zh"`, and `create_decomposition()` (the
  contributions-API write path) derives it from the target kanji's own
  `script` column, same pattern `_resolve_parts_detail` uses for
  `parent_group`.
  - **Verification caveat**: this sandbox can't run `import_hanzi.py`
    end-to-end (it downloads `Unihan.zip` + `cjkvi-ids` from
    unicode.org/GitHub — not attempted, would be slow and this session
    didn't need real hanzi data to verify the fix). Verified instead with a
    synthetic repro: inserted a fake `zh-Hans` row sharing 一's glyph with a
    different keyword into the rebuilt shadow DB, confirmed
    `expand_part_terms(term, script_group="ja")` picks rtk1's "one" and
    `script_group="zh"` picks the fake Chinese keyword — both fail without
    the fix (old code always picked whichever the dict-building query
    returned last). Also rebuilt `kanji.db` from scratch and re-ran
    `rtk.py detail rtk259/rtk1495` and `audit_radicals.py` to confirm no
    regression on the ja-kanji-only path (identical output to session 2's
    numbers: 11 single-glyph undefined terms, same rtk1495 grouping).
    **Not yet verified against a real, fully-seeded hanzi DB** — whoever
    next runs `import_hanzi.py` for real (or has one already seeded, e.g.
    the live production DB) should spot-check a handful of the ~2,628
    dual-script glyphs' decompositions to confirm the fix holds outside the
    synthetic repro.
- Did not start the bulk decomposition audit (item 3) or bulk mnemonic
  generation (item 4) this session — the script-scope fix was the whole
  chunk for this wake-up, per the brief's "steady incremental progress,
  not everything in one sitting."

**Next session**: item 3 (bulk decomposition audit via
`audit_decomposition.py`) is the natural next step — needs `OPENAI_API_KEY`
set in the environment, which hasn't been available in any session so far;
check whether it's set before assuming this is blocked again. If still
unavailable, the deterministic Finding 1 leftovers (11 single-glyph terms:
`ノ ハ 并 扎 杰 个 阡 疔 マ 禹 ユ`, see session 1's notes above) or Finding 2's
five proxy-character fixes (乞/化/刈/買/犯, now largely unblocked by session
1's radical naming) are good API-key-free alternatives.

### 2026-08-14 — session 4

- Triggered by the owner asking why searching "old" doesn't find 故 (happenstance,
  `rtk355`) — tracing it surfaced 乞 ("beg") sitting unaliased in 故's parts list,
  i.e. Finding 2 in the wild. Went to actually root-cause Finding 2 rather than
  continue treating it as "needs case-by-case investigation, uniform assumption
  rejected" as the original doc text said.
- **Root cause of all 5 confirmed proxies (乞/化/刈/買/犯), confirmed empirically**:
  fetched the real upstream KRADFILE (`ftp.edrdg.org/pub/Nihongo/kradfile.gz`) and
  checked it directly, rather than continuing to guess from symptoms. Its own header
  comment: "the elements used have been drawn from JIS X 0208 — where the element
  alone is not in JIS X 0208, a kanji which contains the element is used instead."
  All 5 are exactly this — KRADFILE's own stand-in glyphs for stroke shapes with no
  JIS X 0208 codepoint, not an error `import_rtk.py`/`data.txt` introduced. This
  reverses the original doc's "not a clean 1:1 substitution" framing: it's not that
  each proxy needs a different real primitive identified per host, it's that none of
  them ever stood for one consistent thing — they're a generic "no exact glyph
  available" placeholder in the source data itself, used across whatever unrelated
  kanji happened to need it. `犯`'s own KRADFILE entry even lists itself as one of
  its own components, confirming it's an index artifact, not a decomposition.
- **Second-order bug found while fixing**: `expand_part_terms` auto-expands each raw
  proxy glyph into an *additional* sibling row holding the glyph's own (irrelevant)
  keyword at import time — e.g. every 犯 row was paired with a stored "crime" row.
  Deleting only the glyph rows would have left "crime"/"beg"/"change"/"reap"/"buy"
  behind as orphaned search hits. Verified (on the pre-fix DB) that within
  `owner_id=1` + `ja-kanji` scope, every occurrence of these 5 keyword strings
  paired exactly 1:1 with the glyph's own occurrences (167/137/54/31/27, matching
  each proxy's known host count) — safe to delete both together in that scope.
  Outside that scope (unscoped, including `zh-*` hanzi rows) the pairing did *not*
  hold cleanly (e.g. "change" appeared in 24 hanzi decompositions with no 化 glyph
  present) — a reminder that this fix must stay scoped to `ja-kanji`, not generalized
  by pattern-matching the keyword string alone.
- **Fix executed**, not just diagnosed:
  - `backend/data.txt`: stripped the 5 glyphs from all 397 affected lines (scripted,
    not hand-edited — see git diff). One line (`rtk1007` 竹 "bamboo") lost its only
    listed part and now correctly shows no decomposition, same pattern as the
    already-documented `rtk1743` 門 case (atomic Heisig primitive, not a bug).
  - New script `backend/fix_kradfile_proxies.py`: deletes both the glyph rows and
    their paired auto-expanded keyword rows directly from an already-seeded
    `kanji.db`, scoped to `owner_id=1 AND k.script='ja-kanji'` — deliberately leaves
    user contributions alone (real editorial choice, not this artifact) and leaves
    `zh-*` hanzi rows alone (`import_hanzi.py` sources decompositions from cjkvi-ids
    IDS data, a different and stricter source where these same 5 characters can be
    genuine drawn components, not a JIS-substitution artifact).
  - Ran it for real: 416 glyph rows + 416 paired keyword rows removed (832 total),
    matching the original doc's "~416 occurrences across the 5 confirmed proxies"
    estimate exactly.
  - **Discovered mid-task that this box has no separate dev/prod database** —
    `database.py`'s `DB_PATH` is always `Path(__file__).parent / "kanji.db"`, no env
    override, and `kanji-backend.service`'s `WorkingDirectory` is the same
    `backend/` folder. What was being verified as "local" was already production.
    Backed up (`cp kanji.db kanji.db.bak-<timestamp>`) before patching regardless.
  - Verified live against the running production API after the fact: `GET
    /kanji/rtk259` (猫 cat) no longer lists 犯/crime in its decomposition; `POST
    /search/parts {"parts":["crime"]}` now returns only 犯 itself, not the 27
    unrelated former hosts. Also spot-checked via `rtk.py`: "beg"/"buy" parts
    searches now return only hanzi entries (untouched, different valid source) plus
    乞/買 themselves.
- **Not done this session**: `data.txt`'s fix and `fix_kradfile_proxies.py` are
  uncommitted as of this entry — ask before committing/pushing next session if not
  already done. The full multi-owner-decomposition architecture migration
  (source pseudo-owners + `sources` filter, items 1/3/4 from the architecture
  decision above) is still not started; this session's fix stayed inside the
  existing flat `data.txt` → `owner_id=1` pipeline, same as session 1, because the
  concrete bug (Finding 2) turned out to have a clean, well-evidenced answer that
  didn't need the bigger migration to fix correctly — the migration is still the
  right call for *preventing this class of bug*, just wasn't required to *fix this
  instance* of it.

- **Named the remaining 11 Finding-1 single-glyph terms** (`ノ ハ 并 扎 杰 个 阡 疔 マ 禹 ユ`),
  closing out Finding 1's deliberately-deferred list from session 1. Split into two
  groups by the same KRADFILE-header investigation used for the proxy fix above:
  - **7 are KRADFILE JIS-substitutes** (并 扎 杰 个 阡 疔 禹) — found in the *same*
    documented substitution table used above, which also cross-references each
    substitute glyph to its real Unicode CJK Radical Supplement / Kangxi Radical
    codepoint. This incidentally cross-validated the proxy fix: 犯→"CJK RADICAL DOG"
    (⺨) matches the doc's original 猫/dog-radical example exactly; 化→"CJK RADICAL
    PERSON" (⺅), 刈→"CJK RADICAL KNIFE TWO" (⺉), 買→"CJK RADICAL NET TWO" (⺲) all
    match their hosts' visual structure. Named these 7 after their verified radical
    identity (`rad1043`-`rad1049`: "person radical", "eight radical", "hand
    radical", "mound radical", "fire radical", "sickness radical", "track
    radical") rather than deleting them like the first 5, since — unlike those 5 —
    none of them collided with an existing unrelated kanji's own keyword, so there
    was no accidental-search-hit problem to fix by removal; they just needed a name.
  - **4 are katakana-shaped glyphs** (ノ ハ マ ユ) *not* in KRADFILE's substitution
    table — i.e. used directly, not as a stand-in for a missing JIS element,
    matching session 1's note that these are primitives Heisig's book names
    explicitly. Named literally by katakana identity (`rad1050`-`rad1053`:
    "katakana no/ha/ma/yu") rather than guessing the Heisig term, per owner's
    explicit request: decomposition should show the glyph (so it's visible and
    clickable) and resolve to *some* honest, verifiable name; the owner will attach
    the actual book primitive name as their own alias on top via the contributions
    flow, rather than have an agent guess it and risk a wrong-name repeat of the
    original Finding-2 mistake.
  - Inserted directly into the live `kanji.db` (`kanji` + `aliases` rows,
    `owner_id=1`, `script='ja-kanji'`, public) — no `parts` table changes needed,
    since the raw glyph terms were already present in every host's decomposition
    and only lacked a resolvable name. Added the same 11 lines to `data.txt` for
    future-reseed parity. Verified via `audit_radicals.py`: single-glyph undefined
    count is now **0** (was 11); confirmed live via the actual detail API (not just
    `rtk.py`, which reads raw `parts` text and doesn't reflect alias-table
    resolution) that e.g. `rtk1311` 矛 (halberd) now resolves マ → "katakana ma"
    (`rad1052`), clickable.
- **Owner asked, separately**: should the future `sources` filter (architecture
  decision item 3) include KRADFILE as a selectable checkbox alongside Heisig/
  official-radicals? Yes — this was already the plan (item 1 names `krad` as one of
  the proposed source pseudo-owners) and this session is a concrete argument for
  prioritizing it: every fix this session existed only because KRADFILE's
  mechanical, lookup-oriented decomposition got merged into the same undifferentiated
  `owner_id=1` bucket as Heisig's actual taught primitives.

**Open follow-up for a future session**: the same "KRADFILE JIS-substitution"
mechanism that produced these 5 confirmed proxies almost certainly produced others
that just haven't been pattern-reviewed yet — worth writing a deterministic check
(cross-reference every `rtk*` decomposition's part terms against a downloaded
KRADFILE, flag any part glyph whose KRADFILE host list is large/visually
unrelated) rather than waiting for more one-off user reports like this session's
"old"/happenstance question. `backend/audit_radicals.py` is the natural place to
add this as a second check mode.

### 2026-08-14 — session 5

- Owner asked the *exact same* "old"/happenstance question again. Turned out
  session 4 hadn't actually closed it: it found and fixed a real bug in
  故's decomposition (the unaliased 乞 proxy) but that wasn't the bug behind
  the reported symptom. Confirmed by rebuilding `kanji.db` fresh from
  current `data.txt` (the on-disk DB left over in this container was stale
  — still showed 乞 — a reminder to always rebuild from source before
  trusting a query against whatever `kanji.db` happens to be sitting on
  disk, in this sandbox "production" claims from past sessions notwithstanding)
  and running the actual search: `古` alone matched "old", `故` didn't.
- **Root cause, this time correctly identified**: `rtk355`'s override was
  `古,十,攵`... no — `口,十,攵`. `古` ("old") is itself `rtk16`, already
  correctly named and searchable, decomposed as 十(ten)+口(mouth). Whoever
  wrote `故`'s override flattened `古`'s own two sub-parts directly into
  `故`'s list instead of referencing `古`/"old" — **the exact same flattening
  bug class as this doc's opening 猫/苗 example**, just a different glyph.
  Grepped `data.txt` for every other line listing `口` immediately followed
  by `十` (40 hits) and checked each by hand against the real kanji
  structure (not a blind find/replace — several are coincidental: e.g.
  `rtk1281` 噴, `rtk1979` 哺, and `rtk2291` 叶 all legitimately contain a
  real, separate 口 "mouth" radical that has nothing to do with 古, and
  several others — the `辟`-based cluster in 壁/璧/癖/譬, the `啇`-based
  cluster in 嫡/滴/敵/摘 — are a *different* flattening bug worth its own
  pass later, not this one). **19 lines confirmed as genuine `古` flattening
  and fixed**: `rtk109` 克, `rtk159` 湖, `rtk219` 枯, `rtk239` 苦, `rtk355`
  故, `rtk622` 固, `rtk623` 錮, `rtk1047` 個, `rtk1143` 居, `rtk1144` 据,
  `rtk1145` 裾, `rtk2185` 箇, `rtk2260` 做, `rtk2317` 姑, `rtk2537` 胡,
  `rtk2615` 瑚, `rtk2692` 糊, `rtk2776` 醐, `rtk2782` 鋸.
  - Where the correct grouping was actually a *deeper* existing kanji
    rather than `古` directly — `固`(=囗+古), `胡`(=古+月), `居`(=尸+古),
    `故`(=古+攵) are each themselves the parent of further compounds — the
    fix references that kanji instead of re-flattening to `古` a second
    time (e.g. `錮`→`金,固` not `金,古,囗`; `瑚`→`王,胡` not `王,古,月`;
    `做`→`人,故` not `人,古,攵`). This leans on the recursive
    query-time resolution session 2/3 built: `錮`'s detail view now shows
    `固` as an expandable chip that opens into `古`+`囗`, verified directly
    against `get_kanji_detail()`'s output, not just the flat `parts` list.
  - Two of the 19 (`rtk1047` 個, `rtk2260` 做) were also missing their
    person radical (亻) entirely, unrelated to the `古` bug — added it while
    fixing the `古` flattening since both fixes touched the same line
    anyway; left `rtk1145` 裾's separately-suspect `初` term alone (probably
    should be `衣`/clothing, but that's a different question and this
    session was scoped to the `古`-adjacency pattern specifically).
  - **Not fixed, flagged for a future session**: the `辟` cluster (壁 wall,
    璧 sphere, 癖 mannerism, 譬 illustrate — all list `尸,口,辛` where the
    real structure is `尸+口+辛` with `口` genuinely real, not `古`-related,
    but the cluster still reads as under-resolved / possibly redundant with
    a `辟` primitive that doesn't exist as its own entry) and the `啇`
    cluster (嫡 legitimate wife, 滴 drip, 敵 enemy, 摘 pinch, 括 fasten — all
    carry a `并,立,亠,冂` fragment that looks like the same "flatten instead
    of reference" pattern applied to some `商`/`啇`-shaped primitive that
    was never given its own entry). Neither is the `古` bug; both are
    plausible instances of the *general* flattening-bug class and worth a
    dedicated pass, same shape as this session's fix.
- Verified: rebuilt `kanji.db` from scratch, `search_by_parts(['old'])` now
  returns 9 kanji (`古 克 枯 苦 故 固 姑 胡 居`, up from 1); `search_by_parts
  (['crime'])` still returns only `犯` itself (session 4's fix intact, not
  regressed); `audit_radicals.py` still reports 0 unresolved single-glyph
  terms (unaffected — this fix didn't touch Finding 1's territory, it's
  a decomposition-quality fix, closer to Finding 2/3's territory);
  spot-checked `get_kanji_detail()` output directly (not just `rtk.py`'s
  flat view) for `rtk355`/`rtk1047`/`rtk623`/`rtk1144` to confirm the
  recursive sub_parts render correctly through the new reference chains.
- **This is the same lesson as session 3's stale-log correction, from a
  different angle**: a "fixed" note in this log isn't enough on its own —
  session 4's fix was real and correctly scoped to what it found, but
  didn't fully resolve the symptom that triggered it, and nothing caught
  that until the owner re-asked. Future sessions inheriting a "done" item
  from this log should still spot-check the original reported symptom
  directly, not just trust that the linked fix closed it.

### 2026-08-14 — session 6

- Owner asked how a `data.txt` fix actually reaches the *live* server, and
  separately whether the KRADFILE-radical fix had "disappeared" (it hadn't —
  confirmed by rebuilding and re-checking, see reply in conversation). That
  surfaced a real gap worth recording here, not just answering once in chat:
  - `import_data()` only ever seeds once (no-op the moment any owner_id=1
    row exists); there's deliberately no `/admin/reimport` (see
    "Architecture" in `CLAUDE.md`). So on a live server, `git pull` +
    restart does **not** pick up a `data.txt` edit — only the idempotent
    schema migration re-runs, not a reseed.
  - Deleting `kanji.db` to force a reseed is not a safe workaround: the
    same file holds every real user's account and contributions, so
    deleting it destroys those along with the stale system data.
  - Also flagged for the owner directly: this agent runs in an isolated
    cloud container with no SSH access to the real deployed box
    (`srv.alteon.help`). Session 4's "verified live against the running
    production API" almost certainly meant its own container's local
    `kanji.db`, not the real server — worth the owner double-checking
    the real server's state independently rather than trusting that claim.
- **Built `backend/sync_system_data.py`** to close the gap: a script meant
  to be run after every `git pull` on the actual server, that reconciles an
  already-seeded live `kanji.db`'s system rows (`owner_id=1`,
  `script='ja-kanji'`) with whatever `heisig-kanjis.csv` /
  `data_from_pdf.txt` / `data.txt` currently say — without wiping user data.
  - Design: build a disposable shadow DB via the real import pipeline
    (`build_shadow_db()`, same helper the audit scripts use — so the merge/
    override logic is never duplicated, this script only diffs against it),
    then diff+apply against the live DB's kanji/aliases/decompositions+parts,
    strictly scoped to `owner_id=1 AND script='ja-kanji'` throughout.
  - Deliberately does **not** just call `import_data()` with its guard
    removed: that function's `DELETE FROM parts WHERE kanji_id IN (system
    kanji)` deletes every parts row for a system kanji_id regardless of
    which decomposition owns it — it would also delete a real user's own
    alternate decomposition on a system kanji, since `parts` rows aren't
    scoped to decomposition-owner at that granularity. Only safe against an
    empty DB, which is the only case it's actually guarded to run against.
  - Decompositions/parts are reconciled per-kanji against specifically the
    `owner_id=1` decomposition row (create if the source now wants one and
    there was none, replace its parts if they differ, delete it if the
    source now wants none — same "atomic primitive" convention as e.g.
    rtk1743 門) — a user's alternate decomposition on the same kanji_id is
    a different `decompositions.id` and is never touched.
  - Takes a timestamped backup of `--db` before writing (skippable), runs
    everything in one transaction (rolled back on any error), supports
    `--dry-run`, and is idempotent — a second run reports all-zero changes.
  - **Supersedes `fix_kradfile_proxies.py`** for ongoing use (that script
    now points to this one in its own docstring) — this generically
    reproduces that exact fix, plus every other `data.txt` content change
    made since, including this session's own test of it (see below).
  - **Tested end-to-end**, not just read: built a "stale live" DB from the
    pre-session-4 `data.txt`/`data_from_pdf.txt`/`heisig-kanjis.csv`
    (checked out from commit `294e27b`, the last commit before any of
    session 4/5's content fixes), seeded a fake user (id 42) with their own
    alias and their own alternate decomposition on `rtk355` (the same kanji
    session 5's `古` fix touched) to make sure user data survives, then ran
    `sync_system_data.py` against it pointed at the *current* source files.
    Result: 11 kanji inserted (session 4's 11 named radicals), 33 aliases
    added, 1292 decompositions replaced (large number is real and expected
    — once those 11 radicals became resolvable kanji rows,
    `expand_part_terms`'s char→keyword auto-expansion now fires for every
    decomposition that uses one of them as a part, e.g. `ノ` used 320 times;
    spot-checked one such kanji to confirm before/after matches that
    explanation, not a bug), 1 decomposition removed (an entry that's now
    fully atomic post-fix). Confirmed after applying: the fake user's alias
    and decomposition on `rtk355` were both untouched; `rtk355`'s *system*
    decomposition now correctly reads `古,old,攵,rap`; `犯` no longer
    appears in any host besides itself. Ran the script a second time against
    the same now-synced DB and got an all-zero diff, confirming idempotency.
    Also ran it (no-op, as expected) against this session's own freshly
    rebuilt `kanji.db`, which was already current.
- **What the owner should actually do**: `git pull && python3
  backend/sync_system_data.py` on the real server after every pull that
  touches `data.txt` et al. (a `--dry-run` first pass if nervous). The
  owner separately mentioned periodically committing a flat anonymized
  export of the live DB to the repo as a disaster-recovery copy —
  `backend/export_backup.py` (from an earlier, not-yet-logged-here session)
  already does exactly that (`BACKUP_ANON_SECRET`-keyed pseudonymous JSONL
  dump, safe to commit); this session didn't touch it, just confirmed it
  exists and fits the workflow the owner described.

### 2026-08-14 — session 7

- Deployed session 6's work to the live server (`srv.alteon.help`) for the
  first time: `git pull`, `sync_system_data.py --dry-run` then for real (42
  kanji inserted, 15 updated, 171 aliases added/1 removed, 2272
  decompositions replaced — large "replaced" count expected per the
  now-documented `DEPLOY_README.md`, not itself a red flag), backend
  restart, spot-checked `rtk355` live to confirm the `古`-flattening fix
  (session 5) actually reached production.
- Owner then asked whether the hanzi (`zh-Hans`/`zh-Hant`/`zh-Hani`) side of
  the data has the same class of problems. Answered from this doc's own
  findings rather than guessing, plus one live check:
  - The specific `古`-style flattening bug (sessions 2/5) is structurally
    `data.txt`-only — hanzi decompositions come from `import_hanzi.py`
    (cjkvi-ids IDS data), a different, non-hand-typed source. That exact
    bug class doesn't apply there.
  - But two *other*, hanzi-relevant issues are already on record and not
    yet fully closed out:
    1. The cross-script keyword-resolution bug in
       `expand_part_terms`/`_build_char_lookup` (found session 2, fixed
       session 3) — fixed in code but per session 3's own note, **"not yet
       verified against a real, fully-seeded hanzi DB."** Spot-checked live
       this session: `漢` as `ja-kanji` (rtk1701) resolves to
       water/mugwort/mouth/one/large/two; the same glyph as `zh-Hant`
       (hanzi-6f22) resolves to water/twenty/mouth/man — correctly
       separated, no keyword bleed-through observed. Only a single spot
       check, not a systematic pass across the ~2,628 dual-script glyphs.
    2. Session 4's KRADFILE-proxy fix noted in passing that the same
       keyword strings it was cleaning up in `ja-kanji` (e.g. "change")
       also show up messily across ~24 unrelated `zh-*` decompositions —
       evidence the `cjkvi-ids` source has its own noise, unaudited so far.
- **Queued, explicitly non-urgent (owner's framing)**: a dedicated
  decomposition-quality audit pass over the `zh-*` rows, parallel to the
  one this doc's sessions 1–6 already did for `ja-kanji`. Likely a
  different bug shape (IDS-parsing noise, not hand-typed flattening) —
  nobody has looked yet. Natural first steps whenever picked up: (a)
  broaden the session-7 spot check into a systematic sweep of the ~2,628
  dual-script glyphs to confirm the cross-script fix holds generally, not
  just for `漢`; (b) decide whether `audit_decomposition.py`/
  `audit_radicals.py` should gain a `zh-*`-scoped mode or a hanzi audit
  needs its own tooling, given the source data (IDS) is structurally
  different from `data.txt`.

### 2026-08-14 — session 8

- Continued the backlog item session 7 flagged while fixing `rtk311` 各
  ("each"): 9 other kanji also listed both `夂` (walking legs/go-slowly)
  and `攵` (rap/knock) as parts, same shape as 各's bug (one of the two is
  always a spurious extra, not something the character actually contains).
  Session 7 explicitly deferred these, noting each needs its own structural
  check rather than a uniform assumption — same caution this doc has used
  since Finding 2's original "乞 isn't a clean 1:1 proxy" lesson.
- Checked each of the 9 against the character's real composition (not
  pattern-matched):
  - **`夂` is real, `攵` is the spurious extra** in `rtk318` 処 (dispose,
    = 夂+几, no rap element anywhere), `rtk319` 条 (article, = 夂+木), and
    `rtk456` 冬 (winter, = 夂+two dots/ice) — none of these three visually
    contain the 4-stroke "rap" radical at all.
  - **`攵` is real, `夂` is the spurious extra** in `rtk358` 警 and
    `rtk2141` 驚 (both built on 敬, whose own right side is genuinely 攵 —
    敬/警/驚 all share it, a very standard combination), `rtk998` 数 and
    `rtk2483` 薮 (both built on the rice+woman+攵 "count/number" primitive
    — 薮 = 艹+数), `rtk1031` 悠 (built on 攸 = 亻+丨+攵), and `rtk2369` 撒
    (built on 散, whose own right side is also 攵) — none of these six
    visually contain the 3-stroke "go slowly" radical.
  - Net: 3 kanji lost their spurious `攵`, 6 lost their spurious `夂`.
- Verified: rebuilt `kanji.db` from scratch, confirmed both directions —
  `search_by_parts(['walking legs'])` no longer includes the 6 that
  shouldn't have it and still includes the 3 (plus `rtk311` 各 from session
  7) that should; `search_by_parts(['rap'])` no longer includes the 3 that
  shouldn't have it and still includes the 6. `audit_radicals.py` and the
  `古`/`crime` spot-checks from sessions 4/5 are unaffected (0 single-glyph
  undefined terms, same result sets as before).
- **Not yet synced to the live server** — this is a `data.txt`-only change;
  per `DEPLOY_README.md`, whoever next has access to `srv.alteon.help` needs
  to `git pull && python3 backend/sync_system_data.py` there before this
  reaches real users (same as every session since 6's script existed — the
  fix lives in the repo the moment it's pushed, but the live DB needs the
  sync step run separately, on the actual server).
- This closes out session 7's specific backlog item. The `辟`/`啇` clusters
  flagged in session 5 (壁/璧/癖/譬 and 嫡/滴/敵/摘/括) are a similar shape of
  "under-resolved or duplicated primitive" question and remain open —
  natural next candidate for the same treatment.

## Tooling produced this session

- `backend/audit_decomposition.py` — committed to `master`. Rebuilds a
  throwaway DB via the real import pipeline, batches kanji to an LLM
  (OpenAI) for a plausibility verdict, caches results in a gitignored
  `audit_results.jsonl`, writes a gitignored `audit_report.md`. Not yet run
  against the real API (no key available in this session) — the findings
  above came from a manual pass plus ad hoc deterministic checks instead.
- The deterministic "undefined glyph" / "proxy frequency" checks used for
  Findings 1–2 were run ad hoc, not folded into the committed script. Worth
  revisiting whether they belong there as a free, no-API-key mode.
- `backend/audit_radicals.py` — committed 2026-08-13. The no-API-key half
  of the above: rebuilds the same throwaway DB and reports every part_term
  in an rtk* decomposition that resolves to no kanji row or alias, split
  into single-glyph vs. multi-char terms. This is now the authoritative way
  to recheck the Finding 1 radical count (`python3 audit_radicals.py`); the
  proxy-frequency check from Finding 2 is still ad hoc, not yet scripted.
- `backend/fix_kradfile_proxies.py` — added 2026-08-14 (session 4), committed
  in a later session (this doc's session-4 note that it was still uncommitted
  is stale — see session 3's note above about logs written before the
  closing commit). One-off direct-DB patch, not a reusable audit tool:
  deletes the 5 confirmed KRADFILE-proxy glyphs (乞/化/刈/買/犯) and their
  auto-expanded keyword rows from `owner_id=1`/`ja-kanji` decompositions in
  an already-seeded `kanji.db`. Superseded for ongoing use by
  `sync_system_data.py` below (still kept as the original record of this
  specific fix).
- `backend/export_backup.py` — added in an earlier session not otherwise
  logged in this doc. Anonymized flat-file (JSONL) export of `kanji.db`
  (every kanji/alias/decomposition/part/story, public and private, with
  every non-system `owner_id` replaced by an HMAC-keyed pseudonym instead of
  the real username) meant to be committed to git periodically as a
  disaster-recovery copy — the owner's own stated plan (session 6). Never
  reads `password_hash` or `sessions`, so it can't leak credentials.
- `backend/sync_system_data.py` — added 2026-08-14 (session 6). The answer
  to "how do `data.txt` fixes reach the live server without wiping user
  data": diffs a live, already-seeded `kanji.db`'s `owner_id=1`/`ja-kanji`
  rows against a freshly-built shadow DB (same source files, real import
  pipeline) and applies only the difference, never touching another
  owner's rows even on a shared `kanji_id`. Meant to be run after every
  `git pull` on the real server. See session 6 above for the full design
  rationale and the end-to-end test (fake user + stale pre-session-4 DB)
  that verified it.
