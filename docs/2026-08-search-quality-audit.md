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

### 2026-08-15 — session 9

- Picked up session 5's `辟`/`啇` cluster backlog item. First correction:
  `括` (rtk714, "fasten") doesn't actually belong to the `啇` cluster —
  checked its current parts (`ノ,口,十,舌,扎`) and there's no
  `并,立,亠,冂` fragment; its real structure is 扌+舌 (hand+tongue), a
  different primitive entirely. Session 5's list of 5 was off by one;
  the real `啇` cluster is 4 kanji (嫡/滴/敵/摘).
- **`辟` cluster (壁/璧/癖/譬)** — resolved with high confidence, derived
  from already-verified data rather than guessed: all 4 hosts' flattened
  fragment (`口,十,辛,立,尸`, plus one host-specific extra each) is exactly
  `尸 + 口 + 辛`, where `辛`'s own decomposition (`rtk1612`, already
  correct) is `十,立` — the "extra" `十,立` in each host is `辛` flattened
  a second time, same pattern as session 5's `古`/`固`/`胡`/`居` fix.
  Created `辟` as a new primitive (`rad1054`, alias `heki` — its modern
  on'yomi, matching `癖`'s own `heki` reading) with parts `尸,口,辛`, then
  pointed all 4 hosts at it: `壁`→`辟,土`, `璧`→`王,辟`, `癖`→`疔,辟`
  (`疔` = "sickness radical" per session 4), `譬`→`言,辟`.
- **`啇` cluster (嫡/滴/敵/摘)** — same flattening shape, but *not* fully
  derivable from already-verified data (unlike `辟`, nothing in the repo
  already independently confirms `啇`'s own internal structure), so
  handled more conservatively: created `啇` as a new primitive
  (`rad1055`, alias `teki`) but left it **atomic — no sub-parts
  recorded**, rather than guess one. The naming evidence is still solid
  (3 of its 4 hosts — 敵/滴/摘 — share the on'yomi "teki"; its hosts'
  flattened fragment `口,并,立,亠,冂` is near-identical to `商`/`rtk471`'s
  own already-correct `口,并,立,亠,儿,冂`, missing only `儿`), just not
  strong enough to also assert what `啇` itself is made of. Fixed the 4
  hosts to reference it: `嫡`→`女,啇`, `滴`→`水,啇`, `敵`→`啇,攵`,
  `摘`→`扎,啇` — also dropped a separate, unrelated bug found along the
  way: `嫡`/`敵`/`摘`'s old flattened lists each nonsensically included
  `滴` itself as one of their own parts (a different character listed as
  a sub-component, not a flattening artifact — no idea how that got
  there, just removed it since none of the three actually contain 滴).
- Verified: rebuilt `kanji.db` from scratch. `search_by_parts(['heki'])`
  and `search_by_parts(['teki'])` each cleanly group their primitive with
  exactly its 4 real hosts. `get_kanji_detail('rtk1616')` (壁) confirmed
  the full recursive chain renders: 辟 → {尸 (→ its own corpse/death
  sub-parts), 口, 辛 (→ 十, 立)}. `search_by_parts(['spicy'])` no longer
  over-matches the 4 former 辟-hosts (they no longer literally list 辛 in
  their own flat parts — available one click down via the recursive UI
  instead, not lost). `audit_radicals.py` still 0 undefined single-glyph
  terms; all of sessions 4/5/8's spot-checks (`old`, `crime`, `walking
  legs`, `rap`) unchanged.
- **Not yet synced to the live server** — same as session 8's fix, needs
  `sync_system_data.py` run on `srv.alteon.help` per `DEPLOY_README.md`.
- No more flagged-but-unresolved decomposition clusters remain from
  Findings 1/2's original list as of this entry. Next open items: the
  queued `zh-*` hanzi audit (session 7, explicitly non-urgent), the full
  multi-owner/query-time-resolution architecture migration (still not
  started since the architecture decision was recorded in session 1), or
  running `audit_decomposition.py`'s LLM pass if `OPENAI_API_KEY` is ever
  available in a session (checked again this session — still not set).

### 2026-08-15 — session 10

- Owner-reported: `報` (report, `rtk1625`) should decompose to include
  `幸` ("happiness") as a named component, not flatten it. Investigated
  rather than just patching the one line, since the shape looked familiar:
  - `heisig-kanjis.csv`'s own baseline `components` field for **both**
    `執` (`rtk1623`) and `報` already lists `happiness` as a first-class
    component — the CSV got this right from the start. `data.txt`
    overrides for both entries **discarded** that correct CSV grouping
    and replaced it with a raw flattened stroke list (`報`'s override had
    `十,辛,土,又,立,亠,卩` — exactly `幸`'s own flattened parts plus a
    spurious `土` and the genuine extras `又,卩`). Same bug class as every
    other fix in this doc, just newly found on a different pair.
  - Fixed `rtk1625` 報 → `幸,卩,又` (`卩`+`又` = the traditional "subdue"
    component on report's right side; dropped the spurious `土`, which
    doesn't appear anywhere in 報's real structure).
  - **Found but deliberately not fixed this session**: `執` (`rtk1623`,
    "tenacious") and `熱` (`rtk1634`, "heat") have the *identical* bug —
    both `data.txt` overrides flatten away a PDF-sourced grouping that
    names a primitive called **"fat man"** (`data_from_pdf.txt` already
    has the correct, unflattened `執`→`happiness,fat man` and `熱`→`rice
    seedlings,ground,fat man`, both currently shadowed by worse `data.txt`
    overrides). Unlike `辟`/`啇` last session, I don't have a confident
    glyph to assign to "fat man" — it's not obviously any single
    already-resolvable character in this dataset, and guessing wrong here
    would recreate exactly the kind of error this doc exists to fix.
    Flagged for a future session, ideally one with access to the actual
    RTK book/PDF to confirm what "fat man" refers to before naming it
    (mirrors session 5's "open question for the owner" about the katakana
    primitives, resolved by session 4 once the owner could check).
- Verified: rebuilt `kanji.db` from scratch, `search_by_parts(['happiness'])`
  now correctly returns both `幸` and `報`; `get_kanji_detail('rtk1625')`
  shows the full recursive chain (幸 → its own — still redundant, see
  below — parts; 卩 → stamp → …; 又). `audit_radicals.py` and all prior
  spot-checks (`old`, `crime`, `heki`, `teki`) unaffected.
- **Adjacent quality issue noticed, not fixed**: `幸` (`rtk1622`) itself
  lists `十,辛,立,亠` as its own parts — but `辛` (`rtk1612`) already
  independently decomposes to exactly `十,立`, so `幸`'s list redundantly
  includes both `辛` *and* `辛`'s own already-expanded pieces side by
  side. Lower priority than the flattening bugs this doc tracks (it's a
  redundancy, not a wrong or missing match — recursive display still
  renders correctly, see the `get_kanji_detail` output above), but worth
  cleaning up if someone's already in this area.
- Not yet synced to the live server — needs `sync_system_data.py` run on
  `srv.alteon.help` per `DEPLOY_README.md`, same as sessions 8/9.

### 2026-08-15 — session 11

- Two more owner-reported flattening bugs, same shape as session 10's
  `報`/`幸` fix — both confirmed against `heisig-kanjis.csv`'s own baseline
  before touching anything, not just taken on the owner's word alone
  (though both turned out exactly right):
  - **`告`** (revelation, `rtk262`): CSV baseline is `cow; mouth` — a
    `data.txt` override replaced it with `ノ,口,土`, losing `牛`/"cow"
    entirely and adding two terms (`ノ`, `土`) that don't belong. Fixed to
    `牛,口`.
  - **`産`** (products, `rtk1681`): CSV baseline is `stand up; cliff;
    life; ...` (plus several duplicate/redundant terms from the CSV's own
    pre-expansion, not relevant here). The `data.txt` override was
    *closer* than 告's case — already had `生,立,厂` (life/stand/cliff)
    right, but padded with three extra terms (`ノ,并,亠`) that don't
    belong. Fixed to `立,厂,生`.
- Verified: rebuilt `kanji.db` from scratch. `get_kanji_detail` for both
  now shows exactly the expected parts (告 → 牛,口; 産 → 立,厂,生, no
  more, no less). `search_by_parts(['cow'])` and `search_by_parts(['stand
  up'])` both include their respective kanji correctly.
  `audit_radicals.py` and prior spot-checks (`old`, `happiness`, `heki`)
  unaffected.
- **Pattern worth naming explicitly for whoever continues this**: sessions
  10 and 11 both found the exact same failure mode — `heisig-kanjis.csv`'s
  own baseline `components` field is already correct, and a hand-written
  `data.txt` override silently discarded it in favor of something worse.
  This is a different discovery path than most of this doc's earlier
  fixes (which mostly came from reasoning about a character's real visual
  structure from scratch); here the correct answer was sitting in the
  repo's own baseline source the whole time. **Worth a dedicated pass**:
  script a comparison of every `data.txt`-overridden `rtk*` entry against
  its own CSV baseline component list, and flag any override that looks
  like a regression (drops a CSV term without a clear reason) rather than
  a genuine improvement (CSV terms are known to need expansion/aliasing
  work sometimes — not every override is bad, e.g. correcting CSV's own
  duplicate-component bugs). Nobody has done this systematically yet;
  sessions 10/11 only found these because the owner happened to spot them.
- Not yet synced to the live server — needs `sync_system_data.py` run on
  `srv.alteon.help` per `DEPLOY_README.md`.

### 2026-08-15 — session 12

- **Owner-reported: `广` shouldn't be named "dotted cliff".** Checked
  before renaming — "dotted cliff" was the official Kangxi radical name I
  used when naming it in session 1, but `data_from_pdf.txt` (the actual
  4th-edition PDF extraction, sitting unused in the repo) consistently
  calls this shape **"cave"** across every kanji that uses it (店, 座, 康,
  度, 麻, 応, 庸, 鎌, ...) — the real curriculum term. Made "cave" the
  primary alias on `rad1010` (so it becomes the keyword), kept "dotted
  cliff" as a secondary alias. Found and left alone a harmless dormant
  duplicate: `rad3.25`, one of the 250 never-resolved legacy `radN.M`
  ghost entries, already had alias "cave" but `character` still `?`
  (inert, same "leave it, not worth the churn" call as session 7's
  "taskmaster").
- **Owner-reported, individually, before the systematic pass below**:
  `告` (revelation) should be cow+mouth, `産` (products) should be
  stand+cliff+life. Both confirmed against `heisig-kanjis.csv`'s own
  baseline (which was right) before fixing — same failure mode as
  session 10's `報`/`幸` find: a `data.txt` override had discarded the
  CSV's already-correct grouping. `告` → `牛,口` (was `ノ,口,土`,
  losing `牛`/cow entirely); `産` → `立,厂,生` (was already mostly right,
  `生,立,厂`, just padded with three terms that don't belong).
- **Built the systematic pass sessions 10/11 flagged as queued but
  undone**: `backend/audit_csv_regressions.py`, a deterministic (no API
  key) script comparing every `data.txt`/`data_from_pdf.txt`-overridden
  `rtk*` entry against `heisig-kanjis.csv`'s own baseline `components`
  field, flagging any CSV concept the override lost.
  - **A naive version was almost useless**: comparing flat term-sets
    directly flagged **1729 of 3000 kanji** — because CSV's baseline is
    *itself* already fully recursively pre-expanded (documented in
    `CLAUDE.md`), so it always lists both a compound primitive and that
    primitive's own sub-pieces side by side. A modern override correctly
    referencing just the compound and relying on query-time recursion
    (the whole point of session 2/3's architecture work) looks like a
    "regression" to a naive diff even when it's strictly better.
  - **Fix**: only count a CSV concept as genuinely dropped if it's
    unreachable from the override even after following recursive
    decomposition (same transitive-closure logic `_resolve_parts_detail`
    already uses for the UI's expandable chips, reimplemented against the
    shadow DB). This barely moved the raw count (1723) on its own —
    the real noise source turned out to be CSV's own habit of listing
    multiple historical/synonym-layer names for what's ultimately the
    same one or two visual atoms (e.g. 貝's CSV baseline separately lists
    "clam", "oyster", "animal legs", AND "eight" for what's really just
    eye+legs). Filtering to kanji where every dropped concept is *rare*
    across the whole flagged set (appears as a drop reason in ≤3 other
    entries — common ones like "eight"/"drop"/"animal legs"/"person" are
    almost always this synonym-layer noise, not a per-kanji bug) cut it to
    **98**, then requiring the dropped concept resolve to a real
    (non-`?`) character cut it to **90** — a genuinely reviewable list.
  - Read all 90 by hand rather than batch-applying anything (per this
    doc's standing rule). Most are a real but *debatable* editorial
    question — CSV's compound term vs. the override's already-present
    flattened sub-pieces (e.g. 原's CSV baseline has "spring", the
    override has "white"+"little" instead — plausibly Heisig's own
    deliberate simplification, not a bug, and not touched). Narrowed
    further to the subset where the dropped concept's own sub-pieces
    *aren't* present in the override *either* (no flattened trace of it
    at all — the character is just missing a real visual chunk, same
    unambiguous shape as 告/report's bugs): **13 candidates**, of which
    **7 verified and fixed** (6 skipped after individual review — see
    below):
    - `rtk118` 石 (stone): missing `厂`/cliff entirely → `厂,口`.
    - `rtk214` 棚 (shelf) and `rtk836` 崩 (crumble): both only had one
      `月` where they needed `朋` ("companion", literally two 月 side by
      side) → `木,朋` / `山,朋`. (Along the way: found "companion" is
      itself an ambiguous alias, shared by `rtk19` 朋 and `rtk1025` 侶 —
      used the literal `朋` character in the fix to sidestep it rather
      than fix the ambiguity itself, which is out of scope here and
      flagged below.)
    - `rtk618` 曜, `rtk619` 濯, `rtk1379` 躍: all three share the
      phonetic 翟 (=羽+隹) and were all missing `羽`/"feathers" while
      keeping `隹` — added `羽` to all three.
    - `rtk931` 励 (encourage): had `斤`/"ax" where `万`/"ten thousand"
      belongs (CSV-confirmed, and 斤 doesn't visually appear in 励 at
      all) → replaced `斤` with `万`.
  - **Skipped, lower confidence, left for a future pass**: `rtk371` 語
    (whether "i"/吾 should replace its already-present flattened
    five+mouth), `rtk1509`/`rtk1510`/`rtk2146` (男/"male" — its own parts,
    rice-field+power, are already substantially present, so likely CSV
    synonym-layer noise rather than a real drop), `rtk1608` 爽 (whether
    "large"/大 should replace its plausible one+person flatten),
    `rtk2041`/`rtk2043` (CSV says 革/leather contains "car"/車, which
    doesn't match 革's known structure at all — likely a CSV bug, not a
    `data.txt` regression, so out of this script's stated scope).
- Verified: rebuilt `kanji.db` from scratch after every batch this
  session. All 7 fixes confirmed via `get_kanji_detail` (exact expected
  parts, no more no less) and forward search (`cliff` now includes 石,
  `feathers`/`ten thousand` searches return the right sets).
  `audit_radicals.py` and every prior session's spot-checks (`old`,
  `crime`, `happiness`, `heki`, `teki`, `cow`, `cave`) unaffected.
- **Open items for a future session**: (1) the "companion" alias
  ambiguity (`朋`/rtk19 and `侶`/rtk1025 both claim it — `resolve_alias`-
  style lookups currently pick one non-deterministically, same shape as
  the script-scope bug fixed in session 3, just same-script this time);
  (2) the remaining 6 skipped candidates above, and the ~77 kanji in the
  broader 90-entry list not reviewed in this pass at all (the "compound
  vs. already-flattened" cases, which need real editorial judgement, not
  a mechanical check); (3) whether `heisig-kanjis.csv` itself has a bug
  at 革/rtk2041 ("car" doesn't belong).
- Not yet synced to the live server — needs `sync_system_data.py` run on
  `srv.alteon.help` per `DEPLOY_README.md`.

### 2026-08-15 — session 13

- Owner-reported: `警` should decompose to `敬` (respect/awe) + `言`
  (say/words), not the flattened `言,口,勹,艾,攵` it had. Confirmed
  against `heisig-kanjis.csv` first: baseline for `警` literally starts
  with "awe" (敬's own keyword, `rtk356`) followed by *its* own flattened
  sub-pieces, then "say;words;...". Exact same session 10-13 pattern —
  `data.txt` discarded a real CSV-correct compound reference. Fixed
  `rtk358` 警 → `敬,言`.
  - Checked `驚` (`rtk2141`, wonder) too, since it shares 敬 as its left
    component (敬+馬) and had the identical bug (`口,馬,勹,艾,攵,杰` →
    should be `敬,馬`). `馬`/`rtk2132` already independently decomposes
    to `杰` (the fire-radical-shaped bottom strokes), so the `杰` in
    驚's old flattened list was the same "compound and its own already-
    expanded piece both present" redundancy this doc keeps finding —
    dropped, since `馬` alone already carries it via recursion. Fixed to
    `敬,馬`.
- Verified: rebuilt `kanji.db` from scratch. `get_kanji_detail` for both
  shows the exact expected two-part decomposition, with `敬` correctly
  expanding to its own `口,勹,攵,艾` on demand and `馬` to `杰`.
  `search_by_parts(['awe'])` now correctly returns `敬,警,驚` grouped
  together. Noted, not a regression: session 8's flat `search_by_parts
  (['rap'])` no longer includes `rtk358`/`rtk2141` directly (攵 is now one
  level deeper, inside 敬, same as every other recursive-reference fix in
  this doc — `故`/old lost the same flat "mouth"/"ten" matches for the
  identical reason). `audit_radicals.py` and the full spot-check set
  (`heki`, `teki`, `old`, `cave`, `feathers`) unaffected.
- This is now the fourth session in a row (10, 11, 12, 13) finding the
  same bug shape one owner-report at a time, on top of session 12's
  systematic pass already turning up 90 more candidates from the same
  root cause. Worth a future session revisiting whether it's worth
  extending `audit_csv_regressions.py`'s "rare dropped term" filter to
  also catch cases like 警 (where the dropped term, "awe", would likely
  have been common enough — it recurs across 警/驚's whole family — to
  get filtered out as "probably CSV noise" under session 12's current
  threshold; worth checking directly next time rather than assuming).
- Not yet synced to the live server — needs `sync_system_data.py` run on
  `srv.alteon.help` per `DEPLOY_README.md`.

### 2026-08-15 — session 14

- Owner asked for a different verification method going forward: web
  search each kanji (e.g. "執 heisig") and read what's out there about its
  real decomposition, rather than relying only on this repo's own CSV
  baseline as the source of truth (sessions 10-13 all leaned on
  `heisig-kanjis.csv` alone). Tried it on the session-10 backlog item
  first: `執`/`熱`'s undefined "fat man" primitive.
  - `hochanh.github.io/rtk/` (a per-kanji RTK community reference site)
    confirmed `執` = "happiness" + "fat man" independently of our own CSV,
    and separately confirmed `丸` (`rtk44`, keyword "round") is informally
    nicknamed "fat man"/"rotund"/"Laughing Buddha" in RTK community
    material — corroborated by a second, unrelated web search result
    making the same "round"/"rotund figure" association for `丸`. `丸`'s
    own already-correct parts (`九,丶`) also match `執`'s old flattened
    list verbatim (which literally contained `九` and `丶` among its raw
    strokes) — three independent signals converging on the same answer.
    Fixed `rtk1623` 執 → `幸,丸` (was `ノ,九,十,辛,土,立,丶,亠`).
  - `熱`'s case turned out less clean on the same sources — different
    community references show genuinely different primitive groupings
    for it ("rice-seedlings+ground+fat man" vs. "artistry(埶)+divot+
    round"), i.e. real disagreement between sources, not just one
    unverified guess. Left unfixed rather than pick one arbitrarily;
    "rice seedlings" also still isn't a named primitive in this dataset
    either way. Still open.
  - Also found and fixed `矛` (halberd, `rtk1311`): its own override was
    just the bare `マ` glyph, but `heisig-kanjis.csv`'s baseline says
    `矛` = "beforehand" — and `予` (`rtk1719`, "beforehand") already
    exists with its own correct parts `マ,一,亅`. Same flatten-instead-
    of-reference shape as every other fix this week, just caught by
    re-reading the CSV baseline for the specific kanji involved (this one
    didn't come up in session 12's systematic pass because `矛`'s override
    has only one term, so nothing was "dropped" in that script's sense —
    a reminder that script's blind spot is single-term overrides, not
    just multi-term ones). Fixed to `予`.
  - **Bigger finding, not acted on**: chasing `マ` down to `予` prompted
    checking `ハ` the same way. `heisig-kanjis.csv`'s own baseline calls
    the `ハ` shape "eight" for **137 of the 237** kanji currently using
    literal `ハ` in their decomposition (confirmed programmatically, not
    sampled) — meaning at least those 137 should likely reference `八`
    (`rtk8`, already a real, correctly-resolving kanji) instead of the
    separate "katakana ha" primitive (`rad1051`) session 4 invented when
    no confident Heisig term was available at the time. **But the other
    100 hosts' CSV baseline does *not* say "eight"** (e.g. `rtk229`/230/
    231's baseline is "tree; wood; one", no "eight" anywhere) — meaning
    `ハ` as a literal decomposition string is doing double (or more) duty
    for at least two visually-similar-but-conceptually-different things,
    and a blind merge into `八` would be wrong for a large fraction of its
    237 uses. **Not fixed this session** — needs someone to work out what
    the other ~100 non-"eight" uses of `ハ` actually represent before any
    merge is safe (possibly more than one further split is needed, not
    just a two-way one). Flagged here rather than guessed at under time
    pressure, same standing rule as everywhere else in this doc. This is
    likely the single highest-impact open item in the whole audit if
    someone resolves it correctly — `ハ` alone touches ~237 kanji, more
    than any single fix so far.
- Verified: rebuilt `kanji.db` from scratch after each fix. `search_by_parts`
  confirms `round`/`beforehand`/`awe` groupings are correct;
  `audit_radicals.py` and the full spot-check set unaffected.
- Not yet synced to the live server — needs `sync_system_data.py` run on
  `srv.alteon.help` per `DEPLOY_README.md`.
- **Note on methodology for next time**: web search is a genuinely useful
  *additional* evidence source (it caught the `丸`/"fat man" identity,
  which our own CSV alone couldn't — CSV just says "fat man" without
  saying what glyph that is) but isn't a free substitute for the CSV-
  baseline-first approach sessions 10-13 used — most web results for a
  specific kanji + "heisig" are thin or generic (see the `執`/`敬`
  searches above), and community sites can disagree with each other (see
  `熱`). Treat it as corroboration to raise or lower confidence on a
  specific, already-suspected case, not as a search-every-kanji-cold
  strategy — doing that literally for all ~3000 rtk kanji was not
  attempted this session and would be a large, slow undertaking for
  likely-thin per-kanji signal on most of them.

### 2026-08-15 — session 15

- Continued straight from session 14's `ハ` finding. Owner proposed a
  concrete resolution: `ハ`'s canonical meaning should be "eight", with
  "katakana ha" demoted to a secondary alias, plus possibly "animal legs"
  as a third. Investigated before applying it, since session 14 already
  flagged this as the single highest-impact open item (~237 kanji) and a
  wrong bulk move here would be a large regression, not a small one.
- **Found the real reason ~100 of 237 hosts didn't confirm "eight" in
  CSV**: it wasn't that `ハ` means something else for them — **103 hosts
  (a much larger, separate group, overlapping the original 237) were
  redundantly re-flattening `貝` (shellfish) right alongside listing `貝`
  itself**, since `貝`'s own already-correct decomposition is exactly
  `目,ハ`. Textbook instance of the same "compound plus its own already-
  expanded pieces, both present" duplication this whole doc keeps finding
  (古/幸/辟/啇/敬/朋 sessions 5-13) — just not visible as a `data.txt`-vs-
  CSV diff, since these hosts' CSV baselines are blank (post-RTK-6th-
  edition-scope kanji session 12's script can't check at all). Fixed
  mechanically and safely: for every host listing `貝` **and** `目` **and**
  `ハ` together, dropped the redundant `目,ハ` (kept `貝`, which still
  correctly expands to them on demand via recursion). **103 kanji fixed**
  in one pass — no per-character judgment needed, since presence of the
  parent compound made the redundancy unambiguous.
- That cleanup alone dropped the `ハ`-host count from 237 to 134. Re-ran
  the CSV cross-check on what remained and found a second, smaller family:
  `未`/`末` (rtk229/230, "not yet"/"end") and **9 compounds built on
  them** (昧/沫/味/妹/朱/珠/抹/殊/魅) were all flattening `未`/`末`/`朱`
  down to raw strokes (`｜,二,ハ,木,亠` etc.) instead of referencing the
  base character — same shape again, this time verified per-kanji against
  CSV rather than mechanically (each compound's real makeup, e.g. 昧=日+未,
  妹=女+未, checked individually; `魅`'s extra `田,儿,匕,厶` turned out to
  be the *same* redundant-compound pattern again — `鬼`/rtk2175's own
  parts are exactly `田,儿,匕,厶`, so `魅` simplifies to `鬼,未`). **11 more
  kanji fixed.**
- **Net for this session: 114 kanji cleaned up**, and the `ハ`-host count
  is down to **123** (from the original 237). Of those 123, CSV now
  confirms "eight"/"animal legs" for 63; the other **60 are still
  unresolved** and split into identifiable but not-yet-fixed sub-groups:
  a `兼`-family (兼/嫌/鎌/謙/廉, 5 kanji, CSV says "animal horns" not
  "animal legs" or "eight" — genuinely might be a third, distinct meaning,
  not just noise), a family built around `个`/`王` ("umbrella" — 全/金/
  詮/途/塗/余 and others, CSV mentions neither eight nor legs), ~30 hosts
  with **no CSV baseline at all** (frames beyond `heisig-kanjis.csv`'s
  6th-edition scope, unverifiable by the script, need one-by-one manual
  or web-search-based checking), and a handful of scattered singletons.
  **Given 60/123 (still just under half) don't confirm "eight" — did
  NOT rename `ハ`'s canonical alias / merge into `八` this session.**
  Doing so now would still misfire for a large fraction of remaining
  hosts, i.e. would recreate the exact class of bug this whole effort
  exists to remove. This is the natural next step once the remaining 60
  are individually resolved (or confirmed as a genuinely separate
  primitive that needs its own name, e.g. if `兼`'s "animal horns" turns
  out real and distinct).
- Verified: rebuilt `kanji.db` from scratch after both batches (103, then
  11). Spot-checked several rewritten entries via `get_kanji_detail`
  (`貝` correctly still expands to `目,ハ` on demand; `未`-family shows
  the right compound relationships). `search_by_parts(['shellfish'])`,
  `(['not yet'])` and the full standing spot-check set (`old`, `awe`,
  `heki`, `teki`, `round`, `happiness`, `crime`, `cave`) all correct, no
  regressions. `audit_radicals.py` still 0 undefined single-glyph terms.
- Not yet synced to the live server — needs `sync_system_data.py` run on
  `srv.alteon.help` per `DEPLOY_README.md`. This is the largest batch of
  content changes queued for a live sync since session 4's original
  KRADFILE-proxy fix (114 kanji here vs. that session's 397 lines) —
  worth prioritizing the next live sync sooner rather than letting it
  queue up further.

### 2026-08-15 — session 16

- **Standing scope change from the owner: check all ~3000 kanji, not just
  ones a report or script flags.** Recorded here explicitly, same as the
  architecture decision in session 1 — this changes the shape of ongoing
  work from "wait for a report or a systematic script to surface a
  candidate" to "cover the dataset methodically." Not attempted as a
  single-session task (that's neither realistic nor a good use of one
  turn), but future sessions should treat steady, tracked coverage of the
  full `rtk*` set as the default posture, not a one-off ask. No coverage-
  tracking mechanism exists yet (e.g. a persisted "kanji IDs checked so
  far" list) — worth building before the next content-focused session, so
  progress toward "all 3000" is actually measurable across wake-ups
  instead of restarting the question each time.
- **Second, larger owner request implemented this session: alternative
  decompositions, end to end.** Two parts — (1) search should consider
  *all* alternative decompositions of a kanji and of its parts,
  recursively, not just one; (2) the detail view should show each
  alternative decomposition on its own line, not behind a tab.
  - **Detail view (backend + frontend)**: `get_kanji_detail` already
    returned every top-level decomposition as a list (built for user
    contributions, mostly unused in the UI until now) — the gap was
    `_resolve_parts_detail`'s recursion, which picked exactly one
    sub-decomposition per part via `_pick_decomposition` (removed).
    Replaced with a shared `_list_decompositions` helper (also now used
    by `get_kanji_detail`, de-duplicating what used to be two near-
    identical queries) and changed each resolved part to carry
    `sub_decompositions: [{id, label, owner, parts: [...]}, ...]` —
    *every* visible alternative, each recursively resolved the same way,
    all the way down the tree (bounded by the existing
    `MAX_DECOMPOSITION_DEPTH`/ancestor-cycle-guard, unchanged). Verified
    with a synthetic multi-decomposition test (added a second, user-
    owned decomposition partway down a real recursion chain — `辛`
    nested inside `辟` inside `壁` — confirmed both alternatives render
    at the correct nested position, then rolled back). `KanjiDetail.jsx`
    changed from a tab strip (`decompIdx` state, one `activeDecomp`
    shown) to rendering every non-empty decomposition as its own
    `.decomposition-block`, and `PartChip` from a flat `sub_parts` list
    to iterating `sub_decompositions` the same way, nested. Verified
    live in a real browser (Playwright against `vite dev` + `uvicorn`,
    not just a description of expected behavior) — screenshotted the
    壁 detail page, expanded `辟`, confirmed the nested chips render.
  - **Search (bigger, riskier change)**: `search_by_parts` was a flat
    SQL `EXISTS` check (a term must appear directly in *some* visible
    decomposition — already "all alternatives" at one level, but no
    recursion into parts' own parts). Rewrote as a BFS,
    `_reachable_kanji_for_term`: layer 0 is the direct match (unchanged
    semantics), each further layer asks "which kanji use *any* kanji
    found in the previous layer as a part, in any visible decomposition"
    (`_kanji_with_part_terms` + `_terms_for_kanji_ids`), building the
    full transitive closure up to a depth cap. Confirmed the motivating
    case: searching "corpse" now finds 壁 (壁→辟→尸/corpse) at depth ≥ 2,
    which no flat search could ever do.
  - **Measured the real impact before shipping it blind**: at full depth
    (5), "mouth" jumps from ~527 direct hits to 1954 (65% of all rtk
    kanji), "one" to 1892 (63%), "old" from 9 to 643. Flagged this to the
    owner rather than assuming it was fine — the answer was to make depth
    a **user-facing choice**, not a fixed default. Implemented: `depth`
    param on `search_by_parts`/`_reachable_kanji_for_term` (default `1`,
    exactly the pre-existing flat behavior — confirmed byte-for-byte
    identical result counts on the whole standing spot-check set before
    touching anything else), threaded through `POST /search/parts`
    (validated to `1..MAX_DECOMPOSITION_DEPTH`, 400s outside that range)
    and a new "Search depth" `<select>` on the parts-search form
    (`App.jsx`/`i18n.js`, EN+RU), defaulting to 1 so nobody's search
    experience changes unless they opt in.
  - Also moved `MAX_DECOMPOSITION_DEPTH` earlier in `database.py` (was
    defined after its first use as a default-parameter value in the new
    BFS helpers — Python evaluates defaults at function-definition time,
    so the old position would have thrown `NameError` at import).
  - **Verified thoroughly, not just unit-level**: full backend spot-check
    suite (`old`, `crime`, `heki`, `teki`, `awe`, `round`, `beforehand`,
    `cave`, `shellfish`, `not yet`, multi-term AND) all unchanged at the
    default `depth=1`; `audit_radicals.py` still 0 undefined terms;
    `npm run build` and `npm run lint` both clean; installed real
    dependencies (`fastapi`/`uvicorn`/a `venv` to dodge a system
    `cryptography` conflict) and ran the *actual* FastAPI + Vite dev
    servers, hit `POST /search/parts` directly with `depth=1/3/9` (9
    correctly 400s), and drove the real UI with Playwright — screenshots
    confirmed the depth selector, a parts search, and the expandable
    nested-decomposition detail view all work as built, not just as
    described. This is the first session to actually launch the app and
    click through it rather than testing only through `database.py`
    calls or `rtk.py` — worth doing again for future UI-touching changes,
    per `CLAUDE.md`'s own standing instruction to test UI changes in a
    browser before calling them done.
  - Noted, not fixed: expanding `辟` in the live detail view showed both
    `尸` ("corpse") and a second, separate kanji `屍` (also "corpse") as
    siblings — this is pre-existing `expand_part_terms` auto-keyword-
    expansion behavior (a part term that's itself a kanji character gets
    its own keyword appended as a second term at import time), not
    something this session's changes introduced or need to fix; flagging
    only so a future session doesn't mistake it for a new bug.
- Not yet synced to the live server (this is a backend + frontend code
  change, not a `data.txt` content change — needs an actual deploy of
  both, not just `sync_system_data.py`).

### 2026-08-17 — session 17

- **Built the coverage tracker session 16 flagged as needed before more
  content work**: `backend/coverage_status.py`, regenerating
  `docs/kanji_review_coverage.tsv` (id, character, keyword, frame,
  reviewed yes/no for all ~3000 `rtk*` kanji). "Reviewed" is defined
  honestly and narrowly: a kanji's `data.txt` line was added or edited by
  a content-fix commit *after* the audit began (commit `0a46e3d`, the
  first Finding-1 fix) — not "has ever been in a git diff" (the whole
  file was bulk-written once at the very start, which would make
  everything trivially "reviewed" and defeat the point). This is a proxy,
  not a perfect record (an edit for an unrelated reason would count), but
  it errs toward under- rather than over-counting, and it's the only
  signal derivable without hand-maintaining a separate log. Current
  count: **548/3000 (18.3%)** reviewed as of this session's commits.
- **Used it immediately**: filtered to the lowest, most foundational
  frame numbers (1-100) — the kanji with the largest downstream blast
  radius, since so many other kanji reference them as compounds — and
  found a real cluster still unfixed:
  - `可`(rtk97)/`町`(rtk96)/`頂`(rtk98) all flattened `丁` (rtk95,
    "street" = `一,亅`) instead of referencing it directly; `頂` also
    redundantly listed `貝` alongside `頁` (which already contains it).
    Fixed to `丁,口` / `田,丁` / `丁,頁`.
  - `卓`(rtk52)/`朝`(rtk53) did the same to `早` (rtk26, "early" =
    `十,日`); `嘲`(rtk54) flattened `朝` once that was fixed. Fixed to
    `卜,早` / `早,月` / `口,朝`.
  - Finally fixed the **original Finding-3 bug** from the very first
    audit session (`rtk91` 昭, parts literally `?, ?, pipe, minus` —
    the unresolved-glyph placeholder listed twice) — it had survived
    every session since because nothing ever specifically went looking
    for it again. Real structure is `日,召` (`召`/rtk90 already correct).
    Its `data.txt` line also carried an unrelated leftover alias
    ("street" — apparently contamination from editing `rtk95` nearby at
    some point) which had nothing to do with 昭's actual meaning
    ("shining"); cleared it.
- **Also closed out session 12's 6 skipped candidates** (had been open
  since 2026-08-15): re-verified exact CSV frame numbers first (caught
  and corrected a mismatch from session 12 — `吾`/"I" is `rtk17`, not
  `rtk1091`, which is a different "I" kanji, `俺`). `語`(rtk371) → `言,吾`;
  `勇`(rtk1509) → `男,マ`, `湧`(rtk1510) → `水,勇`, `虜`(rtk2146) →
  `男,卜,匕,厂,虍` (all three were flattening `男`/rtk923, "man" = `田,力`,
  instead of referencing it). `爽`(rtk1608) and `革`/`覇`(rtk2041/2043)
  stay unfixed — genuinely still uncertain (see the commit message for
  why), not just left out of laziness.
  - **Found a real alias collision while fixing `男`**: both `男`
    (rtk923) and `牡` (rtk2609, "male animal") had the bare alias
    "male" — same shape as the "companion" ambiguity flagged session 12.
    Removed `牡`'s redundant copy (kept its own more specific "male
    animal", already sufficient). A residual 2-way ambiguity remains
    between `男` and `雄` (rtk804 — CSV's own `keyword_6th_ed` for it is
    literally "male", not something `data.txt` introduced), not resolved
    this session — flagged for whoever next has bandwidth for a proper
    "which kanji should canonically own this English word" pass across
    the whole alias table, since "companion" and "male" are unlikely to
    be the only two instances of this shape.
- Verified: rebuilt `kanji.db` from scratch after each batch.
  `audit_radicals.py`'s multi-char undefined-term count dropped 6 → 5
  (the `?` placeholder gone); full standing spot-check suite (`old`,
  `crime`, `heki`, `awe`, `round`, `beforehand`, `cave`, `shellfish`,
  `happiness`, plus this session's new terms `street`/`shining`/`early`/
  `seduce`/`courage`) all resolve correctly to exactly their real hosts.
- Not yet synced to the live server — needs `sync_system_data.py` run on
  `srv.alteon.help` per `DEPLOY_README.md` (content changes) **and** an
  actual code deploy for session 16's search/detail architecture change,
  which is still queued too.
- **Next session**: keep working frame-ordered (or by whatever grouping
  turns out efficient) through `docs/kanji_review_coverage.tsv`'s
  unreviewed rows — re-run `python3 backend/coverage_status.py` first to
  get the current count before picking a batch, since it'll drift as
  fixes land. 2452/3000 still unreviewed as of this session.

### 2026-08-18 — session 18

- **Continued the frame-ordered review, picking up frames 101-250** where
  session 17 left off (frames 1-100). Two batches, two commits:
  - First batch (frames 101-175, commit `74c7641`): 9 more instances of
    the same flattening pattern in the 石/頁/原 clusters — `貫`(母,貝),
    `硝`(石,肖), `砂`(石,少), `妬`(女,石), `順`(川,頁), `願`(原,頁),
    `源`(水,原), `測`(水,則), `煩`(火,頁) — each was re-flattening a
    compound (貝/石/頁/原/則) that was already correctly named elsewhere,
    instead of referencing it.
  - Second batch (frames 176-250, commit `c1deffb`): 13 more fixes —
    `灯`(火,丁), `点`(占,杰), `照`(昭,杰), `漁`(水,魚), `墨`(土,黒),
    `鯉`(魚,里), `量`(旦,里), `洞`(水,同), `胴`(月,同), `桐`(木,同),
    `完`(宀,元), `宵`(宀,肖) — same pattern, plus one genuinely different
    bug at `rtk200`:
    - **`rtk200` was assigned the wrong kanji entirely.** The override
      read `rtk200:枠:frame:wood 90 9 10 , 十九 木` — both a frame
      mismatch and garbled parts text. Checking `heisig-kanjis.csv`
      directly: `id_6th_ed=200` is actually `宣` (proclaim), not `枠`.
      `枠`'s real 6th-edition frame is **212** — its *5th*-edition frame
      was 200, so whoever wrote this override years ago used the wrong
      edition's frame number, the same class of mistake as the original
      `rtk91` Finding-3 bug session 17 closed out. `rtk212` had no
      override at all, so it had been silently showing `枠`'s correct
      CSV baseline (`tree,wood,ninety,nine,baseball,ten,needle`) the
      whole time — meanwhile `rtk200`/`宣` was being overwritten with a
      wrong character and garbage parts on every import. Fix: deleted
      the `rtk200` line outright; `宣` now correctly falls back to its
      own (already-correct) CSV baseline, and `rtk212`/`枠` needed no
      change.
- **New finding, not fixed this session**: while spot-checking `完`
  (rtk199, now `宀,元`), its rendered parts showed **three** chips
  (`roof, roof, beginning`) instead of two. Root cause: `宀` (rad1041)
  and `屋`/`rtk1138` (frame 1138) are *both* officially keyworded "roof"
  in the 6th-edition CSV itself — a genuine Heisig naming collision, not
  a data-entry error. `expand_part_terms`'s existing behavior of
  auto-appending a literal character term's own keyword as a second
  synthetic lookup term (documented pre-existing behavior, e.g. the
  benign 尸/屍 double-chip case) turns this collision into an actively
  wrong result: resolving the synthetic "roof" term picks `屋` — a
  completely different kanji that `完`, `字`(rtk197), `守`(rtk198),
  `宵`(rtk201), and `安`(rtk202) do not actually contain. Confirmed via
  `search_by_parts(['roof','beginning'])`, which over-matches `rtk1401`
  and `rtk2488` alongside the correct `rtk199`. This is a resolution-
  logic bug, not a data bug — the right fix is probably having
  `expand_part_terms` skip the synthetic-keyword expansion when the part
  term is already a literal, unambiguous character reference, but that
  needs actual design thought (risk of breaking the legitimate cases the
  synthetic expansion exists for) rather than a quick edit. Deferred to a
  future session; flagged here so it isn't lost.
- Verified: rebuilt `kanji.db` from scratch after each batch.
  `audit_radicals.py`'s multi-char undefined-term count dropped 5 → 3
  (the two dropped were `rtk200`'s garbage text, now gone with the line
  deletion). `get_kanji_detail` spot-checks on all 14 touched ids
  (including confirming `rtk200`→`宣`/proclaim and `rtk212`→`枠`/frame
  are now both correct) plus the full standing regression suite
  (`old`/`crime`/`heki`/`awe`/`round`/`cave`/`shellfish`/`street`/
  `shining`/`early`/`courage`/`happiness`) — no regressions from either
  batch.
- Coverage: **564/3000 (18.8%)** reviewed as of this session's commits
  (`docs/kanji_review_coverage.tsv` regenerated).
- Not yet synced to the live server — same standing gap as every prior
  session (`sync_system_data.py` for content, a real code deploy for the
  session 16 alternative-decompositions architecture change).
- **Next session**: continue frame-ordered through the unreviewed rows
  (2436/3000 remain); consider picking up the `roof`/`屋` collision fix
  above if there's bandwidth, since it's a concrete, well-understood bug
  now rather than a vague "some aliases collide" note.

### 2026-08-18 — session 19

- **Fixed the `roof`/`屋` collision flagged at the end of session 18**,
  prompted by the owner asking how to handle keyword collisions like this
  in a user-friendly, tolerant way generally (not just for this one
  case). Answer applied here: split the two behaviors that were sharing
  one mechanism. `expand_part_terms` (import time) still stores a
  literal-character part term's own keyword as a second synonym row
  alongside it — that's genuinely useful for **search** (matching a
  decomposition on either the character or its keyword) and stays
  untouched. But **display** (`_resolve_parts_detail`, `KanjiDetail.jsx`)
  has no business showing two chips for what the contributor entered as
  one part. Fix: at read time, recompute exactly which part_term rows
  `expand_part_terms` would have synthesized (same char→keyword lookup,
  same `script_group` preference used at import) and drop only those
  rows before resolving chips — the literal character's own row still
  resolves normally. This is display-only and reversible per-request; it
  doesn't touch stored data or search.
  - Fixes the `完`/`字`/`守`/`宵`/`安` bogus-`屋` case exactly as
    diagnosed in session 18.
  - Turned out to also fix the previously-documented "尸/屍 double-chip
    quirk" (session-notes elsewhere had called this benign/not-a-bug) —
    it was the identical mechanism, just landing on a same-*meaning*
    kanji instead of an unrelated one, so it read as merely confusing
    rather than wrong. Confirmed `rtk1132`/`rtk1133` (尿/尼, both list 尸)
    now show a single `corpse` chip instead of two.
- **On the broader "how to handle collisions tolerantly" question**: for
  cases where a *search term a user actually types* is genuinely
  ambiguous across kanji (e.g. free-text "roof" still matches both `宀`
  and `屋` — confirmed still true after this fix, `search_by_substring`
  correctly returns both), the right posture is to keep returning every
  match rather than silently picking one canonical owner — same
  philosophy the app already applies to multiple decompositions (show
  every alternative, let the user pick). The `男`/`雄`/`牡` "male" and
  `朋`/`侶` "companion" alias collisions noted in sessions 12/17 are a
  different shape (two kanji fighting over which one alias-resolution
  picks for search-by-parts term matching, not a display bug) and are
  still open — this session's fix doesn't touch that class, only the
  display-time duplicate-chip mechanism.
- Verified: full rebuild from scratch; `audit_radicals.py` unchanged (3
  multi-char undefined terms, same as session 18 — this was a query-time
  fix, not a data fix, so the undefined-term count is unaffected);
  `get_kanji_detail` spot-checks on `rtk199`/`197`/`198`/`201`/`202`
  (roof case) and `rtk1132`/`1133` (corpse case) all show the correct
  chip count now; `search_by_parts(['roof','beginning'])` and
  `search_by_substring('roof')` return identical results to before the
  change (search untouched, as intended); `search_by_char('屋')` still
  resolves; a 15-kanji random sample across the dataset all resolve
  without error; full standing regression suite
  (`old`/`crime`/`heki`/`awe`/`round`/`cave`/`shellfish`/`street`/
  `shining`/`early`/`courage`/`happiness`) — no regressions.
- Not yet synced to the live server — same standing gap as every prior
  session.
- **Next session**: continue the frame-ordered `data.txt` review
  (2436/3000 unreviewed as of session 18); the `男`/`雄`/`牡` and
  `朋`/`侶` search-side alias collisions are still open and are a
  different fix shape from this session's display fix — worth a session
  of their own once there's bandwidth for the "which kanji canonically
  owns this English word" pass across the whole alias table that
  sessions 12/17 flagged.

### 2026-08-18 — session 20

- **Built `backend/audit_flattening.py`**, a deterministic detector for
  this audit's dominant bug pattern (a kanji's override re-flattens
  another compound's own already-correct parts instead of referencing
  it): finds every pair (K, M) of system rtk kanji where M's full
  resolved parts-set is a proper subset of K's. Raw output is noisy —
  lots of coincidental overlap from tiny common primitives, the same
  problem `audit_csv_regressions.py` hit in session 12 — so, same as
  every prior session, results were manually filtered to high-confidence
  single-candidate matches before touching any data.
- **Continued the frame-ordered review into 251-400** (picking up after
  session 18's 101-250) using the new tool, and fixed 15 more:
  - **`成` cluster (7 kanji)**: `城`, `誠`, `茂`, `戚`, `威`, `滅`, `蔑`
    were all listing 成's (rtk386, "turn into" = `ノ,戈`) raw strokes
    directly instead of referencing it — the largest single cluster
    found in one pass so far. Fixed to `土,成` / `言,成` / `艾,成` /
    `小,卜,成` / `女,厂,成` / `火,水,成` / `艾,成` respectively.
  - `涼`, `鯨` were flattening `京` (rtk334, "capital" = `口,小,亠`);
    `鯨` had a second, independent bug stacked on top — it also
    re-flattened `魚` (rtk183) into its own `田,杰`, the identical
    pattern to the `漁`/`墨`/`鯉` fixes from session 18's second batch.
    Fixed `涼`→`水,京`, `鯨`→`魚,京`.
  - `荘`→`艾,壮` (was flattening 壮/rtk343); `読`→`言,売` (was
    flattening 売/rtk345); `試`→`言,式` (was flattening 式/rtk377);
    `訂`→`言,丁` (was flattening 丁/rtk95); `詰`→`言,吉` (was
    flattening 吉/rtk342); `落`→`艾,洛` (was flattening both 各's parts
    and, more completely, 洛's full parts — 洛/rtk2396 already
    correctly encapsulates 各+水, so collapsed to the deeper reference
    rather than the shallower one).
  - **Noted, not investigated further**: `茂` and `蔑`'s pre-fix raw
    overrides were byte-for-byte identical (`ノ,戈,艾`) despite being
    unrelated kanji ("overgrown" vs. "revile"). The mechanical fix
    preserves the coincidence (both are now `艾,成`) rather than
    resolving it — worth a closer look with real source material
    (kanjidic2/a dictionary) to see if one was copy-paste contamination
    from the other, or if they're a legitimate convergent pair.
  - **Left open, lower confidence / multi-candidate ambiguity**: the
    detector also flagged a `高`/`向`/`尚`/`周`/`週`/`調` cluster and a
    `言`-radical cluster (`詩`, `詔`, `詠`, `諾`, `諭`, `域`, `詮`) where
    more than one compound's parts-set matched as a subset — resolving
    which one is the *intended* reference needs the same real-source
    verification the confident fixes above got, not just structural
    subset-matching. Also `栽`/`弐` (multi-candidate, likely
    coincidental) and the pre-existing observation that `rtk3`
    (三/"three")'s override literally lists the English words
    `one,two` instead of the characters `一,二` — flagged, not fixed,
    since it's unclear whether that's deliberate (matching search on the
    English word) or an old data-entry slip.
- Verified: full rebuild from scratch, `get_kanji_detail` spot-checks on
  all 15 touched ids confirming exactly the expected 2-3 chip
  decomposition, `audit_radicals.py` unchanged (3 multi-char undefined
  terms), full standing regression suite
  (`old`/`crime`/`heki`/`awe`/`round`/`cave`/`shellfish`/`street`/
  `shining`/`early`/`courage`/`happiness`) — no regressions.
- Coverage: **578/3000 (19.3%)** reviewed as of this session's commit
  (`docs/kanji_review_coverage.tsv` regenerated).
- Not yet synced to the live server — same standing gap as every prior
  session.
- **Next session**: run `audit_flattening.py --min-frame 401 --max-frame
  550` (or wherever `coverage_status.py` shows the next unreviewed block
  starting) to keep the frame-ordered sweep going; consider following up
  on the deferred multi-candidate clusters above once there's a good way
  to verify the *intended* compound (real dictionary/PDF source, not
  just structural subset matching) rather than guessing among ties.

### 2026-08-19 — session 21

- **Noted an out-of-band commit found on pull**: `7d4af32`, authored
  directly on the deployment box ("EC2 Default User"), not by any prior
  session in this doc. Fixed a self-identity search bug
  (`_reachable_kanji_for_term` used `resolve_alias`'s single arbitrary
  pick instead of crediting every kanji a script-ambiguous term names —
  new `_self_identity_kanji_ids()` helper), a `祈`/CSV-contradiction fix
  (was `礼,斤`, should be `altar,axe` per the 6th-ed CSV), and a `亠`/`蓋`
  "lid" alias-collision fix on `航` (same general shape as session 19's
  `roof`/`屋` fix, but resolved with an added disambiguating alias rather
  than the display-layer skip mechanism). Verified it rebuilds cleanly
  and doesn't regress the standing suite before building on top of it —
  per this repo's standard practice, out-of-band changes found on pull
  are taken as current state, not reverted, unless they look wrong.
- **Tightened `audit_flattening.py`** before reusing it: the frame
  401-550 sweep with the old subset-based detector was swamped by
  coincidental overlap (`東`/`棟`/`凍` alone produced 20+ spurious
  candidates from generic 2-stroke primitives like `一`/`亅`/`厶`).
  Changed the match from "M's parts are a subset of K's parts" to "M's
  parts appear as a contiguous, order-preserving run inside K's parts" —
  matches the actual bug shape (someone pasted a compound's raw parts in
  place) far more precisely than plain set containment.
- **Added a second, harder filter this session that the tool itself
  can't automate**: even a single unambiguous contiguous-run match can
  still be coincidental — two unrelated kanji can happen to share a
  2-stroke run without one being "derived" from the other. Cross-checked
  every remaining candidate against `heisig-kanjis.csv`'s own baseline
  `components` column. This caught real near-misses that would have
  shipped wrong fixes without it:
  - `延` (prolong)'s CSV components are "drop;stop;footprint;stretch" —
    no mention of "correct" (正), even though `正`'s exact 2-part
    signature (`一,止`) appears contiguously in `延`'s current override.
    Left alone.
  - `歌` (song)'s CSV components mention "street;nail;spike" (→ 丁) but
    never "blow" (吹's keyword), even though `吹`'s signature (`欠,口`)
    matches contiguously. Left alone.
  - `妊` (pregnancy)'s CSV components are "woman;porter;drop;samurai" —
    four *separate* atomic terms, not "responsibility" (任) as a unit,
    even though `任`'s 3-part signature matches as a contiguous prefix.
    Left alone.
  - Chasing `転`/`芸`/`雲` (all matched `伝`'s `二,厶` signature)
    surfaced a deeper, separate suspicion: `伝`'s *own* current override
    is just `二,厶`, but `data_from_pdf.txt` describes it as "person,
    rising cloud" and a genuine primitive `云` ("rising cloud",
    `rtk2241`) already exists in the system distinct from `伝`. CSV's
    components for all three K's say "...rising cloud;two;elbow;wall",
    consistent with them referencing the *primitive* `云`-shape directly
    rather than the *kanji* `伝` — the two just happen to share a raw
    stroke signature. Left all three alone rather than guess which
    reading is right; `伝`'s own decomposition may itself need fixing
    first, in a future session, before anything built on top of it can
    be trusted.
  - Same shape of caution applied to `装`/`製` (both touch `衣`/rtk423,
    whose own override — bare `亠` — doesn't match its CSV components
    "top hat;scarf" either, another foundation-level suspect) and `猿`
    (CSV components include "pack of wild dogs" — an entire missing
    animal radical, not just a flattening issue).
  - `培`/`商`/`帯`/`脱`/`説`/`541`(増) were also contiguous matches whose
    CSV components didn't support the matched compound — left alone for
    the same reason.
- **Fixed 19 confirmed** (CSV directly names the matched compound's own
  keyword or meaning): `賦`→`貝,武` ("warrior" in CSV); `政`→`攵,正`
  ("correct"); `錠`→`金,定` ("determine"); `題`→`貝,頁,是` ("just so");
  `堤`→`土,是`; `帆`→`巾,凡` ("mediocre"); `帽`→`巾,冒` ("risk");
  `霜`→`雨,相` ("inter"); `章`→`音,立,早` ("early"); `瞳`→`目,童`
  ("juvenile"); `鐘`→`金,童`; `背`→`月,北` ("north"); `諧`→`言,皆` (CSV
  has no components listed for this one — applied on structural signal
  alone, lower confidence, flagged here rather than silently treated as
  equally certain); `混`→`水,昆` ("descendants"); `脂`→`月,旨`
  ("delicious"); `詣`→`言,旨`; `茨`→`艾,次` ("next"); `資`→`貝,次`;
  `燃`→`火,然` ("sort of thing" — this is literally Heisig's own
  canonical worked example in the book).
- Verified: full rebuild from scratch, `get_kanji_detail` spot-checks on
  all 19 touched ids, `audit_radicals.py` unchanged (3 multi-char
  undefined terms), full standing regression suite
  (`old`/`crime`/`heki`/`awe`/`round`/`cave`/`shellfish`/`street`/
  `shining`/`early`/`courage`/`happiness`) — no regressions.
- Coverage: **595/3000 (19.8%)** reviewed as of this session's commit
  (`docs/kanji_review_coverage.tsv` regenerated).
- Not yet synced to the live server — same standing gap. Note the
  out-of-band commit at the top of this entry suggests someone *does*
  have direct access to the live box and has been making changes there
  directly rather than through `sync_system_data.py` — worth clarifying
  with the owner at some point whether that's the intended deploy path
  going forward, since parallel direct-edit and audit-sourced-fix paths
  could conflict if they ever touch the same kanji differently.
- **Next session**: continue frame-ordered past 550 (2405/3000 still
  unreviewed); the `伝`/`衣` foundation-level suspicions raised this
  session are worth a dedicated look before the `転`/`芸`/`雲`/`装`/
  `製`/`猿` cluster can be fixed with confidence — start there if there's
  appetite for real (PDF/dictionary) source verification rather than
  more structural-only passes.

### 2026-08-21 — session 22

- **Picked up the `伝` investigation session 21 flagged**, and it led to
  a much bigger find than expected. `伝`'s own override (`二,厶`) really
  was wrong — both `heisig-kanjis.csv` ("person; rising cloud; ...") and
  `data_from_pdf.txt` ("person,rising cloud") agree it should include
  `人` (person), which had been dropped entirely at some point. Fixed to
  `人,云` (referencing the existing `云`/rtk2241 primitive for the
  "rising cloud" shape) — this was the actual blocker session 21
  flagged; the `転`/`芸`/`雲`/`装`/`製` cluster's coincidental-looking
  matches were downstream of this, not a separate problem.
- **While tracing how `伝` got broken, found the real root cause, and it
  turned out to be much bigger and completely unrelated to flattening**:
  `import_data()`'s canonical-resolution step (database.py, "Insert
  primitive entries from data.txt") reassigns a primitive's canonical
  target to any of its own listed aliases that happens to already match
  an *existing kanji id string*. This is intentional and safe when it's
  used to consolidate an old KRADFILE-style radical-numbering id onto
  the one real kanji it represents (15 such lines exist in the `rad*.X`
  block, e.g. `rad2.1` merging onto `rtk2`/二 — all confirmed harmless,
  since their own parts override is empty, a pure no-op consolidation).
  But **8 more `rad*.X` lines had a literal `rtkNNNN` token mixed into
  their alias list *and* their own non-empty, unrelated parts list** —
  each one a scratch/orphaned entry (their other aliases — "deceased",
  "reach out", "long time", "king", "beginning", "not", "superb",
  "outstanding", "understandably" — all already correctly belonged to a
  completely different, distinct real kanji elsewhere in the file, e.g.
  "deceased" is really `亡`/rtk524, not whatever `rad3.42` was scribbling
  down). Depending on data.txt's line-processing order, **4 of these 8
  collisions were live, active corruption** — a real, commonly-referenced
  kanji's correct decomposition silently overwritten by the orphaned
  entry's unrelated leftover parts:
  - `看` (rtk688, "watch over") showed only `['fist']` instead of its
    real `ノ,一,手,二,目`.
  - `動` (rtk1806, "move") — a very high-frequency kanji, not some
    obscure corner case — showed only `['two', 'fence posts']`, with
    "fence posts" not even resolving to anything, instead of its real
    `｜,一,日,力,里,ノ`. This was the exact bug `audit_radicals.py`'s
    'fence posts' undefined-term flag (present every session since it
    started reporting undefined terms) was pointing at, and nobody had
    traced it back to its actual cause until now.
  - `側` (rtk1049, "side") showed only `['bound up']` instead of `貝`.
  - `鎖` (rtk2087, "chain") showed only `['chihuahua with one human
    leg']` instead of `貝,金,尚`.
  - The other 4 (`楷`/rtk485, `等`/rtk1016, `黙`/rtk255, `員`/rtk59)
    happened to escape damage purely by processing-order luck, not by
    design — same latent bug, just not (yet) triggered.
- Fixed by **deleting all 8 orphaned lines outright**, not just trimming
  the dangerous `rtkNNNN` token — keeping a trimmed version would have
  kept the duplicate alias (e.g. a *second*, wrong "deceased" entry),
  creating a fresh alias-collision ambiguity of exactly the shape
  session 19's `roof`/`屋` fix addressed, rather than actually fixing
  anything.
- **Also fixed, same investigation**: named the previously-undefined
  "top hat" primitive (used literally in `六`'s own CSV baseline,
  "top hat;animal legs", and flagged by `audit_radicals.py` every
  session) as a new alias on `亠`/rad1001 ("lid") — same shape as the
  existing `primitive_lid` disambiguating alias from the out-of-band
  commit. `六`'s decomposition was silently showing only "eight" before
  (the "top hat" term was simply undefined, so it dropped out).
- `audit_radicals.py`'s multi-char undefined-term count: **3 → 1** (only
  `'ninety'` remains — confirmed pure CSV pre-expansion noise for
  `枠`/rtk212, not a data.txt bug; see session 18's notes on why that one
  is intentionally left as-is).
- **Swept the whole file for the same id-as-alias pattern** beyond the
  `rad*.X` block that happened to contain all 8+15 instances found — no
  other occurrences exist elsewhere in `data.txt`. The pattern is fully
  contained to the old KRADFILE-import block from early in this
  project's history.
- Verified: full rebuild from scratch, `get_kanji_detail` spot-checks on
  all 6 directly-touched ids (`看`/`動`/`側`/`鎖`/`伝`/`六`) confirming
  correct real decompositions, `audit_flattening.py` re-run over the
  whole dataset (no new candidates introduced), full standing regression
  suite (`old`/`crime`/`heki`/`awe`/`round`/`cave`/`shellfish`/`street`/
  `shining`/`early`/`courage`/`happiness`) — no regressions.
- Coverage: 595/3000 (19.8%, unchanged from session 21's count — this
  session's fixes mostly worked by *deleting* unrelated orphaned lines
  rather than editing the affected kanji's own lines, so most of them
  don't register under `coverage_status.py`'s "was this kanji's own line
  touched" proxy even though they're now demonstrably correct; a known
  limitation of that proxy, documented in its own module docstring, not
  a sign the fixes didn't happen — `動`/`看`/`側`/`鎖`/`六` are all
  verified fixed above regardless of what the tracker shows).
- Not yet synced to the live server — same standing gap. This session's
  fix in particular (`動`'s decomposition alone) is high-value to
  deploy soon given how common that kanji is.
- **Next session**: the `衣`/rtk423 suspicion from session 21 is now the
  clearer of the two remaining foundation-level issues (CSV components
  "top hat;scarf" vs. the current bare `亠` override) — worth resolving
  before revisiting the `装`/`製` pair; `転`/`芸`/`雲` should be
  re-checked against `audit_flattening.py` now that `伝` itself is fixed,
  since the contiguous-match signal that flagged them may now point
  somewhere more trustworthy. Otherwise continue the frame-ordered sweep
  past 550 (2405/3000 unreviewed).

### 2026-08-21 — session 23

- **Resolved the `衣`/rtk423 foundation suspicion.** Its override was
  just `亠` (lid) — a single stroke for a 6-stroke character, and
  inconsistent with how every *other* kanji in the system already uses
  `衣`: as an atomic leaf primitive referenced directly, never expected
  to expand further (hundreds of kanji reference it this way). CSV's own
  components for `衣` ("top hat; scarf; cloth; clothes; clothing" — the
  last three are keyword-synonym noise) confirm "top hat"+"scarf" as its
  real sub-shapes, but neither needs to be a separately surfaced live
  primitive. Made `衣` explicitly atomic (empty override, the documented
  "this primitive is atomic" convention).
- That one wrong value (`亠` instead of atomic) had been silently
  propagating: every kanji that both referenced `衣` directly *and* also
  listed `亠` as a separate remainder part was double-counting the same
  visual area — the identical "flattening" pattern this whole audit
  targets, just one level removed (a compound plus its own already-
  included sub-stroke, both listed). Fixed the whole dependent cluster,
  cross-checking each against CSV before touching it:
  - `依` (reliant): CSV = "person; cloth" — override was `衣,亠`,
    missing "person" entirely. Fixed to `人,衣`.
  - `装` (attire): CSV = "turtle; samurai; top hat; scarf; ..." —
    confirms `士,爿` (= `壮`/rtk343's own exact parts) plus `衣`'s
    redundant top-hat/scarf. Fixed to `衣,壮` — this closes out
    session 20's original deferred hypothesis for `装`, which was right
    all along but got blocked on exactly this `衣`/`亠` ambiguity at the
    time.
  - `裏` (back): CSV = "top hat; scarf; computer" ("computer" = `里`'s
    keyword variant). Fixed to `衣,里`.
  - `哀` (pathetic): CSV = "top hat; scarf; mouth". Fixed to `衣,口`.
  - `壊` (demolition), `製` (made in...): CSV components are messier
    here and hint at possibly-missing pieces beyond just the `亠`
    redundancy (`製` in particular may be missing a "system"/`制` or
    "sword" component CSV mentions). Only dropped the confirmed-
    redundant `亠` for both (`壊`→`衣,十,土`; `製`→`衣,牛,巾`) — left the
    rest open rather than guess at pieces CSV's noisy list doesn't
    clearly resolve.
- **Re-checked `転`/`芸`/`雲` against `audit_flattening.py`** now that
  `伝` itself is fixed — none of the three appear as candidates anymore,
  confirming they were coincidental matches against `伝`'s old *wrong*
  decomposition, not a real bug of their own. Left them as-is (still
  valid raw-stroke usage `二,厶`, not contradicted by CSV, just not
  maximally using the `云` primitive `伝` now references — a style
  choice, not a confirmed bug, not worth guessing at further).
- Verified: full rebuild from scratch, `get_kanji_detail` spot-checks on
  all 7 touched ids, `audit_radicals.py` unchanged (1 remaining
  undefined term, `'ninety'`, pre-existing documented CSV noise), full
  standing regression suite (`old`/`crime`/`heki`/`awe`/`round`/`cave`/
  `shellfish`/`street`/`shining`/`early`/`courage`/`happiness`) — no
  regressions.
- Coverage: **599/3000 (20.0%)** reviewed (`docs/kanji_review_coverage.tsv`
  regenerated) — the audit has now individually reviewed/fixed one in
  five rtk kanji since it began.
- Not yet synced to the live server — same standing gap. Between this
  session and session 22, a meaningful cluster of high-value fixes has
  accumulated (`動`'s corruption fix especially) that would benefit real
  users soon.
- **Next session**: no more flagged foundation-level suspicions remain
  open (both `伝` and `衣` are resolved) — clear to resume the plain
  frame-ordered sweep past 550 using `audit_flattening.py` +
  `coverage_status.py`, same workflow as sessions 20-21. `壊`/`製`'s
  possibly-missing CSV-flagged pieces and `猿`'s missing animal-radical
  bug (session 21) remain open as lower-priority, harder-to-verify
  items if there's ever a session with appetite for deeper per-kanji
  research beyond structural matching.

*(Note: between this entry and the next, an unrelated one-off request
landed — commit `649576b` adds `android/`, a WebView-shell Android app
around the deployed frontend. Not part of this audit's scope; see
`android/README.md`.)*

### 2026-08-22 — session 24

- **Continued the frame-ordered sweep into 550-700**, and found something
  bigger than the usual flattening pattern: `search_by_parts(['busy'])`
  was returning **42** completely unrelated kanji — `慎`/humility,
  `憾`/remorse, `恐`/fear, `寡`/widow, and 38 more — instead of just `忙`
  itself.
- **Root cause**: the 忄 radical (Heisig's own name for it is "Freud" —
  our system calls it "state of mind") already has a working primitive
  entry, `rad4.2`, and `search_by_parts(['state of mind'])` already
  correctly returned 88 genuine 忄-radical kanji *before* this fix. But
  **41 kanji had the literal character `忙`** (a real, distinct kanji
  meaning "busy") in their override's part list instead of `state of
  mind` — visually plausible, since `忙` is itself built from 忄, but
  semantically wrong: referencing the *kanji* `忙` pulls in *its*
  keyword/alias ("busy"), not the radical concept that was actually
  intended.
- Cross-checked against `data_from_pdf.txt` (the original 4th-edition PDF
  extraction, lower merge priority than `data.txt` but independent of
  whatever introduced this bug) for the 7 of the 41 it has entries for —
  every single one correctly uses "state of mind" there. `data.txt`'s
  override had replaced the correct term with `忙` at some point in this
  project's history, for these and (going by the overwhelming pattern
  consistency — all 心-radical "emotion" kanji, `忙` sitting exactly
  where 忄 visually sits) presumably the other 34 by the same mechanism.
  Fixed by replacing every literal `忙` token with `state of mind` across
  all 41 (frames 666-682, 773, 891, 892, 1271, 1283, 1570, 1595, 1657,
  1679, 1736, 1771, 1857, 2085, 2208, 2215, 2228, 2374-2381).
- **Also found, while investigating**: a duplicate `rad3.34` line in
  `data.txt` — one copy says `state of mind`, another says `finger`. Since
  `data.txt`'s parser builds a plain dict keyed by id, the second
  definition silently won, so `rad3.34`'s own "state of mind" alias was
  never actually live (not that it mattered here, since `rad4.2`
  independently covers "state of mind" correctly). `rad3.34`'s surviving
  "finger" meaning is itself legitimately used elsewhere (the 指-family
  kanji), so this wasn't touched — flagged for a future hygiene pass
  rather than fixed now, since removing the dead line is a pure no-op
  either way.
- **Also applied 13 confirmed flattening fixes** found in the same frame
  range, each cross-checked against `heisig-kanjis.csv` before applying
  (several *candidates* in this range were left alone because CSV didn't
  confirm them — see the commit message for the full list of both):
  `胞`→`月,包`; `砲`→`石,包` (also dropped an extra `口` not present
  anywhere in CSV's components — same for `礁` below); `泡`→`水,包`;
  `礁`→`石,焦`; `雌`→`此,隹`; `姻`→`女,因`; `店`→`占,广`; `忍`→`心,刃`;
  `誌`→`言,志`; `恩`→`心,因`; `想`→`心,相`; `恐`→`工,心,凡`;
  `憧`→`state of mind,童`.
- Verified: full rebuild from scratch. `search_by_parts(['busy'])` now
  returns only `rtk665` itself (was 42); `search_by_parts(['state of
  mind'])` now returns 125 (was 88); `get_kanji_detail` spot-checks
  across a broad sample of the touched ids; `audit_radicals.py` unchanged
  (1 remaining undefined term, `'ninety'`, pre-existing documented CSV
  noise); full standing regression suite (`old`/`crime`/`heki`/`awe`/
  `round`/`cave`/`shellfish`/`street`/`shining`/`early`/`courage`/
  `happiness`) — no regressions.
- Coverage: **646/3000 (21.5%)** reviewed (`docs/kanji_review_coverage.tsv`
  regenerated).
- Not yet synced to the live server — same standing gap. This session's
  `busy`/`state of mind` fix is high-value to deploy given how many
  kanji (41) it touches and how badly wrong the old search result was.
- **Next session**: continue frame-ordered past 700 (2354/3000 still
  unreviewed). Worth a quick scan for whether the same `忙`-style
  "real kanji used as a radical stand-in" mistake shows up with *other*
  radical-adjacent kanji (e.g. `个`/rad1043's "person radical" already
  has a dedicated entry — check nothing similarly substitutes a full
  kanji for it) before assuming this was a one-off.

### 2026-08-22 — owner report between sessions

- **"looked for 'head', got critters. why?"** — `rtk2238` (疋, official
  6th-ed CSV keyword "critters") had a hand-added `head` alias present
  since this repo's very first commit, predating the whole audit. It
  doesn't match the kanji's real meaning at all and made both text and
  parts search for "head" incorrectly include it via self-identity
  matching, alongside the genuine head-related kanji (`rtk1549` head,
  `rtk98` place-on-the-head, `rtk2074` hair-of-the-head, `rad3.31` pig's
  head). `疋` is used as a literal-character component in many other
  kanji (`定`, `礎`, `提`, `従`, `旋`, `縦`, `綻`, `疑`, `擬`, `捷`, `淀`,
  `碇`) — confirmed none reference it via the *word* "head" (only the
  literal character), so deleting the alias doesn't touch any of them;
  CSV's own components for this frame are empty too, so it's a pure
  no-op for `疋`'s own decomposition. Commit `88006dd`.
- Verified: full rebuild, search for "head" now returns only genuine
  head-related kanji, spot-checked `定`/`礎`/`従` still resolve `疋`
  correctly by character, `audit_radicals.py` and the standing regression
  suite unchanged.

### 2026-08-22 — session 25 (review of out-of-band work)

- **Two more out-of-band commits landed directly on `master`** since the
  last entry (`8d88a20`, `20140a6`), same pattern as session 21/22's
  discovery — someone with direct server access working in parallel with
  this audit. Asked to review and verify them rather than just noting
  their existence this time. Real, valuable fixes: `遺` restored to
  `貴,辶` (was flattened, dragging in a misleading `込`/"crowded"
  fragment); `辶`/`阝`/`扌` all got their real glyphs linked to their
  primitive entries for the first time (`rad3.1`, `rad3.40`, `rad3.34`);
  `働`→`亻,動`; `降`→`阝,夂,㐄` (new primitive, replacing a `十`
  approximation of a rare shape) and `換`→`扌,𠂊,央`, both verified
  against `cjkvi-ids`; a Unihan self-reference parsing bug that had
  silently skipped 429 CJK Unified characters during hanzi import, fixed
  with a new `backfill_missing_hanzi.py`; two more KRADFILE
  JIS-substitution proxy bugs in the same class as `fix_kradfile_proxies.py`
  (`扎`→`扌` across 114 kanji, `阡`→`阝` across 40); `七`'s self-referencing
  bogus "diced" alias removed; and a more thorough version of session 22's
  orphaned-primitive cleanup — 23 lines removed instead of my 8, since the
  other 15 were ones I'd judged "currently harmless" at the time (their
  own parts were empty, so they weren't actively clobbering anything) and
  deliberately left alone.
- **That extra thoroughness introduced a real regression**, though: some
  of those 15 "harmless" lines carried *aliases* other kanji depend on by
  word, not just the dangerous id-references I was focused on. Removing
  the whole line silently broke every word-based reference, not just the
  dangerous part — something I didn't fully think through in session 22
  either (I judged them safe because their *parts* were empty, without
  checking whether their *aliases* were load-bearing elsewhere). Caught by
  rebuilding from scratch and re-running `audit_radicals.py`: undefined
  terms jumped from 1 to 7 (50 occurrences). Worst case: **`rtk20` (明,
  "bright") — this project's own flagship search example, literally the
  one in `CLAUDE.md`'s first paragraph ("sun" + "moon" finds 明) —
  silently lost its entire decomposition display.** `get_kanji_detail`
  returned an empty `parts_detail` list, because neither "sun" nor "moon"
  resolved to any kanji anymore (they used to via `rad4.13`/`rad4.15`'s
  now-removed consolidator aliases). `search_by_parts` kept "working" only
  because it does looser text matching than the exact-resolution path
  `get_kanji_detail` uses — easy to miss if you only test search and not
  the detail view. Same mechanism broke "flesh" (`rtk19`/朋), "tongue
  wagging in mouth" (`rtk21`/唱), "baseball" (already-noisy `rtk212`), and
  — worse — `卜` lost its *only character mapping in the entire database*
  (`search_by_char('卜')` returned nothing), breaking all 42 kanji that
  use it as a literal part.
- Fixed by restoring exactly the missing resolvability, nothing more: a
  clean `rad2.22` entry for `卜` (dropping the original dangerous
  id-alias tokens, keeping its real "divining rod/augury/divination"
  aliases), and the 5 lost words added back as plain aliases on their
  correct real targets (`rtk9`/九 gets "baseball" back, `rtk12`/日 gets
  "sun"/"tongue wagging in mouth" back, `rtk13`/月 gets "moon"/"flesh"
  back). Not a revert of the out-of-band cleanup — the dangerous
  id-references stay gone, only the legitimately-needed aliases came
  back. Commit `ccf9fd2`.
- Verified: full rebuild from scratch, `audit_radicals.py` back to 1
  (only `'ninety'`, the pre-existing documented CSV noise), 明's
  decomposition renders `['day','month']` again, `search_by_char('卜')`
  resolves again, ran the two new scripts the out-of-band commits added —
  `audit_self_reference.py` (0 found) and `test_regression_fixes.py` (5
  failures, all explained: every one needs a hanzi-populated `kanji.db`
  via `import_hanzi.py`, which this audit's rebuild methodology —
  `rm kanji.db` + `import_data()` only — has never run in any prior
  session across the whole audit; not a regression from this fix, just a
  scope mismatch between how the out-of-band session tested and how this
  audit always has) — full standing regression suite, and a 45-kanji
  spot-check spanning every session's prior fixes (17 through 24)
  confirming none were silently reverted by the out-of-band commits.
- Coverage: **881/3000 (29.4%)** — a big jump, since the out-of-band
  commits' 550+ line changes to `data.txt` all register as "reviewed" by
  `coverage_status.py`'s proxy (`docs/kanji_review_coverage.tsv`
  regenerated).
- **Lesson for future sessions**: when judging a batch of similar-looking
  entries "safe to leave because nothing currently breaks," also check
  whether their *aliases* (not just their *parts*) are load-bearing
  elsewhere — an alias with zero live consumers today can still be the
  only path some future removal needs to not go through. Also: test the
  detail-view rendering path (`get_kanji_detail`), not just search — this
  session's regression was invisible to `search_by_parts` alone.
- Not yet synced to the live server — same standing gap, now spanning
  work from both this audit and whoever has direct server access.
- **Next session**: continue frame-ordered past 700 if picking up the
  plain sweep again (per session 24), though given how much ground the
  out-of-band commits covered, re-running `coverage_status.py` first to
  see what's actually still unreviewed is worth it before picking a
  frame range.

### 2026-08-19 to 2026-08-22 — session 26 (fuller detail behind session 25's out-of-band work)

Written from the other side of session 25's review: this is the Claude Code
session the owner was directing in parallel, working chat-turn-by-chat-turn
on owner-reported "X looks wrong" spot checks rather than a frame-ordered
sweep. Kept as its own entry (renumbered from a duplicate "session 25" to
avoid colliding with the entry above) because it has finer-grained reasoning
behind several fixes the review entry only summarizes — including exactly
how the alias-clobbering regression happened, useful alongside that entry's
"lesson for future sessions" note. Grouped by finding, not chronologically:

Ran as a series of owner-reported "X looks wrong" spot checks rather than a
frame-ordered sweep, but several turned into systemic bugs affecting many
kanji at once. Grouped by finding, not chronologically:

- **Self-identity search bug**: `search_by_parts` credited self-identity
  (a kanji "is made of" itself) to only one kanji when a term is ambiguous
  across scripts — e.g. searching `族` alone found `rtk1307` (ja-kanji) but
  silently dropped `hanzi-65cf` (zh-Hani), since `resolve_alias` collapses
  ambiguity to one arbitrary pick. Added `_self_identity_kanji_ids()` to
  credit every matching kanji, not just one.
- **`亠`/`蓋` "lid" collision**: `航ロード`'s decomposition used the bare
  keyword "lid" for its `亠` component, ambiguous with `蓋`/rtk1561 (also
  keyworded "lid") under an unscoped search — `_resolve_parts_detail`'s
  script-based tie-break can't disambiguate two candidates of the *same*
  script. Added a `primitive_lid` alias to `亠`/rad1001 and included it
  alongside the existing `亠` token in 航's decomposition (kept the literal
  character too — dropping it broke plain `亠`/`lid` search, since literal-
  presence matching is what protects search from the tie-break's own
  non-determinism).
- **`亠` itself cross-script ambiguous**: separately from the above, `亠`
  is *also* shared between `rad1001` (ja "lid") and `hanzi-4ea0` (zh "head/
  tou") — unscoped search for bare `亠` or `lid` can non-deterministically
  resolve to the wrong one. Not fixed, flagged as a latent gap.
- **`祈` (pray) wrong primitive**: decomposed to `礼`/salutation (a whole,
  visually-unrelated kanji) + `斤`/ax instead of the CSV baseline's
  `altar; axe`. Fixed to `斤,altar`.
- **`六` (six) "top hat" silently dropped**: `data_from_pdf.txt`'s own
  "top hat,animal legs" used Heisig's alternate name for `亠` with no
  alias linking it to `亠`'s entity, so the chip vanished entirely from
  display (not just resolved wrong). Added `top hat` as another alias of
  `亠`/rad1001.
- **`宀`/"roof" vs `家` "house" collision (the big one)**: searching parts
  for `家` returned `宣` (`rtk200`) as a false positive, and `宣`'s own
  detail view falsely showed `家` as one of its own parts. Root cause:
  `宣`'s decomposition (CSV-only, no `data.txt`/PDF override) uses the
  orphaned Heisig primitive name "house" for its own roof-shaped top —
  Heisig's alternate name for `宀`, same pattern as `六`'s "top hat" — but
  "house" is *also* `家`'s real keyword, so it wrongly resolved to `家`
  itself both ways. Fixed `宣` to use the literal `宀` character (same
  proven-safe mechanism `家` itself already used correctly). Given the
  scale of `宀` usage, added a `primitive_roof` alias to `宀`/rad1041 and
  bulk-applied it alongside the existing `宀` token across **all 220**
  kanji using it (109 ja-kanji via `data.txt`, 111 zh-Hani/Hant/Hans
  inserted directly into `parts` since hanzi decompositions aren't sourced
  from `data.txt`).
- **"family name" collision, `rad4.23`**: a fully orphaned duplicate
  primitive (`character='?'`, keyword "family name") never used as a part
  anywhere and never actually inserted as its own kanji — self-identity
  search for "family name" surfaced it as a bare, unlabeled `?` glyph
  alongside the real primitive (`rtk1970`/氏). Deleted outright (confirmed
  zero references first).
- **`働`/`動` and the systemic orphaned-alias-clobbering bug**: `働`
  (work) didn't decompose to `動` (move) at all — flattened radical soup
  instead. Tracing why led to a much bigger bug: 23 leftover scratch
  primitive entries in `data.txt`, dating to the repo's first commit
  (`rad1.5`, `rad2.1`, `rad3.42`, `rad4.39`, etc.), had alias fields that
  accidentally contained real kanji IDs as notes-to-self (e.g.
  `rad4.39:?:rtk1806,well:two,fence posts`). `import_data()`'s "if an
  alias matches an existing kanji ID, treat that as canonical" fallback
  silently redirected identity to that kanji, and where a 4th (parts)
  field was present, **overwrote that kanji's real decomposition**. Live-
  broken for 4 kanji: `看`/rtk688 → just "fist", `側`/rtk1049 → just
  "bound up", `鎖`/rtk2087 → just "chihuahua with one human leg", `動`
  itself → "two, fence posts". All 23 entries were confirmed dead weight
  (never their own kanji, never used as a part) — removed all of them,
  which restored the 4 corrupted decompositions as a side effect and
  stripped 67 bogus aliases leaked onto unrelated kanji. Then fixed `働`
  itself to `亻,動` (matching `data_from_pdf.txt`'s "person,move" and the
  already-correct zh-Hant hanzi row).
- **`遺` (bequeath) wrong primitive + unidentified `辶`**: decomposed to a
  flattened `一,貝,込,口,｜` (dragging in a misleading "crowded" fragment)
  instead of `貴`+`辶`(road), per `data_from_pdf.txt`'s "precious,road".
  The "road" primitive (`辶`, used in `込`/`近`/`通`/`速`/`追`/`遍`/dozens
  more) already existed as `rad3.1` but had never been linked to its real
  glyph (`character='?'`) even though `辶` already existed as a separate
  zh-Hani row (`hanzi-8fb6`). Linked it, fixed `遺`.
- **`夜` (night) incomplete + unidentified `亻`**: decomposed to only
  `夕,亠` (evening, lid) — missing `亻`(person) and `夂`(walking legs)
  entirely, per owner's own breakdown (亠+亻+夂+夕). Fixed to all 4. While
  fixing it, found `亻` had the same unidentified-glyph problem as `辶`:
  an ja-kanji placeholder (`rad2.3`, keyword "person") existed separately
  from the real `亻` character, which only existed as a poorly-named
  zh-Hani row (`hanzi-4ebb`, "radical number 9") — meaning **every** ja-
  kanji decomposition using literal `亻` (618 total, including `働` from
  earlier this session) was silently showing "radical number 9" instead
  of "person". Linked `rad2.3` to `亻`, fixing both `夜` and `働` in one
  sync without disturbing the zh-Hani side (verified via a zh sanity
  check that it still correctly shows "radical number 9" there — script-
  scoped resolution kept both contexts distinct).
- **`換` (interchange) wrong primitive + a 114-kanji KRADFILE proxy bug**:
  decomposed to a flattened `大,儿,冂,勹,扎` instead of `扌,𠂊,央` per
  owner's breakdown. The `扎` token turned out to be the same class of bug
  `fix_kradfile_proxies.py` already fixed for five other characters
  (乞化刈買犯): a real, unrelated kanji (`扎`, "pull up") standing in for
  the `扌` hand radical, because `扌` alone has no JIS X 0208 codepoint —
  used this way across **114** kanji. An unidentified placeholder already
  existed for the real primitive (`rad3.34`, keyword "finger", matching
  Heisig's actual name) but had never been linked to `扌`. Linked it,
  bulk-replaced all 114 occurrences of `扎`→`扌`. Also found and removed a
  duplicate `rad3.34` line (a dead, shadowed "state of mind" definition —
  flagged but not fixed in session 24, fixed here) and added the missing
  `𠂊` primitive ("bound up").
- **`降` (descend) wrong primitives + a second, 40-kanji KRADFILE proxy
  bug**: same pattern as `扎`/`扌` — `阡` (a real, unrelated kanji
  "footpaths between fields") standing in for the left-side mound/hill
  radical `阝`, across **40** kanji (`降`,`陽`,`防`,`陸`,`険`,`阜`, etc.).
  An unidentified placeholder existed (`rad3.40`) with a typo'd keyword
  ("leftside **befa**" instead of "beta") plus a mislabeled `rad3.39`
  ("rightside beta") that had "pinnacle" backwards — `rad3.39` turned out
  to be completely unused (zero references), while "pinnacle" per the
  owner's own Heisig reference belongs to the *left* side. Linked
  `rad3.40`→`阝`, fixed the typo, moved "pinnacle" to the correct entry,
  added a plain "beta" alias. Verified against `cjkvi-ids`'s authoritative
  IDS data that `降` = `阝`(left) + `夅`(right), and `夅` = `夂`(walking
  legs) + `㐄` (U+3404, a rare shape previously approximated as `十`/
  "ten") — added `㐄` as a new primitive ("winter cow", per owner's
  mnemonic) and corrected `降` to `阝,夂,㐄`.
- **`頭` (head) redundant flattening + `豆` wrong primitive**: `頭`'s own
  decomposition directly listed `貝,口,豆,并,頁` — redundant, since `豆`
  already contains `口`+`并` and `頁` already contains `貝` one level down
  via their own sub-decompositions. Collapsed to the clean `豆,頁`. While
  verifying, the owner correctly challenged whether `豆`'s own `口,并`
  breakdown was right in the first place — it wasn't: the CSV baseline
  says `豆`'s real components are "table; one; mouth" (`几,一,口`), not
  `并`("eight radical") at all, and cjkvi-ids doesn't record any
  structural decomposition for `豆` (treats it as atomic), so there was no
  independent source supporting `并`. Fixed `豆` to `几,一,口`.
- **Unihan self-reference hanzi-import bug — 429 missing Chinese
  characters**: unrelated to decomposition quality, found chasing "报
  (report) doesn't find anything." `import_hanzi.py`'s ambiguity check
  treated a self-referencing `kSimplifiedVariant`/`kTraditionalVariant`
  (Unihan's way of saying "this char already IS that form", e.g. `报`'s
  own `kSimplifiedVariant` points at `报` itself) as genuine both-
  directions ambiguity, and separately, a multi-value variant field
  listing the char itself *first* (e.g. `万`'s `kTraditionalVariant`
  "U+4E07 U+842C") only ever read the first value. Together these
  silently skipped **429** CJK Unified characters during the one-time
  hanzi import — 270 missing outright, ~160 more missing their own
  Chinese-script row despite having an unrelated Japanese one (e.g. `万`
  existed as `rtk68` but not as its own `zh-Hans` row). Fixed both
  parsing bugs in `import_hanzi.py`; `backend/backfill_missing_hanzi.py`
  (new) backfills the missing rows + `variant_of` links directly into a
  live, already-seeded `kanji.db` without re-running the full import.
- **"kanji as part of itself" — general audit, owner-mandated**: wrote
  `backend/audit_self_reference.py` to check for both `variant_of`
  self-loops and a decomposition resolving one of its own parts back to
  itself. First version was too naive (a per-term `resolve_alias` check
  flagged 23 false positives — radicals sharing a keyword with an
  unrelated whole kanji built from them, e.g. `虍`/"tiger" the radical vs
  `虎`/"tiger" the kanji, which the app's real synthetic char+keyword-pair
  dropping already handles safely); rewrote it to replicate the app's
  exact resolution logic. Found and fixed one genuine case: `七` (seven)
  had picked up "diced" as a bogus self-alias from a stray `data.txt`
  line (`rtk7:?:diced,seven` — colliding with the real `rtk7` id), causing
  it to list itself as its own decomposition part. Full-database rerun
  after the fix: 0 self-references of either kind.
- **Standing regression coverage, owner-mandated**: `七` bugs like these
  (and the whole "orphaned entry clobbers a real kanji" class) don't get
  caught until someone happens to look at the exact affected kanji.
  `backend/test_regression_fixes.py` pins every individually-verified fix
  above to its exact expected decomposition, spot-checks the hanzi
  backfill, and asserts the two systemic invariants (no KRADFILE proxy
  characters, no self-references) as a fast, always-run smoke test.
  Verified it actually catches regressions (not just trivially passing)
  by running it against a pre-fix backup, where it correctly failed all
  18 originally-pinned checks.
- Also merged 10 upstream commits (`git pull --rebase`) partway through —
  4 conflicts in `data.txt`, all from a parallel session's own fixes to
  similar bugs (its own 8-entry orphaned-alias cleanup, `政`/`定`/`錠`/
  `燃` restructured to use proper intermediate kanji). Resolved by taking
  the better structure from each side rather than picking one wholesale.
- Every fix in this session was applied to the live server: `data.txt`
  edited → `sync_system_data.py --dry-run` to confirm scope → applied →
  spot-verified via `get_kanji_detail`/`search_by_parts` → `kanji-backend.
  service` restarted. `backup_db.py` run before every write.
- **New standing rule (owner-mandated, this session)**: every fix/commit
  from now on gets a doc entry here (or a new dated section) explaining
  what was done and why — not just a commit message — so a `git pull`
  can be understood by reading these files, not just `git log`.

### 2026-08-23 — session 26

- **Reviewed and verified two more out-of-band commits** (`9568402`,
  `5c6c575`) found on pull before starting new work, per this session's
  standing practice: `頭`'s own decomposition was redundantly flattening
  `貝,口,豆,并,頁` when `豆` already contains `口,并` and `頁` already
  contains `貝` a level down — collapsed to `豆,頁`. While verifying that,
  the owner directly challenged whether `豆`'s own existing `口,并`
  breakdown was even right — it wasn't: CSV's real components are
  "table; one; mouth" (`几,一,口`), not `并` ("eight radical"), and
  `cjkvi-ids` records no structural decomposition for `豆` at all (treats
  it atomic) — nothing supported `并`. Fixed to `几,一,口`. Also merged
  the session-25 regression fix and, as a side effect of restoring
  `rtk12`'s "sun" alias, fixed a second pre-existing bug: `宣`'s own "sun"
  component used to resolve to an unrelated pinyin collision
  (`hanzi-5b6b`/孫, "grandchild") since `rtk12` had no "sun" alias to
  correctly win the script-scoped tie-break before. Verified via full
  rebuild: `audit_radicals.py` back to 1 (only `'ninety'`),
  `test_regression_fixes.py` down to the same 4 expected hanzi-scope-
  mismatch failures as every prior rebuild this whole audit (this repo's
  standard rebuild — `rm kanji.db` + `import_data()` only — has never run
  `import_hanzi.py`, so any pin expecting a hanzi-* id will always show
  "missing" here; not a real regression, see session 25's notes), 45-kanji
  spot-check across sessions 17-24 clean, no reversions found.
- **Continued the frame-ordered sweep**, picking frame 1443-1490 (one of
  the largest remaining contiguous unreviewed blocks after the
  out-of-band commits' extensive coverage elsewhere — re-ran
  `coverage_status.py` first to find it, per session 24's own advice).
  `audit_flattening.py` found a large, clean cluster: `絵`, `統`, `給`,
  `絡`, `結`, `納`, `紛`, `約`, `総` — every one of these `糸`-radical
  (thread) kanji redundantly listed the literal character `糸` *and* its
  own already-flattened sub-parts (`幺,小`) side by side, on top of a
  *second*, independent flattening bug layered underneath (another
  compound's own parts spelled out raw instead of referenced). `終` (end)
  had the identical `糸+幺+小` self-doubling with no second bug on top.
  `蓄` and `擁` were separate, single-compound flattening bugs in the
  same frame range, unrelated to the `糸` cluster.
  - Cross-checked every candidate against CSV before applying. Where CSV
    directly names the compound's own keyword, applied the full collapse:
    `絵`→`糸,会` ("meeting"); `統`→`糸,充` ("allot"); `納`→`糸,内`
    ("inside"); `紛`→`糸,分` ("part"); `約`→`糸,勺` ("ladle"); `総`→
    `糸,心,公` ("public"); `蓄`→`艾,畜` ("livestock"). `擁`→`亠,幺,推`
    applied on a clean, unambiguous structural match with no CSV
    contradiction.
  - Where CSV instead listed the matched compound's own sub-parts as
    independent atomic terms rather than naming the compound itself
    (`結`'s CSV says "samurai;mouth", not "good luck"; `絡`'s says "each;
    walking legs;mouth", not "end"; `給`'s says "meeting", contradicting
    the structural match to `今`/"now") — left the secondary collapse
    alone and fixed only the confirmed `糸` redundancy: `給`→`口,糸,个,一`;
    `絡`→`口,糸,夂`; `結`→`口,士,糸`. `終`→`糸,夂` (no secondary question,
    a straightforward drop of the redundant `幺,小`).
- Verified: full rebuild from scratch, `get_kanji_detail` spot-checks on
  all 12 touched ids, `audit_radicals.py` unchanged (1 remaining
  undefined term, `'ninety'`), `test_regression_fixes.py` unchanged (same
  4 expected hanzi-scope-mismatch failures), full standing regression
  suite (`old`/`crime`/`heki`/`awe`/`round`/`cave`/`shellfish`/`street`/
  `shining`/`early`/`courage`/`happiness`/`busy`/`head`/`sun`/`moon`) —
  no regressions.
- Coverage: **893/3000 (29.8%)** reviewed (`docs/kanji_review_coverage.tsv`
  regenerated).
- Not yet synced to the live server from this session's own commits —
  same standing gap for this audit's own fixes (the out-of-band session
  has been syncing its own work directly, per its notes above).
- **Next session**: continue frame-ordered — re-run `coverage_status.py`
  first each time now, since the out-of-band commits' coverage is
  scattered rather than contiguous and the next-largest unreviewed block
  will keep shifting.

### 2026-08-23 — owner check between sessions

- **"check 痴"** — same flattening pattern as the rest of this audit:
  `痴` (stupid) listed `口,矢,疔` (mouth, dart, sickness-radical) instead
  of referencing `知` (rtk1308, "know"), whose own decomposition is
  already exactly `口,矢`. Collapsed to `知,疔`. Also confirmed `疔`
  itself isn't a bug — it's an intentionally-named stand-in glyph for the
  疒 (sickness) radical (`rad1048`, keyword "sickness radical"), not a
  real RTK frame being clobbered like the genuine KRADFILE-proxy bugs
  (`扎`/`阡`) fixed in earlier out-of-band commits — `heisig-kanjis.csv`
  has no row for `疔` at all. Commit `f31b72b`.
- Verified: full rebuild, `get_kanji_detail` confirms `痴` now resolves to
  `['知:know', 'rad1048:sickness radical']`, `audit_radicals.py` and the
  standing regression suite unchanged.
- **Follow-up owner question**: "почему 疔 ???? он не часть этого
  иероглифа" (why 疔? it's not part of this character) — a fair
  challenge, and it turned out to be properly fixable rather than just
  an accepted limitation. `疔` (U+7594, "boil/carbuncle") was used as
  `rad1048`'s glyph because `疒` (U+7592, the *actual* sickness radical)
  had no codepoint in the 1978 JIS X 0208 standard KRADFILE (this
  project's original radical-decomposition source, back before this
  audit even started) was built against — documented in session 4 as a
  limitation shared by 6 other primitives (`并`/`扎`/`杰`/`个`/`阡`/`禹`).
  That JIS constraint doesn't apply to this Unicode-throughout app at
  all, though, and `疒` itself was sitting completely unused. Changed
  `rad1048`'s character from `疔` to `疒`, kept `疔` as a secondary alias
  so all 22 existing kanji whose part_term is literally "疔" (病, 痛,
  痴, 癖, ...) keep resolving with zero per-kanji edits —
  `_resolve_parts_detail` renders a resolved part's own `character`
  column, not the literal search term, so the displayed glyph flips
  correctly everywhere automatically. Commit `eab66c2`.
- Verified: full rebuild, `get_kanji_detail` on `痴`/`癖` now shows `疒`
  (not `疔`) for the sickness-radical chip, `search_by_parts(['sickness
  radical'])` still returns all 22 hosts + the primitive itself,
  `audit_radicals.py`/`test_regression_fixes.py`/standing regression
  suite unchanged. The other 6 documented JIS substitutes
  (`并`/`扎`/`杰`/`个`/`阡`/`禹`) weren't touched — worth the same
  treatment in a future session if their real Unicode radical forms are
  similarly free to use.

### 2026-08-23 — primitive-id migration (owner-driven)

- **The 疔 fix prompted a bigger, valid question**: "меня это беспокоит.
  берем нумерацию откуда попало, не указывая источник... почему мы не
  используем официальные таблицы там где возможно?" (this worries me —
  we're taking numbering from wherever, without citing a source... why
  don't we use official tables where possible?). Fair on both counts —
  investigated properly before touching anything, since a wrong "official"
  number would be worse than the honest-but-arbitrary status quo.
  - The legacy `rad{N}.{M}` scheme (used throughout `data.txt` for
    primitives with no kanji frame) turned out to be **the old Perl
    app's own numbering**, inherited as-is into this project — not
    derived from KRADFILE or any external standard, confirmed by
    checking session-1-era notes above ("the legacy `radN.M` dotted
    scheme was the *old Perl app's* convention, not this project's").
    The newer `rad{N}` (1001+) scheme is just this project's own
    sequential counter. Neither claims an external source, but neither
    disclaims one either — exactly the "resolved but misleads" shape
    this audit keeps finding.
  - **Kangxi radicals are real and citable**: 214 of them, used
    identically for Japanese and Chinese, with an authoritative
    machine-readable source at Unicode's own `CJKRadicals.txt`
    (radical-number -> ideograph mapping) plus positional-variant forms
    (亻/扌/攵/辶/etc.) documented in `NamesList.txt`'s CJK Radicals
    Supplement block. Verified every candidate against these files
    directly, not from memory.
  - **A separate numbered "primitive index" in RTK 6th edition does
    NOT exist**, contrary to the initial assumption. The owner pointed
    at github.com/cyphar/heisig-rtk-index (the most thorough third-party
    RTK index project) to check; its own primitive-numbering generator
    script (`scripts/index_primitives.py`) comments its own output
    field `# A "fake" Heisig number for the primitive` — computed as
    either `{parent_frame}.{child_index}` or a project-internal
    processing-order counter, never anything Heisig's book itself
    assigns. Heisig numbers *frames*, never primitives independently of
    them. Inventing an `rtk6.N` scheme (the original idea) would have
    manufactured exactly the same false-authority problem this whole
    audit exists to catch — decided against it, used descriptive slugs
    for non-Kangxi primitives instead (owner's own suggested
    alternative, e.g. "user-комбинация-шляпа-вода2").
  - **Migrated 78 primitive-only ids**: 61 confirmed Kangxi radicals ->
    `kangxi{N}` (`rad1041` 宀 -> `kangxi40`, `rad3.34` 扌 -> `kangxi64`,
    `rad2.22` 卜 -> `kangxi25`, ...); 17 genuine non-Kangxi primitives
    (katakana-shaped ノハマユ, the still-active KRADFILE proxies 艾/个/并/
    杰/禹, book-specific `heki`/`teki`) -> descriptive `prim-{slug}` ids
    that don't claim numbered authority they don't have. Verified zero
    other lines in `data.txt` reference any of the 78 old ids literally
    before renaming (everything else references primitives by character
    or keyword text, never by raw id string), so the diff is exactly 78
    pure id-field renames — no other kanji's own content touched.
    Updated `test_regression_fixes.py`'s pinned ids and `CLAUDE.md`'s
    id-format documentation to match. Commit `5fb7d8e`.
- Verified: full rebuild from scratch, `audit_radicals.py` unchanged (1
  remaining undefined term, `'ninety'`), `test_regression_fixes.py` back
  to only the 4 expected hanzi-scope-mismatch failures, full standing
  regression suite plus fresh spot-checks on renamed primitives
  (`search_by_parts` on `'roof'`/`'cliff'`/`'fire radical'`/`'katakana
  ha'`/`'heki'` all still resolve correctly), grep confirms no frontend
  or backend runtime code hardcodes any of the old ids.
- **Not fixed here, flagged as a follow-up** — a different kind of
  change (merging duplicate content, not renaming): 4 of the 17
  `prim-{slug}` entries (个/并/杰/禹, ~392 kanji combined) are KRADFILE
  JIS-substitution proxies that likely *duplicate* an
  already-correctly-identified Kangxi radical elsewhere (e.g.
  `prim-person-radical`/个 probably duplicates `kangxi9`/亻 — same shape
  as this session's earlier `疔`->`疒` fix, but at consolidation scale
  rather than a single character swap). `扎`/`阡` (hand/mound proxies)
  were already consolidated by an out-of-band session and now sit at 0
  live usages.
- **Next session**: continue the plain frame-ordered sweep (re-run
  `coverage_status.py` first, 2107/3000 rtk kanji still unreviewed);
  the `个`/`并`/`杰`/`禹` duplicate-radical consolidation above is a good
  candidate for a session with room for it.

### 2026-08-23 — visual verification method + 个/umbrella fix

- **Following up on the flagged `个`/`并`/`杰`/`禹` consolidation candidate
  above turned into a methodology lesson.** Guessed `个` (kept in
  `data.txt` as "person radical", 101 host kanji) duplicated `kangxi9`
  (亻) — wrong. "Corrected" to guessing it was a proxy for `𠆢` (radical
  9's top-position variant form) — also wrong, still reasoning from
  Unicode variant tables rather than looking. Owner pushed back with a
  specific, simple ask: render the actual glyphs and compare them as
  images, not as codepoints. Doing that immediately settled it — `个`
  has an extra vertical stroke through the middle that the real
  top-of-会/谷/令 shape doesn't have (confirmed via
  `backend/render_glyphs.py`, a new tool built for exactly this — see
  Tooling below). Cross-checked against `heisig-kanjis.csv`'s own
  components column: "umbrella" is literally listed for both `会` and
  `谷`. The primitive has nothing to do with "person" at all, in either
  Heisig's own naming or the actual drawn shape — the "person radical"
  label had been wrong for as long as this line has existed (predates
  the whole audit).
- **This is now the standing verification method for primitive
  identity, owner-mandated**: render and visually compare before
  trusting a codepoint/keyword match, working toward eventually checking
  every kanji this way. Documented in `CLAUDE.md` so it's visible
  immediately in any future session, not buried in this doc alone.
- **Used the new tool to check the other 3 remaining KRADFILE proxies**
  before touching anything, rather than assuming they had the same bug:
  - `杰` ("fire radical", 96 hosts) — **confirmed correct**: renders as
    木 + 灬 (the 4-dot fire radical), visually matches its hosts
    (魚/烈/熱/鳥/駒/...). Not touched.
  - `禹` ("track radical", 13 hosts) — rendered side-by-side with its
    actual hosts (属/嘱/偶/遇/愚/隅/寓/萬), all of which visibly share
    the same bottom component `禹` renders as. Not clearly wrong: not
    touched without stronger evidence than "looks roughly right."
  - `并` ("eight radical", 182 hosts) — `并` itself renders as a
    6-stroke character, visually nothing like the 2-stroke `丷`/`八`
    shape its own keyword implies. But its 182 hosts span visibly
    diverse, structurally unrelated contexts (羊-related: 義/犠/群/善;
    and many unrelated: 従/弟/尊/喜/南/...) — the same multi-meaning-
    single-glyph shape this audit already found for `ハ` (session ~14)
    and deliberately did *not* blanket-fix. Flagged as found, explicitly
    not fixed today — needs the same careful per-cluster investigation
    `ハ` got (which kanji actually share which visual role), not a
    single rename.
- **Fixed the one confirmed case**: `prim-person-radical` (个) ->
  `prim-umbrella`, keyword "person radical" -> "umbrella". Single line
  change — every host kanji already references `个` by character, not
  by id or keyword text, so nothing else needed touching. Commit
  `73a64bd`.
- Verified: full rebuild from scratch, `get_kanji_detail` on `会` now
  shows the "umbrella" chip correctly, `search_by_parts(['umbrella'])`
  returns 102 kanji, old text "person radical" no longer resolves to
  anything, `audit_radicals.py`/`test_regression_fixes.py`/standing
  regression suite unchanged (same 4 expected hanzi-scope-mismatch
  failures as every prior rebuild).
- **Next session**: `并`'s multi-meaning investigation (same shape as
  `ハ`) is the natural next step if there's appetite for it — expect it
  to be slow (182 hosts to sort into visual clusters) and to end with a
  partial fix plus an explicitly-documented remainder, same as `ハ`
  rather than a single clean answer. `render_glyphs.py` should make the
  per-cluster visual checks much faster than the original `ハ` session
  had available. Otherwise continue the frame-ordered sweep.

### 2026-08-23 — owner report: `并` search returning wrong results

- **"поиск 并 дал кучу неправильных ответов"** (search for 并 gave a
  bunch of wrong answers) — turned the flagged-but-deferred `并`
  investigation above into an actual fix, sooner than expected.
  `search_by_parts(['eight radical'])` was returning 183 kanji, matching
  exactly the false-positive count `并`'s 182 hosts implied.
- Went back to the visual sample from the earlier flag (羊/首/帝/前/曽/
  遂/従) and this time cross-checked *every one* of the 182 hosts against
  `heisig-kanjis.csv`'s components column systematically (not just the
  hand-picked sample) — confirmed the earlier suspicion properly: `并`
  is genuinely polysemous, bundling at least 3-4 distinct real concepts
  under one wrong character, not a single mislabeling like `个` turned
  out to be:
  - **54 hosts** whose CSV components explicitly say "horns" — a real,
    distinct, CSV-confirmed Heisig primitive. There was already an
    unlinked placeholder for exactly this sitting unused:
    `rad2.9:?:horns`, character never set.
  - The whole 羊-family (洋/詳/義/犠/儀/...) where `并` is really just
    `羊`'s own top stroke, redundantly re-flattened *alongside* a
    separate `羊` token already in the same line — a flattening bug,
    not a mislabeling one; not fixed here (different fix shape).
  - Several more distinct sub-clusters visible in the CSV data (a
    帝-family "crown"-ish cluster, a 豆-family "beans" cluster, others)
    not yet individually verified.
- **Fixed only the CSV-confirmed "horns" cluster**, the one
  highest-confidence, cleanly-separable piece: linked `rad2.9`'s real
  glyph (丷, U+4E37 — confirmed by rendering it directly next to
  羊/首/前's actual top stroke, they match exactly) and renamed it to
  `kangxi12` (丷 is an official Kangxi radical 12/八 variant form per
  `CJKRadicals.txt`'s own variant listing — but kept "horns" as the
  keyword, since that's the genuinely distinct mnemonic name Heisig
  gives this shape, not "eight"). Replaced the `并` token with `丷` in
  exactly the 54 CSV-confirmed hosts' own lines — a contiguous
  single-token swap, nothing else touched. `并` itself (`prim-eight-
  radical`, still wrong, ~128 hosts left) was deliberately left alone —
  the remaining clusters each need the same individual verification
  before touching, not a second guess applied broadly. Commit `36227c6`.
- Verified: full rebuild from scratch, `search_by_parts(['horns'])` now
  returns exactly 55 (was 0 live before — the keyword existed but
  nothing resolved to it), `search_by_parts(['eight radical'])` down
  from 183 to 129, `get_kanji_detail` on 羊/首/前 all correctly show the
  horns chip, `audit_radicals.py`/`test_regression_fixes.py`/standing
  regression suite unchanged (same 4 expected hanzi-scope-mismatch
  failures as every prior rebuild).
- Coverage: **935/3000 (31.2%)** reviewed (`docs/kanji_review_coverage.tsv`
  regenerated).
- **Next session**: `并`'s remaining ~128 hosts still need per-cluster
  sorting (羊-family flattening fix is probably the next cleanest piece —
  structurally simple, just needs each host's redundant `王,...,并,...,羊`
  pattern collapsed once `并`→`丷` is applied and `羊` already covers the
  rest). Otherwise continue the frame-ordered sweep.

### 2026-08-24 — `并`'s 羊-family cluster: redundant-flattening fix

- Continuing the previous session's "next session" pointer: the 羊-family
  (sheep) cluster of `并`'s remaining ~128 hosts, the piece flagged as
  cleanest. `rtk586` (羊, sheep) already correctly decomposes to `王,丷`
  (fixed earlier this audit). Many compounds built on top of 羊 were
  listing **both** that flattened pair (`王,并`) *and* a separate `羊`
  token in the same line — the same "flattening bug" pattern that has
  been this whole audit's dominant bug class, just with 羊 as the
  re-flattened compound this time instead of a kanji.
- Cross-checked every candidate against `heisig-kanjis.csv`'s components
  column first (per the audit's standing CSV-before-fix methodology):
  587/588/589/590/591/592/593/594 (美/洋/詳/鮮/達/羨/差/着), 691/692/693
  (義/議/犠), 1003/1059/1148/1169/1247/1423/1591 (様/儀/遅/祥/群/窯/養) all
  have CSV `components` listing "sheep" as a single named item — never
  "wool"/"eight" separately — confirming Heisig treats 羊 as one atomic
  primitive here, so re-listing its own flattened parts alongside it is
  pure redundancy.
- Seven more candidates (羞/瑳/痒/蟻/叢/翔/躾, ids 2198/2612/2622/2726/
  2904/2940/2949) fall outside the ~2200-kanji CSV's coverage, so used
  the standing visual-verification method instead: rendered all seven via
  `render_glyphs.py` and confirmed by eye that each one visibly contains
  the same 羊 top-shape (see `uncovered_cluster.png` from this session) —
  same fix applies.
- **Explicitly did NOT touch** 業/撲/僕 (rtk1931/1932/1933), even though
  their data.txt lines also list `王,并,羊` together, matching the same
  surface pattern. CSV components for these three list no "sheep" at all
  ("business; upside down in a row; not yet; tree; wood" for 業, etc.),
  and rendering 業 next to 羊 shows a visibly different top shape (業's
  top is three separate strokes/hooks, not 羊's clean two-horn-and-cross
  shape) — so `羊` may itself be the wrong token in these three lines,
  a different (and not yet diagnosed) bug, not this session's redundant-
  flattening pattern. Left alone and flagged here rather than guessed at.
- Applied: removed the redundant `王` and `并` tokens (both, when both
  present) from exactly the 25 confirmed lines, keeping `羊` as the sole
  representation of "sheep" in each. Single mechanical script, no other
  tokens touched. Full list of ids: rtk587, rtk588, rtk589, rtk590,
  rtk591, rtk592, rtk593, rtk594, rtk691, rtk692, rtk693, rtk1003,
  rtk1059, rtk1148, rtk1169, rtk1247, rtk1423, rtk1591, rtk2198, rtk2612,
  rtk2622, rtk2726, rtk2904, rtk2940, rtk2949.
- Verified: full rebuild from scratch; `search_by_parts(['sheep'])` now
  returns 32 kanji (was under-matching before, since many hosts only
  found 羊 via the redundant flattened tokens rather than a clean `羊`
  chip); `test_regression_fixes.py` — added 5 new pinned entries for this
  fix (rtk587, rtk588, rtk691, rtk1591, rtk2622) — passes with the same 4
  expected hanzi-scope-mismatch failures as every prior rebuild, nothing
  else; full search-term regression checklist (old/crime/heki/awe/round/
  cave/shellfish/street/shining/early/courage/happiness/busy/head/sun/
  moon/umbrella/sheep/horns) unchanged/correct.
- Coverage: **935/3000 (31.2%)** reviewed (unchanged — these ids had
  already been touched by an earlier commit in this audit's window, so
  they don't add newly-reviewed kanji to the counter; the fix itself is
  still new and verified this session).
- **Next session**: `并`'s remaining hosts: the 帝-family "crown"-ish
  cluster, the 豆-family "beans" cluster, and the CSV-uncovered rare
  kanji, per the previous session's clustering — none individually
  verified yet. Separately, the 業/撲/僕 `羊` mismatch flagged above needs
  its own investigation (render + trace what `并`/`羊` are actually meant
  to represent there) before either is touched. Otherwise continue the
  frame-ordered sweep.

### 2026-08-25 — `并`'s 半-family cluster: missing-component bug (worse than flattening)

- Continuing the daily sweep of `并`'s remaining hosts (previous session's
  "next session" pointer named 帝-family and 豆-family as the next
  clusters). Ran the same CSV cross-check across all ~105 remaining
  non-羊-family hosts first, to map out sub-clusters before touching
  anything (`heisig-kanjis.csv` components for frames 287, 294, 466, 467,
  471, 473, 857, 988, 1090, 1118-1120, 1286-1294, 1358, 1367, 1440,
  1550-1554, 1596-1599, 1619-1621, 1740-1742, 1757, 1815, 1838-1839,
  1843-1845, 1852, 1855, 1892, 1924-1926, 2067-2068, 2089, 2113-2115,
  2144, 2186, and the ~50 kanji outside CSV's ~2200-frame coverage).
- Found several genuine sub-clusters (帝-family "vase"+"stand up", a
  "quarter" cluster at 1290-1294, the 半 "half" cluster, more) — same
  polysemy pattern as the 羊-family and horns clusters, confirming `并`
  really does bundle many distinct concepts. The 帝-family "vase" shape in
  particular doesn't have an obvious clean standalone Unicode match on
  inspection (帝/商/新/南's shared top structure is compact and the exact
  stroke grouping isn't obvious from rendering alone) — deferred rather
  than guessed at, per the standing "don't force a fix without full
  render+CSV confidence" rule.
- The 半 (half) cluster was clean and high-confidence, so fixed it this
  session: `伴`/`畔`/`判` (rtk1287/1288/1289, "consort"/"paddy ridge"/
  "judgement") were each listing `半`'s own already-flattened parts
  (`｜,二,并,十`) instead of referencing `半` (rtk1286) directly — **and in
  doing so silently dropped their own actually-distinguishing part
  entirely**: `伴` had no "person" component at all despite 亻 being right
  there in the glyph, `判` had no "sword"/刂 despite it being the entire
  right half of the character. This is a step worse than the usual
  redundant-flattening pattern (which just duplicates information) — this
  one *lost* information a learner needs. Confirmed via
  `heisig-kanjis.csv` ("person;half" / "paddy-ridge;rice field;brains;
  half" / "judgement;half;sword") and by rendering all four glyphs side
  by side (`ban_cluster.png`) — 伴/畔/判 visually and unambiguously show
  半's exact right-hand shape plus their own distinct left/right part.
- Applied: `rtk1287:伴:consort:亻,半`, `rtk1288:畔:paddy ridge:田,半`,
  `rtk1289:判:judgement:半,刀` — referencing `半`/`田`/`刀`/`亻` as literal
  character tokens (all four already resolve to existing entries:
  rtk1286, rtk14, rtk87, kangxi9), not by resolving what `并` itself
  means (left as `prim-eight-radical`, still wrong, orthogonal to this
  fix — `半` itself wasn't touched).
- Verified: full rebuild from scratch; `get_kanji_detail` on all four now
  shows `rtk1287 → {kangxi9, rtk1286}`, `rtk1288 → {rtk14, rtk1286}`,
  `rtk1289 → {rtk1286, rtk87}`; `search_by_parts(['half'])` now correctly
  returns all 4 (rtk1286/1287/1288/1289), was previously missing all
  three derived kanji; `test_regression_fixes.py` — added 3 new pinned
  entries — passes with the same 4 expected hanzi-scope-mismatch
  failures as every prior rebuild, nothing else; full search-term
  regression checklist unchanged/correct.
- Coverage: **958/3000 (31.9%)** reviewed.
- **Next session**: `并`'s remaining hosts — the "quarter" cluster
  (1290-1294: 拳/券/巻/圏/勝, CSV-confirmed, looks as clean as this
  session's 半-family), the 豆-family "beans" cluster (largest remaining,
  ~17 hosts), the 帝-family "vase" cluster (deferred — needs a slower,
  more careful glyph-isolation pass, possibly cropping/zooming individual
  strokes rather than whole-character rendering), and the ~50 CSV-
  uncovered rare kanji (need per-kanji visual verification with no CSV
  backstop). The 業/撲/僕 `羊` mismatch from the previous session is still
  open too. Otherwise continue the frame-ordered sweep.

### 2026-08-25 — owner requests: in-app review queue, back-button placement, About page

Three unrelated owner-driven requests in one session (verbatim, Russian):
"добавь 2 кнопки в интерфейсе: одобрить разбиение или оспорить. оспоренные
разбиения ты будешь потом проверять. а одобренные вносить в список тестов
на предмет регресссии. после обработки этого список очистить. еще хочу
чтобы кнопка back была слева а не в центре." and, mid-turn, "добавь на
интерфейс линк about с описанием проекта и ссылкой на репо и скачивание
приложения".

**1. In-app decomposition review queue.** Turns this whole audit's standing
"render it, don't just reason about it" verification method into something
any logged-in user can do from the page, not only something that happens
inside a Claude session. `decomposition_reviews` table (`_migrate_v4`,
schema now at v4): one row per `(decomposition_id, reviewer_id)`, `verdict`
`approved`/`disputed`, `processed_at` nullable. `POST
/decompositions/{id}/review` upserts a reviewer's own vote (changing your
mind updates the row, doesn't duplicate it, and clears `processed_at` so a
changed vote gets re-triaged); gated the same way every other write in
this app is (`visibility = 'public' OR owner_id = reviewer`), so a user
can't vote on a decomposition private to someone else even by guessing
its id — verified with a two-user test (owner can review their own
private decomposition, a second user is correctly blocked with the same
"not found" response `_visible_kanji_id` uses elsewhere for privacy,
public/system decompositions are reviewable by anyone logged in).
`KanjiDetail.jsx` shows two buttons under
every decomposition block when logged in, highlighting whichever verdict
(if any) the current viewer already cast. `backend/review_queue.py` is the
maintainer-facing other half — lists pending (`processed_at IS NULL`)
reviews grouped by verdict; a maintainer works through them (approved →
pin a `test_regression_fixes.py` entry, disputed → investigate the same
way any owner-reported bug in this audit gets investigated) then runs
`--mark-processed <id>...`, which is the "после обработки этого список
очистить" step — rows are marked processed, not deleted, so there's still
an audit trail. Not wired into the standing daily-checkin loop yet; that's
next.

**2. Back button placement.** Root cause: `.back-btn` was never explicitly
centered — it renders flush-left inside `.detail-panel`, but `.app` itself
is a centered `max-width:900px` column (`margin:0 auto`), so on a wide
viewport the button reads as floating near screen-center rather than
pinned to an edge, since it's the only element near the top of that
column with nothing beside it. Confirmed by rendering the actual
`.back-btn` + `App.css` in headless Chromium before and after (same
render-and-compare method as the primitive-identity work, applied to CSS
layout instead of glyphs — `backbtn_before.png`/`backbtn_after.png`).
Fixed by pinning it `position: fixed; top/left: 20px`, matching the
existing symmetric pattern where `.header-controls` (lang toggle, auth)
is already pinned to the app column's top-right corner — now the back
button is genuinely anchored to the browser window's left edge, visible
while scrolled too, not just left-aligned within a column that's itself
centered on screen.

**3. About page.** New `AboutPage.jsx` (`view === "about"`, reachable from
a header nav button shown to everyone, not just logged-in users) with the
project description (same framing as this file's own intro), a link to
the GitHub repo, and a download link for the Android app. The APK wasn't
published anywhere (`android/README.md`'s own "Known limitations" said so
explicitly — no Play Store, no CI, no GitHub Release) — asked the owner
how to source a download link rather than fabricate one; told to "publish
it yourself. put it somewhere." Built `:app:assembleRelease` (points at
the live `https://srv.alteon.help/kanji/`, unlike the debug variant which
targets a local dev server), signed it with a fresh throwaway keystore
(not committed — same "signing secret stays out of git" policy the README
already states for a hypothetical future *real* signing key; sideloaded
apps don't need Play-Store-grade key provenance), `zipalign` + `apksigner
verify`d it, and committed the signed APK directly into the repo at
`android/releases/rtk-kanji-latest.apk` (the GitHub MCP tools available in
this session have no release-asset-upload capability, and their
file-content tool assumes text content — base64/binary-safe via plain
`git add`/`commit`/`push` instead, which is how this whole session's work
already reaches GitHub). `android/README.md` documents the caveats: this
signing key isn't the "real" one, no auto-update, rebuild-and-replace to
update. About page links the raw GitHub URL for direct download.

**Verified**: `npm run build` and `npm run lint` clean; `test_regression_fixes.py`
same 4 expected hanzi-scope failures as every prior rebuild, nothing else;
manually exercised the review-queue backend end-to-end via `database.py`
directly (upsert, verdict change, queue read, mark-processed, invalid-verdict
and invalid-decomposition-id rejection) and `review_queue.py`'s CLI, since
this sandbox's FastAPI/uvicorn won't start (`google.auth` → `cryptography`
Rust-bridge crash unrelated to this session's changes — same limitation as
every prior session in this audit, which have never had a live server to
test against either); `apksigner verify` confirmed the APK's signature.
Coverage counter unaffected (this session touched app code and docs, not
`data.txt`).

**Next session**: wire `review_queue.py` into the standing daily-checkin
routine (check the pending queue as one of the first things each session
does, alongside pulling and reading the progress notes) now that real
reviews can start accumulating; otherwise continue the `并` cluster sweep
above.

### 2026-08-25 — `并`'s "quarter" cluster: another missing-component bug

- Continuing the `并` sweep (checked `review_queue.py` first per the
  previous entry's "next session" note — empty, no reviews submitted
  through the live site yet). Picked up the "quarter" cluster
  (1290-1294: 拳/券/巻/圏/勝) flagged two sessions ago as CSV-confirmed
  and clean.
- `heisig-kanjis.csv` components list "quarter" as a distinct concept
  across all five (e.g. 1290 "quarter; hand", 1291 "quarter; sword") —
  never split into separate strokes. Cross-checking against
  `data_from_pdf.txt` (the pre-`data.txt`-override source) confirmed the
  same: `rtk1291:券:ticket:quarter,dagger`, etc. — "quarter" was
  originally one atomic, unresolved term (no character assigned), same
  shape as this whole audit's other `?`-glyph primitives before real
  glyphs got attached.
- The five 1290-1294 hosts already correctly include `并` (now
  `prim-eight-radical`, the still-unresolved mislabeled home for
  "quarter" — same open question as the 帝-family "vase" cluster, not
  resolved this session either) among their flattened tokens — the
  common subset across all five is `大,二,并`, confirmed by rendering all
  five glyphs and visually checking they share the same top-left shape.
  So no bug there.
- But two *further* hosts sharing "quarter" per both `heisig-kanjis.csv`
  and `data_from_pdf.txt` — `rtk1295:藤` (wisteria) and `rtk1296:謄`
  (mimeograph, CSV's own keyword typo'd "facsimilie") — had `data.txt`
  overrides that kept `一,二,大` but **silently dropped `并`**, the exact
  same missing-component bug as last session's `伴`/`判` (半-family): not
  redundant flattening, an outright lost part. Confirmed visually by
  rendering 藤/謄 next to 拳 and checking they share the same "quarter"
  top-shape (they do — 謄's structure above 言 and 藤's structure to the
  right of 艹/水 both match). Checked all 6 `data_from_pdf.txt` "quarter"
  references for the same bug (the 7th, `rtk2141:驚`, was already fixed to
  a better decomposition — 敬,馬 — unrelated to this pattern, left alone);
  only 1295/1296 were broken.
- Applied: `rtk1295:藤:wisteria:｜,一,月,水,艾,二,大,并` and
  `rtk1296:謄:mimeograph:｜,一,月,言,二,大,并` — added the missing `并`
  token, nothing else changed.
- Verified: full rebuild from scratch; `get_kanji_detail` on both now
  includes `prim-eight-radical` alongside the other five siblings;
  `test_regression_fixes.py` — added 2 new pinned entries — same 4
  expected hanzi-scope failures as every prior rebuild, nothing else;
  full search-term regression checklist unchanged/correct.
- Coverage: **959/3000 (32.0%)** reviewed.
- **Next session**: `并`'s remaining hosts — the 豆-family "beans" cluster
  (largest remaining, ~17 hosts) is the next likely-clean candidate; the
  帝-family "vase" cluster and the "quarter" cluster's own real identity
  both still need a proper glyph-isolation pass before either can be
  resolved (not just patched for missing/redundant tokens); the ~50 CSV-
  uncovered rare kanji still need per-kanji visual verification. The
  業/撲/僕 `羊` mismatch from two sessions ago is also still open.

### 2026-08-25 — `并`'s 豆-family cluster (17 kanji): the same bug wearing a bigger coat

- Picked up the 豆-family (beans) cluster flagged as "the next likely-clean
  candidate." It looked simple at first glance (17 hosts all listing
  `口,豆,并` together) but turned out to be the deepest single cluster
  fixed so far — not just `并` mislabeling, but a chain of ordinary
  redundant-flattening bugs stacked on top of each other, because several
  of these kanji are themselves built from *other* already-taught kanji
  in this same family (鼓 "drum", 登 "ascend", 豊 "bountiful", 喜
  "rejoice") that were *also* flattened instead of referenced directly.
- First checked whether `豆` (rtk1548, beans) itself contains `并` —
  it doesn't (`几,一,口`), so `并`'s presence in these 17 lines isn't
  redundant-flattening-of-豆 the way the 羊-family was redundant-
  flattening-of-羊. Cross-checked `heisig-kanjis.csv` components for all
  17 (via id_6th_ed) and `data_from_pdf.txt`'s pre-override originals
  where available (6 of the 17: 1550/1551/1553/1757/1838/1855) — in every
  single case, CSV/pdf corroborate every token *except* `并`, which
  appears in none of them under any name ("dart", "table", "beans",
  "drum", "bend", "glue", "gates", "part of the body", "shape" — no
  concept anywhere maps to it). Unlike the sheep/quarter/horns families,
  where `并` mapped to *something* real, here it's pure unexplained
  noise — most likely introduced by whatever bulk edit corrupted this
  whole cluster at once (uniform `口,...,并` pattern across all 17 points
  at one bad pass, not 17 independent typos).
- Also found, layered underneath: `鼓` (rtk1552, drum) — a taught kanji
  frame five of these hosts build on — was itself corrupted the same way
  (`口,士,支,豆,并,又,十` instead of its own real `士,豆,支`, i.e. it
  redundantly re-flattened its own 支 into 又+十 too). Fixed it first
  since 喜/樹/膨 depend on it. Similarly `登` (rtk1838, ascend, `癶,豆`)
  turned out to already be a real building block for 澄/燈, and `豊`
  (rtk1551, bountiful, `曲,豆` — "bend" = rtk1256/曲 = `｜,日`) for 艶,
  and `喜` itself for 嬉.
- The 6 kanji outside CSV's ~2200-frame coverage (2223/2224/2275/2319/
  2502/2978) had no CSV or pdf backstop, so verified those by rendering
  all 17 large (`dou_cluster1.png`/`dou_cluster2.png`) and confirming each
  host's other tokens (山, 寸, 厂, 女, 込, 火, 几, etc.) visually match
  what's actually drawn, same standing method as everywhere else in this
  audit.
- Applied (17 lines, each collapsed to reference the real already-taught
  compound instead of a flattened+corrupted stand-in, `并` dropped
  entirely): `rtk1550:短:矢,豆`, `rtk1551:豊:曲,豆`, `rtk1552:鼓:士,豆,支`,
  `rtk1553:喜:鼓,口`, `rtk1554:樹:木,鼓,寸`, `rtk1757:闘:門,豆,寸`,
  `rtk1815:痘:豆,疔`, `rtk1838:登:癶,豆`, `rtk1839:澄:水,登`,
  `rtk1855:膨:月,鼓,彡`, `rtk1892:艶:豊,色,勹`, `rtk2223:鎧:金,山,豆`,
  `rtk2224:凱:山,豆,几`, `rtk2275:厨:豆,寸,厂`, `rtk2319:嬉:女,喜`,
  `rtk2502:逗:込,豆`, `rtk2978:燈:火,登`.
- Verified: full rebuild from scratch; every one of the 17 resolves to
  clean, sensible chips (spot-checked via `get_kanji_detail`, e.g.
  `喜 → {鼓/drum, 口/mouth}`, `澄 → {水/water, 登/ascend}`); "eight
  radical" search dropped from 129 to 86 remaining wrong hosts (a mix of
  removals from this fix and the small `+2` from last session's 1295/1296
  addition — net direction is down); "beans"/"drum"/"bend"/"ascend"
  search all correct; `test_regression_fixes.py` — added 17 new pinned
  entries — same 4 expected hanzi-scope failures as every prior rebuild,
  nothing else; full search-term regression checklist unchanged/correct.
- Coverage: **977/3000 (32.6%)** (regenerated after this commit —
  `coverage_status.py` reads git history, not the working tree, so it has
  to run post-commit to reflect a session's own fixes).
- **Next session**: `并`'s remaining ~69 hosts (down from ~182 at the
  start of this whole `并` investigation) — the 帝-family "vase" cluster
  and the "quarter" cluster's own identity are the two biggest still-open
  identity questions, both needing a slower glyph-isolation pass; smaller
  scattered clusters (半-hint clusters, 弓-adjacent `梯`/`悌`/`鵜`/`剃`
  group, `新`/`薪`/`親` "red pepper" group, others) haven't been triaged
  individually yet. The 業/撲/僕 `羊` mismatch is also still open.

### 2026-08-25 — two more `并` clusters, and a CSV-wording false lead

- Continuing straight on: picked up the `新`/`薪`/`親` "red pepper" group
  (flagged above as untriaged) and the 弓-adjacent `剃`/`悌`/`梯`/`鵜`
  group.
- **`新`-family**: `heisig-kanjis.csv`'s components for 1619/1620/1621
  ("red pepper; stand up; vase; tree; wood; axe") read exactly like the
  帝-family "vase" cluster's own wording, so the working assumption
  coming in was that these belonged to that same still-open cluster. But
  rendering 新/薪/親 next to 辛 (spicy, rtk1612) showed the left side is
  actually 立 directly over 木 — **not** 辛 (which is 立 over 十, a plain
  cross, visibly different from 木's extra diagonal strokes). CSV's
  "red pepper"/"vase" wording was noise for this specific case, not a
  real shared concept — a useful reminder that CSV text matches are a
  lead to check, never a fact to trust without rendering, even when they
  look exactly like a pattern confirmed elsewhere. Fixed by dropping the
  spurious `辛,并,亠` entirely and keeping just the real visible parts:
  `rtk1619:新:立,木,斤`, `rtk1620:薪:艾,立,木,斤`, `rtk1621:親:見,立,木`.
- **`弟`-family**: `弟` (younger brother, rtk1328) already correctly uses
  `丷` (fixed two sessions ago in the horns cluster) — but `剃`/`悌`/
  `梯`/`鵜` were all re-flattening 弟's raw strokes with the stale `并`
  token instead of referencing `弟` directly, the same pattern as the
  豆-family. `剃` (shave) additionally **dropped its knife (刀) entirely**
  — another missing-component bug in the 伴/判 mold, not just redundant
  flattening: the current `｜,ノ,弓,并` line had no representation at all
  of the 刂 clearly visible on 剃's right side. `鵜` (cormorant) also had
  a second bug stacked in: `杰` (fire radical) redundantly re-flattening
  `鳥`'s own already-correct single sub-part, on top of the 弟 issue.
  Fixed: `rtk2271:剃:弟,刀`, `rtk2381:悌:弟,state of mind`,
  `rtk2545:梯:木,弟`, `rtk2847:鵜:弟,鳥`.
- Along the way, fixing 悌 needed the "state of mind" primitive (heart
  radical, 忄) to actually resolve to something — it was still sitting as
  `rad4.2:?:heart,valentine,state of mind`, one of the original
  never-migrated `rad4.*`/`rad3.*`-style entries with no real character,
  missed by the 78-id kangxi/prim migration two sessions ago (that pass
  clearly wasn't exhaustive — there's at least a `rad4.20` "missile",
  `rad4.21` "compare", `rad4.22` "fur", `rad4.24` "spirit", `rad4.25`
  "water", `rad4.27`/`rad4.28` "fire", `rad4.29` "claw, vulture" still
  sitting the same way, none investigated this session). Fixed just this
  one (needed for 悌): linked the real glyph `忄` (Kangxi radical 61's
  left-side variant, same reasoning as `亻`/kangxi9) and renamed
  `rad4.2` → `kangxi61`, distinct from `rtk639` (心, the standalone
  "heart" kanji frame) same as person's variant/standalone split.
- Verified: full rebuild from scratch; all 7 fixed kanji resolve to
  clean chips (`get_kanji_detail` spot-checked); "eight radical" search
  down from 86 to 79 remaining wrong hosts; "new"/"younger brother"/
  "heart"/"state of mind" searches all correct (heart correctly splits
  into `rtk639`/standalone and `kangxi61`/variant, matching the
  person-radical precedent); `test_regression_fixes.py` — added 8 new
  pinned entries — same 4 expected hanzi-scope failures as every prior
  rebuild, nothing else; full search-term regression checklist
  unchanged/correct.
- Coverage: **982/3000 (32.7%)**.
- **Next session**: the leftover `rad4.*`/`rad3.*`-style uncharactered
  primitives found above (missile/compare/fur/spirit/water/fire/claw)
  are a fresh, previously-missed instance of this audit's very first
  Finding 1 ("radicals have no name anywhere in the system") — worth a
  dedicated pass to find how many hosts each affects and give them real
  glyphs, same treatment as `kangxi61` above. Otherwise `并`'s remaining
  ~62 hosts: 帝-family "vase" and "quarter" cluster identities still
  need a slower glyph-isolation pass; the 業/撲/僕 `羊` mismatch is still
  open too.

### 2026-08-25 — census of uncharactered primitives, and `并`'s 平-family

- Followed up on the `rad4.*` finding above with an actual census rather
  than guessing at scope: **201** `rad{n}.{m}`-style rows still have
  `character = '?'` (no real glyph), not the handful spotted by chance.
  But cross-checking each one's alias keywords against every literal
  part-term actually used anywhere in `data.txt` found only **3** are
  presently reachable through any live decomposition — `rad1.1`
  ("one"/"floor"/"ceiling"/"minus", used in `rtk200`/宣), `rad2.8`
  ("animal legs", used in `rtk6`/六), and `rad4.36` ("altar", used in
  `rtk1209`/祈). All three are already known and deliberately left alone
  — the earlier kangxi/prim migration's own verification step explicitly
  named these exact three as "intentionally untouched" (see that
  session's entry above), because assigning them a real glyph risks
  exactly the kind of same-shape-different-meaning mistake this audit
  keeps having to correct (个/umbrella, and now 新-family and 平 below).
  The other 198 are orphaned/unused — dead weight, not a live bug — so
  left alone rather than a low-value 198-row cleanup pass.
- Picked up the CSV-flagged "water-lily; lily pad" cluster (呼/坪/評,
  1597-1599) while investigating this. Same story as 弟/鼓/登/豊 earlier
  today: `data_from_pdf.txt`'s originals used "water lily" as a direct
  reference to `平` (even, rtk1596) itself — `口,water lily` / `土,water
  lily` / `言,water lily` — but `data.txt`'s override had re-flattened
  it into `干,并` (plus stray fragments `ノ`/`亅`/`｜`/`一`/`二`)
  instead of citing `平` directly. Rendering confirmed all three
  visually contain 平's exact shape intact on their right/bottom side.
  Fixed: `rtk1597:呼:口,平`, `rtk1598:坪:土,平`, `rtk1599:評:言,平`.
  Left `rtk1596:平` itself alone — its own `干,并` breakdown is the same
  kind of small-stroke identity question as `帝`'s "vase" and the
  "quarter" cluster (what is the small extra mark above `干` really
  called), not something to guess at without the same careful pass.
- Verified: full rebuild from scratch; `呼`/`坪`/`評` all resolve to
  `{mouth/soil/say, rtk1596}` cleanly; `test_regression_fixes.py` —
  added 3 new pinned entries — same 4 expected hanzi-scope failures as
  every prior rebuild, nothing else; full search-term regression
  checklist unchanged/correct, plus "even"/"call" spot-checked.
- Coverage: **985/3000 (32.8%)**.
- **Next session**: `并`'s remaining ~59 hosts — 帝-family "vase",
  "quarter", and now `平`'s own top-stroke identity are the three
  open small-stroke questions that all need the same careful
  glyph-isolation pass (possibly worth doing together in one session,
  since they may turn out to share an answer — Heisig does reuse tiny
  strokes like this across multiple names, per the `rad1.1`
  "one/floor/ceiling" precedent found this session); the 業/撲/僕 `羊`
  mismatch is also still open.

### 2026-08-26 — `并`'s real identity, resolved: it was `丷` all along

- Picked up exactly where the last entry left off: the three grouped
  small-stroke identity questions (帝-family "vase", "quarter", `平`'s
  top stroke). Instead of guessing from renders alone, fetched
  `cjkvi-ids`'s IDS (Ideographic Description Sequence) database — the
  same authoritative structural-decomposition source `import_hanzi.py`
  already uses for the hanzi import, just never previously turned on
  this audit's own `并` investigation. It gives an actual documented
  stroke-group breakdown per character, not a human-written word list
  (CSV) or a single flat render — something in between, and it cracked
  the whole thing open in one query: **`并` itself (U+5E76) decomposes
  to `丷`+`开`.** Every one of this session's "vase"/"quarter"/`平`
  mystery shapes turned out to be the plain 2-stroke `丷` (already
  correctly identified and fixed as "horns" two sessions ago) — `帝`'s
  own structure is `亠`+`丷`+`冖`+`巾`, `拳`'s "quarter" top (`龹`) is
  `丷`+`夫`, `平`'s extra mark over `干` is `丷` in an overlap
  composition. The `并` token wasn't standing in for several different
  *new* primitives needing individual names — it was the same single
  mislabeling (真 `丷` mistyped/OCR'd as the visually-similar but
  extra-stroke `并`) recurring throughout, just harder to see by eye
  once buried several structural layers deep (e.g. `撲`/`僕`'s `菐` =
  `业`+`䒑`(`丷`+`一`)+`夫`).
- Built a recursive IDS-expansion check, with two important
  refinements learned the hard way mid-investigation (both would have
  produced false positives otherwise):
  1. **Stop recursing at `并` itself** the moment it's found as a
     direct component — a host that genuinely contains the *full* `并`
     glyph (with `开` below `丷`) needs no fix at all. Exactly one host,
     `屏` (rtk2333, `⿸尸并`), turned out to be this case — its current
     `并` token is already correct, left untouched.
  2. **Stop recursing at any character already taught in this app's
     own data** (e.g. `帝`, `半`, `南`, `並`, `巻`, `平`, `前`, `岡`,
     `尊`, `酋`, `金`) rather than diving into *their* internal strokes
     — a host built from one of these should *reference that compound
     directly*, not re-derive `丷` by chasing the IDS tree all the way
     down. Skipping this the first pass produced a false positive:
     `噺`'s path went through `新`/`亲`/`立`/`丷`, but `立` (a
     completely ordinary, already-correctly-taught primitive) happens
     to itself decompose to `亠`+`丷`+`一` at the IDS database's
     stroke-level granularity — which doesn't mean every kanji built
     from `立` secretly needs a `丷` chip, any more than `平`'s `干`
     containing a `丨` means every `干`-kanji needs a `丨` chip. Caught
     this by noticing `新` (already fixed this session, confirmed via
     render to be cleanly `立`+`木`+`斤` with nothing resembling `丷`)
     showing up as a "hit" — a live self-check the migration two
     sessions ago didn't have.
  3. Even with both refinements, still rendered a representative
     sample per sub-pattern before trusting anything (`帝`/`商`/`南`/
     `彦`/`平`/`傍`/`締`/`龹`-family/`業`-family/`屏`, plus a 28-glyph
     Tier-B compound-reference batch) — the IDS data narrows the
     search enormously but doesn't replace the standing render-and-look
     method, same lesson as the `个`/umbrella case that started all
     this two sessions ago.
- This surfaced two more of this audit's dominant bug patterns
  layered on top of the mislabeling itself, now that the real
  identity was clear:
  - **Redundant flattening of an already-taught compound**, the same
    pattern as the 半/豆/弟/平 fixes earlier this week: many hosts
    (`締`, `諦`, `蹄`, `楠`, `献`, `圏`, `普`, `譜`, `鋼`, `綱`, `噂`,
    `揃`, `溢`, `鄭`, `楢`, `樽`, `秤`, `箭`, `絆`, `諺`, `鱒`, `叛`,
    `薩`, `噺`) had re-flattened `帝`/`南`/`半`/`並`/`巻`/`平`/`前`/
    `岡`/`尊`/`酋`/`新` into raw strokes (plus the stray `并`) instead
    of citing the compound directly, once that compound turned out to
    already be correctly taught elsewhere in the app.
  - **Missing component**, the 伴/判/剃 pattern: `剛` (sturdy) had
    *no* sword/knife at all despite the 刂 being clearly visible on
    its right side — fixed to `岡,刀` alongside the `并` cleanup.
  - **Pure redundant noise with no structural role**: `鉛`/`鎮`/`錬`/
    `鋲` already correctly referenced `金` as a compound *and*
    separately carried a flattened `并` fragment that `金` (itself
    fixed this session, `丷`-inclusive) already fully covers — just
    dropped, no replacement needed.
  - Two small pre-existing **wrong-character typos**, caught while
    reading these hosts' real IDS structure and cross-checking against
    render: `噂` (rumor) had `西` (west) where the glyph actually shows
    `酉` (the wine-jar radical inside `尊`) — moot once fixed to
    reference `尊` directly instead of the raw stroke; `鄭` had `邦`
    (an unrelated whole kanji meaning "nation") where the glyph shows
    `阝` (the mound/city radical) — fixed directly.
- Applied 66 fixes total: a direct `并`→`丷` swap for hosts whose own
  glyph shows the bare `丷` with nothing else already covering it
  (`金`, `帝`, `商`, `適`'s `啇`-component notwithstanding, `傍`,
  `幣`/`蔽`/`弊`, `半`, `拳`/`券`/`巻`/`勝`/`藤`/`謄`, `頬`, `釜`,
  `平`, `南`, `瞭`/`寮`/`療`, `彦`, `並`, `騰`, `侠`/`倦`, `噌`, `渕`,
  `蕨`, `遼`, `燎`, `鑿`, `朔`, `酋`, `瞥`) and a compound-reference
  fix (dropping the flattened remnants, citing the real compound) for
  the rest (see the full per-kanji list in this commit's diff). Full
  list and reasoning too long to repeat here — this entry is already
  the long version.
- Verified: full rebuild from scratch; every fixed kanji spot-checked
  via `get_kanji_detail` (all resolve to clean, sensible chips — no
  leftover `?` or mismatched parts); `search_by_parts(['horns'])` now
  returns 90 kanji (was 55 after the original two-sessions-ago fix);
  `search_by_parts(['eight radical'])` (the mislabel's old name) is
  down to **9 hosts** from ~182 at the very start of this whole `并`
  investigation — `業`/`撲`/`僕` (deferred, `业`+`䒑`+`未`/`夫` doesn't
  match their current `王`/`羊` tokens at all, needs its own
  reconstruction pass, not a token swap), `為`/`偽`/`誉`/`糞`/`粉`
  (never showed `丷` in the IDS trace, genuinely a different question),
  and `屏` (correct as-is, see above); `test_regression_fixes.py` —
  updated the two `藤`/`謄` pins from the "quarter" session
  (`prim-eight-radical` → `kangxi12`, since it's now correctly linked)
  and added 13 new representative pins, one per sub-pattern — same 4
  expected hanzi-scope failures as every prior rebuild, nothing else;
  full search-term regression checklist unchanged/correct, plus
  "sovereign"/"south"/"mount"/"revered"/"front"/"chieftain" spot-checked.
- Coverage: **1034/3000 (34.5%)** — crossed the one-third mark.
- **Next session**: the remaining 9 `并`/"eight radical" hosts are a
  small, cleanly-scoped scope for whenever someone wants to finish
  this off — `業`/`撲`/`僕` need their decomposition rebuilt around
  `业`+`丷`+`一`+`未`/`夫` (their current `王`/`羊` tokens don't match
  their real IDS structure at all), and `為`/`偽`/`誉`/`糞`/`粉` need
  fresh individual investigation from scratch (CSV + render), since
  the `丷` lead doesn't apply to them. The uncharactered `rad4.*`
  primitives census from the previous session is still open too.

### 2026-08-27 — `業`/`撲`/`僕` rebuilt: the last big `并` cluster closed out

- Picked up exactly the item flagged above. Their old tokens (`王`,`羊`
  in various combinations) never matched either character's real
  structure at all — confirmed via the same IDS approach that resolved
  the rest of `并`'s identity two sessions ago: `業` = `业` (a 4-stroke
  block IDS can't decompose further, tagged only "④") + `𦍎`, and
  `𦍎` = `䒑`(`丷`+`一`) + `未`; `撲`/`僕` share a right-hand component
  `菐` = `业` + `䒑`(`丷`+`一`) + `夫` (husband) instead of `未`.
- `heisig-kanjis.csv`'s own wording for 1931 independently names `业`
  as "upside down in a row" (distinct from the "business" self-
  reference-artifact CSV noise this audit has seen before, e.g. with
  `業`/`豊`/`業` itself) — no existing entry anywhere in `data.txt` had
  this name, so added a new primitive for it: `prim-upside-down-row:业`.
  It's IDS-atomic (no further real decomposition available) and not
  one of the 214 Kangxi radicals, matching the `prim-{slug}` half of
  the id-migration convention from three sessions ago.
- Rendered `業`/`撲`/`僕` next to `业`/`未`/`木`/`夫` to settle the one
  remaining ambiguity IDS couldn't: whether `業`'s own bottom stroke is
  `未` (not yet, rtk229, already taught) or plain `木` (tree) — visually
  it reads as `木` (missing `未`'s distinguishing shorter top stroke),
  matching both the *pre-existing* (if otherwise wrong) `data.txt` token
  and `heisig-kanjis.csv`'s explicit "tree; wood" wording, so went with
  `木`. `撲`/`僕`'s bottom-right, by contrast, unambiguously matches `夫`
  (husband, rtk901) — not `木` — confirmed the same way.
- Applied: `rtk1931:業:业,丷,一,木`, `rtk1932:撲:扌,业,丷,夫`,
  `rtk1933:僕:亻,业,丷,夫`.
- Verified: full rebuild from scratch; all three resolve cleanly
  (`業 → {upside down in a row, horns, one, tree}`, `撲/僕 → {finger/
  person, upside down in a row, horns, husband}`); `test_regression_
  fixes.py` — added 3 new pinned entries — same 4 expected hanzi-scope
  failures as every prior rebuild, nothing else; full search-term
  regression checklist unchanged/correct, plus "husband"/"upside down
  in a row" spot-checked; `search_by_parts(['eight radical'])` now
  down to **6 hosts**: `為`/`偽`/`誉`/`糞`/`粉` (genuinely unrelated to
  `丷`, need fresh individual investigation) plus `屏` (already
  confirmed correct as-is, not a bug) — from ~182 at the very start of
  this `并` investigation.
- Coverage: **1035/3000 (34.5%)**.
- **Next session**: `為`/`偽`/`誉`/`糞`/`粉` — the last 5 kanji of the
  original `并` mislabeling report — need CSV + render investigation
  from scratch, unrelated to the `丷`/horns thread that resolved
  everything else. The uncharactered `rad4.*` primitives census is
  still open too. Otherwise this multi-session `并` investigation is
  essentially done — worth picking a fresh area of the dataset once
  those last 5 are closed out (frame-ordered sweep, or another owner
  report if one comes in).

### 2026-08-27 — full deploy sync + `个`/`umbrella` collision bug

- **Owner asked for a plain `git pull` + full redeploy** ("it will bring
  changes in UI, database etc, so merge and restart everything"). This
  session's own local checkout had already fast-forwarded through every
  commit back to the 2026-08-23 primitive-id migration at some point
  without a matching live sync in between (last live sync was still the
  2026-08-23 baseline) — so this pull's own 2 new commits (`業`/`撲`/`僕`
  rebuild) were small, but the *unsynced* backlog behind them was not:
  `sync_system_data.py --dry-run` reported 81 kanji inserted (the
  `rad{N}` → `kangxi{N}`/`prim-{slug}` id migration), 294 decompositions
  replaced, 300 aliases added/294 removed. Applied after the usual
  `backup_db.py` — matched the dry run exactly, no surprises. The old
  `rad{N}` ids are flagged "exist live but not in source, NOT
  auto-deleted" by the sync script's own safety design; left them alone
  rather than unilaterally deleting kanji rows — worth a deliberate
  cleanup pass later, not a side effect of a routine sync.
- **Restart hit a real deploy hazard, not a code bug**: `systemctl
  restart` crash-looped on `[Errno 98] address already in use` — a
  stray, non-systemd `uvicorn` process (pid from Aug 26, started
  manually, never a `kanji-backend.service` child) was still squatting
  on port 8000, meaning production traffic since Aug 26 11:50 had been
  served by an unmanaged process running whatever code was checked out
  at the time — not this session's synced DB, not any commit merged
  since. Killed it; `systemctl restart` then bound cleanly and
  `migrate_schema()` applied `_migrate_v4` (the `decomposition_reviews`
  table from the 2026-08-25 review-queue feature) for the first time on
  this live DB. Worth checking `ss -ltnp | grep :8000` before any future
  "restart isn't working" investigation — the systemd unit's own logs
  don't mention a competing process unless you look.
- **Frontend build needed the box's `/usr/bin/node-20` explicitly**
  (system default is still node 18, which `vite build` now hard-rejects
  with a `CustomEvent is not defined` crash rather than a version
  warning) — symlinked it first in PATH rather than editing global
  config. `npm run build` then succeeded; copied `dist/` over
  `/usr/share/nginx/html/kanji/`.
- **Found via the regression suite, not an owner report**: after the
  sync, `test_regression_fixes.py` flagged `rtk287`/金 as having an
  unexpected extra part (`rtk1103`). Traced it to the 2026-08-23
  `个`→"umbrella" rename (the `个`/umbrella fix earlier in this file):
  `个`'s own primary keyword "umbrella" is *also* `rtk1103`/傘's primary
  keyword, both `ja-kanji` — same-script collision, so
  `resolve_alias("umbrella", script_scope="ja")` is non-deterministic
  between the two, and whenever it happens to pick `rtk1103` instead of
  `prim-umbrella`, `_resolve_parts_detail`'s synthetic char+keyword-pair
  dedup fails to recognize the pair (char term resolves to
  `prim-umbrella`, keyword term resolves to `rtk1103` — they don't
  match, so neither gets dropped) and both chips render. Not
  `rtk287`-specific: confirmed live on `rtk814`/会 too before the fix,
  and by extension every one of the ~101 kanji using `个` as a literal
  part — a real, currently-live display bug on a lot of pages, just
  never caught because `test_regression_fixes.py`'s existing `rtk287`
  pin only started asserting an exact set (rather than "at least
  these") once it was written 2026-08-26, and nothing had run the suite
  against a freshly-synced DB since. Fixed the same way the `亠`/`宀`
  lid/roof ambiguity was fixed originally: gave `prim-umbrella` a
  distinguishing primary alias (`primitive_umbrella`, keyword) while
  keeping `umbrella` as a secondary alias for text search — the
  auto-synthesized keyword pair for any `个`-using decomposition now
  resolves unambiguously to `prim-umbrella` alone. No `data.txt` line
  anywhere references "umbrella" as literal decomposition text (checked
  before applying), so nothing else needed touching.
- Verified: `sync_system_data.py --dry-run` on the fix showed exactly
  101 decompositions replaced (matching the known `个` host count);
  applied; `rtk287`/金 and `rtk814`/会 both spot-checked back to their
  correct 4-chip and 3-chip sets via `get_kanji_detail` and the live
  API; `test_regression_fixes.py` — 82/82 passing (no expectation
  changes needed, unlike the earlier 宣/sun case — this was a pure bug,
  not an improvement to re-pin); `audit_self_reference.py` full sweep
  clean; restarted `kanji-backend.service` again after the fix, live
  API (`curl .../kanji/rtk814`) and the deployed frontend both
  spot-checked.
- **Next session**: a deliberate pass to delete the 81 orphaned old-id
  `rad{N}`/`rad{N}.{M}` rows now sitting dead in the live DB (content
  already migrated to their `kangxi{N}`/`prim-{slug}` replacements,
  confirmed zero other lines reference them) would tidy this up — not
  urgent, but noted since `sync_system_data.py` will keep re-flagging
  them on every future dry run otherwise.

### 2026-08-27 — first real use of the in-app review queue: `犭`-family missing-component bug

- **Owner used the new review-queue UI** (shipped 2026-08-25, this was
  its first real use) and disputed `猫`/cat's decomposition. Checking
  `review_queue.py`'s pending list showed 3 rows: `猫` disputed, `聴`
  (listen) disputed, `聞` (hear) approved.
- **`聞` (approved) confirmed correct**: `⿵門耳` per `cjkvi-ids`, matches
  the live `門,耳` exactly. No action needed beyond pinning it.
- **`猫`'s dispute was right, and much bigger than one kanji.** Live
  decomposition was `田,艾` (rice field + grass) — missing the `犭` "dog"
  radical entirely, even though `heisig-kanjis.csv`'s own components
  column says "pack of wild dogs; seedlings; flowers; rice field;
  brains" and `cjkvi-ids` confirms `猫 = ⿰犭苗`. Checked whether this was
  `猫`-specific or systemic by grepping CSV for every frame whose
  components mention "pack of wild dogs": **all 15** (`荻`/`狩`/`猫`/
  `狂`/`獄`/`猿`/`独`/`獲`/`猪`/`狭`/`犯`/`猶`/`猛`/`狙`/`猟`) were missing
  `犭` from their live decomposition, confirmed one-by-one against
  `cjkvi-ids`. Root cause: the placeholder primitive for this radical
  (`rad4.35`, character still `?`) was skipped by the 2026-08-23 id
  migration for exactly the reason it stayed unidentified — and even if
  it had been identified, its own first alias was plain "dog", which
  collides with `rtk253`/`犬`'s own "dog" keyword (same same-script
  collision class as this session's earlier `个`/umbrella fix) — a
  believable reason someone historically avoided wiring it in rather
  than a random data-entry gap repeated 15 times. Linked it to the real
  glyph `犭` as `kangxi94` (finishing the migration convention:
  Kangxi radical 94, positional-variant glyph), keyword "pack of wild
  dogs" (Heisig's own term, matches CSV, doesn't collide with `犬`'s
  "dog"), and added it to all 15 hosts' decompositions — flattening
  otherwise left untouched (only the missing radical was added; existing
  sub-decompositions like `苗`→`田,艾` or `者`→`日,老` weren't
  re-litigated here).
- **`聴`'s dispute was also right, different bug**: live `耳,十,心` vs.
  `cjkvi-ids`'s `聴 = ⿰耳⿳十罒心` — missing `罒` ("net", Kangxi radical
  122). No existing `ja-kanji` primitive for `罒` at all (only a
  `zh-Hani` hanzi row existed) — added `kangxi122:罒:net,eye
  radical,cross-eyed` and fixed `聴` to `耳,十,罒,心`.
- Verified: `sync_system_data.py --dry-run` matched expectations exactly
  each time (15 decompositions for the `犭` batch, 1 for `聴`); every one
  of the 15 plus `聴` spot-checked via `get_kanji_detail` and the live
  API post-restart; `test_regression_fixes.py` — added 17 new pinned
  entries (15 `犭`-family + `聴` + `聞`) — 99/99 passing;
  `audit_self_reference.py` full sweep clean; confirmed no new same-
  script keyword collision (`"dog"` → `rtk253` only, `"pack of wild
  dogs"` → `kangxi94` only). Marked all 3 review-queue rows processed
  (`review_queue.py --mark-processed 1 2 3`).
- **Next session**: the review queue is now a real input source, not
  just shipped code — check it early each session, same as reading this
  file. Also worth a wider sweep for the same "unidentified `rad4.*`
  placeholder never actually wired into any decomposition" pattern that
  produced this bug (the open "uncharactered `rad4.*` primitives census"
  item from 2026-08-25 is exactly this, just not yet cross-checked
  against which ones are silently missing from real kanji).

### 2026-08-27 — owner spot-check: `爿`'s keyword, plus `警`/`特` pinned, plus a `北` bug found in passing

- **Owner asked to double-check `爿`'s glyph and whether it deserves its
  own primitive name.** Couldn't do the full render-and-compare method
  this time -- this production box has no headless Chromium and no CJK
  fonts installed at all (`render_glyphs.py` needs the former; a
  from-scratch PIL/font-based fallback would need the latter), so said
  so plainly rather than skip the check silently. Confirmed instead via
  codepoint: the DB's `爿` is `U+723F`, the correct standard Unicode
  Kangxi radical 90 -- not a substitution artifact or lookalike.
  `heisig-kanjis.csv` settles the naming question independently: its
  components column says **"turtle"** for all 5 of `爿`'s CSV-covered
  hosts (`状`/`壮`/`将`/`奨`/`寝`), consistently -- Heisig's own name for
  it, just never entered into `data.txt`, which only had the dry
  "radical 90" (plus the official Kangxi gloss "half of a tree
  trunk"/"split wood" as secondary aliases). Checked for a same-script
  collision first (the `个`/umbrella and `犭`/dog lesson from earlier
  this session) -- clear, every other "turtle" alias in the DB is a
  `zh-*` row (real turtle/tortoise hanzi like `亀`/`龜`). Renamed
  `kangxi90`'s primary keyword `"radical 90"` -> `"turtle"`, kept
  "radical 90"/"half of a tree trunk"/"split wood" as secondary aliases.
- **Found a real bug while cross-checking `爿`'s host list**: `rtk480`/
  `北` (north) currently lists `爿` as one of its own components, but
  that's wrong -- `cjkvi-ids` gives `北 = ⿰③匕` (a mirrored/backward
  `匕`-shaped 3-stroke element with no Unicode codepoint of its own,
  `cjkvi-ids`'s own placeholder notation for that, not a specific named
  IDS component) plus a real `匕`, and CSV agrees ("spoon; sitting on
  the ground", never "turtle"). Not fixed here -- needs the same
  "identify or create a placeholder primitive for an unencoded shape"
  treatment as `犭`/`罒` got two sessions ago, not a simple swap, and
  CSV's second term ("sitting on the ground") needs its own
  investigation before committing to what that second component
  actually is.
- **Two more review-queue approvals surfaced separately** (`警`/admonish,
  `特`/special) -- confirmed both correct against `cjkvi-ids` (`警 =
  ⿱敬言`, `特 = ⿰牛寺` with `寺` already flattened to `土,寸` elsewhere)
  and pinned, no `data.txt` change needed. Marked processed.
- Verified: `sync_system_data.py --dry-run` for the `爿` rename matched
  expectations (1 kanji updated, 11 decompositions replaced -- its
  character-referencing hosts); `get_kanji_detail` on `状` confirms
  `爿` now resolves with keyword "turtle", no ambiguity
  (`resolve_alias("turtle", "ja-kanji")` -> `kangxi90` only);
  `test_regression_fixes.py` -- 102/102 passing; `audit_self_reference.py`
  full sweep clean; `kanji-backend.service` restarted, live API
  spot-checked.
- **Next session**: `北`'s bug (above) and the still-open
  "uncharactered `rad4.*` primitives census" from 2026-08-25 are related
  -- worth doing together, since the census is exactly how `北`'s
  mislabeled `爿` would surface on its own.

### 2026-08-27 — owner tried adding `丗`/"thirty" themselves: found a real creation bug and a real privacy bug

- **Owner tried to self-serve a fix**: created a new private `ja-kanji`
  primitive `丗` named "thirty" via the app's own Create Kanji UI, then
  tried to add a new decomposition of `帯` (sash) using "thirty" +
  "apron" (per Heisig's real components for this kanji, which they'd
  looked up externally). Reported it "did not show", and that searching
  "apron" found nothing.
- **Root cause #1, a real bug in kanji creation**: `create_kanji_entry`
  (`database.py`) inserted the new kanji row with `keyword = "thirty"`
  but never inserted a matching row into `aliases` -- and `resolve_alias`
  only ever checks `kanji.id` or the `aliases` table, never
  `kanji.keyword` directly (this is exactly what `import_data()` does
  right, via its own explicit `_insert_alias(conn, r["id"], r["keyword"])`
  call that `create_kanji_entry` was missing). So the new primitive was
  created successfully but could never be *found* by its own name --
  not by search, not by referencing it in a decomposition. Fixed by
  adding the same `_insert_alias` call to `create_kanji_entry`; backfilled
  the owner's existing `usr3` row directly (the code fix only helps
  future creations).
- **"apron" was never missing** -- it just isn't a term this DB has yet.
  Checked `heisig-kanjis.csv`'s own components for `帯` (frame 444):
  "buckle; apron; crown; towel" -- and `cjkvi-ids` confirms `帯 =
  ⿳丗冖巾` (three parts: `丗`, `冖`, `巾`). "buckle"/"apron" are both CSV's
  own alternate names for the same top shape the owner had already
  correctly identified and named "thirty" -- not a fourth, separate
  primitive. Since `丗` is a real, previously entirely-missing `ja-kanji`
  primitive (it only existed as an unrelated `zh-Hani` hanzi row before
  today), added it properly as a system primitive: `prim-thirty:丗:
  thirty,buckle,apron` (checked for same-script collisions first --
  none), and fixed `帯`'s own system decomposition from its old
  `｜,一,巾,冖` flattening to `丗,冖,巾`, matching the real structure
  directly instead of a deeper, less book-faithful stroke-level
  flattening.
- **Root cause #2, found while verifying the above, more serious**:
  once both a public `prim-thirty` and the owner's own private `usr3`
  existed with the same "thirty" alias, `帯`'s decomposition started
  showing the *same* primitive as two separate chips for the owner's own
  view. Traced to `_resolve_parts_detail`'s two lookup queries (the
  direct-id match and the alias-candidate match) having **no
  visibility/owner_id filtering at all** -- the one place in this whole
  module that didn't follow the "every read function is scoped by
  viewer_id" pattern documented at the top of this file. Concretely
  verified this is a real cross-user privacy gap, not just a cosmetic
  duplicate: inserted a throwaway private kanji owned by a different,
  unrelated user id also named "thirty" (inside an uncommitted
  transaction, rolled back after) and confirmed it appeared nowhere in
  another viewer's resolved decomposition *before* the fix -- i.e. before
  the fix, a decomposition's part term could silently resolve through a
  different user's private alias or kanji row and surface that
  stranger's character/keyword to any viewer, public or anonymous.
  Fixed by scoping both queries to `(visibility = 'public' OR owner_id =
  ?)` with `viewer_id` bound, same as every other read function, and
  adding the same "prefer public over the viewer's own private
  duplicate" tiebreak `resolve_alias` already uses, so a genuine
  same-name collision resolves deterministically instead of by SQL row
  order.
- Verified: the throwaway-other-user test above (leak closed, both
  before/after states checked in the same session); `get_kanji_detail`
  on `帯` for the owner, an anonymous viewer, and after the throwaway
  private-kanji test all spot-checked; `test_regression_fixes.py` --
  added a `帯` pin, doubling as a regression guard for the visibility fix
  itself -- 103/103 passing; `audit_self_reference.py` full sweep clean
  (this touches the same resolution path); `kanji-backend.service`
  restarted.
- **Next session**: this privacy gap existed since `_resolve_parts_detail`
  was written and had never been exercised by two genuinely conflicting
  users before -- worth a quick audit of whether any *other* ad hoc query
  in `database.py` skips the viewer_id-scoping pattern the same way,
  now that one real instance has turned up.

### 2026-08-28 — follow-up privacy audit: three more unscoped queries closed

- Read through every function in `database.py` that takes a `viewer_id`,
  checking each query against the module's own documented invariant
  (every read scoped to `visibility = 'public' OR owner_id = ?`) —
  exactly the follow-up the previous entry asked for. Confirmed
  `search_by_substring`, `search_by_char`, `search_by_parts`'s own final
  result query, `_rows_to_dicts`, and `get_all_aliases_for_term` were
  already correct (each properly scopes both the alias/decomposition
  table *and* the joined kanji row). Found three more instances of the
  exact same gap class as the `_resolve_parts_detail` leak, all in the
  parts-search BFS graph (`search_by_parts` → `_reachable_kanji_for_term`
  → these three):
  - `_self_identity_kanji_ids` — its alias-lookup join checked the
    alias's own visibility but never the joined kanji's. A kanji can be
    private while a *separate* public alias exists on it (nothing stops
    a user setting alias visibility independently of the kanji's own —
    confirmed by reading `create_alias`/the `/aliases` endpoint, no
    coupling enforced), so this let a term matching that alias treat the
    private kanji as a self-identity match.
  - `_kanji_with_part_terms` — checked the *decomposition's* visibility
    but not the kanji it decomposes. Same story: a decomposition's
    visibility is independently settable from its kanji's own, so a
    private kanji with a public decomposition on it (again, nothing
    prevents this combination) could surface via a literal part-term
    match.
  - `_terms_for_kanji_ids` — the alias half was already scoped, but the
    plain `SELECT character FROM kanji WHERE id IN (...)` had **no
    visibility check of any kind**, not even the basic pattern.
  - **Severity note, to be precise about it**: unlike the original
    `_resolve_parts_detail` bug, none of these three directly return a
    private kanji's character/keyword to an API response —
    `search_by_parts`'s own final query (line ~778) already re-filters
    the candidate id set by `k.visibility`/`owner_id` before anything is
    returned, so a private kanji injected into the BFS graph via one of
    these gaps could never itself appear in search results. The real
    exposure was indirect: a private kanji's aliases/character could
    leak into the *next BFS layer's search frontier*, meaning an
    unrelated, fully public kanji could spuriously match (or fail to
    match) a query depending on whether it happened to share text with
    someone else's private data — a subtler bug than "renders your
    private data to a stranger," but still real cross-user leakage of
    *which private terms exist*, and still a violation of this module's
    own stated invariant. Fixed for consistency and defense-in-depth
    regardless of the lower severity, matching the exact scoping
    pattern `_resolve_parts_detail` already uses.
- Verified with the same two-user methodology as the original fix:
  created a throwaway "victim" user with a private kanji, a *public*
  alias on it, and a *public* decomposition listing a private term —
  confirmed each of the three functions returned nothing for a second
  "attacker" viewer both before asserting (i.e. the test itself
  correctly reproduced the leak pre-fix logic) and after the fix
  correctly excluded the private data, while the victim's own view was
  unaffected; rolled back the transaction, never persisted. Full rebuild
  from scratch; `test_regression_fixes.py` — 103/103 passing, no pin
  changes needed (data-layer fix, not a `data.txt` change); full
  search-term regression checklist unchanged/correct, including a
  `sun`+`moon` parts-search spot-check (14 results, unchanged).
- Not deployed to the live server from this session (no production
  access here — see the standing note on this in earlier entries);
  whoever next runs the deploy procedure should restart
  `kanji-backend.service` after pulling this (a `database.py` code
  change, not just `data.txt`).
- **Next session**: this closes out the privacy-audit follow-up
  cleanly — no further unscoped queries found in a full read-through of
  the file. Other still-open items from recent sessions: delete the 81
  orphaned old-id `rad{N}` rows sitting live (data-only, needs live DB
  access), `北`'s `爿` bug (needs the "identify or create a placeholder
  primitive for an unencoded shape" treatment `犭`/`罒` got), the
  uncharactered `rad4.*` primitives census cross-referenced against
  which are silently missing from real decompositions (same pattern
  that produced the `犭`/`罒` bugs), and the final 6 `并`/"eight radical"
  hosts (`為`/`偽`/`誉`/`糞`/`粉`, plus `屏` which is already correct).

### 2026-08-28 — the `rad4.*` census, done properly: `礻` (altar) missing from 28 hosts

- Picked up the queued "uncharactered `rad4.*` primitives census" item,
  scripted this time rather than by-hand sampling: for each of the ~76
  still-uncharactered `rad{N}.{M}` primitives with at least one alias,
  searched every `heisig-kanjis.csv` frame whose `components` column
  names that exact alias, then checked whether the frame's *current*
  `data.txt` line already references it under any of its aliases. Naive
  first pass returned 56 "hits" — almost all false positives, because
  most of these old placeholders (one/water/fire/tree/woman/child/
  house/small/soil/mountain/crotch/…) are simply **pre-migration
  duplicate stubs of kanji frames that were already properly taught
  under their own real character** (一/水/火/木/女/子/宀/小/土/山/又/…) —
  the same "orphaned duplicate" class as `rad2.26`/"crotch" (=`又`,
  found two sessions ago). Filtered those out by dropping any candidate
  whose alias also matches an *already-charactered* primitive's own
  keyword — down to 9 genuine candidates, structurally similar to
  `犭`/`罒`: a real, distinct concept with no charactered home anywhere
  in the system.
- Verified the strongest one, `rad4.36` ("altar"/"leftside altar"),
  first — it already had a live, owner-confirmed-correct pin (`祈`/
  rtk1209, from two sessions ago), so any sibling gap here was very
  likely the same real bug, not census noise. It was: **28 more hosts**
  missing it, splitting into two distinct sub-bugs once rendered
  side-by-side (`shi_cluster.png`):
  - `礼`/`祥`/`祝`/`福`/`祉`/`社`/`視`/`神`/`禍`/`祖`/`禅` used the
    *whole kanji* `礼` (salute, rtk1168) as a stand-in for just its own
    left radical — confirmed wrong by rendering all of them together:
    none show `礼`'s distinguishing `乙` hook, only the narrow altar
    shape. `礼` itself was missing the radical too (its own line was
    just `乙`, no altar at all) — the proxy and the thing it was
    standing in for turned out to share the same root cause.
  - `奈`/`尉`/`慰`/`款`/`禁`/`襟`/`宗`/`崇`/`祭`/`察`/`擦`/`際`/`票`/
    `漂`/`標`/`斎`/`隷` instead redundantly re-flattened the
    *different*, already-correctly-taught standalone `示` (show,
    rtk1167 — same concept, full width, not compressed to a left
    margin) into its own `二`+`小` parts alongside the reference —
    confirmed the width difference is real by rendering `示` next to
    the narrow-form hosts. `斎` had a second, independent
    redundant-flatten of `斉` nested in the same line.
  - Where an already-taught compound covered the rest of a host's
    non-altar strokes exactly (`申`/rtk1198 for `神`, `且`/rtk2190 for
    `祖`, `単`/rtk2078 for `禅`), referenced it directly instead of
    guessing at a further flatten.
  - Linked `rad4.36` to its real glyph `礻` (U+793B, confirmed via
    render against the narrow-form hosts) and renamed it to
    `kangxi113` (示/Kangxi radical 113's positional left-side variant —
    same reasoning as `kangxi9`/`亻` and `kangxi61`/`忄`), distinct from
    `rtk1167`'s own standalone `示`.
  - The other 8 candidates from the census (`rad2.7`/"enter" 1 host,
    `rad2.8`/"animal legs" 122, `rad2.10`/"hood" 39, `rad2.14`/"shovel"
    18, `rad3.3`/"pent in" 23, `rad3.30`/"broom" 15, `rad4.3`/"fiesta"
    29, `rad4.19`/"bones" 10, `rad4.20`/"missile" 18) are real too by
    the same census logic, but **not verified or touched this
    session** — each needs its own render-and-CSV pass the way `礻`
    just got, not a blind bulk apply; flagging the counts here so a
    future session doesn't have to re-derive them.
- Applied: `rad4.36` → `kangxi113:礻:leftside altar,altar`; 28 host
  fixes (11 `礻`+compound-reference swaps, 17 redundant-flatten
  collapses). Full list in this commit's diff.
- Verified: full rebuild from scratch; all 16 spot-checked kanji resolve
  cleanly via `get_kanji_detail` (e.g. `神 → {altar, 申/rtk1198}`,
  `奈 → {示/rtk1167, large}`); `search_by_parts(['altar'])` now returns
  13 hosts (was silently 0 live, despite the keyword existing, before
  today — same "named but never wired in" pattern as `犭`/`罒`);
  `test_regression_fixes.py` — updated the `祈`/rtk1209 pin
  (`rad4.36`→`kangxi113`) and added 8 new representative pins — same 4
  expected hanzi-scope failures as every prior rebuild, nothing else;
  full search-term regression checklist unchanged/correct, plus
  "show"/"salute"/"altar" spot-checked; confirmed zero remaining
  literal `rad4.36` references anywhere in `data.txt`,
  `test_regression_fixes.py`, or `database.py`.
- Not deployed to the live server from this session (no production
  access here); needs a `sync_system_data.py` run (data-only, no
  `database.py` change this time, so no backend restart required)
  whenever someone next runs the deploy procedure.
- Coverage: **1059/3000 (35.3%)**.
- **Next session**: the 8 unverified census candidates above
  (`rad2.7`/`rad2.8`/`rad2.10`/`rad2.14`/`rad3.3`/`rad3.30`/`rad4.3`/
  `rad4.19`/`rad4.20`) are the natural next chunk — `rad2.8`/"animal
  legs" (122 candidate hosts) and `rad4.20`/"missile" look like the
  next-most load-bearing by host count, worth checking first. Otherwise
  the standing list is unchanged: the 81 orphaned `rad{N}` rows on the
  live DB, `北`'s `爿` bug, and the final 6 `并` hosts.

### 2026-08-28 — the `rad4.*` census, closed for good; `北`'s `爿` bug fixed

- Worked through the 8 remaining unverified census candidates
  (`rad2.7`/`rad2.8`/`rad2.10`/`rad2.14`/`rad3.3`/`rad3.30`/`rad4.3`/
  `rad4.19`/`rad4.20`) properly instead of leaving them queued. **All
  8 turned out to be false positives**, same class as the 56 filtered
  out before `kangxi113` was found, just one layer deeper: the census's
  "already covered" check only looked for the primitive's own alias
  *text* as a literal token, not for an *already-charactered* primitive
  covering the same concept under a completely different name. Checked
  each one's full host list by hand and every single host in every
  group already carried a giveaway token: `rad2.8`/"animal legs"'s 122
  "hits" all already contained `ハ` (katakana ha) directly, or a
  compound (`貝`/`頁`/`則`/`貴`) that itself already contains `ハ` — not
  a missing radical at all, just Heisig's own well-established practice
  of reusing a katakana shape as a kanji-component mnemonic, already
  correctly wired in everywhere. The other 7 resolved the same way,
  each against its own already-taught duplicate: `rad4.20`/"missile" →
  `殳`/kangxi79 ("weapon,lance"), `rad4.3`/"fiesta" → `戈`/kangxi62
  ("spear,halberd"), `rad3.30`/"broom" → `ヨ`/prim-katakana-yo
  ("elbow"), `rad4.19`/"bones" → `歹`/kangxi78 ("death,bad"),
  `rad2.10`/"hood" → `冂`/kangxi13 ("border,down box"), `rad2.14`/
  "shovel" → `凵`/kangxi17 ("container,open box"), `rad3.3`/"pent in" →
  `囗`/kangxi31 ("enclosure"), `rad2.7`/"enter" → `入`/rtk842 ("enter",
  an exact keyword match even). **Conclusion, stated plainly so a
  future session doesn't re-derive it**: the entire multi-session
  `rad4.*`/uncharactered-primitives investigation is done. Exactly one
  real bug existed in this whole class (`kangxi113`/altar, previous
  entry) — everything else checked (201 uncharactered rows total across
  both sessions) is either genuinely unused dead weight or an orphaned
  duplicate stub of a primitive that's already correctly taught under a
  different name. No further census work is owed here.
- Also chased down and closed a small false alarm from the same
  investigation: `rtk6` (六, six) and `rtk8` (八, eight) both have
  `character = '?'` in their own `data.txt` lines, which looked like
  the same "basic kanji missing its glyph" bug class at first glance —
  but `import_data()`'s merge logic doesn't let a blank/`?` override
  blank out a real character already provided by a lower-priority
  source (`data_from_pdf.txt` has `六`, the CSV baseline has `八`), so
  both already resolve correctly live (checked directly against the
  rebuilt DB). Not a bug, just a slightly misleading `data.txt` line;
  left alone.
- **`北`'s `爿` bug**, flagged by the owner two sessions ago while
  double-checking `爿`'s own identity: fixed. `cjkvi-ids` gives `北` as
  a mirrored/backward `匕`-shaped element (no Unicode codepoint of its
  own — IDS's own placeholder notation for that) plus a real `匕`, and
  CSV independently agrees ("spoon; sitting on the ground", never
  "turtle"). Added `prim-sitting-on-the-ground:?:sitting on the
  ground` for the unencoded mirrored element (same "name it, don't
  guess a fake glyph" convention this whole `data.txt` already uses
  for dozens of other primitives with no real Unicode codepoint) and
  fixed `rtk480:北:north:匕,prim-sitting-on-the-ground`.
- Verified: full rebuild from scratch; `北` resolves to
  `{spoon/rtk476, sitting on the ground}`, no more `爿`;
  `search_by_parts(['turtle'])` no longer includes `rtk480` (11 hosts,
  all genuine); `test_regression_fixes.py` — added 1 new pinned entry
  — same 4 expected hanzi-scope failures as every prior rebuild,
  nothing else; full search-term regression checklist unchanged/
  correct, plus "turtle"/"spoon"/"sitting on the ground"/"north" spot-
  checked.
- Not deployed to the live server from this session (no production
  access here); data-only change, no backend restart needed on next
  deploy.
- Coverage: **1060/3000 (35.3%)**.
- **Next session**: standing list is now just the 81 orphaned `rad{N}`
  rows sitting on the live DB (data-only, needs live access to clean
  up — `sync_system_data.py`'s own safety design won't delete them
  automatically) and the final 6 `并`/"eight radical" hosts (`為`/
  `偽`/`誉`/`糞`/`粉`, plus `屏` which is already correct). Both small,
  well-scoped. Worth picking a fresh area of the dataset (frame-ordered
  sweep, or another owner report) once those two are closed out.

### 2026-08-29 — the `并` investigation, finally closed: last 5 hosts fixed

- Picked up the last item on the standing list: `為`/`偽`/`誉`/`糞`/
  `粉`, the 5 remaining `并` hosts confirmed unrelated to `丷`/horns
  three sessions ago. Each turned out to be its own distinct, unrelated
  bug — no shared root cause this time, unlike every other `并` cluster
  this investigation has found:
  - **`粉`** (flour): simple redundant flattening. `heisig-kanjis.csv`
    lists "rice; part; eight; sword; dagger", and "part" (`分`,
    already-taught `rtk844` = `刀,ハ`) exactly covers "eight; sword;
    dagger" — `粉` was flattening `分` into its own raw strokes instead
    of citing it, plus the stray `并`. Fixed to `米,分`.
  - **`為`/`偽`** (do / falsehood): `并` was pure unexplained noise,
    same as the `豆`-family and `弟`-family pattern from earlier this
    week — CSV ("so; strange building; tail feathers") maps cleanly to
    the other existing tokens (`杰`/fire radical, `ユ`/katakana yu,
    `丶`/drop, `勹`/wrap) with nothing left over for `并` to represent,
    and rendering both characters closely shows no separate mark
    beyond what those four already cover. Dropped `并` from both,
    touched nothing else.
  - **`誉`** (reputation): `尚` was a wrong stand-in for `誉`'s real top
    shape. Rendered `誉` directly above `興` (leaping; already correctly
    `臼,口,ハ,冂,一`) and confirmed `誉`'s top is *exactly* `興`'s own
    top portion (`臼`+`ハ`+`一`) with none of `興`'s bottom (`口`,`冂`)
    — `尚` (which itself = `口,冂`) doesn't belong to this shape at
    all. Fixed to `言,臼,ハ,一`, dropping `尚,并`.
  - **`糞`** (excrement): had `井` (well) where the glyph actually shows
    `共` (together, `rtk1934` = `ハ,｜,一,二`) — a wrong-character
    mix-up in the same small family as `噂`'s `西`/`酉` and `鄭`'s
    `邦`/`阝` typos found two sessions ago, compounded with the usual
    redundant-flattening pattern once `共` is referenced properly.
    Fixed to `米,田,共`.
- Verified: full rebuild from scratch; all five spot-checked via
  `get_kanji_detail` and resolve to clean chips (e.g. `誉 → {say,
  mortar, katakana ha, one}`, `糞 → {rice, rice field, together}`);
  `search_by_parts(['eight radical'])` now returns **exactly 1 host**
  (`屏`/rtk2333, confirmed genuinely correct two sessions ago) — down
  from ~182 at the very start of this whole investigation.
  `test_regression_fixes.py` — added 5 new pinned entries — same 4
  expected hanzi-scope failures as every prior rebuild, nothing else;
  full search-term regression checklist unchanged/correct, plus
  "flour"/"part"/"reputation"/"mortar"/"together" spot-checked.
- Not deployed to the live server from this session (no production
  access here); data-only change, no backend restart needed on next
  deploy.
- Coverage: **1064/3000 (35.5%)**.
- **This closes the `并` investigation** that ran across roughly a
  week of sessions: from ~182 wrong hosts down to 1 confirmed-correct
  one, via the horns cluster, the sheep/half/quarter/豆/弟/平 families,
  the IDS-based mass resolution (66 kanji in one pass), `業`/`撲`/`僕`'s
  reconstruction, and finally these five unrelated stragglers. See the
  full session-by-session history above for anyone auditing how a
  single mislabeled character turned into this much investigation.
- **Next session**: the only standing item left is the 81 orphaned
  `rad{N}` rows sitting on the live DB (data-only, needs live access —
  `sync_system_data.py` won't delete them automatically by its own
  safety design). Otherwise this is a good point to pick a fresh area
  of the dataset — a frame-ordered sweep, or wait for the next owner
  report / review-queue dispute.

### 2026-08-29 — starting a proper frame-ordered sweep via `audit_flattening.py`

- With the `并` investigation closed and no owner report or review-queue
  item pending, picked up the standing "frame-ordered sweep" idea for
  real. `audit_flattening.py` (built session 21, noted as noisy without
  the CSV cross-check filter session 12 established) currently flags
  **1728** raw candidates dataset-wide — far too many to review by eye.
  Applied the same filter session 12 used: keep only candidates where
  the *contained* kanji's own keyword literally appears in the
  *containing* frame's `heisig-kanjis.csv` components column. Cuts it
  to **231** plausible candidates — still a lot, but a real, trackable
  backlog for future sessions rather than 1728 undifferentiated noise.
- Verified and fixed a first batch of 9, each checked against
  `test_regression_fixes.py`'s existing pins first (to avoid re-treading
  already-deliberated decisions — `rtk691`/義 is in this candidate list
  too but was already reviewed and pinned during the 羊-family fix, so
  skipped) and rendered before touching:
  - `博`/dr. (`rtk48`): the one genuinely interesting case in this batch
    — not a simple redundant flatten. CSV lists "ten; needle" *twice*
    ("ten; needle; acupuncturist; specialty; drop; **ten; needle**; rice
    field; brains; glue"), and rendering confirmed why: `博` has its own
    standalone `十` on the left, structurally separate from `専`
    (specialty)'s own internal `十` on the right — the current flattened
    line (`十,寸,田,丶`) only ever showed one `十` chip total (both
    occurrences collapse to the same resolved id), which isn't wrong
    exactly, just less structurally accurate than showing the outer `十`
    plus an expandable `専` chip (which itself shows its own `十` on
    expand). Fixed to `十,専,丶`.
  - The rest were the standard pattern, one compound-reference swap
    each: `貼``貝,占` (was `貝,口,卜`), `時``寺,日` (was `寸,土,日`),
    `釣``金,勺` (was `金,丶,勹`), `銘``金,名` (was `金,口,夕`), `詔`
    `言,召` (was `言,口,刀`), `詩``言,寺` (was `言,寸,土`), `調`
    `言,周` (was `言,口,土,冂`), `咽``口,因` (was `口,大,囗`).
- Verified: full rebuild from scratch; all 9 spot-checked via
  `get_kanji_detail`, resolve to clean 2-3-chip sets;
  `test_regression_fixes.py` — added 9 new pinned entries — same 4
  expected hanzi-scope failures as every prior rebuild, nothing else;
  full search-term regression checklist unchanged/correct
  ("specialty"/"fortune-telling"/"buddhist temple"/"ladle"/"name"/
  "seduce"/"circumference"/"cause"/"time"/"dr." all spot-checked).
- Not deployed to the live server from this session (no production
  access here); data-only change, no backend restart needed on next
  deploy.
- Coverage: **1072/3000 (35.7%)**.
- **Next session**: **222 candidates remain** in the CSV-filtered
  `audit_flattening.py` list (231 minus this session's 9) — a real,
  trackable backlog for continuing the sweep. Re-run the same filter
  script (CSV cross-check against `audit_flattening.py`'s raw output)
  to regenerate the list, since ids shift as fixes land; check each
  candidate against `test_regression_fixes.py`'s existing pins first
  before re-investigating (a few, like `rtk691`, are already
  deliberately-settled false positives for this tool's purposes). The
  81 orphaned `rad{N}` rows on the live DB is still the other standing
  item, needs production access.

### 2026-08-29 — sweep batch 2: 24 more fixes, one missing-component catch

- Continued the frame-ordered sweep: regenerated the CSV-filtered
  `audit_flattening.py` candidate list (still 222 — ids shift slightly
  release to release but the count landed back where it started once
  batch 1's fixes were accounted for) and worked through another batch.
  Checked each against `test_regression_fixes.py`'s existing pins first
  (skipped `rtk261`/特, already deliberately settled as "flattened on
  purpose" during an out-of-band review-queue session) and rendered a
  representative sample before applying anything.
- 23 of the 24 were the standard pattern — one compound-reference swap
  each, all confirmed via render: `銅→金,同`, `賂→貝,各`,
  `客→各,宀,primitive_roof`, `詠→言,永`, `鍵→金,建`, `海→水,毎`,
  `贈→貝,曽`, `嫁→女,家`, `坂→土,反`, `返→込,反`, `販→貝,反`,
  `賀→貝,加`, `丙→一,内`, `暫→斬,日`, `漸→斬,水`, `槽→曹,木`,
  `領→貝,頁,令`, `鈴→金,令`, `概→既,木`, `含→口,今`, `吟→口,今`,
  `琴→王,今`, `誤→言,呉`.
- **`停` (halt) was different — a real missing-component bug**, the
  same class as `伴`/`判`/`剃` from earlier this week: its old line
  (`口,亅,亠,冖,一`) exactly matched `亭`'s own four flattened parts
  plus a stray `一`, but rendering `停` next to `亭` and `亻` showed the
  actual glyph is `亻`(person) + `亭`(pavilion) — the person radical
  was entirely absent, silently replaced by an unrelated `一` that
  doesn't correspond to anything visible in the character. Fixed to
  `亻,亭`.
- Verified: full rebuild from scratch; all 24 spot-checked via
  `get_kanji_detail`, resolve to clean 2-3-chip sets (`停` now
  correctly shows `{person, pavilion}`); `test_regression_fixes.py` —
  added 23 new pinned entries (skipped a duplicate pin for `吟`, which
  is structurally identical to `含`) — same 4 expected hanzi-scope
  failures as every prior rebuild, nothing else; full search-term
  regression checklist unchanged/correct (24 spot-check terms,
  including "person" to confirm `停`'s fix didn't create a duplicate).
- Not deployed to the live server from this session; data-only change,
  no backend restart needed on next deploy.
- Coverage: **1087/3000 (36.2%)**.
- **Next session**: roughly 200 CSV-confirmed `audit_flattening.py`
  candidates remain — continue the same batch-by-batch process
  (regenerate the filtered list, skip already-pinned frames, render a
  sample, apply, pin, verify). The 81 orphaned `rad{N}` rows on the
  live DB is still the other standing item, needs production access.

### 2026-08-29 — sweep batch 3: 187 fixes in one pass (owner asked for "next 500 kanji")

- The owner explicitly asked for a much larger volume this session than
  the previous 9- and 24-fix batches, so this batch scaled the same
  methodology up rather than changing it: fresh rebuild, fresh
  `audit_flattening.py` run (1650 raw candidates), CSV cross-check against
  `heisig-kanjis.csv`'s `components` column (198 confirmed), minus frames
  already pinned in `test_regression_fixes.py` (190 remaining, covering
  186 unique outer frames — 4 frames each had two structurally-plausible
  collapse targets, resolved by hand below).
- **Methodology upgrade**: instead of matching the *raw* data.txt token
  text (last batch's approach, which produced one unresolvable anomaly on
  `rtk154`/活 because `rtk16`/古's own line uses alias text the raw
  matcher couldn't line up), this batch matched the *resolved part-id*
  sequence directly — the same contiguous-run logic `audit_flattening.py`
  itself uses — then converted the matched run back to a token (the
  matched compound's own character, or its keyword if it has no glyph).
  Zero anomalies this time; the `rtk154` case resolved cleanly as
  `ノ,古,水,舌` (via `rtk16`/古/old) once matched on ids rather than text.
  This id-based approach is strictly better and should be the default for
  any future batch.
- Four outer frames had two valid-looking collapse targets (both fully
  explain a contiguous run); picked by hand, verified against CSV/render
  where the two choices weren't just cosmetically different:
  - `往`(journey, rtk945): `主`(lord) over `玉`(jewel) — both resolve to
    the identical two sub-parts, but Heisig's real story for 彳-compounds
    is "lord", and CSV explicitly lists "lord" among 往's components.
  - `慨`(rue, rtk1595): `既`(previously)+忄 over 牙+`恨`(resentment) —
    rendered `慨` next to `既`/`恨`/`忄`: the real glyph is unambiguously
    忄 (left) + 既 (right), not 牙+恨.
  - `蒸`(steam, rtk2049): `丞`(helping hand) over `了`(complete) — 丞's
    own resolved parts fully cover the 3-token run (了's only cover 2 of
    the 3), the strictly larger/cleaner collapse, confirmed by CSV.
  - `遵`(abide by, rtk2187): `尊`(revered) over `酋`(chieftain) — same
    logic, 尊 fully covers the leftover 3 tokens after 込, 酋 only 2.
- **Two more real missing-component bugs caught by the mandatory
  render/CSV spot-check** (same class as `伴`/`判`/`剃`/`停` from earlier
  sessions — a wrong/irrelevant token standing in for an entirely absent
  person radical), both found while sampling roughly 35 of the 190
  proposals across different structural clusters before trusting the
  mechanical pattern for the rest:
  - `便`(convenience, rtk1066): old line was `｜,更` — rendering `便` next
    to `亻`/`更`/`｜` showed the "｜" was a wrong stand-in for the person
    radical; the real glyph is `亻`+`更` exactly, no `｜` anywhere in it.
    Fixed to `亻,更`.
  - `侯`(marquis, rtk1767) — **not in the original 190-candidate list at
    all**, found by cross-checking `heisig-kanjis.csv`'s components
    column ("person; key; dart; drop; heavens") against its current
    data.txt line while separately verifying `候`(climate, rtk1769),
    which references it: `侯` was defined as just `矢,ユ`, missing the
    person radical entirely. Confirmed via `cjkvi-ids`:
    `侯 = ⿰亻⿱ユ矢` (person + [ユ over 矢]). Fixed to `亻,矢,ユ`. `候`
    itself needed no separate person fix — `cjkvi-ids` shows
    `候 = ⿰⿰亻丨⿱ユ矢`, i.e. `侯`'s own person+ユ+矢 plus one extra `｜`
    stroke fused onto the person radical — so `候` collapses cleanly to
    `侯,｜` referencing the now-fixed compound.
- The remaining 185 fixes were the standard redundant-flattening pattern
  — a compound's own already-taught parts pasted in place instead of a
  reference to the compound itself — spot-checked in batches of ~10-15
  across distinct clusters (the `扌`-hand-radical cluster: `拭→式,扌`,
  `抱→包,扌`, `抄→少,扌`, `招→召,扌`, `持→寺,扌`, `授→受,扌`, etc.; the
  `糸,幺,小`-thread cluster: `縮→糸,幺,小,宿`, `縦→糸,幺,小,従`,
  `線→糸,幺,小,泉`, etc.; the `阝`-cluster: `阪→反,阝`, `陥→旧,勹,阝`,
  `階→皆,阝`; plus dozens of one-off compound swaps like `寄→奇,宀`,
  `運→込,軍`, `熱→土,丸,儿,杰`, `影→景,彡`, `熊→能,杰`, `演→水,寅`) — all
  confirmed via render on the sampled subset, all structurally consistent
  with CSV.
- Verified: full rebuild from scratch; `test_regression_fixes.py` — added
  187 new pinned entries (336 checks total), same 4 expected hanzi-scope
  failures as every prior rebuild, nothing else; standard search-term
  regression checklist (old, crime, sheep, horns, half, beans, altar,
  turtle, lord, marquis, climate, convenience, revered, helping hand) all
  sane; re-running `audit_flattening.py` afterward shows raw candidates
  down from 1650 to 1294.
- Not deployed to the live server from this session; data-only change, no
  backend restart needed on next deploy.
- Coverage: **1193/3000 (39.8%)**.
- **Immediate follow-up, same session**: re-ran `audit_flattening.py` +
  the CSV filter right after this batch landed and got only **10**
  CSV-confirmed candidates back (not the ~150-200 expected) — this batch
  essentially cleared the queue rather than just dented it, because
  fixing 187 frames removed most of the redundant structure earlier
  fixes were themselves overlapping with. Worked through all 10:
  - **3 were iterative-convergence catches** — a fix from this very
    batch left a *new* redundant-flattening opportunity visible, because
    the collapse only went one level deep. `認`(rtk643, fixed to
    `言,心,刃` earlier in this batch) still had `心,刃` sitting there
    matching `忍`(endure, rtk642)'s own parts exactly — collapsed
    further to `言,忍`. `病`(rtk1813, fixed to `一,内,疒`) had `一,内`
    matching `丙`(third class, rtk1096) — collapsed to `丙,疒`
    (CSV confirms: "sickness; hospital; third class; one; ceiling;
    inside"). Lesson: a single audit_flattening.py pass isn't a fixed
    point — worth a quick re-run after any large batch.
  - **4 were pre-existing pins nobody had circled back to for this
    specific pattern**: `指`(rtk711, finger) had `日,匕` sitting next to
    `扌` instead of referencing `旨`(delicious, rtk493) — collapsed to
    `旨,扌`; `狩`(hunt, rtk258), `猪`(boar, rtk1352), `猶`(furthermore/
    waver, rtk1546) all came from the earlier out-of-band `犭`(dog
    radical)-missing fix, which only added the missing radical and left
    each one's *remainder* flattened — `寸,宀`→`守`(guard, rtk198),
    `日,老`→`者`(someone, rtk1345), `酉,丷`→`酋`(chieftain, rtk2915)
    respectively. `薪`(firewood, rtk1620) had `立,木,斤` sitting next to
    `艾` instead of referencing `新`(new, rtk1619) — collapsed to
    `艾,新`. All 7 rendered and confirmed before applying.
  - **3 were correctly left alone**, each with an explicit prior
    decision on record: `特`(rtk261) and `義`(rtk691) were both
    owner-reviewed/pinned in earlier sessions with comments explaining
    the flattened form is deliberate, not a bug; `業`(rtk1931) looked
    like it should collapse `一,木`→`未`(not yet, rtk229), but the
    2026-08-27 entry already rendered `業` specifically to settle
    whether its bottom stroke is `未` or plain `木` and confirmed `木` —
    the resolved-id match here is coincidental (both `一,木` runs exist,
    but `未`'s own compound shape genuinely isn't in `業`'s glyph). This
    is exactly the "coincidental overlap" false-positive `audit_
    flattening.py`'s own docstring warns about — checking for an
    existing pin's reasoning before touching it caught it.
  - Verified: rebuild from scratch; `test_regression_fixes.py` updated
    (7 entries changed, 336 checks total, same 4 expected hanzi-scope
    failures, nothing else); search-term regression checklist including
    "guard"/"someone"/"chieftain"/"third class"/"endure"/"delicious"/
    "hunt"/"boar"/"waver"/"firewood" all sane; re-running `audit_
    flattening.py` afterward: 1284 raw candidates (was 1294).
  - Coverage: **1193/3000 (39.8%)** — unchanged from the previous entry;
    all 7 of this follow-up's frames had already been touched by an
    earlier commit (either the previous batch or the older out-of-band
    `犭` fix), so none were new to the reviewed set.
- **Next session**: the CSV-confirmed `audit_flattening.py` queue is
  essentially empty for the first time this audit — re-run the filter
  fresh rather than assuming a large backlog still exists. 1284 *raw*
  (pre-CSV-filter) candidates remain, so there's likely real signal left
  that the CSV-components heuristic simply can't confirm (CSV's own
  components column is incomplete/noisy per session 12's findings) —
  worth spot-sampling the raw list directly, render-first, rather than
  trusting the CSV filter as the only gate from here. The 81 orphaned
  `rad{N}` rows on the live DB is still the other standing item, needs
  production access.

### 2026-08-29 — owner spot-check: `境`'s redundant flattening, plus `竟` added as a real primitive

- **Owner reported `境` should be `土`(ground) + `竟`(finally)**, with
  `竟` itself being `音`(sound) + `儿`(legs). Confirmed via `cjkvi-ids`:
  `境 = ⿰土竟`, `竟 = ⿱音儿` — exactly right. Live line was
  `音,土,日,立,儿`, a redundant-flattening bug of the exact class this
  audit's frame-ordered sweep has been clearing all session: `音`
  (rtk518, "sound") is itself already `日,立` (matches `cjkvi-ids`'s
  `音 = ⿱立日` directly), so listing `音` *and* its own already-flattened
  `日`/`立` side by side double-counted the same structure.
- **First fix (deduplicate only) wasn't what the owner wanted.** Dropped
  the redundant `日,立`, leaving `土,音,儿` — correct, but flattened
  through `竟` rather than showing it. Owner asked directly for `竟` to
  be added to the database as its own entry. Added it as a new
  primitive, `prim-finally:竟:finally`, with its *own* sub-decomposition
  (`音,儿`) rather than just deduplicating -- matches the existing
  recursive sub-decomposition architecture (`_resolve_parts_detail`'s
  `sub_decompositions`, same mechanism `丗`/`prim-thirty` used two
  sessions ago for `帯`): `境` now shows two top-level chips (`土`,
  `竟`), and `竟` expands on demand to reveal `音`+`儿` underneath,
  rather than flattening straight to five atomic pieces. Checked for a
  same-script collision on "finally" first (only a `zh-Hani` hanzi row
  existed with that meaning, no `ja-kanji` collision).
- Verified: `sync_system_data.py --dry-run` matched expectations each
  step (1 decomposition replaced for the first fix; 1 primitive
  inserted + 1 decomposition replaced for the `竟` addition);
  `get_kanji_detail` on `境` confirms the two-chip top level with
  `竟`'s sub-decomposition resolving correctly; `test_regression_fixes.py`
  — added a `境`/`竟` pin — 337/337 passing; `audit_self_reference.py`
  full sweep clean; `kanji-backend.service` restarted, live API
  spot-checked.

### 2026-08-29 — owner asked "how many visitors": added a real first-party visit counter

- **Owner asked how many people had visited the site.** No analytics of any
  kind existed (no GA/Plausible/etc. in the frontend), so answered from
  nginx's access logs directly first: of **201 unique IPs** hitting
  `/kanji/*` paths over the last ~10 days (the log retention window),
  only **15 ever loaded the actual page** rather than just probing a
  path — and of those 15, most were identifiable bots (GPTBot,
  DuckDuckBot, Google-Lens, Claude-SearchBot alone accounted for 3,706
  of the raw hits, plus a botnet reusing one canned iPhone user-agent
  string across dozens of unrelated IPs worldwide). What was left after
  stripping bots pointed to the owner's own repeated testing (same
  `87.58.x.x`/`5.22.130.12` ranges, heavy sustained interactive use
  spread across the whole week), not a distinct outside visitor.
  Realistic estimate: 0–1 genuine outside visitors in the last 10 days —
  unsurprising for a newly-public site, but genuinely not knowable from
  logs alone without this kind of manual bot-filtering every time.
- **Owner asked for a real counter going forward**, picking a
  self-hosted option over a third-party analytics script. Added:
  `page_views` table (`_migrate_v5`, schema now at v5) — one row per
  page load, tagged with a `visitor_id` read from (or freshly issued
  into) a long-lived first-party `kanji_visitor` cookie, deliberately
  *not* IP-based. `POST /analytics/pageview` (new `analytics.py`
  router, no auth required) is called once per app load from
  `App.jsx`'s mount effect, fire-and-forget (`recordPageView()` in
  `api.js` never awaited or surfaced to the user — a failure here, ad
  blocker or offline, can't affect the app). The key property this
  gives over log-parsing: a bot that only ever hits URLs directly (which
  this session's log analysis showed is the overwhelming majority of
  this site's raw traffic) never executes the frontend JS that calls
  this endpoint, so it never shows up here at all — no manual
  bot-filtering needed going forward. `backend/visit_stats.py` is the
  owner-facing read side (today/7d/30d/all-time summary, or `--days N`
  for a daily breakdown) — same "one-off script reads `kanji.db`
  directly" convention as `review_queue.py`/`coverage_status.py`, not a
  public HTTP stats endpoint, since this schema has no admin-role
  concept to gate one behind.
- Verified: migration applied cleanly against the live DB
  (`PRAGMA user_version` 4 → 5); `POST /analytics/pageview` tested
  directly against both `127.0.0.1:8000` and the real public URL
  (`https://srv.alteon.help/kanji/api/...`), cookie set and read back
  correctly; `visit_stats.py` reflects the test hits; `npm run
  build`/`lint` clean, frontend rebuilt with `/usr/bin/node-20`
  (system default is still node 18) and deployed;
  `test_regression_fixes.py` — 337/337 passing, unaffected (this
  session touched no `data.txt` content); `kanji-backend.service`
  restarted.
- **Next session**: no immediate follow-up needed — this is a small,
  self-contained addition. If real visitor numbers start showing up,
  worth eventually deciding whether `visit_stats.py`'s output should
  also get folded into whatever the "check things at the start of a
  session" routine ends up being (alongside `review_queue.py` and
  reading this file), same as that item flagged after the review-queue
  feature shipped.

### 2026-08-29 — owner questioned coverage, tried to get an external cross-check running: what worked and what didn't

- **After the `境` fix, the owner asked why it wasn't caught automatically** —
  they'd assumed every kanji was already being cross-checked against an
  external source (specifically, the AI Overview Google shows for a
  Heisig search). Answered plainly: no such per-kanji external check has
  ever existed. What runs automatically is pattern-based (redundant
  flattening, missing known radicals, self-references) plus this session's
  own manual frame-ordered sweep against `cjkvi-ids`/CSV — currently
  **1193/3000 (39.8%)** individually reviewed by any method, so `境` was
  simply still in the unreviewed ~60%, not a check that failed.
- **Tried to close that gap by actually reaching Google's AI Overview**,
  in order of what was attempted:
  1. `WebFetch` on a Google search URL — returned an error/troubleshooting
     page, no real content.
  2. The built-in web search tool — a different backend entirely (result
     links + its own summary), never surfaces Google's AI Overview widget.
  3. Installed Playwright + Chromium directly on the production server
     (`pip install playwright`, `playwright install chromium`; Amazon
     Linux 2023 has no `apt-get`, so `--with-deps` failed — installed the
     actual missing shared libs, `atk`/`at-spi2-atk`/`mesa-libgbm`/`pango`/
     etc., via `dnf` by hand) and pointed it at a real Google search.
     **CAPTCHA-blocked on the very first request** — "Our systems have
     detected unusual traffic from your computer network," tied to the
     server's own public IP. Confirmed this is IP-reputation, not
     rate-limiting: the same IP already shows up as a plain `curl` bot in
     this project's own nginx logs (see the visit-counter entry above),
     so Google has almost certainly already flagged it as a data-center
     address — pacing requests out over a long period (the owner's
     original "10 a day for a year" idea) targets the wrong failure mode
     and likely wouldn't fix this specific block.
  4. Owner offered remote-control access to their own home computer's
     browser (AnyDesk-style) — not usable either: this session has no
     remote-desktop viewing/control tool at all, independent of any
     policy question.
  5. **What actually works**: a standalone script the owner runs
     themselves, locally, on their own computer — real residential IP,
     a real visible (non-headless) browser window, no fingerprint
     spoofing or CAPTCHA-defeating of any kind (if one appears, the
     script pauses for the owner to solve it by hand). Built as
     `tools/heisig-google-check/` (deliberately outside `backend/` to
     make "does not run on the server" obvious): `check_kanji.py` picks
     N not-yet-reviewed kanji per run (random by default, `--resume-only`
     to go in order, `--id` for one specific kanji), searches each on
     Google, extracts the AI Overview text via a best-guess CSS selector
     list (Google's markup isn't a stable API and will drift — a
     screenshot is saved for every kanji regardless, so nothing is lost
     if the selector goes stale), and paces itself with a random 20-60s
     delay between queries. `unreviewed_kanji.json` (1807 entries, a
     snapshot of the coverage tsv's "no" rows plus each kanji's current
     resolved parts) ships alongside it so the owner's machine doesn't
     need any access back to this server. Progress persists locally
     (`progress.json`) so repeated runs advance instead of repeating.
     Results (`results.jsonl`) come back however's easiest — pasted
     into a message, or committed and pushed if that checkout has git
     access — for a future session to actually do the comparison
     against `data.txt` and fix what's confirmed wrong.
- **Not done here**: no actual cross-checking against `data.txt` yet —
  this session only built and verified the collection tool exists and
  the server-side blocker is real, not the analysis of any results
  (there are none yet; the owner hasn't run it).
- **Next session**: once `results.jsonl` comes back from the owner,
  read it, spot-check `extracted_text` against `current_parts` per
  entry, and treat each disagreement the way any owner-reported bug in
  this audit gets investigated (`cjkvi-ids` as the tiebreaker when the
  two disagree, since an LLM-generated AI Overview is exactly as
  fallible as any other LLM's guess — including this project's own past
  mistakes). If `extracted_text` comes back empty/wrong across most
  entries, the CSS selectors in `check_kanji.py` need updating first
  (instructions are in its own `README.md`).

## Tooling produced this session

- `backend/render_glyphs.py` — added 2026-08-23. Renders requested
  characters large to a PNG via the pre-installed headless Chromium (no
  `playwright` package needed) for actual visual comparison —
  `python3 render_glyphs.py 个 会 谷 --out /tmp/compare.png`, then look
  at it. The standing method (owner-mandated) for verifying a
  primitive's real identity: render and compare glyphs, don't reason
  from Unicode codepoint/variant tables or keyword text alone — see this
  session's `个`/"umbrella" entry above for exactly the kind of mistake
  that method catches and codepoint-reasoning alone didn't.
- `backend/audit_flattening.py` — added 2026-08-18 (session 20), tightened
  2026-08-19 (session 21). Finds every (K, M) pair of system rtk kanji
  where M's own full resolved part-id sequence appears as a contiguous,
  order-preserving run inside K's — the structural signature of the
  "redundant flattening" bug that's been the majority of this audit's
  content fixes since session 9. `python3 audit_flattening.py
  [--min-frame N] [--max-frame N]`. Session 20's version used plain subset
  containment and was swamped by coincidental overlap; session 21 switched
  to a contiguous-run requirement, which cut the noise a lot but not to
  zero — even a single unambiguous match can be coincidental. **Always
  cross-check a candidate against `heisig-kanjis.csv`'s own `components`
  column before applying it** (does CSV's baseline actually mention the
  matched compound's meaning?) — session 21's notes above document
  several real near-misses this caught.
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
- `backend/audit_csv_regressions.py` — added 2026-08-15 (session 12). The
  systematic pass sessions 10/11 flagged as queued: diffs every `data.txt`/
  `data_from_pdf.txt` override against `heisig-kanjis.csv`'s own baseline
  `components`, flagging concepts the override lost. Not a "run it and
  trust the output" tool — the raw flagged count is large (1723/3000) and
  mostly noise from CSV's own pre-expansion redundancy; session 12's entry
  above documents the manual filtering (rarity of the dropped term across
  the whole run, then "no trace of it at all vs. present but flattened")
  that got from that raw list down to 7 confirmed, fixed bugs. Rerunning it
  cold will reproduce the same large noisy list — read the session 12 notes
  before trusting anything from it without that filtering.
- `backend/coverage_status.py` — added 2026-08-17 (session 17). Regenerates
  `docs/kanji_review_coverage.tsv`, tracking which of the ~3000 `rtk*`
  kanji have actually been individually reviewed (data.txt line touched by
  a content-fix commit since the audit began) vs. never checked at all —
  the infrastructure for the "check all kanji" standing mandate from
  session 16. Run it after any content-fix commit lands so the persisted
  count stays current; see session 17 above for exactly what "reviewed"
  does and doesn't mean.
- `backend/backfill_missing_hanzi.py` — added 2026-08-22 (session 25).
  One-off patch for the Unihan self-referencing-variant bug in
  `import_hanzi.py` (see session 25 above): re-parses the same Unihan/ids
  sources with the now-fixed ambiguity logic and inserts only the rows
  genuinely missing from a live, already-seeded `kanji.db` (kanji rows,
  aliases, `variant_of` links in both directions, IDS decompositions) —
  not a full reimport. Safe to rerun; every step checks the row doesn't
  already exist first.
- `backend/audit_self_reference.py` — added 2026-08-22 (session 25), owner-
  mandated general check for "kanji lists itself as its own part" and
  `variant_of` self-loops. Checks the *live* DB directly (not a shadow
  rebuild) since the variant_of bug is hanzi-only data, not reproducible
  via `import_data()`'s rtk pipeline. Replicates the app's actual
  synthetic char+keyword-pair resolution logic exactly (see session 25's
  note on its first, too-naive version) — reusing a naive per-term
  `resolve_alias` check here will reintroduce false positives on any
  radical that happens to share a keyword with an unrelated whole kanji
  built from it. `python3 audit_self_reference.py`; exits non-zero if
  anything is found.
- `backend/test_regression_fixes.py` — added 2026-08-22 (session 25),
  owner-mandated. Pins every individually-verified kanji fix from session
  25 to its exact expected decomposition (`get_kanji_detail`-level, i.e.
  what the app actually renders), spot-checks the hanzi backfill, and
  asserts the two systemic invariants found this session (no KRADFILE
  proxy characters, no self-references) — a fast smoke test, not a
  replacement for `audit_self_reference.py`'s full sweep. Run it after
  any `sync_system_data.py` apply or `data.txt` edit; exits non-zero on
  any failure. New fixes should add a pinned entry here in the same
  commit, per the standing doc-per-commit rule below.
- `backend/render_glyphs.py` — added 2026-08-23, owner-mandated. Renders
  requested characters/strings large to a PNG via the pre-installed
  headless Chromium for visual comparison — the "actually look at it,
  don't just reason about codepoints/keywords" standing verification
  method (see CLAUDE.md's "Verifying a primitive's real identity"
  section). `python3 render_glyphs.py 個 亻 人 会 谷 --out /tmp/compare.png`,
  then Read the PNG.
- `backend/review_queue.py` — added 2026-08-25, owner-mandated. Lists the
  pending rows in the new `decomposition_reviews` table (any logged-in
  user's approve/dispute vote on a kanji's decomposition, cast from the
  detail page itself) and clears them with `--mark-processed <id>...`
  once a maintainer has acted on each — approvals become pinned
  `test_regression_fixes.py` entries, disputes get individually
  investigated. `python3 review_queue.py` / `--verdict approved` /
  `--verdict disputed` to list; see this session's log entry above for
  the full design.
- **cjkvi-ids's `ids.txt`** (external data, not a script in this repo) —
  used ad hoc 2026-08-26 to resolve `并`'s real identity; fetched via
  `curl -sSL https://raw.githubusercontent.com/cjkvi/cjkvi-ids/master/ids.txt`
  (the same source `import_hanzi.py` already depends on for the hanzi
  import). TAB-separated `codepoint / character / IDS-decomposition`
  per line, one or more decomposition variants per character
  (region-tagged `[GTJV]`/`[G]`/`[T]`/`[K]` etc. for
  Guobiao/Traditional/Japan/Vietnam/Korea glyph variants where they
  differ). Worth remembering for future primitive-identity questions —
  a structural stroke-group breakdown sits usefully between a CSV word
  list (human-authored, can be noisy/redundant per session 12's
  findings) and a single render (accurate but a dead end past what's
  visually obvious) — but see this session's entry above for two real
  false-positive traps it produces if you naively recurse the whole
  tree (stop at the target character `并` itself when found, and stop
  at any character your own app already treats as atomic/taught,
  rather than decomposing indefinitely).

### 2026-08-30 — daily check-in: caught up on out-of-band work, one more real bug via `audit_csv_regressions.py`

- Pulled latest first: since the previous entry, an out-of-band session
  fixed `境`/added `竟` as a real primitive (owner spot-check), added a
  first-party visit counter (`page_views` table, schema now v5,
  `backend/visit_stats.py`), and built `tools/heisig-google-check/` — a
  script the *owner* runs locally (not on the server, which is
  CAPTCHA-blocked by Google) to cross-check kanji against Google's AI
  Overview. No `results.jsonl` back yet, so nothing to process from that
  channel this session. Rebuilt and ran the full test suite clean
  (338 checks, same 4 expected hanzi-scope failures) before doing
  anything else, coverage confirmed at 1194/3000 (39.8%).
- With `audit_flattening.py`'s CSV-confirmed queue empty (see the
  previous entry), tried a different existing tool instead of the same
  one again: `audit_csv_regressions.py` (1604 raw hits, same noise level
  session 12 found originally). Applied a **rarity filter** — only trust
  a "dropped" CSV term if it (its resolved id) appears in 2 or fewer
  flagged entries total across the whole run, on the theory that a term
  dropped from dozens of unrelated kanji is CSV's own pre-expansion
  redundancy, not a real per-kanji mistake. Cut it to **61** candidates.
- Checked whether each candidate's dropped compound is fully present as
  a *subset* of the kanji's current resolved parts (not necessarily
  contiguous): 42 yes, 19 no. The 19 "no" cases mean the CSV-named
  concept's own sub-pieces aren't even all there — worth a future
  session's individual attention but not a quick win.
- Of the 42, checked which form a *contiguous* run (i.e. a clean
  mechanical collapse like `audit_flattening.py`'s pattern) — only 13,
  and several of those turned out to be `tid` already being a leaf/atomic
  primitive already directly present (the checking script conflated
  "no decomposition to recurse into" with "not present", flagging some
  false collapses that were actually no-ops on closer look). Rather than
  batch-apply a script with a known logic gap, worked two of them by
  hand instead:
  - **`唱`(chant, rtk21) — a real missing-component bug, same class as
    `便`/`侯` two sessions ago.** Old line was `mouth,tongue wagging in
    mouth` (口 + one 日). `cjkvi-ids` confirms `唱 = 口+昌`,
    `昌 = 日+日` (two suns stacked) — CSV's components independently
    name "prosperous" (昌) as the real compound, not just its own loose
    sub-parts. The old line only ever showed one of `昌`'s two `日`s.
    Fixed to `口,昌` (referencing the already-taught rtk25 directly, same
    convention `昌` itself already uses for showing its own repeated `日`
    as one chip). Confirmed via render.
  - **`希`(hope, rtk1602) — investigated, NOT fixed, flagging for next
    session.** CSV lists "sheaf" as a real component alongside "linen",
    and the current line (`ノ,一,巾`) turns out to be an *exact*
    reproduction of `布`(linen, rtk433)'s own 3 parts with nothing else
    — meaning `希`'s actual top stroke (a double-X shape, confirmed by
    rendering `希` next to `布` and candidate primitives) is entirely
    unrepresented. `cjkvi-ids` says `⿱㐅布` (a single U+3405 `㐅` on top),
    but the rendered glyph clearly shows two crossing strokes, and it
    does **not** match `爻`(trigrams, kangxi89 — already used in `璽`/
    `駁`/`爾`) either — `爻`'s bottom has an extra hook `希`'s top lacks.
    Needs a fresh, uncontaminated look at what that top shape actually
    is (possibly a new `prim-{slug}` primitive, following the `竟`/
    `丗` precedent) before touching it. Also flagging `柳`(willow,
    rtk1525)/`卵`(egg, rtk1526) as related: both currently reference
    `卩`(kangxi26, "stamp") directly, but CSV says their real component is
    `卯`(rtk2199)/its own left-hook variants, and `卯`'s own current
    entry (`kangxi26` alone) looks like it might be missing its own left
    stroke the same way — a small cascade worth resolving together.
  - Left the other ~40 candidates (both non-contiguous and the
    still-untrusted "contiguous" ones) alone rather than risk a rushed
    batch — noting the specific script bug (atomic/leaf terms need an
    explicit "already directly present?" check, not a silent skip) for
    whoever continues this.
- Verified: full rebuild from scratch; `test_regression_fixes.py` — 1
  new pinned entry (`rtk21`), 338 checks, same 4 expected hanzi-scope
  failures, nothing else; search-term regression checklist including
  "chant"/"prosperous"/"tongue wagging" (still resolves to 日 itself via
  self-identity, just no longer double-listed under 唱) all sane.
- Not deployed to the live server from this session; data-only change,
  no backend restart needed on next deploy.
- Coverage: **1195/3000 (39.8%)**.
- **Next session**: `希`/`柳`/`卵` cluster needs a fresh from-scratch
  investigation (possible new primitive for `希`'s top stroke); the other
  ~40 `audit_csv_regressions.py` rarity-filtered candidates from this
  session need individual review, fixing the atomic-term subset-check
  bug noted above first if scripting the check again. Once
  `results.jsonl` comes back from the owner's Google cross-check tool,
  read it and treat each disagreement as an owner-reported bug (`cjkvi-
  ids` as tiebreaker). The 81 orphaned `rad{N}` rows on the live DB is
  still the other standing item, needs production access.

## 2026-08-30 — processed the owner's results.jsonl (first pass)

Owner ran `tools/heisig-google-check/check_kanji.py` on their home computer and
pushed `tools/heisig-google-check/results.jsonl` (1812 entries: each kanji's
Google AI Overview text, captured with "Show more" expanded). Instruction: "i
pushed the results. please read and update our db if necessary."

**Methodology, in order of trust:**

1. Read a few entries in full by hand first (`rtk5`/五, `rtk6`/六) rather than
   jumping straight to scripting — `rtk6` turned up a real bug on the first
   try: its "animal legs" part was still the legacy placeholder `rad2.8`
   (`character='?'`), never re-homed onto `prim-katakana-ha`(ハ) even though
   that primitive already existed with the same glyph/meaning — the exact
   "orphaned duplicate, never wired to its real glyph" pattern as `犭`/`罒`
   earlier in this audit. Fixed: `rtk6`'s part → `prim-katakana-ha`; confirmed
   `rad2.8` had zero remaining `parts`/`aliases` references and deleted the
   dead row outright (data.txt line already had no other entry to remove).
2. Wrote `backend/triage_google_check.py`: extracts CJK characters mentioned
   in each entry's `extracted_text` (cut off at "Examples of X as a
   Primitive"/"Would you like"/etc. markers, which introduce unrelated
   example kanji, not X's own parts) and diffs against the live resolved
   decomposition. Result: 1812 total, 0 not-found live, 1036 "consistent",
   776 flagged (50 disjoint, 726 partial). Too noisy to trust as a direct bug
   list — natural-language AI Overview text keeps mentioning unrelated
   example kanji even past the cutoff markers — but it's a legitimate
   discovery aid: it directly surfaced `rtk11` (below).
3. Tried a stricter filter first (CSV's `components` column blank → flag):
   862 candidates, 834 flagged. Rejected — re-confirms the known CSV
   data-completeness gap (`rtk3`/三=一+二 is correct and well-known, CSV is
   just blank for it).
4. Switched to the authoritative check: real Unicode IDS atomicity
   (`cjkvi-ids`; a character is atomic only if its own decomposition entry
   equals itself, i.e. no structural decomposition exists in Unicode at all)
   cross-referenced against kanji whose live decomposition is non-empty.
   67 candidates (full list kept in this session's scratch output, not
   committed — Heisig legitimately decomposes some Unicode-atomic glyphs on
   purpose, e.g. 東=日+木 is a standard, celebrated RTK mnemonic despite
   Unicode treating 東 as one ideograph, so this list needs case-by-case
   judgment, not a blanket "empty it out").

**Confirmed and fixed from the 67-item list:**

- `rtk11`(口, mouth): was `口:mouth:囗` — an unrelated character (囗, "enclosure")
  listed as 口's own part. CSV lists no components for 口 and IDS confirms it's
  fully atomic. Fixed to empty parts (`rtk11:口:mouth:`). Spot-checked that
  hosts using 口 as a part (e.g. `rtk21`/唱) still resolve correctly afterward.
- `rtk543`(東, east): was `｜,一,日,木,田` — redundant flattening (｜+一 double-
  counts 日's own strokes) plus an erroneous, unrelated 田 ("rice field", no
  connection to "east"). CSV: "sun; day; tree; wood" → fixed to `日,木`.

**Explicitly flagged, deliberately NOT fixed:** `rtk1186`(由,"wherefore"),
`rtk1194`(甲,"armor"), `rtk1198`(申,"speaketh") all currently show the
*identical* parts `｜,日,田` — clearly a copy-paste artifact, not per-glyph
analysis (CSV gives each of them a completely different meaning: "sprout/
shoot" / "armour/roots" / "monkey/sun/stick/day"). IDS confirms all three
(and 田 itself) are genuinely Unicode-atomic, so any real decomposition here
would be a *visual* Heisig-style teaching (each is 田 plus/minus a
protruding stroke), not a structural one — exactly the case this audit's
"render it, don't just reason about it" rule exists for. Tried to render them
via `render_glyphs.py` to compare the three shapes side by side; no Chromium
binary was available in this environment this session (`/opt/pw-browsers/`
empty, none on PATH) — left this list for the next session that has a
working renderer, rather than guess at which of ｜/一/etc. each one actually
adds. `神` elsewhere in this file already references `申`/rtk1198 as a whole,
atomic unit, which is at least consistent with leaving 申 atomic rather than
inventing a decomposition for it.

**Applied:** `sync_system_data.py --dry-run` → 1 decomposition replaced
(rtk543), 1 removed "now atomic" (rtk11) → matched expectations exactly →
`backup_db.py` → applied for real → verified live via `get_kanji_detail`.
Manually deleted the now-fully-orphaned `rad2.8` row (kanji table only;
`sync_system_data.py` never auto-deletes orphans by design).

**Verified:** `test_regression_fixes.py` — updated the stale `rtk6` pin
(`rad2.8`→`prim-katakana-ha`), added new pins for `rtk543` and a new
`EXPECTED_ATOMIC`/`check_atomic` for `rtk11` (the checker requires a non-empty
`decompositions` list, so a genuinely-atomic kanji needed its own check
rather than reusing `EXPECTED_DECOMPOSITIONS`) — 340 checks, all pass, no
other regressions. `audit_self_reference.py` also run clean.

**Not deployed yet this session** — `git pull`/restart pending, see below.

**Second wave — the same corruption had propagated to every 東-containing
compound.** After fixing `rtk543`, grepped `data.txt` for the literal
`｜,一,日,木,田`-style pattern and found it copy-pasted into every kanji whose
CSV components mention 東 as a sub-part: `rtk544`(棟,ridgepole, CSV "tree;
wood; east"), `rtk545`(凍,frozen, CSV "ice; east"), `rtk2186`(錬,tempering,
CSV "...east; tree; wood; sun; day", plus a stray extra `ハ` with no CSV
basis at all), `rtk2745`(諌,admonish, CSV blank but IDS `⿰言東` confirms it
unambiguously). Also found `rtk2549`(柚,citron) with the same corrupted
string despite IDS showing it's structurally unrelated to 東 at all
(`⿰木由` — real right side is 由/rtk1186, not 東). And `rtk1756`(欄,column,
CSV "tree; wood; gates; east...") — its real IDS parent `闌` isn't a taught
Heisig frame in this dataset, so its mnemonic decomposition is 木+門+東 (all
three already-taught primitives CSV names), not a literal IDS structural
path. All six collapsed back to referencing the compound part as a whole
(木/由/東/門 etc.) instead of re-flattening stale strokes. Verified each via
`get_kanji_detail` post-sync; all six resolve exactly as expected.

**Related, explicitly NOT fixed this session (flagged for next time):**
`rtk749`(更,"grow late") itself carries the same `ノ,一,日,田`-style corrupted
parts, and CSV's gloss for it ("Ameratasu; one; ceiling; sun; tucked under
the arm") doesn't map cleanly onto any current primitive set — real IDS
structure is `⿱一⿻日乂` (一 over an overlapping 日/乂), and 乂 has no taught
primitive home yet. `rtk751`(梗) inherits the same problem since CSV names
"tree; wood" + 更's own gloss-terms, i.e. it decomposes via 更, not 東 (a
different fix path than the six above — was initially mis-suspected of being
another simple 東-swap, corrected after checking IDS: `梗 = ⿰木更`, not
`⿰木東`). `rtk1969`(典), `rtk1257`(曹), `rtk1806`(動 — CSV says "heavy"/重,
not 東, and 重 is itself in the atomic-but-has-parts list above), `rtk2691`
(糟), `rtk2895`(暢), and `rtk2449`(蘭 — CSV components blank, so no textual
confirmation either way) all still carry a similar `｜,一,日`-style stroke
cluster and need the same individual CSV+IDS (and ideally render, once
Chromium is available again) treatment before touching — grouping them here
as one cluster so the next session doesn't have to re-derive the grep.

**Applied (both waves), verified, regression-tested**: `sync_system_data.py
--dry-run` → backup → apply, twice (11 decompositions replaced total across
both waves, 1 removed "now atomic"); `test_regression_fixes.py` now carries
9 new/updated pins from this session (`rtk6`, `rtk543`, `rtk544`, `rtk545`,
`rtk2186`, `rtk2549`, `rtk2745`, `rtk1756`, plus the new `EXPECTED_ATOMIC`/
`check_atomic` for `rtk11`) — all checks pass; `audit_self_reference.py`
clean (0 found).

**Next session**: this is explicitly open-ended per the owner ("даже если
проверка займет год, это стоит сделать" — even if it takes a year, worth
doing). Priority follow-ups, roughly in order:
1. The `更`/`梗`/`典`/`曹`/`動`/`糟`/`暢`/`蘭` cluster flagged just above —
   needs a working Chromium (`render_glyphs.py` had no binary available this
   session) plus individual CSV/IDS review, not a blind pattern-swap like the
   six above got, since at least one candidate already turned out to need a
   different fix path (更 itself, not 東) than the initial grep suggested.
2. Render/resolve the 由/甲/申/田 cluster (identical copy-pasted parts on
   three CSV-distinct glyphs).
3. Continue through the remaining ~63 items of the original 67-item
   IDS-atomic list (most are probably legitimate Heisig teachings needing
   only a quick CSV/IDS confirmation, e.g. 犬=大+丶, 自=目, but none
   individually verified yet).
4. Consider mining the noisier 776-item `triage_google_check.py` output for
   further genuine bugs beyond what the stricter IDS-atomic check catches
   (e.g. wrong-but-non-atomic decompositions, which the atomic check can't
   see at all).

## 2026-08-30 (same session, continued) — got a renderer working, resolved the flagged clusters

Installed a real headless Chromium (`./venv/bin/python3 -m playwright install
chromium`, landed in `~/.cache/ms-playwright/`) plus `google-noto-sans-cjk-jp-fonts`
/`google-noto-sans-cjk-sc-fonts` (the box had *no* CJK font installed at all --
`render_glyphs.py` was silently producing blank glyph cells with only the
codepoint label visible until this was caught and fixed). Updated
`render_glyphs.py`'s `CHROME_CANDIDATES` to also probe the default
`~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome` path, and its
`FONT_STACK` to lead with `Noto Sans CJK JP`. This unblocks the "render it,
don't just reason about it" method for future sessions without needing the
owner's local machine.

**由/甲/申 resolved**: rendered side by side with 田 -- confirmed all three
really are 田 plus one added vertical stroke (由: pokes through the top edge
only; 甲: bottom only; 申: both). That's exactly Heisig's own `｜` primitive
(`prim-pipe`, "pipe, walking stick, cane, line" -- already used elsewhere in
the dataset), just placed differently, which this flattened parts-list model
can't distinguish by position. Fixed all three to `田,｜` (dropping the
erroneous `日` each previously also carried -- render confirms the base
shape is unambiguously 田, not 日).

**曹/動/糟 resolved**: `曹` was `｜,一,日`, silently missing `曲`("bend")
despite CSV *and* the independent `data_from_pdf.txt` 4th-edition extraction
both saying "one, bend, sun" -- render confirmed the top is 曲-shaped. Fixed
to `一,曲,日`. `動`("move") and `糟`("dregs") were both re-flattening 曹-family
strokes instead of referencing whole compounds; IDS (`動=⿰重力`,
`糟=⿰米曹`) and render both confirm they should reference `重`+`力` and
`米`+`曹` respectively. Fixed.

**重 resolved** (found as a side effect of fixing 動): IDS says 重 is
actually Unicode-atomic, but render confirms the standard, well-known Heisig
mnemonic 千("thousand")+里("village") holds up visually -- the top matches 千
exactly, the bottom matches 里 exactly. CSV's "thousand; computer; rice
field; brains; soil; dirt; ground" turned out to be 千's and 里's own
sub-component gloss fragments bleeding through onto 重's row, not 重's real
parts. Fixed `｜,ノ,一,日,里` → `千,里`.

**Still flagged, deliberately not fixed**: `更`("grow late") and `梗`
(which decomposes via 更, not 東 as initially suspected -- corrected after
checking IDS) both need a *new* primitive for the "tucked under the arm"
concept CSV and `data_from_pdf.txt` agree on (IDS's own structural answer,
`乂` inside `⿱一⿻日乂`, isn't a taught Heisig frame here, same "real IDS
parent isn't independently taught" situation as 闌/欄 from the first pass) --
creating and correctly rendering a brand-new primitive is real, careful work
that deserves its own session, not a quick copy-fix. `暢`("carefree") has the
same problem: its real IDS parent `昜` isn't a taught frame here either, and
visually 昜/易 are close enough to have caused a confirmed mix-up mid-session
(typed 易 by mistake while working from a codepoint copy-pasted out of a
terminal grep, caught by re-verifying against the exact UTF-8 bytes in
`cjkvi-ids` rather than trusting the terminal's rendering) -- another reason
to be careful with this one specifically before touching it. `典`("code")
render confirms 八 as the bottom component clearly, but the top shape and
its correct primitive identity is still unconfirmed. `蘭`("orchid") CSV
components are blank, so still no textual confirmation either way for its
`門`/`東`-adjacent parts.

Also noticed in passing (not touched, flagging for later): `rtk200`(宣)'s
pinned decomposition includes `rad1.1` (`character='?'`, aliases
"one,floor,ceiling,minus") as an expected part -- this looks like the same
"orphaned legacy placeholder colliding with an already-taught primitive"
bug class as `rad2.8`/`犭`/`罒` earlier in this audit (`rtk1`/一 already
covers "one"), but `rtk200`'s own parts list is *also* visibly bloated/
duplicated (`宀,primitive_roof,span,one,ceiling,sun,day,one,floor,one` --
"one" appears three times), so untangling this one properly means fixing
both the placeholder and the corrupted parts list together, not a quick
alias rename like the earlier fixes in this class. Left as-is.

**Applied, verified, regression-tested**: two more `sync_system_data.py
--dry-run` → backup → apply rounds (6 decompositions replaced, then 1 more
for 重 found afterward); all fixes verified live via `get_kanji_detail`;
`test_regression_fixes.py` now has 9 more new pins from this half of the
session (also removed one stale duplicate `"rtk1806"` key found while adding
the new one -- Python dicts silently let the later definition win, so it had
been dead code masking what the live pin actually checked); full suite and
`audit_self_reference.py` both clean.

**Next session priorities, updated**:
1. `更`/`梗`/`暢` need a new "tucked under the arm"-style primitive
   (name/glyph TBD -- CSV and PDF both hint at the concept but neither gives
   a ready-made Unicode component to point at) -- treat this as new-primitive
   creation work, following the `竟`/`丗` precedent, not a data.txt copy-fix.
2. `典`'s top shape and `蘭`'s 東/門-adjacent parts still need resolving.
3. The `rad1.1`/`rtk200` combined placeholder+corrupted-parts issue noted
   above.
4. Continue through the remaining ~63 items of the original 67-item
   IDS-atomic list; keep mining `triage_google_check.py`'s 776-item output.

### 2026-08-31 — daily check-in: cleared the `更`/`梗`/`典`/`暢`/`亘`/`rad1.1` cluster

- Pulled latest (two out-of-band commits since yesterday: the Google
  cross-check results got processed, 15 bugs fixed total, and a real
  Chromium+CJK-fonts renderer got installed in this environment). Rebuilt
  and confirmed clean before starting: 352 checks, same 4 expected
  hanzi-scope failures, review queue empty.
- Picked up the previous session's "next session priorities" list in
  order. All confirmed via `cjkvi-ids` + render (not just CSV, which is
  blank or only loosely worded for several of these):
  - **`rad1.1` was exactly the orphaned-legacy-placeholder pattern**
    (`犭`/`罒`/`rad2.8` precedent) — its aliases (`one`, `floor`,
    `ceiling`, `minus`) are all just Heisig's own recurring names for
    the single primitive `一`("one"), reused under a different alias
    depending on mnemonic context frame-to-frame. Moved all three
    unclaimed aliases onto `rtk1`, deleted the now-fully-orphaned
    `rad1.1` row (it had no other references anywhere in `data.txt`).
  - **`亘`(span, rtk32)** was `一,二,日` — the `二`("two") has no real
    connection to the glyph at all. `cjkvi-ids` confirms `亘 = 一+旦`
    (already-taught `rtk30`, itself `日+一`). Fixed to `一,旦`.
  - **`宣`(proclaim, rtk200)**, the corrupted/bloated line flagged two
    sessions ago, resolved as a side effect of the `rad1.1` fix:
    `cjkvi-ids` confirms `宣 = 宀+亘` exactly. The old line's `ceiling`/
    `floor`/`one`(×3) tokens were all just noisy synonyms for tokens
    `亘` itself already contains. Fixed to `宀,亘`.
  - **`更`(grow late, rtk749)** was `ノ,一,日,田` — `田` has zero
    connection to "grow late". `cjkvi-ids`: `更 = ⿱一⿻日乂` (一 on top,
    乂 overlapping 日 below). `data_from_pdf.txt`'s 4th-edition
    extraction independently names the same three primitives Heisig
    actually teaches: "ceiling" (now `rtk1`/一, see above), "sun"
    (`rtk12`/日), and "tucked under the arm" — a real Unicode character
    (`乂`, U+4E42) that had no entry yet. Added
    `prim-tucked-under-the-arm:乂:tucked under the arm` (checked for a
    same-script collision first — none). Fixed `更` to `一,日,乂`.
  - **`梗`(spiny, rtk751)** re-flattened `更`'s stale strokes instead of
    referencing it (`cjkvi-ids`: `梗 = ⿰木更`). Fixed to `木,更`.
  - **`典`(code, rtk1969)** was `｜,一,日,ハ` — render confirms the top is
    unmistakably `曲`(bend, already-taught `rtk1256`), matching CSV's
    own "bend; tool" gloss exactly; bottom is `八`. Fixed to `曲,八`.
  - **`暢`(carefree, rtk2895)** was `｜,一,日,田,勿`, none of which belong.
    `cjkvi-ids`: `暢 = ⿰申昜`, `昜 = ⿱旦勿`. Deliberately did **not** add
    `昜` as its own primitive and flattened one level further instead
    (`申,旦,勿`, all three already taught) — `昜`(U+661C) and
    `易`(U+6613, "easy") render near-identically in this box's font, and
    the previous session already caught itself mistyping one for the
    other once; not worth the confusability risk for one rare kanji when
    the fully-flattened form is just as accurate and uses only
    unambiguous existing primitives.
  - **`蘭`(orchid, rtk2449) investigated, deliberately left unfixed.**
    `cjkvi-ids`: `蘭 = 艹+闌`, `闌 = 門+柬`. `柬`("selection") is real,
    Unicode-atomic, and not currently taught — but CSV's components
    column is completely blank for this kanji (no id_5th_ed keyword
    hint either), meaning there's no Heisig-sourced confirmation of
    what he actually calls this primitive or whether he even
    distinguishes it from `東`("east", which the old broken line
    approximated it with). Rendered `柬` next to `東` and confirmed
    they're visually distinct (subtle extra strokes), but inventing a
    decomposition with no textual Heisig source to back it, for one
    rare frame, isn't worth the risk of guessing wrong — flagging for
    whoever next has a way to actually check the book itself or a
    reliable Google/AI Overview result for this specific frame.
- Verified: full rebuild from scratch; `test_regression_fixes.py` — 6 new
  pins (`rtk32`, `rtk749`, `rtk751`, `rtk1969`, `rtk2895`) plus `rtk200`'s
  stale expected-value updated — 357 checks, same 4 expected hanzi-scope
  failures, nothing else; `audit_self_reference.py` clean; search-term
  regression checklist (ceiling/floor/minus/one all correctly collapse to
  the same 456-hit count now that they share one id; span/proclaim/grow
  late/tucked under the arm/spiny/bend/code/carefree all sane).
- Not deployed to the live server from this session; data-only change +
  one new primitive row, no backend restart needed on next deploy (a
  `sync_system_data.py` run picks up new/changed/deleted rows the same
  way regardless).
- Coverage: **1216/3000 (40.5%)**.
- **Next session**: `蘭`'s `柬`/`東` question above, if a reliable
  external source turns up. Continue through the remaining IDS-atomic
  list and `triage_google_check.py`'s 776-item output, same as the
  previous two sessions' standing priority. The 81 orphaned `rad{N}`
  rows on the live DB is still the other standing item, needs
  production access.

## 2026-09-01 — continuing the IDS-atomic-but-has-parts review, 21 more fixes

Owner: "займись проверкой иероглифов" (continue the kanji-checking work) —
picking the standing task back up from the 67-item IDS-atomic list first
compiled two sessions ago. Went through the list top-to-bottom, checking each
against `heisig-kanjis.csv`'s `components` column and `render_glyphs.py`
(Chromium now works in this environment, no longer blocked).

**Fixed (real, confirmed bugs) — 13 kanji re-decomposed:**
- `世`(generation, rtk28): was `｜,一` -- render confirms it's `廿`("twenty",
  rtk1274) + a bottom horizontal stroke, matching CSV's "ten; twenty".
- `廿`(twenty, rtk1274) itself: was `｜,一,凵` -- the lone `｜` was redundant,
  both verticals already come from `凵`. Fixed to `凵,一`.
- `自`(oneself, rtk36): was missing its top dot entirely (`目` alone). CSV:
  "drop; eye" = `丶`+`目`.
- `頁`(page, rtk64): was `貝` alone, missing the top horizontal stroke that's
  clearly visible on render. Fixed to `一,貝`.
- `州`(state, rtk135): had a redundant extra `｜` alongside the correct
  `川,丶`. Removed it.
- `及`(reach out, rtk743): had a redundant extra `ノ`; render confirms `及`
  visually matches `乃`(rtk741, whose own CSV components gloss is literally
  "fist") plus one added dot, not a separate `ノ` stroke.
- `丈`(length, rtk746): was `ノ,一,丶`, none of which reflect CSV's "stick;
  tucked under the arm". Render confirms the bottom matches
  `prim-tucked-under-the-arm`(乂, added last session) exactly. Fixed to
  `一,乂`.
- `史`(history, rtk747): was `ノ,口` -- CSV: "mouth; tucked under the arm" =
  `口`+`乂`, confirmed by render. Fixed.
- `吏`(officer, rtk748): was re-flattening `史`'s parts (`ノ,一,口,丶`);
  render confirms `吏` = `一` + `史`(whole compound). Fixed.
- `久`(long time, rtk1092): was `ノ,入` -- render confirms the top matches
  `prim-hooked-hand`(𠂊, "bound up") exactly and the bottom matches `人`; CSV:
  "bound up; person; mummy". Fixed to `𠂊,人`.
- `肉`(meat, rtk1098): was `冂,人` -- render confirms `肉` and `内`("inside",
  rtk1095) share almost the same outer contour; CSV: "person; inside; belt;
  person". Fixed to reference `内` as a whole compound plus the one extra
  internal stroke `肉` adds over `内`.
- `年`(year, rtk1114): was `ノ,一,干` -- render confirms `年` and `午`("noon",
  rtk610) are nearly identical, differing by one added short stroke on top;
  CSV: "sign of the horse; sunglasses" (午 is the zodiac "horse" hour). Fixed
  to reference `午` as a whole compound plus that one extra stroke.

**Fixed (made atomic) — 8 kanji, all confirmed via the same pattern: CSV's
`components` column holds a single word naming the whole glyph's traditional
mnemonic gloss (not a parts list), each is used elsewhere as a whole-compound
reference already, and render shows the old "parts" bore no resemblance:**
- `凹`(concave, rtk33) / `凸`(convex, rtk34): CSV components blank entirely;
  simple atomic pictographs, no render-confirmable parts.
- `兆`(portent, rtk250): CSV "turtle" -- rendered next to `kangxi90`(爿,
  itself renamed "turtle" earlier in this audit) and confirmed they don't
  match at all, so "turtle" isn't pointing at an existing primitive here,
  it's just 兆's own traditional gloss.
- `欠`(lack, rtk505): CSV "yawn". Also found and deleted the orphaned legacy
  placeholder `rad4.17`(character=`?`, aliases "lack, yawn") that duplicated
  it -- zero references anywhere, safe to remove outright (same "orphaned
  KRADFILE-era placeholder" pattern as `犭`/`罒`/`rad2.8` earlier).
- `己`(self, rtk564): was pointing at `已`("stop", rtk2944) -- rendered `己`/
  `已`/`巳` side by side and confirmed all three are genuinely different
  glyphs (differing only in how closed the bottom hook is), so `己`
  referencing `已` was simply wrong, not a stylistic choice. CSV: "snake"
  (己's own traditional gloss, unrelated to any of the three).
- `才`(genius, rtk736): CSV "genie".
- `臣`(retainer, rtk911): was `匚`, which doesn't remotely resemble the real
  glyph. CSV "slave" -- rendered next to `kangxi171`(隶, which *also* has a
  "slave" alias) and confirmed they don't match either, so this is a
  same-gloss-word coincidence, not a collision to fix.
- `巨`(gigantic, rtk920): CSV "Fafner" (an unusual Heisig mnemonic reference,
  not a components list).

**Investigated, deliberately left unfixed (flagging for next session):**
- `以`(by means of, rtk1105): CSV says "plow; drop; person", but rendering
  `耒`("plow", kangxi127) next to `以` shows no resemblance at all -- CSV
  wording doesn't cleanly explain this one. Current `｜,人,丶` is at least
  plausible-looking (right side resembles 人) but not confirmed either way.
- `瓦`(tile, rtk1108): CSV lists 7 loosely-related gloss words ("one; ceiling;
  cane; stick; drop; fishhook; ice"). Render shows the current lone `一` part
  is not wrong, just incomplete -- the glyph has real additional structure
  CSV's noisy wording doesn't cleanly decompose. Needs a slower, dedicated
  pass, not a same-session guess.
- `尺`(shaku, rtk1151): CSV "flag; stick". The only existing primitive with a
  "flag" alias (`rad3.16`, character=`?`) is itself a fully orphaned,
  glyph-less placeholder -- can't confirm what it's supposed to look like, so
  left both `尺`'s current `尸,丶` parts and the orphaned `rad3.16` row alone
  rather than guess. Flagging `rad3.16` specifically as a candidate for a
  future "give it a real glyph or delete it" pass, same as `rad4.17` this
  session.
- `示`(show, rtk1167): checked and confirmed already correct (`二,小`,
  matching CSV's "two; small" exactly) -- CSV's "altar" is just 示's own
  traditional gloss, not a components hint. No change needed, noted here
  only so the next session doesn't re-check it.
- `礻`/`kangxi113` and the `己`/`已`/`巳`-as-a-part-elsewhere question: found
  that `已`(rtk2944) is used as a literal part in 18+ other kanji (起, 妃,
  記, 包, 忌, 配, 巻, 紀, 選, etc.) -- given 己/已/巳 are confirmed genuinely
  distinct glyphs (see 己 above), some fraction of those 18 hosts may
  actually need 己 or 巳 instead of 已. This needs a dedicated render pass
  per host, not a blind bulk swap -- flagging as the single highest-value
  next investigation, since it could be a systematic, longstanding KRADFILE-
  era mix-up (same root-cause class CLAUDE.md already documents for other
  proxy substitutions) affecting a two-digit number of kanji at once.
- `匚`/`巨` overlap: `拒`(rtk921) and `距`(rtk1375) both list `匚` *and* `巨`
  side by side as separate parts -- since 巨 itself was just confirmed
  atomic-with-no-匚-relation, this pairing might be a redundant double-count
  (巨's own shape may already contain what 匚 is standing in for) rather than
  two genuinely separate strokes. Not investigated further this session;
  flagging for the next one.

**Applied**: two `sync_system_data.py --dry-run` → `backup_db.py` → apply
rounds (12 decompositions replaced total, 7 removed "now atomic"); manually
deleted the confirmed-orphaned `rad4.17` row after sync (zero remaining
references). Verified live via `get_kanji_detail` for every fixed id, plus
spot-checked several downstream hosts (姫/拒/丙/桃/吹/次 etc.) that reference
the newly-atomic or newly-recomposed primitives, to confirm nothing broke.
`test_regression_fixes.py` — 21 new pins (13 `EXPECTED_DECOMPOSITIONS`, 8
`EXPECTED_ATOMIC`) — full suite passes; `audit_self_reference.py` clean.

**Next session**: the `已`/`己`/`巳` host-by-host review (flagged above) is
the standing top priority now -- it's the first finding this session that
plausibly affects double digits of kanji at once, not just one or two.
After that: `以`/`瓦`/`尺` (the three left unresolved above), the `匚`/`巨`
redundancy question, `rad3.16`'s "flag" identity, then continue down the
remaining ~35 items of the original 67-item IDS-atomic list not yet reached
this session, and eventually back to `triage_google_check.py`'s noisier
776-item output.

### 2026-09-01 — daily check-in: the 已/己/巳 host-by-host review, 18 hosts fixed

- Pulled latest first: an architecture-review session had landed since
  yesterday (CI, an isolated pytest API suite, atomic migrations/image
  uploads, rate limits, analytics retention) plus another content session
  had already picked up the standing IDS-atomic-list task and fixed 21
  more kanji, closing out most of the list except the `已`/`己`/`巳`
  cluster it flagged as top priority. Environment note: this sandbox's
  system `cryptography`/`google-auth` install was missing `cffi` (a
  `pyo3` panic on import) and `python-multipart` wasn't installed either
  — both blocked `test_regression_fixes.py`'s new alias-visibility check
  and the new pytest suite entirely. Fixed with
  `pip install cffi && pip install -r requirements.txt -r requirements-dev.txt`;
  full suite (398 checks after this session) and all 48 pytest tests then
  ran clean. Worth normalizing this into whatever the box's setup step is
  if it recurs.
- Went through all 18 hosts using `已`("stop") as a part, per the previous
  session's flagged priority. Methodology: pulled exact `cjkvi-ids`
  entries for every host (catching two of my own codepoint typos this way
  before they became commits — `妃`/`鞄` needed re-lookup with the correct
  code point), since Unicode's region-tagged IDS variants (`[G]`/`[T]`/
  `[J]`/`[K]`/`[V]`) directly answer "which of 己/已/巳 does the *Japanese*
  standard glyph use" far more reliably than eyeballing three
  near-identical box shapes at render size.
- **11 hosts were a simple character swap** — `已`→`己`, confirmed by the
  `[J]` (or unmarked/single-form) IDS variant in every case: `起`(rouse,
  also dropped a spurious `土` token render couldn't confirm any trace
  of), `妃`(queen), `改`(reformation), `記`(scribe), `包`(wrap), `忌`
  (mourning), `巻`(scroll), `紀`(chronicle), `配`(distribute), `遷`
  (transition, left its other flagged-but-out-of-scope `西`/`大` tokens
  untouched), `港`(harbor — also dropped `ハ`/`井`, neither connected to
  the real glyph at all; real structure is `氵`+`共`+`己` per `巷 = 共+己`,
  flattened past `巷` itself since it's not a taught frame with any
  Heisig citation).
- **1 host needed `巳` instead**: `祀`(enshrine) — `cjkvi-ids`'s `[JK]`
  variant confirms `巳`, not `己` or `已`. Also caught a *second*, unrelated
  bug on the same kanji while rendering it: the altar radical (`礻`,
  `kangxi113`) was standing in as the whole `礼`("salute", rtk1168) kanji
  again — the exact bug class `kangxi113`'s dataset-wide fix addressed
  weeks ago, just missed on this one host. Fixed to `礻,巳`.
- **`巳`(rtk2200) and `巴`(rtk2237) themselves were bugs, not hosts**:
  `巳`'s own line literally said its parts were `已` (a *different*
  character) — fixed to atomic, confirmed via render that 己/已/巳 are
  three genuinely distinct glyphs (differing only in how closed the
  top-right corner is). `巴` had fabricated parts (`乙,已`) despite being
  Unicode-atomic with a blank CSV components field and one continuous
  render shape — fixed to atomic too.
- **5 hosts needed a real re-decomposition**, not just a character swap:
  `選`(elect) and `撰`(assortment) both resolve through `巽`("southeast")
  per `cjkvi-ids`, which is a genuine 5th-edition-only Heisig frame
  (`id_5th_ed=2861`, dropped from the 6th, per `heisig-kanjis.csv`) —
  added as a new primitive (`prim-southeast:巽:southeast`, sub-decomposed
  to `己,共`) rather than repeating `己+共` in both hosts separately, since
  it's a real, citable compound, not an invented one. `倦`(fed up) was a
  flattened re-copy of `巻`'s own sub-parts plus stray tokens — fixed to
  reference `巻`(rtk1292) directly. `庖`(cleaver) and `鞄`(briefcase) both
  reference `包`(rtk569, "wrap") directly per `cjkvi-ids`, not `已`.
- **Side effect worth flagging, not fixed this session**: `已`(rtk2944,
  "stop") now has zero hosts left, which surfaced that its own keyword
  ("stop") collides with `rtk396`(止)'s identical keyword — `resolve_alias`
  picks `rtk396` for a bare "stop" search, so `已` is effectively
  unreachable by its own primary keyword. Same collision *class* as the
  `个`/umbrella bug from a few sessions ago, just not yet confirmed
  whether it needs a rename or is otherwise harmless since nothing
  references `已` as a part anymore.
- Verified: full rebuild from scratch; `test_regression_fixes.py` — 16 new
  `EXPECTED_DECOMPOSITIONS` pins + 2 new `EXPECTED_ATOMIC` pins — 398
  checks, same 4 expected hanzi-scope failures, nothing else; full pytest
  suite (48 tests) green; `audit_self_reference.py` clean; search-term
  regression checklist (self/snake/rouse/queen/reformation/scribe/wrap/
  mourning/scroll/chronicle/distribute/transition/harbor/elect/
  comma-design/fed up/cleaver/assortment/briefcase/enshrine/southeast)
  all sane.
- Not deployed to the live server from this session; data-only change +
  one new primitive row, no backend restart needed on next deploy.
- Coverage: **1249/3000 (41.6%)**.
- **Next session**: the `已`/"stop" keyword collision noted above; then
  back to the previous session's remaining queue — `以`/`瓦`/`尺`, the
  `匚`/`巨` redundancy question, `rad3.16`'s "flag" identity, the
  remaining ~35 items of the original 67-item IDS-atomic list, and
  `triage_google_check.py`'s noisier 776-item output. The 81 orphaned
  `rad{N}` rows on the live DB is still the other standing item, needs
  production access.

### 2026-09-01 (same day, continued) — closed the 已/"stop" collision

- Owner asked directly how the `已`/`止` "stop" keyword collision (flagged
  a few entries above) would get resolved. Checked `heisig-kanjis.csv`
  first rather than inventing a new name: `已`'s real 6th-edition keyword
  is **"stop short"**, not bare "stop" — `data.txt`'s override had
  clipped the CSV keyword down to just "stop" at some point, which is
  the actual root cause of the collision with `止`(rtk396)'s own,
  correct "stop". Restored `已`'s keyword to CSV's exact wording.
  `resolve_alias` for both "stop" and "stop short" now correctly return
  different ids.
- Verified: full rebuild; `test_regression_fixes.py` — 398 checks, same
  4 expected hanzi-scope failures; full pytest suite (48 tests) green.
- Coverage unchanged (this touched an already-reviewed row's keyword
  field, not a first-time review).

### 2026-09-01 — 匚/巨 redundancy in 拒/距, plus reconciling a parallel session

Picked up the other item flagged for this same priority (already fixed
independently and pushed by a parallel session for the 已/己/巳 cluster
itself — see the entry directly above, which arrived first): `拒`(rtk921)
and `距`(rtk1375) both listed `匚` alongside `巨`. `cjkvi-ids` gives
`拒`=`⿰扌巨` and `距`=`⿰𧾷巨` — no `匚` in either; render confirmed 拒/距's
right side matches `巨` stroke-for-stroke, no separate box shape. `距` also
re-listed 足's own parts (`口`,`止`) instead of referencing `足`(rtk1372,
already taught as `口`+`止`) as a whole compound. Fixed `拒` to `扌,巨` and
`距` to `足,巨`. 2 new regression pins added (both landing on the
`kangxi64`/`扌` duplicate-row id, same as several pins in the entry above —
see that entry's "not fixed this session" note on the orphaned-`rad{N}`-rows
issue, confirmed independently by both sessions now).

Reconciliation note: found on push that a parallel session had already done
the full 已/己/巳 host review (more thoroughly than my own first pass at it —
real structural re-decompositions for 港/選/撰/倦/庖/鞄 via `cjkvi-ids`
rather than a flat character swap, plus catching an unrelated `礼`/`礻` bug
on 祀 in passing). Reset my own duplicate work and rebased just the
additive `匚`/`巨` fix on top of theirs rather than pushing a competing
version.

**Next session**: `以`/`瓦`/`尺`, `rad3.16`'s "flag" identity, the orphaned
`rad{N}`/`kangxi{N}`/`prim-{slug}` duplicate-row cleanup (confirmed by two
independent sessions now — ~79-83 characters, needs a dedicated dedup pass
with a script, not manual checks), the remaining ~35 items of the original
67-item IDS-atomic list, and `triage_google_check.py`'s noisier 776-item
output.

### 2026-09-01 (same day) — Russian keyword aliases, pilot batch

- Owner: "я подумал перевести названия каждого иероглифа по хейсигу на
  русский и добавить как алиас. это возможно?" (thought about translating
  every Heisig kanji name into Russian and adding it as an alias — is that
  possible?). Recommended doing it as a small pilot batch first under a
  dedicated pseudo-account (the `ai-mnemonics` pattern CLAUDE.md already
  queues, applied to translations instead of mnemonics) rather than
  editing `data.txt` directly, since these are machine-translated, not
  Heisig-sourced. Owner confirmed, and asked to make sure hanzi are
  covered too, not just the RTK kanji set.
- Built `backend/add_ru_aliases.py`: creates (idempotently) a `ru-aliases`
  account — `auth_provider='system'`, no password, same reserved-account
  pattern as `owner_id=1` itself — then attaches a Russian alias to every
  public `owner_id=1` row whose English `keyword` matches an entry in a
  hardcoded `TRANSLATIONS` dict. Matches by **keyword text**, not id or
  script, so translating one English word (e.g. "one") automatically
  covers every row sharing that exact keyword across `ja-kanji` *and*
  every `zh-*` script in a single pass — no separate hanzi-specific code
  path needed.
- Pilot batch: RTK frames 1-100, each translated by hand against the real
  keyword text pulled from a live-imported DB (not guessed from memory of
  "what frame N usually is"). A few non-obvious ones: `旬`("decameron",
  Heisig's own wordplay on a 10-day period) → "декада" (the actual Russian
  word for a 10-day period, closer to the real meaning than a literal
  transliteration of "Decameron"); `中`("in") → "внутри" rather than the
  bare preposition "в", since 中 as a primitive means "inside/within", not
  the preposition.
- **Verified hanzi coverage specifically**, since that was the explicit
  ask: ran `import_hanzi.py` once in this sandbox (not part of the
  standard local rebuild — see CLAUDE.md) purely to test end-to-end, and
  confirmed the same 100-word pilot dict matched **208 rows total**, not
  just the ~100 RTK ones — e.g. translating "sword" alone correctly
  labeled `hanzi-92d8`/`hanzi-92e3`/`hanzi-93cc`/`hanzi-94d8`/`hanzi-9546`
  (five different rare sword-related hanzi sharing that gloss), and
  "bribe" similarly covered 6 hanzi variants beyond `rtk84`/賄. Reverted to
  the standard non-hanzi local rebuild afterward for the rest of this
  session's regression testing, matching this audit's established
  convention — the script itself has no hanzi-specific logic to diverge,
  so this was purely a one-time verification, not a permanent local-env
  change.
- Verified end-to-end via real searches, not just insert counts:
  `search_by_substring(conn, "один")` → `rtk1`/一 (+ hanzi rows when
  hanzi-seeded); `search_by_parts(["рот", "глаз"])` correctly returns
  嗅/憩/眠 (kanji containing both mouth and eye) exactly like the English
  equivalent search would.
- **Not yet applied to the live server** — this only writes to a local
  test DB in this sandbox; `add_ru_aliases.py` needs to be run by whoever
  has production access (same "no SSH here" limitation as every other
  live-DB script in this audit — see CLAUDE.md's Deployment section).
  Documented in CLAUDE.md's "One-off data/maintenance scripts" list and
  a new paragraph under Internationalization.
- Not added to `test_regression_fixes.py` — deliberately, matching the
  precedent set by `backfill_readings.py` (also live-DB-only content
  outside the `data.txt`/CSV seeding pipeline, also not pinned there).
- **Next session / ongoing**: `TRANSLATIONS` currently covers only
  frames 1-100 (~100 English keywords, ~208 rows including hanzi
  synonyms) — extending it to more of the ~3000 RTK keywords (and
  eventually a meaningful slice of the ~21000 hanzi-only keywords, which
  are far more numerous and often more obscure/verbose to translate well)
  is open-ended, ongoing work: translate a batch, spot-check with real
  searches the way this session did, re-run the script (idempotent, safe
  to re-run with a grown dict).

### 2026-09-01 (same day) — basic SEO so Google can actually find the site

- Owner: "хочу попросить: сделать чтоб гугл находил наш сайт srv.alteon.help.
  хотелось бы получить фитбек настоящих юзеров" (want Google to be able to
  find the site, to get real user feedback).
- `frontend/index.html` had a bare `<title>RTK Kanji Search</title>` and
  nothing else — no meta description, no canonical URL, no Open Graph tags,
  no `robots.txt`/`sitemap.xml` at all. Fixed:
  - Real `<title>` and `<meta name="description">` (reused the existing
    English `aboutIntro` copy from `i18n.js`, trimmed), explicit
    `<meta name="robots" content="index, follow">`, `<link rel="canonical"
    href="https://srv.alteon.help/kanji/">`, and Open Graph
    title/description/url/type tags for link-preview quality.
  - `frontend/public/robots.txt` (`Allow: /` + a `Sitemap:` line) and
    `frontend/public/sitemap.xml` (one `<url>` entry, see below for why
    only one) — verified via a real `npm run build` that Vite's HTML
    transform correctly rewrites the existing favicon reference and the
    new sitemap `<link>` from `/x` to `/kanji/x` (matching the site's
    `base: '/kanji/'` config), and that both files land in `dist/` at the
    paths the deployed site will serve them at (`/kanji/robots.txt`,
    `/kanji/sitemap.xml`) — confirmed by inspecting `dist/index.html` and
    `dist/*.{txt,xml}` after the build, not assumed.
  - `npm run lint` clean.
- **Three things need action outside this repo**, documented as a new
  section in `DEPLOY_README.md` rather than attempted here — none of them
  are things a session without server/Google credentials can do:
  1. The crawler-standard `https://srv.alteon.help/robots.txt` (domain
     root) is outside this repo's nginx scope (shared box, see
     `deploy/nginx/README.md`) — needs checking/adding by whoever has
     server access, with exact content given. If a root `robots.txt`
     already exists and blocks everything, that alone would defeat
     everything else here.
  2. Google Search Console setup (add property, verify ownership, submit
     the sitemap, "Request Indexing" on the main URL) needs the owner's
     own Google account — can't be done by an AI session. Step-by-step
     instructions given, including where to paste a verification meta tag
     if the owner wants a future session to add it.
  3. **Real limitation, not just a missing config**: the frontend has no
     client-side routing at all (`App.jsx` — no react-router, the URL
     never changes across a search) — Google can only ever index the one
     root URL, not individual kanji. Flagged as a real, separate feature
     project (per-kanji URLs + something for the crawler to see besides
     an empty `<div id="root">`) if deeper discoverability is ever wanted,
     not attempted this session.
- Verified: full backend regression suite unaffected (frontend-only
  change) — 400 checks, same 4 expected hanzi-scope failures; 51 pytest
  tests green.
- Not deployed to the live server from this session (no server access
  here) — needs the normal frontend rebuild+copy deploy step, plus the
  three manual items above from whoever has server/Google access.

### 2026-09-01 (same day) — owner bug reports exposed a real detector blind spot: 233 more fixes

- Owner reported five kanji wrong in a row (椅, 格, 燥, 礎, 磨) and, after
  the first couple were fixed reactively, pushed back hard on the pace:
  "ты столько работал, а ошибки в каждом иероглифе. твои тесты не
  годятся" (you worked so much, but there are errors in every kanji, your
  tests are no good). Fair challenge — investigated the *root cause*
  instead of continuing to fix one-by-one, and found a real, previously-
  undocumented blind spot, not just "more unreviewed kanji" (coverage was
  ~41% going into this).
- **The five reports, individually**: `椅`=木+奇 (`cjkvi-ids`), was
  wrongly `口,大,木,丁` — traced to *this audit's own earlier session*
  matching it against `丁`(street) instead of the maximal `奇`(strange)
  match, which also made the bug invisible to `audit_flattening.py`
  afterward (丁 absorbed the tokens that would have matched). `格`=木+各,
  `燥`=火+品+木 (had a redundant extra 口 duplicating 品's own), `礎`=石+
  林+疋 (疋="critters"), `磨`=麻+石 — all the same redundant-flattening
  pattern, all missed because of the bug below.
- **Root cause, confirmed via the fifth report**: `audit_flattening.py`'s
  contiguous-run check (by design, to cut noise — see its own docstring)
  only catches a flattened compound's parts when they sit *adjacent* in
  the outer kanji's part list. `格`'s bug (`各`'s own `口,夂` with `木`
  sandwiched between them) is structurally identical but non-adjacent —
  invisible to the existing tool, not a coverage gap.
- **Fix**: wrote `backend/audit_flattening_subsequence.py` — same
  approach, but matches an order-preserving *subsequence* instead of a
  contiguous run. Noisier (1810 raw vs ~1000 for the contiguous check),
  so applied the same CSV-cross-check filter (222 confirmed), spot-
  rendered a diverse sample, then applied 206 fixes in one batch.
- **Iterative convergence, twice**: re-ran both detectors after applying
  the batch and found second-order matches the first pass could only
  partially collapse — e.g. `苛`/`阿` each matched `丁` first (since `可`
  =丁+口 wasn't literally assembled yet), then fully matched `可` once 丁
  became a real token; `柄` similarly converged to `丙` after an
  intermediate `内` step. Also caught (independently, via the same
  re-run) that `奇`(rtk133, "strange") — the very primitive `椅`'s fix
  now correctly references — was *itself* still wrongly flattened
  (`一,口,大,亅` instead of `大,可`, since `可`=丁+口 wasn't referenced
  either); fixed it too. Third re-run converged cleanly: only the 3
  already-known, deliberately-settled false positives left (`特`/`義`/
  `業`, all previously confirmed as legitimate exceptions with their own
  documented reasoning).
- **Owner's specific follow-up ask**: "в каждом канджи где в разбивке
  есть рот, проверь действительно ли он там должен быть" (for every
  kanji with 口/"mouth" in its breakdown, check it's really supposed to
  be there). Built a precision check: for all 387 kanji currently listing
  `rtk11`(口), recursively expand each one's real `cjkvi-ids` structure
  and check whether 口 appears *anywhere* in it (not just top-level —
  catches cases where 口 is buried inside an unreferenced sub-compound).
  40 candidates where it doesn't. A CSV-text heuristic tried first (176
  candidates) was far too noisy — most of those just had no CSV data at
  all for that frame, not evidence of anything wrong.
  - **Two real clusters shared one missing primitive each**, both never
    added to this dataset at all despite being real, CSV-citable Heisig
    primitives: `𠂤`("maestro", added as `prim-maestro`) — confirmed
    across `追`/`阜`/`師`/`帥`/`官`/`埠`/`獅`/`槌`/`鎚` (9 hosts, one had
    a further sub-primitive `帀`/"noren" = 一+巾, also added); and the
    already-taught `束`("bundle") compound, which `頼`/`瀬`/`勅`/`疎`/
    `辣`/`整`/`漱`/`菅` had all individually approximated with a spurious
    `口`/`｜` instead of ever referencing.
  - **Several were false positives** — legitimate Heisig teachings for an
    otherwise Unicode-atomic glyph (`谷`/`事`/`豆`/`亜`/`民`/`革`/`束`
    itself/`史`), CSV-confirmed and render-confirmed, the same pattern as
    `東`=日+木 elsewhere in this audit. This matters as a general lesson:
    "IDS doesn't structurally decompose X" is not the same claim as "X
    has no real components" — Heisig sometimes teaches real visual
    sub-strokes of a technically-atomic glyph.
  - **Standalone bugs fixed**: `四`(was `口,人`, should be `囗,儿`
    ["pent in; human legs" per CSV, no mouth]), `使`(was missing its
    person radical entirely and didn't reference `吏`, fixed to `亻,吏`),
    `免`/`兎`/`象`(dropped a spurious 口 each, confirmed via render — no
    box shape anywhere in any of the three), `像`(was re-flattening
    `象`'s own then-broken parts instead of referencing it, fixed to
    `亻,象`), `蝦`(→`虫,又`, dropping 口 — the true top element has no
    citable primitive, `又` alone is the closest confirmed real piece).
  - **Deliberately left unfixed**: `壷`(crock) — genuinely ambiguous at
    render resolution (a box-ish shape is visible where IDS says an
    unresolvable stroke cluster sits), not worth guessing on one rare
    kanji.
- Verified: full rebuild from scratch; `test_regression_fixes.py` — 234
  new/updated pins (211 from the subsequence batch + reconciliation
  fixes, 23 from the mouth audit) — 633 checks, same 4 expected
  hanzi-scope failures, nothing else; full pytest suite (51 tests)
  green; `audit_self_reference.py` clean; both detectors re-run to
  confirm convergence (contiguous: only the 3 known false positives;
  mouth check: only CSV-confirmed legitimate cases + the one
  deliberately-skipped `壷`).
- Not deployed to the live server from this session; data-only change +
  two new primitive rows (`prim-maestro`, `prim-noren`), no backend
  restart needed on next deploy.
- Coverage: not captured separately — the follow-up commit below (羽 fix,
  same day) landed before `coverage_status.py` was re-run, so its number
  covers both batches together.
- **Next session**: `壷`'s ambiguous top element, if a better render or
  external source turns up. `triage_google_check.py`'s noisier 776-item
  output is still unmined. The 81 orphaned `rad{N}` rows on the live DB
  is still the standing item needing production access. Worth
  periodically re-running `audit_flattening_subsequence.py` (not just
  the original contiguous one) as part of the standard sweep cadence
  going forward, now that it's proven to catch real bugs the original
  tool structurally cannot.

### 2026-09-01 (same day, continued) — 羽("feathers") itself had the bug

- Owner: "soar не содержит ice. там где есть feathers часто по ошибке
  есть ice." (soar doesn't contain ice; wherever feathers is present,
  ice is often mistakenly there too) — a sharper, more specific version
  of the same pattern-spotting that found the earlier reports today.
- Root cause was a single bad line: `rtk615:羽:feathers:冫` — `羽`
  ("feathers") itself was defined with `冫`("ice") as its own part.
  `cjkvi-ids` confirms `羽 = 习+习` (two mirrored strokes), no ice
  anywhere; render confirmed the same. Checked every kanji using `羽` as
  a part (13 of them) and found `冫` copy-pasted as a literal extra
  token into every single one's own `data.txt` line, not merely
  inherited via resolution — whoever originally wrote each of these
  lines seems to have decomposed `羽` by hand using its own (already
  wrong) sub-parts each time, rather than ever referencing `羽` itself.
  Fixed `羽` to atomic and stripped `冫` from all 13 hosts (`習`, `翌`,
  `翁`, `扇`, `翼`, `翻`, `摺`, `煽`, `謬`, `翰`, `翠`, `翫`, `翔`).
- Verified: full rebuild; `test_regression_fixes.py` — 12 new pins + 2
  stale pins corrected (`翁`/`翼` had `kangxi15` baked into their
  expected value from whatever earlier session introduced this bug) —
  645 checks, same 4 expected hanzi-scope failures; pytest (51) and
  `audit_self_reference.py` both clean.
- **Deployment note, restated plainly since the owner asked directly to
  redeploy and restart production**: this sandboxed session has no
  SSH/server access at any point in this audit — confirmed repeatedly,
  not a new limitation. Every fix from today (and every prior session)
  is committed and pushed to `master`, ready to deploy, but actually
  applying it to the live site requires someone with server access to
  run the procedure in `DEPLOY_README.md` (`git pull` →
  `sync_system_data.py --dry-run` then for-real → restart
  `kanji-backend.service` only if backend code changed, which it didn't
  today — data-only). The live site the owner is testing against has
  none of today's ~250 fixes yet, which is why searches there still show
  the old, broken behavior (e.g. testing "mouth, stone" turned up many
  results — reproduced locally after today's fixes: 24 legitimate
  results, `rtk118`/石 plus every real stone-radical kanji, no errors of
  any kind). Nothing here indicates a software bug; it indicates a
  pending deploy.
- Coverage: **1408/3000 (46.9%)** (covers this batch and the previous
  233-fix batch together, see its own entry's note above).

### 2026-09-02 (daily check-in) — 邦/辰/尚: continuing the proactive common-primitives audit

- No new owner report this session — direct follow-through on the
  standing lesson from "ты столько работал, а ошибки в каждом
  иероглифе. твои тесты не годятся": the same systematic methodology
  that found `羽` (every primitive used ≥5 times as a component,
  cross-checked against CSV components + `cjkvi-ids` real structure via
  a scratch script, `check_common_primitives.py`) is now being run
  proactively as a standing practice, not just reactively after a
  report. Found two more real bugs before anyone hit them:
  - **邦** ("home country", used 12x as a component): was `ノ,二`, with
    no connection to CSV's real components ("bushes; city walls").
    `cjkvi-ids`: `邦 = 丰+阝`. Added `prim-bushes` (丰, IDS-atomic, not a
    taught RTK frame, render-confirmed against 邦's actual glyph).
  - **辰** ("sign of the dragon", used 9x as a component): was `衣,厂`
    — render confirmed `衣`("clothing") has no visual connection to the
    glyph at all. `cjkvi-ids`'s real fine-stroke structure has no clean
    citable primitive for the remainder beyond `厂,二`, so fixed to that
    and stopped there rather than invent a shaky one-off primitive for
    a single stroke detail (same restraint as the earlier `谷`/`事`/`豆`
    atomic-with-mnemonic-substrokes calls). The wrong `衣` (and, once 辰
    is referenced directly, the also-redundant `厂`) had been
    copy-pasted into all 9 hosts that already separately listed `辰`
    itself — classic redundant-flattening, same pattern as `羽`/`冫`:
    `辱`, `震`, `振`, `娠`, `唇`, `農`, `晨`, `膿`, `賑` all cleaned up.
  - **尚** ("esteem", used **49x** as a component — the highest-leverage
    single fix this audit has made): was missing an entire component
    (`口,冂` only, 2 parts). `cjkvi-ids`: `尚 = ⿱⺌冋`, `冋 = ⿵冂口` — a
    real third part is missing. Render (`小` next to `尚`) confirmed
    尚's top two strokes closely match 小's top portion, close enough to
    reuse `小` directly as a pragmatic stand-in (same precedent as `个`
    for "person"), rather than introduce the rarely-rendered CJK Radical
    Supplement character `⺌` on its own. While fixing this, also found
    the "small" alias had been resolving to an **orphaned placeholder**
    row, `rad3.13:?:little,small` — same orphaned-legacy-placeholder bug
    class fixed earlier this audit for `rad1.1`/`rad2.8`/`rad4.17`.
    Retargeted `small` onto `rtk110`(小) directly and deleted the
    orphan. Because 尚's 49 hosts all reference it via the character
    token `尚` itself (not via duplicated flattened sub-parts), fixing
    `尚` alone cascades correctly to every host's "made from" display
    with no further per-host edits needed.
- Verified: full rebuild; `test_regression_fixes.py` — 11 new pins (10
  for the 邦/辰 cluster + 1 for 尚) plus one stale pin corrected
  (`rtk2170`/農 had baked-in references to the old wrong `辰` structure)
  — 656 checks, same 4 expected hanzi-scope failures (hanzi import isn't
  part of the standard rebuild); pytest (51 passed); `audit_self_reference.py`
  clean (0 issues).
- Not deployed to the live server from this session (no SSH/server
  access, as established repeatedly) — data-only change + one new
  primitive row (`prim-bushes`), no backend restart needed on next
  deploy.
- Coverage: **1418/3000 (47.3%)**.
- **Next session**: continue reviewing the remaining unverified entries
  in the ~72-item common-primitives list (most of the high-usage-count
  entries have now been checked; the lower-count tail, roughly
  usage-count 5–30, still has a handful of only-glanced-at entries, e.g.
  `rtk1305`/矢, `rtk2175`/鬼, `rtk2154`/鹿, `rtk1503`/令). Consider
  formalizing `check_common_primitives.py` as a committed, reusable tool
  (like `audit_flattening_subsequence.py` was) rather than a scratch
  script, since it's now found two real bug clusters. Other standing
  items unchanged: `壷`'s ambiguous top element, `triage_google_check.py`'s
  unmined output, the 81 orphaned `rad{N}` rows on the live DB (needs
  production access).

### 2026-09-02 (same day, continued) — 天/矢/夫/規/漢/央/窺, and the 个-vs-亼 conflation

- Still no new owner report — continuing the common-primitives audit
  interactively. While checking `check_common_primitives.py`'s remaining
  lower-usage-count tail (矢, 鬼, 鹿, 令 among others), CSV's components
  column for `矢`("dart") read "drop; heavens" — but `矢`'s current parts
  were `ノ,大,一`, flattening `天`("heavens")'s own parts instead of
  referencing it. Checking `天`(rtk457) itself first: it had a stray
  `二`("two") with no connection to `cjkvi-ids`'s `⿱一大` or the render —
  fixed to `一,大`, then fixed `矢` to `ノ,天`.
- Re-ran `audit_flattening.py` after that (standard iterative-convergence
  practice) and it surfaced three more hosts sharing `天`'s exact old bug
  signature (a stray `二` next to `一,大`) that had been invisible until
  `天`'s own footprint shrank: `夫`(rtk901, "husband") was `人,二,大,亠` —
  none of which except `大` has any relation to the glyph; CSV/`cjkvi-ids`
  agree it's exactly `一,大`, and a render confirms it's `大` with one
  extra stroke on top (same shape family as `天`). That cascaded one more
  level: `漢`(CSV names "husband" as a real component, was flattening
  `夫`'s old wrong parts) and `規`(rtk904, "standard", `cjkvi-ids` `⿰夫見`,
  CSV "husband; see") which was `見,土,人,二,大` — fixed to `夫,見` — which
  in turn fixed `窺`("peep", `cjkvi-ids` `⿱穴規`), which was flattening
  `規`'s old wrong parts under a pile of 9 tokens. Also fixed `央`(rtk1877,
  "center") on render evidence alone (`cjkvi-ids` has no decomposition
  for it to cross-check): was `ノ,一,大,冖` but only `冖`+`大` are actually
  visible.
- Separately, while investigating `令`(rtk1503) more closely than the
  9-2 daily batch had, found a second, larger pattern: the "个 has an
  extra stroke the real shape doesn't have" anti-pattern this project
  already hit once (see the `个`/"umbrella" case in `CLAUDE.md`) recurs
  for a *different* shape. `个`("umbrella", `cjkvi-ids` `⿱人丨`, has a
  vertical stroke through the roof) had been standing in for
  `亼`("meeting", `cjkvi-ids` `⿱人一`, no vertical stroke — just a roof
  over a floor-line) in every kanji whose CSV components column names
  "meeting" as a real, distinct component: `合`, `令`, `今`, `倉`.
  Render-confirmed (`合`/`命`'s peaks visibly lack `个`'s descender) and
  added `prim-meeting` (`亼`, IDS-atomic, not a taught RTK frame — and
  referenced by its own character in every host, not by its id string,
  a mistake caught and corrected before this was verified/committed).
  Deliberately left `余` alone even though `cjkvi-ids` also shows `亼`
  there — its own CSV components say "umbrella", not "meeting", unlike
  the other four, so there isn't the same clear signal Heisig taught it
  via this primitive there. Also left `会`/`金`/`介`/`全`/`傘`/`舎`/`禽`
  alone — their `cjkvi-ids` tops are plain `人`(person), a separate,
  lower-confidence question not examined closely enough this session to
  act on safely. `命`(rtk1502) needed no direct edit since it already
  referenced `合` itself rather than flattening it.
- Verified: full rebuild; `test_regression_fixes.py` — 11 new pins (6 for
  the 天/矢/夫/規/漢/央/窺 cluster, 5 for the 合/令/今/倉/prim-meeting
  cluster — `尚`'s pin was already in from the prior commit today) — 667
  checks, same 4 expected hanzi-scope non-issues; pytest (51 passed);
  `audit_self_reference.py` clean; `audit_flattening.py` re-run to
  confirm convergence — the only remaining hit is a known, pre-existing
  `倉`/`合` false positive (`口` sits next to `亼` in `倉`'s own part list
  coincidentally, but isn't conceptually paired into "`合`" there — same
  coincidental-adjacency class already documented elsewhere in this
  audit, not a bug).
- Not deployed to the live server from this session (no SSH/server
  access) — data-only change + one new primitive row (`prim-meeting`), no
  backend restart needed on next deploy.
- Coverage: **1427/3000 (47.6%)**.
- **Next session**: still-unreviewed entries from the common-primitives
  tail (`鬼`, `鹿` were looked at this session but stayed inconclusive —
  render evidence didn't clearly separate a real bug from CSV's habit of
  listing extra synonym words for the same visual chunk; left unfixed
  rather than force a low-confidence edit). The `会`/`金`/`介`/`全`/`傘`/
  `舎`/`禽`/`余` "plain 人 vs 个" question flagged above is worth a
  dedicated pass with its own careful render comparisons, given how many
  kanji use `个` (70+) and how easy it is to get this kind of shape
  conflation wrong in either direction. Other standing items unchanged:
  `壷`'s ambiguous top element, `triage_google_check.py`'s unmined
  output, the 81 orphaned `rad{N}` rows on the live DB (needs production
  access).

### 2026-09-03 (daily check-in) — resolved the 个-vs-人 question, then fixed 比/鹿's missing "antlers"

- No pending reviews in `review_queue.py`, no new owner report. First
  cleared an item flagged as open at the end of the previous session: is
  `个`("umbrella", `cjkvi-ids` `⿱人丨`, has a vertical stroke) wrongly
  standing in for plain `人`("person", no vertical stroke) in `会`, `金`,
  `介`, `全`, `傘`, `舎`, `企`, `禽` — all kanji whose `cjkvi-ids` top is
  literally `人`, not `亼` or `个`? Checked each against its own CSV
  components row and found CSV explicitly says **"umbrella"** for every
  one of them (`会`: "one; wall; umbrella; rising cloud; two; elbow;
  wall" — which also confirms `会`'s existing `二,个,厶` is exactly right,
  not a bug). This settles it: Heisig's own real primitive choice here
  genuinely is "umbrella," regardless of which existing Unicode character
  `cjkvi-ids` happens to classify the shape under — a useful, generalizable
  lesson (CSV's real named components outrank raw `cjkvi-ids`
  shape-family matching whenever the two disagree on *which primitive
  Heisig actually taught*, even if `cjkvi-ids` is still authoritative for
  *whether a component is structurally present at all*). `余` was
  double-checked too and also left alone — CSV says "umbrella" for it as
  well, not "meeting", consistent with everything else in this batch. No
  data changes from this part; it closes out an open question instead.
- Applied that same lesson to the still-inconclusive `鬼`/`鹿` items from
  last time. `比`(rtk482, "compare") was atomic despite CSV explicitly
  listing "spoon; sitting on the ground" as its real components — the
  exact same pair already used correctly for `北`(rtk480, "north")'s
  identical CSV row. Decomposed `比` to `匕,prim-sitting-on-the-ground` to
  match. That made `鹿`(rtk2154, "deer")'s bug provable where it had
  stayed ambiguous before: CSV's "cave; antlers; compare; spoon; sitting
  on the ground" parses as cave + antlers + compare (redundantly
  re-expanded into its own now-identified spoon/sitting-on-the-ground
  parts) — "antlers" was a real, distinct component missing entirely.
  `cjkvi-ids` confirms a `⿻コ⿰丨丨` shape sitting between `广` and `比` with
  no standalone citable character anywhere in `cjkvi-ids`'s own data, so
  added `prim-antlers` the same glyph-less way as the existing
  `prim-sitting-on-the-ground` (character `?`, hidden by the frontend's
  `displayChar()`). Fixed `鹿` to `广,prim-antlers,比`.
  - `鬼` itself was re-examined too but stayed genuinely inconclusive —
    its current `匕` token does visually match a real hook-stroke in a
    zoomed render, unlike `鹿`'s case where a whole chunk was provably
    absent. Left unchanged.
- Re-ran `audit_flattening.py` after the `鹿` fix (standard
  iterative-convergence practice) — no new hits from this specific fix,
  but a manual grep for other hosts of `比`/`广` alongside `鹿` (prompted
  by how the earlier 邦/辰/天/夫 clusters worked) turned up 6 more kanji
  that each separately re-listed `比` and/or `广` redundantly alongside
  `鹿` itself, confirmed via `cjkvi-ids` showing `鹿` as one clean
  top-level component of each: `麓`(`⿱林鹿`, CSV also separately names
  "grove"=`林`), `麗`(`⿱丽鹿`, kept the existing `一,冂` approximation of
  `丽` since CSV independently confirms "one; ceiling; mediocre"),
  `麟`(`⿰鹿粦`, `粦`=`米`+`舛` per `cjkvi-ids`, dropped a stray "夕" token
  that didn't belong anywhere), `漉`(`⿰氵鹿`), `塵`(`⿸鹿土`), `麒`(`⿰鹿其`,
  kept the existing `甘,ハ` approximation of `其`).
- Left `慶`(rtk2157) alone — its `cjkvi-ids` shows the same `鹿`-shaped
  top, but a direct render comparison against `鹿` shows the bottom
  differs enough (a flowing stroke replacing `比`'s two legs) that
  guessing at the right fix wasn't safe this session.
- Verified: full rebuild; `test_regression_fixes.py` — 8 new pins (比,
  鹿, 麓, 麗, 麟, 漉, 塵, 麒) — 675 checks, same 4 expected hanzi-scope
  non-issues; pytest (51 passed); `audit_self_reference.py` clean;
  `audit_flattening.py` re-run to confirm convergence (no hits involving
  any of these 8, count down slightly from 925 to 919).
- Not deployed to the live server from this session (no SSH/server
  access) — data-only change + one new primitive row (`prim-antlers`), no
  backend restart needed on next deploy.
- Coverage: **1435/3000 (47.8%)**.
- **Next session**: `慶`'s bottom-shape question, left open above. The
  remaining lower-usage-count common-primitives entries not yet given a
  full CSV+render pass. Other standing items unchanged: `壷`'s ambiguous
  top element, `triage_google_check.py`'s unmined output, the 81 orphaned
  `rad{N}` rows on the live DB (needs production access).

### 2026-09-04 — 保 missing "person", and a third detector blind spot: the whole 石(stone) family

- Owner report: after redeploying, "still have problems" — no dispute
  button, Google auth shows a black screen in the app, and searching
  "tree, mouth" surfaces wrong results including `保`("protect")
  specifically "missing left part."
- `保` was `口,木` — entirely missing `亻`("person"), exactly the literal
  left radical the owner pointed at. `cjkvi-ids` confirms `保` = `⿰亻呆`;
  CSV names "person" as a real component alongside `呆`(rtk2297,
  "dumbfounded", already correctly `口,木`)'s own redundantly-restated
  subparts. Fixed to `亻,呆`. The other two "tree, mouth" false positives
  were redundant-flattening, not missing components: `操`("maneuver")
  listed a bare `口` alongside `品`(rtk23, "goods", which already implies
  a mouth-shape recursively) — the extra literal `口` is what made a
  depth-1 "mouth" search wrongly match it; fixed to `扌,品,木`.
  `藁`("straw") similarly re-listed `高`("tall")'s own subparts (`口,亠,
  冂`) alongside `高` itself; fixed to `艾,高,木`.
- The Google auth / dispute button reports turned out to be the same
  root cause: Google blocks its own sign-in SDK from working inside
  embedded WebViews (an anti-phishing measure), already a documented but
  unaddressed limitation of the Android app (`android/README.md`). Fixed
  by detecting the WebView (a marker `MainActivity.kt` now appends to its
  user agent) and hiding the broken Google button there instead of
  letting it render a black screen — username/password auth is
  unaffected, and the dispute button only needs a logged-in user, so this
  should unblock both reports on the Android app specifically. This does
  **not** touch the website; if the same reports recur outside the app,
  that's a different bug to investigate separately.
- Owner then asked, pointedly, to check the decomposition of *every one*
  of a "stone, mouth" search's 24 results and explain why the whole class
  hadn't been caught already, rather than accept one-off fixes. Checking
  all 23 non-atomic kanji currently listing `石`("stone") at once (not
  reactively, one report at a time) found the real scope: `石` itself is
  correctly `厂,口` (cliff, mouth) — but *every single host* built on top
  of it was also separately re-listing a bare `口` alongside `石`, even
  though `cjkvi-ids` confirms all 23 are cleanly `[石 + exactly one other
  component]` with no independent mouth stroke anywhere (`岩`=`⿱山石`,
  `破`=`⿰石皮`, `碑`=`⿰石卑`, …). That stray `口` is exactly what made a
  depth-1 "mouth" search wrongly match all of them — searching
  stone+mouth now correctly returns only `石` itself.
  - **Why this wasn't already caught**: it's a third, previously-
    undocumented detector blind spot, distinct from the two found
    earlier in this audit. `audit_flattening.py` (contiguous) and
    `audit_flattening_subsequence.py` (order-preserving) both look for a
    taught compound's **entire** part-set reappearing inside a host —
    here, `石` is only two parts (`厂,口`), and hosts referenced `石`
    itself directly *plus* just **one** of its two parts (`口`) floating
    redundantly alongside it, never the full `厂,口` pair. Neither
    detector's matching logic is built to catch "a referenced compound's
    parts overlap the host by exactly one token" — a full-part-set match
    would false-positive constantly on any two-part primitive used
    everywhere (imagine flagging every kanji with both `石` and `厂` as
    "redundant" — `厂` alone is extremely common and usually
    unrelated). This is a real gap, not a false-positive tuning issue,
    but it isn't obvious how to close it without reintroducing a flood of
    noise; it took a direct, systematic per-kanji check of one term's
    entire result set to surface it, not automated detection. Worth
    keeping in mind: any single-token overlap between a host and a
    two-part primitive it also references directly is worth a manual
    look, especially for a primitive as common as `石`.
  - Beyond the universal redundant `口`, several also needed their
    *other* component fixed: `硬`(→`更`, rtk749), `砦`(→`此`, rtk2201),
    `磐`(→`般`, rtk2016), `碇`(→`定`, rtk408), `碗`(→`宛`, rtk1521),
    `碩`(→`頁`, rtk64, also dropped a redundant `貝`), `磯`(→`幾`,
    rtk1481), `碍`(→`旦`+`寸`, rtk30), `砺`(→`厂`+`万`, rtk68, dropped a
    stray `斤`) — all "reference the already-taught compound directly"
    fixes. `確`(`⿰石隺`, `隺`=`⿻冖隹`) needed `宀`("roof") corrected to
    `冖`("cover") — render-confirmed the top lacks `宀`'s extra dot.
    `研`(`⿰石开`, `开`=`⿱一廾` exactly) and `砕`(`⿰石卆`, `卆`=`⿱九十`
    exactly) each had several unrelated stray tokens dropped. The rest
    (`拓`, `硫`, `岩`, `磁`, `碑`, `碁`, `柘`, `碧`, `硯`, `碓`) needed only
    the redundant `口` dropped.
  - Noted but **not** fixed this session: `primitive_roof` — a token used
    alongside `宀` in 20+ existing lines throughout `data.txt` — doesn't
    resolve to any real kanji id and is silently dropped on import
    (confirmed via `get_kanji_detail`). It's inert dead weight, not a
    visible bug (no orphan `?` chip appears), so lower priority than the
    fixes above, but worth a dedicated cleanup pass later.
- Verified: full rebuild; `test_regression_fixes.py` — 23 new pins + 1
  corrected stale pin (`rtk1630`/碑, which had been keyed to the same `口`
  bug) — 700 checks, same 4 expected hanzi-scope non-issues; pytest (51
  passed); `audit_self_reference.py` clean; `audit_flattening.py` re-run
  to confirm convergence (897, down from 919); directly re-ran the
  "stone, mouth" and "tree, mouth" parts searches to confirm the false
  positives are gone.
- Not deployed to the live server from this session (no SSH/server
  access) — data changes need `sync_system_data.py` + DB reseed per
  usual; the Android fix needs a new APK build; the frontend fix needs a
  rebuild+redeploy.
- Coverage: **1452/3000 (48.4%)**.
- **Next session**: given `石` alone hid 23 bugs, worth spot-checking a
  few other very common two-part primitives the same deliberate way (list
  every host, not just what an automated detector flags) rather than
  waiting for another owner report to reveal the same blind spot
  elsewhere. `慶`'s bottom-shape question and the `primitive_roof` cleanup
  noted above are also still open. Other standing items unchanged: `壷`'s
  ambiguous top element, `triage_google_check.py`'s unmined output, the
  81 orphaned `rad{N}` rows on the live DB (needs production access).

### 2026-09-04 — three app-behavior reports, then a fourth detector blind spot found at scale

- Owner report, after redeploying: no dispute button, Google auth shows a
  black screen "in app", and a "tree, mouth" search surfaces wrong
  results including `保`("protect") specifically "missing left part".
- `保` was `口,木` — entirely missing `亻`("person"), the literal left
  radical the owner pointed at. `cjkvi-ids` confirms `保` = `⿰亻呆`; fixed
  to `亻,呆` (`呆`, rtk2297, was already correctly `口,木`). The other two
  "tree, mouth" false positives were redundant-flattening: `操`
  ("maneuver") had a bare `口` alongside `品`("goods", which already
  implies a mouth-shape) — fixed to `扌,品,木`. `藁`("straw") re-listed
  `高`("tall")'s own subparts alongside `高` itself — fixed to `艾,高,木`.
- **Google auth / dispute button**: both turned out to share one root
  cause. Google blocks its Identity Services SDK from working inside
  embedded WebViews (an anti-phishing measure) — already a documented,
  unaddressed limitation of the Android app. Fixed by having
  `MainActivity.kt` append a `KanjiAndroidApp` marker to the WebView's
  user agent, which `AuthBar.jsx` now checks to skip loading the Google
  SDK entirely and show a short explanatory note instead of a black
  screen. This needs a **new APK build + install** to take effect — a
  code fix alone doesn't update an already-installed app, and this
  session has no way to build/sign/distribute one.
- Separately verified the dispute button end-to-end locally (register →
  login → search 明 → ✓ Approve / ✗ Dispute render correctly under "Made
  from") after the owner reported it missing again despite logging in
  with username/password — confirmed **not a code bug**. This is the
  second "redeployed but nothing changed" report (SEO tags were the
  first), so `DEPLOY_README.md` now has a concrete checklist: rebuild
  `dist/` (not just `git pull`), verify the copied files have fresh
  timestamps, then suspect `index.html` caching before assuming the code
  is wrong.
- Owner then asked to check every one of a "stone, mouth" search's 24
  results and explain why the whole class hadn't been caught already.
  Found a **third detector blind spot**: `石`("stone") itself is
  correctly `厂,口`, but *every one* of the 23 other kanji built on it
  was also separately re-listing a bare `口` alongside `石` — neither
  existing detector catches a *partial* overlap between a host and a
  directly-referenced compound (both require the compound's *entire*
  part-set to reappear). Fixed all 23 (a few also needed their other
  component corrected — full list in that commit), and built
  `audit_direct_ref_overlap.py` to search for this pattern systematically
  instead of relying on another owner report.
- Owner asked to run that search proactively across other common
  primitives. It found the identical bug at **far larger scale** — four
  more families, 142 kanji: `糸`("thread", 77 hosts — the entire
  silk/thread radical family), `頁`("page", 26 hosts — the "head/page"
  family, plus `嶺` needed a follow-on fix once `領` was corrected),
  `魚`("fish", 20 hosts — the entire fish-radical family), `足`("leg", 19
  hosts — which also surfaced `促` missing "person," same class as `保`,
  plus a few CSV/render-corrected stray tokens). Then four more, 57
  kanji: `尚`(14 hosts — `償` missing "person"; `党`/`哨` were using the
  wrong shape entirely, fixed by correcting `肖` itself), `戸`(17 hosts —
  `偏`/`遍`/`編`/`篇`/`騙` were flattening a second-level compound `扁`
  instead of referencing it, new `prim-fishfinger`; `偏` missing
  "person"), `穴`(16 hosts — `容`/`蓉` don't contain `穴` at all, a
  sharper version of the overlap bug where they'd picked it up only
  because `宀` happens to be one of `穴`'s own parts), `音`(14 hosts —
  `章` likewise doesn't contain `音` at all; `暗` needed *only* one of its
  two overlapping tokens dropped, since its own `日` legitimately does
  double duty as both `音`'s internal part and `暗`'s own external
  neighbor — not a blind drop-the-whole-overlap case). Every fix
  cross-checked against `cjkvi-ids` first, same discipline as the rest of
  this audit; deliberately left a handful of harder cases open rather
  than guess (`蔽`/`弊`/`瞥`/`鼈`/`獣`'s real `敝`-family structure; `慶`'s
  bottom shape from a prior session).
- Verified across all three commits: full rebuilds; `test_regression_fixes.py`
  reached **868 checks** (same 4 expected hanzi-scope non-issues) after
  correcting 31 stale pins and adding 168 new ones; pytest (51 passed)
  and `audit_self_reference.py` (0 issues) after every commit;
  `audit_flattening.py` and the new `audit_direct_ref_overlap.py` re-run
  after each batch to confirm convergence (that detector's candidate
  count at `--min-usage 3` dropped from 384 to 178 over the session).
- Not deployed to the live server (no SSH/server access) — data changes
  need `sync_system_data.py` + reseed; the Android fix needs a new APK
  build; the frontend fix needs a rebuild+redeploy (see the new
  `DEPLOY_README.md` checklist above).
- Coverage: **1558/3000 (51.9%)** — passed the halfway mark this session.
- **Next session**: `audit_direct_ref_overlap.py --min-usage 3` still has
  178 candidates across smaller primitive families (usage 3-13) — this
  is now a standing, high-leverage tool to keep working through
  proactively rather than wait for more owner reports. The deliberately-
  skipped `敝`-family cluster (`蔽`/`弊`/`瞥`/`鼈`/`獣`) and `慶`'s bottom
  shape are still open. Other standing items unchanged: `壷`'s ambiguous
  top element, `triage_google_check.py`'s unmined output, the
  `primitive_roof` dead-token cleanup, the 81 orphaned `rad{N}` rows on
  the live DB (needs production access).

### 2026-09-04 (same day, continued) — five more families, and a second dead alias token found

- Kept working through `audit_direct_ref_overlap.py --min-usage 3`
  proactively rather than stopping at the halfway-mark coverage
  milestone. Same discipline, `cjkvi-ids` cross-checked before every
  edit:
  - `青`(rtk1654, 10 hosts) — the "clear/blue" family (精,請,情,晴,清,
    静,靖,錆,鯖) correctly referenced `青` but redundantly repeated its
    own parts. `瀞` was flattening `静` instead of referencing it
    directly.
  - `示`(rtk1167, 10 hosts) — several hosts (`剽`,`捺`,`禦`,`綜`,`瓢`,
    `祟`) were flattening an already-taught second-level compound
    (`票`, `奈`, `御`, `宗`, `出`) instead of referencing it; `剽` was
    also entirely missing "刀". While fixing it, found a **second dead
    alias token** of the same kind as `primitive_roof`: `刂` (the
    right-side radical form of 刀) isn't a registered alias anywhere in
    this system — only `刀` itself is — so a part list using `刂`
    silently drops that component on import, the same trap as before.
    Corrected `剽` and `到`(rtk817, caught the same way) to use `刀`.
    `蔚` doesn't contain `示` at all (its real structure is unrelated)
    — dropped it rather than force an approximation.
  - `至`(rtk815, 9 hosts) — `到` was missing "刀" (see above) and
    `倒`/`緻`/`渥` were flattening second-level compounds (`到`, `致`,
    `屋`) instead of referencing them.
  - `巾`(rtk432, 9 hosts) — only fixed the one clean case (`凧`=几+巾);
    left `刺`/`策`/`棘` (real `朿`-family) and `幣`/`蔽`/`弊`/`瞥`/`逓`
    (`敝`-family, already an open question) for another session rather
    than force an uncertain call.
  - `自`(rtk36, 9 hosts) — most hosts correctly referenced `自` but
    redundantly repeated its own "目". `嗅`/`榎`/`鼾` were flattening
    already-taught compounds (`臭`, `夏`, `鼻`) instead of referencing
    them.
- Verified: full rebuild; `test_regression_fixes.py` — corrected 3 stale
  pins, added 35 new pins — **903 checks**, same 4 expected hanzi-scope
  non-issues; pytest (51 passed); `audit_self_reference.py` clean;
  `audit_direct_ref_overlap.py`'s `--min-usage 3` candidate count now
  **139** (down from 384 at the start of today's session).
- Not deployed to the live server (no SSH/server access) — data-only
  change, no backend restart needed on next deploy.
- Coverage: **1584/3000 (52.8%)**.
- **Next session**: `刂` joins `primitive_roof` on a short watch-list of
  known-dead alias tokens worth grepping for across the rest of
  `data.txt` at some point (both silently drop the component they were
  meant to represent, with no visible symptom other than a missing
  chip). `audit_direct_ref_overlap.py --min-usage 3` still has 139
  candidates in smaller families (usage 3-8) to keep working through.
  The `朿`/`敝`-family clusters in `巾`'s hosts, the deliberately-skipped
  `敝`-family cluster in `尚`'s hosts, and `慶`'s bottom shape are all
  still open. Other standing items unchanged: `壷`'s ambiguous top
  element, `triage_google_check.py`'s unmined output, the 81 orphaned
  `rad{N}` rows on the live DB (needs production access).

### 2026-09-04 (same day, continued) — a live-search spot-check, and the autocomplete feature shipped

- Owner asked to search "goods" (品, rtk23, used 8x) directly. `品` itself
  is correctly just `口` (no-duplicate-token convention for its own
  3-mouth shape); `燥`/`操`/`嘔` already correctly referenced it. `臨`/
  `繰`/`藻`/`癌` all redundantly repeated a bare `口` alongside `品` —
  same overlap bug as the rest of today, just found by checking a live
  query instead of the automated detector. Fixed all three (`癌`'s
  `疔` token is a pre-existing, legitimate alias of `kangxi104`/`疒`, not
  a separate error).
- Owner asked about "mouse"+"stone" and "goods" searches, then about the
  Russian-aliases feature's status. Ran `add_ru_aliases.py` against this
  session's local DB to demonstrate it works (105 aliases inserted from
  the 100-word pilot batch, e.g. "рот"→口, "глаз"→目, "один"→一) — the
  owner then reported "глаз" found nothing on the live site, confirming
  what was already suspected: the script has never been run against
  production. This is a one-off maintenance script, not something a
  code deploy applies automatically — someone with server access needs
  to run `python3 add_ru_aliases.py` there directly.
- Owner asked why there's no substring hint when typing a primitive
  name, then explicitly asked to prioritize building it — the item
  queued in `CLAUDE.md` since 2026-08-14. Built it:
  - Backend: `suggest_terms(conn, q, limit=10)` in `database.py` — a
    new, different match than `search_by_substring` (whole-word, for
    final search precision): autocomplete needs to match `q` **anywhere**
    inside a candidate name, since the user is still mid-keystroke and
    hasn't necessarily reached a word boundary. Splits comma-separated
    synonym lists into individual names, only considers public rows
    (a private term isn't a useful suggestion for anyone else typing
    into the same bounded vocabulary), ranks prefix-matches first then
    **shortest-first** — an early version sorted purely alphabetically
    among prefix matches and found "mouth" got crowded out of a 10-item
    cap by nine different "mount-" compounds; sorting by length first
    fixed that. New `GET /search/suggest?q=` endpoint (no auth, no
    script/sources — nothing about a suggestion is viewer-specific). 5
    new pytest tests in `test_api_search.py`.
  - Frontend: new `AutocompleteInput.jsx` wraps a text `<input>` with a
    suggestions dropdown; `getQuery`/`applySuggestion` props let each
    caller define what's being typed and what picking a suggestion
    produces — `AliasAdder`'s field is one value (query == value), but
    `DecompositionForm`'s parts field is a comma-separated list
    (autocomplete only applies to the segment after the last comma, and
    picking a suggestion replaces just that segment). New
    `useSuggestions.js` hook debounces the lookup (200ms, 2-char
    minimum). Wired into both inputs in `KanjiDetail.jsx`.
  - Verified end-to-end locally via Playwright: register → login → open
    明 → typing into the alias-add "+" field shows a working dropdown
    (e.g. "wat" → water/watchtower/...), and typing "water, mou" into
    the decomposition-parts field shows suggestions for just the "mou"
    segment, clicking one (e.g. "mountain") correctly produces
    "water, mountain" without disturbing the finished "water" segment.
- Verified: backend pytest (56 passed, up from 51 — the 5 new
  `/search/suggest` tests), `oxlint` clean, `npm run build` succeeds.
  For the `品` fix specifically: full rebuild, `test_regression_fixes.py`
  (906 checks, 1 stale pin corrected + 3 new), `audit_self_reference.py`
  clean, and the "goods" search re-run to confirm the same 8 results
  with the redundant tokens gone.
- Not deployed to the live server (no SSH/server access) — the `品`-family
  fix is data-only; the autocomplete feature needs both a backend
  restart (new endpoint) and a frontend rebuild+redeploy. The Russian
  aliases still need `add_ru_aliases.py` run against production
  separately — that's not part of a normal code deploy at all.
- Updated `CLAUDE.md`: struck the autocomplete item from "Known
  limitations," documented the new endpoint/match semantics in "Search
  logic," and added `AutocompleteInput.jsx`/`useSuggestions.js` to the
  frontend file tree.
- Coverage: **1586/3000 (52.9%)**.
- **Next session**: same standing items as this morning's entry —
  `audit_direct_ref_overlap.py --min-usage 3`'s remaining ~139
  candidates, the `刂`/`primitive_roof` dead-token grep cleanup, the
  `朿`/`敝`-family questions, `慶`'s bottom shape, `壷`'s ambiguous top
  element, `triage_google_check.py`'s unmined output, the 81 orphaned
  `rad{N}` rows on the live DB.

### 2026-09-04 (same day, continued) — mining the owner's own Google results.jsonl

- Owner asked to continue checking the database against the owner's own
  Google AI Overview lookups (`tools/heisig-google-check/results.jsonl`,
  1812 entries, pushed back on 2026-08-30) and research every
  disagreement — not another owner-reported single kanji this time, but
  a standing, already-built tool (`triage_google_check.py`) nobody had
  worked all the way through yet.
- `triage_google_check.py` flags 651 of 1812 kanji where the live
  decomposition and Google's mentioned characters don't overlap enough
  to look consistent, split into 43 "DISJOINT" (zero character overlap
  at all — the strongest signal) and 608 "PARTIAL" (something in ours
  that Google's text doesn't echo — much noisier, most likely just
  Google's own text omitting a real part rather than us having a wrong
  one). Worked through all 43 DISJOINT entries this session, same
  `cjkvi-ids`/CSV/render discipline as every other fix — this is a
  heuristic pre-filter over another LLM's guess, not a verdict, so
  every flag still needed independent verification, not blind trust.
  Most turned out to be false positives (Google mentioning an unrelated
  example kanji that uses the target as a component, not a real part of
  the target itself, or a kanji this same session had already fixed
  earlier today before `results.jsonl` was scraped — 梗, 党, 邦). But 19
  were real, previously-uncaught bugs:
  - **Missing components** (same class as `保`/`促`/`偏` found earlier
    today): `良` was missing "丶" (`cjkvi-ids` confirms `⿱丶艮`, and a
    render shows the extra top dot clearly); `爽` was missing "大"
    entirely (render shows the glyph's outer frame is `大` with a
    doubled-cross shape overlaid inside, approximated with the
    already-established `乂`).
  - **Wrong box shape** — the opposite direction of the same `田`-vs-
    another-box-shape confusion this audit has hit before: `亀` had
    `田`(rice field, 4-cell grid) where a render clearly shows a 2-cell
    `日`(sun/day) box instead. Checked `申` side by side with the same
    question and confirmed its `田` *is* correct there — a useful
    reminder to actually render both directions rather than assume a
    pattern generalizes.
  - **Reference an already-taught compound directly instead of
    flattening** (this audit's most common fix shape by far): `渓`→`夫`,
    `尽`→`尺`, `芝`→`之`, `浜`→`兵`, `浪`→`良`, `英`→`央`, `汀`→`丁`,
    `茉`→`末`, `芥`→`介`, `迪`→`由`, `邁`→`萬`, `慾`→`欲`, `添`→`天`(+`心`),
    and `芸`→`云` — which needed `云` itself fixed first, since it was
    `一,二,厶` but `cjkvi-ids`'s `⿱二厶` has no `一`. `歪`
    (`cjkvi-ids` `⿱不正`) now references both `不` and `正` directly
    instead of a flattened mash of both.
  - Deliberately left several DISJOINT hits alone rather than force a
    low-confidence call: `単`/`脳` share an unusual `cjkvi-ids` "𭕄"
    marker neither side of this session's investigation could resolve
    confidently; `壷`'s top element is the same already-standing
    ambiguous question from earlier sessions; `斡`, `華`, `予`, `共`,
    `蒲`, `汚`, `之`(itself), `了`, `袖`, `浄` all had plausible existing
    approximations without strong enough counter-evidence to override
    them.
- Verified: full rebuild; `test_regression_fixes.py` — 19 new pins —
  **925 checks**, same 4 expected hanzi-scope non-issues; pytest (56
  passed); `audit_self_reference.py` clean; `audit_direct_ref_overlap.py`
  re-run against every newly-referenced compound (夫, 尺, 之, 兵, 良,
  央, 丁, 末, 介, 由, 萬, 欲, 不, 正) to confirm none of today's fixes
  introduced a new redundant-overlap bug.
- Not deployed to the live server (no SSH/server access) — data-only
  change.
- Coverage: **1605/3000 (53.5%)**.
- **Next session**: the 608 PARTIAL hits in `results.jsonl` are still
  completely unmined — much noisier than the DISJOINT set, so probably
  worth a lighter, faster triage pass rather than the same per-kanji
  render treatment for all 608. Otherwise the standing list is
  unchanged: `audit_direct_ref_overlap.py --min-usage 3`'s ~139
  remaining candidates, the `刂`/`primitive_roof` dead-token grep
  cleanup, the `朿`/`敝`-family questions, `単`/`脳`'s shared "𭕄"
  marker, `慶`'s bottom shape, `壷`'s ambiguous top element, the 81
  orphaned `rad{N}` rows on the live DB.

### 2026-09-05 (daily check-in) — mining the noisier 622 PARTIAL results.jsonl flags

- No pending reviews in `review_queue.py`. Picked up exactly where
  yesterday's entry left off: the 622 "PARTIAL" flags from
  `triage_google_check.py` (something in our own decomposition that the
  owner's Google AI Overview text doesn't echo) — much noisier than the
  43 DISJOINT flags finished yesterday, since a short AI Overview
  snippet routinely omits a real component without that meaning our
  side is wrong. Rather than repeat yesterday's full per-kanji render
  treatment on all 622 (explicitly flagged as impractical in yesterday's
  own "next session" note), wrote a quick filter script
  (scratch, not committed) for the highest-signal subset first: exactly
  **one** of our tokens missing from Google's text, **no kana** in
  Google's mentions (kana in the mentions is a strong tell the "AI
  Overview" text leaked furigana/reading notation rather than real
  primitive names), and Google's own mention list short and clean. That
  cut 622 down to 126 candidates worth a manual look — still verified
  every survivor against `cjkvi-ids`/CSV before touching anything, same
  discipline as always, since the filter is a triage aid, not a verdict.
- Most of the 126 were already-known false-positive *patterns* this
  audit has documented repeatedly, just newly encountered via this
  specific tool: `水`/`氵`, `込`/`辶`, `ハ`/`八`, `艾`/`艹` radical-variant
  pairs (both sides are correct, the tool just doesn't know they're
  equivalent), and a handful of `个`("umbrella") cases already resolved
  earlier this same session's `个`-vs-`人` investigation. Skipped all of
  those. Found 14 real bugs in what remained:
  - `忘`/`忙`/`盲`/`妄` all redundantly repeated `亡`(rtk524)'s own "亠"
    part alongside referencing `亡` directly — this audit's most common
    bug shape, this time surfaced by the Google cross-check instead of
    `audit_direct_ref_overlap.py`. `忙` was additionally missing "忄"
    entirely (`cjkvi-ids` `⿰忄亡`) where "亠" was doing nothing useful
    in its place.
  - `朗` was flattening `良`'s **pre-fix** parts instead of referencing
    it directly (`cjkvi-ids`'s K variant `⿰良月`) — confirms yesterday's
    `良` fix (`丶,艮`) was worth doing beyond just `良` itself. `島` had
    a stray extra "白" `cjkvi-ids` doesn't call for at all (`⿹⑦山`,
    confirmed by render: `鳥` sits cleanly on `山` with nothing else
    needed). `烏` was using the **wrong** reference entirely — it's
    render-confirmed missing a stroke `鳥` has (compare `鳥`'s extra
    top-left dash), so CSV's real component list ("drop; mouth; one;
    tail feathers") was used instead of flattening via the too-similar
    `鳥`.
  - `能` was missing "prim-sitting-on-the-ground" — the exact
    spoon/sitting-on-the-ground pair from `北`/`比` found earlier this
    audit; CSV confirms "spoon; sitting on the ground" for `能` too.
  - `雲`/`腸`/`恵` were each flattening an already-taught compound's own
    parts instead of referencing it (`云`, `旦`) or had a plain wrong
    token (`恵` had "一" where CSV explicitly names "ten" — should be
    "十").
  - `双`/`彼`/`秘` each carried one redundant extra stroke duplicating
    part of an already-referenced compound: `双` = `又`+`又` per
    `cjkvi-ids` (the established "no duplicate token" convention
    collapses this to one `又`); `彼`'s extra `又` is already inside
    `皮` per the `rtk865` fix; `秘`'s extra `丶` is already inside `必`.
- Verified: full rebuild; `test_regression_fixes.py` — 1 stale pin
  corrected (`rtk970`/秘, keyed to the pre-fix redundant value), 13 new
  pins — **938 checks**, same 4 expected hanzi-scope non-issues; pytest
  (56 passed); `audit_self_reference.py` clean; `audit_flattening.py`
  and `audit_direct_ref_overlap.py` re-run against every newly-
  referenced compound (`亡`, `良`, `云`, `旦`, `皮`, `必`, `鳥`) to
  confirm none of today's fixes introduced a new bug of either kind.
- Not deployed to the live server (no SSH/server access) — data-only
  change.
- Coverage: **1618/3000 (53.9%)**.
- **Next session**: ~496 of the 622 PARTIAL flags remain un-triaged
  (everything the quick filter excluded — multiple missing tokens, or
  kana/long text suggesting more scraping noise). Worth deciding whether
  a second, looser filter pass is worth the noise, or whether that pool
  is better mined some other way (e.g. cross-referencing against
  `audit_direct_ref_overlap.py`'s own remaining candidates, since
  several of today's real bugs — `忘`/`忙`/`盲`/`妄`'s `亡` overlap, `能`'s
  missing sitting-on-the-ground — turned out to be findable either way).
  Otherwise the standing list is unchanged: `audit_direct_ref_overlap.py
  --min-usage 3`'s ~139 remaining candidates, the `刂`/`primitive_roof`
  dead-token grep cleanup, the `朿`/`敝`-family questions, `単`/`脳`'s
  shared "𭕄" marker, `慶`'s bottom shape, `壷`'s ambiguous top element,
  the 81 orphaned `rad{N}` rows on the live DB.

### 2026-09-05 — 5 disputed reviews, then the whole single-`亻` person-radical family (86 kanji)

- Owner had queued **5 disputed** decompositions in `review_queue.py`
  (#9-13): `椋`(rtk2540), `桔`(rtk2561), `検`(rtk1803), `橋`(rtk460),
  `麿`(rtk2903). All five were the same root cause — **KRADFILE
  over-fragmentation from the original `import_rtk.py` seed**: a whole RTK
  primitive shattered into stray strokes. For three of them
  (`椋`/`桔`/`麿`) `heisig-kanjis.csv` had an *empty* `components` field
  (rare N1/uncommon frames outside the 6th-ed core), so the KRADFILE guess
  in `data.txt` won the merge unopposed; for `橋`/`検` the CSV baseline was
  actually fine but a hand-typed `data.txt` line (KRADFILE-derived) beat it
  (step 3 wins). Fixes, all render- + `cjkvi-ids`-confirmed:
  - `椋` `口,小,木,亠` → `木,京` (亠+口+小 was a shattered `京`).
  - `桔` `口,士,木` → `木,吉` (士+口 was a shattered `吉`).
  - `橋` `ノ,口,木,冂` → `木,ノ,口,大,冂` — was missing `大` and a `口`
    versus its own `喬`-family siblings `嬌`(rtk461)/`矯`(rtk1306), which
    both decompose the `喬` part as `ノ,口,大,冂`.
  - `麿` `口,木,广,麻,ノ` → `麻,呂` — `麻` was **double-counted** (listed
    alongside its own sub-parts `广`,`木`), plus a spurious `ノ`. `麿` =
    `⿸麻呂` per `cjkvi-ids`, render-confirmed.
  - `検` left as the family value `木,口,人,个` — its dispute is really the
    standing `个`-vs-`亼` question shared across the whole `僉` family
    (`剣`/`険`/`験`/`倹` all use `口,人,个`); splitting `検` off alone would
    just diverge it. Flagged for the family-wide `个`/`亼` decision, not
    fixed unilaterally.
  - Also fixed `呂`(rtk24) itself in passing: was `口,ノ` — missing the
    **second `口`** entirely (the `ノ` is another KRADFILE proxy). RTK
    teaches `呂` as two mouths; → `口,口`.
- Then, per the user's "check every one of rtk1000-3000, don't wait for me
  to find errors": ran a `cjkvi-ids`-vs-`data.txt` cross-check for the
  **person radical** — every `rtk*` kanji whose IDS has `亻` as a direct
  top-level component but whose `data.txt` parts list has no
  person-resolving token. **86 hits** — essentially the entire
  single-`亻`-radical family: `佐 侶 但 住 位 仲 体 件 仕 他 伏 仏 休 伯 俗
  信 佳 例 健 側 侍 値 倣 傲 偵 僧 儀 仙 催 仁 侮 倍 優 伐 傑 付 任 代 化 傾
  何 俊 傍 俺 併 伸 作 侵 伊 儒 備 借 係 債 俵 僅 価 俳 候 偉 仰 僚 修 供 倫
  低 伺 偽 偶 倭 俄 佃 仔 仇 伽 儲 僑 倶 侃 偲 侭 脩 伍 什` and more. Every
  one came in from `import_rtk.py`'s KRADFILE pass with `亻` **dropped**,
  usually replaced by a stray `ノ` ("katakana no") — so a "person" search
  missed all 86. This is the exact `保`(rtk1072) bug the owner reported
  2026-09-04, but dataset-wide across one whole radical family — the tip of
  that iceberg.
  - **Why not caught before**: the `保` fix was reactive (one owner
    report). No detector looks for "IDS names `亻` but our parts don't" —
    `audit_radicals.py` only flags *unresolvable* tokens (these lines had
    resolvable but *wrong* tokens), and the flattening detectors look for
    redundancy, not omission. A `cjkvi-ids`-presence check per radical is
    the right tool and hadn't been run for `亻`.
  - Fix: for the ~65 where the IDS right-hand side is itself a taught
    system kanji, collapsed to `亻,<compound>` (enables recursive search,
    matches the already-fixed `rtk1072:保:亻,呆` style); for the rest,
    prepended `亻` and kept the existing sub-decomposition, dropping the
    bare `ノ` proxy. 6 of the 86 had **stale regression pins** keyed to
    their pre-fix (person-less) value — `側`/`偽`/`儀`/`候`/`傾`/`係` — all
    updated to the corrected `亻,X` form.
- Verified: full rebuild; `test_regression_fixes.py` — added a
  `check_person_radical_present` **structural invariant** (all 86 hosts
  must carry a person-resolving part) rather than 86 brittle individual
  pins, matching the KRADFILE-proxy invariant's philosophy; +5 disputed
  pins; 6 stale pins corrected → **1025 real checks pass** (same 4
  expected hanzi-scope non-issues, since the shadow DB doesn't run
  `import_hanzi.py`). pytest: 56 passed. `audit_self_reference.py`: 0.
  `audit_radicals.py`: still just 2 unnamed tokens (`亦`, `'ninety'`) —
  the fix introduced no new unresolvable terms.
- `review_queue.py --mark-processed 6 7 8 9 10 11 12 13` — cleared all 8
  (the 3 remaining `approved` votes #6-8 for `状`/`帯`/`泥` reviewed and
  left as-is; nothing to fix).
- Not deployed to the live server (no SSH/server access) — data-only
  change; needs `sync_system_data.py` + reseed on deploy.
- Coverage: **1625/3000 (54.2%)** — 92 `data.txt` lines edited but only 7
  were first-time reviews; most of the 亻 family had already been touched
  by earlier audit commits (for other reasons) without anyone checking the
  person radical specifically, which is exactly how this bug survived.
- **Next session**: continue the rtk1000-3000 sequential sweep from
  rtk1043 onward (person family done; `氵`/`扌`/`阝`/`艹` radical families
  are worth the same `cjkvi-ids`-presence check `亻` just got). Standing
  list otherwise unchanged: `audit_direct_ref_overlap.py --min-usage 3`
  (~136 candidates), the `个`/`亼` family-wide decision (now also blocking
  `検`), the `刂`/`primitive_roof` dead-token cleanup, `慶`'s bottom shape,
  `壷`'s top element, the 81 orphaned `rad{N}` rows on the live DB.

### 2026-09-05 (continued) — the `亻` presence check, run against 8 more radical families

- Continuing the sequential rtk1000-3000 sweep: ran the same
  `cjkvi-ids`-presence check that found the 86-kanji `亻` family against
  every other common radical (`水`/`扌`/`阝`/`艹`/`忄`/`犭`/`礻`/`衣`,
  `糸`/`貝`/`金`/`馬`/`魚`/`鳥`/`食`/`示`). Most came back clean or
  near-clean — the `亻` family was the outlier, not the norm.
- **First version of the check was too shallow and produced two false
  positives that would have been real regressions** — worth recording
  since it changes how to run this check safely going forward: `擁`
  (rtk1488, `玄,推`) and the `祐`/`祷`/`祇`/`祢`/`禄`/`禎`/`郭`/`郡`/…
  ~16-kanji `礻`/`阝` "hits" all *do* carry the radical, just one level of
  indirection down through a referenced compound (`推`=`扌,隹`,
  `礼`=`礻,乙`, `邦`=`丰,阝`) that a shallow "does `parts_detail`'s
  top-level list contain the radical id" check doesn't see, since
  `parts_detail` only exposes the directly-listed parts, not their own
  recursive expansion. Caught by resolving `擁`'s *pre-edit* value with
  `get_kanji_detail` before committing to the "fix" — it already resolved
  to `{rtk1484, rtk716}`, both of which carry the needed radical
  transitively. Reverted that edit; left the `礻`/`阝` indirect-reference
  cases alone entirely (not bugs). Lesson for next time: verify the *old*
  value's resolution before editing, not just the presence-check's
  top-level output.
- Six real bugs survived that check, confirmed by verifying the *old*
  value's resolution genuinely lacked the radical (not just at the top
  level):
  - `汁`(rtk150, "soup") was `十` alone — missing `水` entirely.
  - `耶`(rtk2720) was `耳,邦` — `邦`("home country") is a semantically
    bogus whole-kanji stand-in for what's really just a bare `阝` on
    ​耶's right side (it happened to carry `阝` transitively, so this
    wasn't a search-index miss, but it's still a nonsense mnemonic
    reference) — replaced with the direct `耳,阝`.
  - `薗`(rtk2980) was `衣,口,土,囗,艾` — flattening `園`(rtk629)'s own
    parts instead of referencing it directly; → `艾,園`.
  - `狒`(rtk2434, "baboon") was `｜,ノ,弓` — missing `犭` entirely, plus a
    botched decomposition of `弗`; → `犭,弓,ノ,｜`.
  - `祓`(rtk2994, "exorcise") was `ノ,一,礼,丶` — a byte-level flatten of
    `礼`(rtk1168)'s own strokes rather than a real reference (and
    render-confirmed the right side is shaped like `犬`, not `礼`); →
    `礻,犬`.
  - `初`(rtk431, "first time") was `刀` alone — missing `衣` (radical
    #145, the clothing radical `衤`, already taught as `rtk423`/"garment"
    since it's RTK's own primitive for it) entirely. This one **silently
    propagated through 15 downstream kanji** that correctly *reference*
    `初` (`裕`/`褐`/`複`/`被`/`裾`/`襟`/`袖`/`裸`/`補`/`衿`/`袷`/`袴`/
    `襖`/`裡`, plus `初` itself) — none of those needed their own edit,
    confirmed by re-checking `裕`(rtk856) after the `初` fix alone.
- Verified: full rebuild; `test_regression_fixes.py` — 6 new pins with the
  false-positive-vs-real-bug distinction noted inline — **1035 checks**,
  same 4 expected hanzi-scope non-issues; pytest (56 passed);
  `audit_self_reference.py` clean.
- Not deployed to the live server (no SSH/server access) — data-only
  change, needs `sync_system_data.py` + reseed.
- Coverage: **1630/3000 (54.3%)**.
- **Next session**: continue the sequential rtk1000-3000 sweep — this
  session covered rtk1000-1043 in detail (person family) plus a handful of
  cross-cutting radical-family checks, but the bulk of rtk1043-3000 still
  hasn't had an individual per-kanji look. `audit_direct_ref_overlap.py
  --min-usage 3`'s ~136 candidates remain the highest-leverage next
  target. Standing list otherwise unchanged: the `个`/`亼` family
  decision, `刂`/`primitive_roof` cleanup, `慶`'s bottom shape, `壷`'s top
  element, the 81 orphaned `rad{N}` rows on the live DB.

### 2026-09-05 (continued) — sequential rtk1043-1350 review: `primitive_roof` cleanup, 換/杯/署 fixed, `罒` (net radical) family found (12 kanji)

- Owner: "continue next sessions, until out of credits" — kept going on
  the strict sequential rtk1000-3000 sweep from rtk1043 (where the person-
  radical session left off), rendering/cross-checking each kanji against
  `cjkvi-ids` + CSV before moving to the next.
- **`primitive_roof` global cleanup**: a prior session's noted-but-
  deferred item. Confirmed the actual mechanism first (it's not quite what
  was assumed): `kangxi40:宀:roof,primitive_roof` — it's a real *alias* of
  `宀`, so `resolve_alias("primitive_roof")` does resolve, it just always
  duplicated an already-separately-listed literal `宀` in the same parts
  field (54 occurrences, 100% paired with `宀`). Stripped the dead
  duplicate token from all 54 lines (a field-aware strip, not a blind
  string replace, so it doesn't corrupt alternate-decomposition `;`
  groups). No resolved-id changes anywhere, confirmed by a clean
  before/after `test_regression_fixes.py` diff.
- **rtk1073 褒** ("praise") was `衣,口,小,亠` — flattening
  `保`(rtk1072)'s own `呆` sub-parts with a wrong `小` where `呆` actually
  has `木`; CSV explicitly names "protect" as a component. → `亠,保,衣`.
- **rtk1122 換** ("interchange") was `扌,𠂊,央` — render-confirmed this is
  simply wrong: `換`'s right side is the *same* `奐` shape as its own
  sibling `喚`(rtk1121, `⿰口奐` vs `換`'s `⿰扌奐`), not remotely
  `央`(rtk1877, "center")-shaped. The **pre-existing regression pin baked
  the bug in** (pinned to the wrong-but-internally-consistent value) — a
  reminder that a pin only proves stability, not correctness. Fixed to
  match `喚`'s own treatment of `奐` (`四,大,冂,勹`), pin corrected.
- **rtk1304 杯** ("cupfuls") was `｜,ノ,一,木,礼` — render-confirmed the
  right side is `不`(rtk1302)-shaped, nothing like `礼`(rtk1168, "altar" +
  "fishhook") which was just a stray wrong reference. → `木,不`.
- **rtk1349 署** ("signature") was `日,老` — an exact copy-paste of its
  neighbor `暑`(rtk1350)'s own value. IDS (`⿱罒者`) and render both confirm
  the top is `罒` (net/eye radical), not `日` (day) — a different
  primitive that only superficially resembles it in a small font. →
  `罒,者`.
- Fixing 署 raised the obvious question of whether `罒` had the same
  dataset-wide omission problem `亻` did. It did: the same recursive-aware
  presence check (verifying actual *resolved* part ids via
  `get_kanji_detail`, not just literal token text — the lesson from
  yesterday's `擁`/`礻`-family false positives) found **12 more kanji**
  missing `罒` entirely: `買`(was just `貝`), `置`, `罰`(was just `言`),
  `徳`, `羅`, `爵`, `憲`, `罪`(was just `非`), `罵`, `罷`, `曼`, `罫`. Every
  one confirmed against `cjkvi-ids`; the clearer ones (買/置/罰/羅/爵/罪/
  罵/罷/罫) also render-confirmed — `罒`'s flatter, four-stroke shape is
  visually distinct from the similar-looking `四`("four") it could easily
  be confused with, which is exactly the kind of mixup this bug pattern
  produces. Fixed by prepending `罒` to each existing decomposition.
- Verified: full rebuild; `test_regression_fixes.py` — new
  `check_net_radical_present` structural invariant (12 hosts, same
  pattern as `check_person_radical_present`), 3 new individual pins
  (褒/杯/署), 1 stale pin corrected (`羅`, which needed `kangxi122` added)
  — **1050 checks**, same 4 expected hanzi-scope non-issues; pytest (56
  passed); `audit_self_reference.py` clean.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1631/3000 (54.4%)**.
- **Next session**: continue the sequential sweep from rtk1351. The
  `罒`-family discovery suggests it's worth running the same recursive-
  aware presence check against a few more common radicals not yet swept
  this way (e.g. `冖`, `匚`, `已`/`巳`-adjacent shapes) rather than waiting
  to stumble into them one kanji at a time. Standing list otherwise
  unchanged: `audit_direct_ref_overlap.py --min-usage 3` (~136
  candidates), the `个`/`亼` family decision, `慶`'s bottom shape, `壷`'s
  top element, the 81 orphaned `rad{N}` rows on the live DB.

### 2026-09-05 (continued) — sequential rtk1351-1840 review: 俸/棒/喉 fixed, everything else already clean

- Continued the sequential sweep (owner: "continue next sessions, until
  out of credits"). rtk1351-1770 covered this pass, each kanji checked
  against `cjkvi-ids` + CSV.
- The `糸`(thread, rtk1431-1477) and `阝`(mound-radical, rtk1390-1412)
  families — both already fixed in earlier sessions per the audit doc's
  own history — held up: every host in both ranges correctly carries its
  radical. Good confirmation those fixes were durable, not a regression
  risk from today's other radical-family work.
- **rtk1696 俸** ("stipend") and **rtk1697 棒** ("rod") were both
  literal-stroke flattens (`｜,一,人,大,二` / `｜,一,人,木,二,大`) instead
  of referencing `奉`(rtk1695, "observance"), which is already taught and
  sitting right next to them in frame order — fixed to `亻,奉` / `木,奉`.
  Checked the rest of `奉`'s Joyo-kanji family via `cjkvi-ids` (`唪 埲 捧
  淎` etc.) — none of the others are in RTK's frame set, so no further
  fixes needed.
- **rtk1768 喉** ("throat") was `口,矢` — a partial flatten that kept only
  one of `侯`(rtk1767, "marquis")'s two parts and silently dropped `ユ`
  (katakana-yu) entirely, even though `侯` itself is already taught two
  frames earlier. Fixed to `口,侯`.
- Everything else in this range checked out, including some that looked
  suspicious at first glance and turned out fine on closer inspection:
  the `疔` token peppered through the `疒`(sickness radical) family
  (rtk1813-1826) looked like a dead/unresolvable placeholder (no visible
  keyword when dumped) but is actually a real listed alias of `疒`
  (`kangxi104:疒:sickness radical,疔`) and resolves correctly — confirmed
  via `get_kanji_detail`, not just eyeballing the dump.
- Verified: full rebuild; `test_regression_fixes.py` — 3 new pins
  (俸/棒/喉) — **1053 checks**, same 4 expected hanzi-scope non-issues;
  pytest (56 passed); `audit_self_reference.py` clean.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1632/3000 (54.4%)**.
- **Next session**: continue the sequential sweep from rtk1841. Standing
  list unchanged: `audit_direct_ref_overlap.py --min-usage 3` (~136
  candidates), the `个`/`亼` family decision, `慶`'s bottom shape, `壷`'s
  top element, the 81 orphaned `rad{N}` rows on the live DB.

### 2026-09-05 (continued) — sequential rtk1841-1980: `audit_radicals.py`'s last 2 undefined terms closed, 0 dataset-wide

- Continued the sequential sweep (rtk1841-1980 checked this pass; all
  clean except the two below). Along the way, spotted the last two
  survivors of a check this project has been chipping away at since
  "Finding 1" of the original search-quality audit: `audit_radicals.py`'s
  undefined-part-term scan, which had been sitting at "2 distinct
  undefined part terms" for several sessions without anyone tracking them
  down individually.
  - **`亦`** (found via rtk1883 `跡`, "tracks") has no defining row
    anywhere in `data.txt` — it was silently dropped on import, so `跡`
    was quietly missing one of its three listed parts. Its siblings
    (`変`/`蛮`/`恋`/`湾`, all sharing the same `亦`-shaped primitive per
    `cjkvi-ids`) all already use `亠` for it instead — aligned `跡` to
    match, closing the gap consistently rather than inventing a new
    primitive name.
  - **`"ninety"`** (found via `rtk212` `枠`, "frame") turned out to be a
    different bug shape entirely: `rtk212` had **no `data.txt` override at
    all**, so `import_data()` fell through to `heisig-kanjis.csv`'s raw
    `components` text verbatim — `"tree; wood; ninety; nine; baseball;
    ten; needle"` — and "ninety" isn't a real primitive name anywhere,
    just the CSV's own gloss for `卆`'s `九`+`十` combination. The existing
    decomposition was also carrying a legacy orphaned `rad4.16` row
    (placeholder `?` glyph, aliased "tree, wood" — a pure duplicate of
    `rtk207`/木). Render-confirmed `枠` = `木` + `卆`(=`九`,`十`); added a
    proper override: `木,九,十`.
  - Both closed the same afternoon `audit_radicals.py` was re-run to
    confirm: **0 distinct undefined part terms, 0 occurrences, across the
    entire rtk* dataset** — every part_term used anywhere now resolves to
    a real kanji/alias. This is a genuine milestone for the project's
    oldest open finding, not just incremental progress.
- Verified: full rebuild; `test_regression_fixes.py` — 2 new pins
  (`跡`/`枠`) — **1054 checks**, same 4 expected hanzi-scope non-issues;
  pytest (56 passed); `audit_self_reference.py` clean;
  `audit_radicals.py` confirmed 0/0.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1633/3000 (54.4%)**.
- **Next session**: continue the sequential sweep from rtk1981. Standing
  list unchanged: `audit_direct_ref_overlap.py --min-usage 3` (~136
  candidates), the `个`/`亼` family decision, `慶`'s bottom shape, `壷`'s
  top element, the 81 orphaned `rad{N}` rows on the live DB (now a
  slightly higher-value target, since `rad4.16` turning up inside `枠`'s
  decomposition today is a concrete example of what those orphaned rows
  are quietly doing to search quality).

### 2026-09-05 (continued) — sequential rtk1981-2270 review: a fourth detector blind spot — 人 vs 亻 (9 kanji)

- Continued the sequential sweep (rtk1981-2270 checked). Cleaned one more
  `primitive_lid` dead-duplicate token in passing (`rtk2014`/航, same
  mechanism as `primitive_roof`, just a single occurrence this time — no
  resolved-id change).
- Spot-checked `rtk2087`/鎖 (`貝,金,尚` looked like it might have the wrong
  top component) by rendering it next to `賞`(rtk859), which shares the
  exact same "small-top over 貝" visual shape and is already correctly
  `尚,貝` — confirms `鎖`'s existing `尚` was right all along. Worth noting
  as a near-miss: briefly changed it to `小` based on a first-glance render
  comparison, caught the mistake by rendering a same-shaped sibling
  side-by-side before committing, reverted. The lesson from `擁`
  yesterday generalizes here too — verify against the *resolved* state or
  a same-shaped sibling, not a first impression.
- Found a **fourth systematic detector blind spot** while checking
  `rtk2245`/侠 and `rtk2259`/倅: both had a bare `人`("person", `rtk1023`)
  where `cjkvi-ids` calls for the compressed left-radical `亻`
  (`kangxi9`) — render-confirmed both clearly show `亻`'s shape, not
  standalone `人`. This is a different failure mode than yesterday's
  86-kanji `亻`-omission family: these hosts weren't *missing* a
  person-concept token, they had the *wrong one* — `人` resolves fine on
  its own (it's a real, correct kanji id), so no search miss, but it's a
  different DB row than `亻`, meaning `check_person_radical_present`'s
  "does any part resolve to `kangxi9`" test structurally can't catch this
  class. A dedicated scan (cjkvi-ids has `亻` as a leaf, `data.txt` uses
  literal `人` instead of `亻`) found **9 total** dataset-wide: `侠`,
  `倅`, `伝`, `依`, `個`, `傷`, `似`, `倹`, `做`. `倹` additionally had a
  wrong non-person reference (`合`/"fit" instead of the real `僉` shape
  shared with `剣`/`険` — render-confirmed side by side) — fixed to match
  the family.
- Verified: full rebuild; `test_regression_fixes.py` — 8 new pins (`侠`
  through `做`), 1 stale pin corrected (`倹`, which had been keyed to the
  wrong `合` reference) — **1062 checks**, same 4 expected hanzi-scope
  non-issues; pytest (56 passed); `audit_self_reference.py` clean;
  confirmed 0 remaining `人`-vs-`亻` mismatches dataset-wide.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1633/3000 (54.4%)** (unchanged — the fixed lines this
  session were mostly already touched by earlier sessions for other
  reasons, same undercounting effect noted in the person-radical batch).
- **Next session**: continue the sequential sweep from rtk2271. The
  `人`-vs-`亻` pattern is now a documented fourth blind spot worth
  remembering when reviewing any left-radical `亻` host by hand (the
  existing detectors can't find it). Standing list otherwise unchanged:
  `audit_direct_ref_overlap.py --min-usage 3` (~136 candidates), the
  `个`/`亼` family decision, `慶`'s bottom shape, `壷`'s top element, the
  81 orphaned `rad{N}` rows on the live DB.

### 2026-09-05 (continued) — sequential rtk2271-2410 review: one more flatten-instead-of-reference fix

- Continued the sequential sweep (rtk2271-2410 checked this pass).
  Double-checked `rtk2276`/仄 (`人,厂`, bare `人` inside a cliff) against
  the newly-documented `人`-vs-`亻` blind spot before moving on — rendered
  it and confirmed the `人` there really is the standalone shape (unlike
  `侠`/`倅`'s compressed `亻`), so no fix needed; a useful confirmation
  that the blind spot is specifically about *compressed left-radical*
  position, not bare `人` everywhere.
- **rtk2283 咳** ("cough") was `口,人,亠,ノ,丶` — an exact literal flatten
  of `亥`(rtk1637, "sign of the hog")'s own parts instead of referencing
  it directly, even though `亥` is already taught six frames earlier and
  render-confirms the right side matches it closely. Fixed to `口,亥`.
- Everything else in this range (the `扌`/finger and `氵`/water radical
  families, `广`/cave, `尸`/corpse, `女`/woman, `子`/child, `宀`/roof) was
  clean and consistently referencing already-taught compounds — no
  further bugs found this pass.
- Verified: full rebuild; `test_regression_fixes.py` — 1 new pin (`咳`)
  — **1063 checks**, same 4 expected hanzi-scope non-issues; pytest (56
  passed); `audit_self_reference.py` clean.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1634/3000 (54.5%)**.
- **Next session**: continue the sequential sweep from rtk2411.

### 2026-09-05 (continued) — sequential rtk2411-2550: the whole `犭` (wild-dog) radical family missing (9 kanji)

- Continued the sequential sweep (rtk2411-2550 checked this pass).
  Found **one unbroken run in frame order**, `rtk2424`-`rtk2432` (`猾 猥
  狡 狸 狼 狽 狗 狐 狛`), all missing `犭`("pack of wild dogs", `kangxi94`)
  entirely — same systemic-omission shape as the `亻` and `罒` families
  found earlier this weekend, this time affecting every single kanji in
  one contiguous frame block. A couple were badly wrong, not just
  missing the radical: `猾` was `月,骨,冂,冖` (right shape, but the wrong
  left radical entirely) and `狡` was `父,亠` (completely unrelated to
  its real `⿰犭交` structure). Render-confirmed all 9 before fixing;
  collapsed each to `犭,<compound>` since every RHS was already a taught
  kanji (`骨`/`畏`/`交`/`里`/`良`/`貝`/`句`/`瓜`/`白`).
- Separately, `rtk2505`/隈 (`衣,田,阝`) turned out to be the exact same
  flatten-instead-of-reference bug already fixed for `猥`(rtk2425) in
  this same pass — both were mangling `畏`(rtk2069)'s own parts (and
  dropping its `一`) instead of referencing it directly. Fixed to
  `阝,畏`.
- Verified: full rebuild; `test_regression_fixes.py` — new
  `check_wild_dog_radical_present` structural invariant (9 hosts, same
  pattern as person/net), 1 new individual pin (`隈`) — **1073 checks**,
  same 4 expected hanzi-scope non-issues; pytest (56 passed);
  `audit_self_reference.py` clean; confirmed 0 remaining `犭`-omissions
  dataset-wide via the recursive-aware presence check.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1634/3000 (54.5%)** (unchanged — same undercounting effect
  as prior radical-family batches).
- **Next session**: continue the sequential sweep from rtk2551. Given
  `亻`/`罒`/`犭` have all turned out to have systemic omission bugs,
  worth running the same recursive-aware presence check proactively
  against the remaining common radicals not yet swept this exact way
  (`忄`, `礻`, `扌`, `阝` were checked with the first-pass shallow script
  earlier and came back clean, but the shallow script was wrong for `犭`
  specifically until this session's recursive-aware version, so those
  results deserve a second look). Standing list otherwise unchanged:
  `audit_direct_ref_overlap.py --min-usage 3` (~136 candidates), the
  `个`/`亼` family decision, `慶`'s bottom shape, `壷`'s top element, the
  81 orphaned `rad{N}` rows on the live DB.

### 2026-09-05 (continued) — sequential rtk2551-2690: a leftover scratch-draft line silently corrupting `砥`

- Continued the sequential sweep (rtk2551-2690 checked). Found
  `rtk2553`/榊 (`｜,日,木,礼,田`) referencing `礼`(rtk1168, "salutation")
  where `⿰木神` calls for `神`(rtk1200, already taught) — fixed to
  `木,神`.
- Then found something structurally different: `rtk2636`/砥
  ("grindstone") showed `bamboo,in front` as its parts when dumped,
  which turned out to be literal English text, not resolved primitive
  names — a strong signal something was wrong with the *line itself*,
  not just its content. Traced it to a **leftover scratch-draft block**
  near the very top of `data.txt` (`rtk3`/`rtk4`/`rtk8`/`rtk16`/`rtk17`/
  `rtk18`/`rtk19`/`rtk20`/`rtk21`/`rtk91`/`rtk2636`, all using `?` as a
  placeholder character, predating the real kanjidic2/CSV import
  pipeline) — an id collision where this pre-import test line happened
  to reuse the real `rtk2636` id and silently override its parts with
  completely unrelated garbage (`竹`/bamboo, `前`/rtk309, nothing to do
  with a grindstone). The character/keyword still came through correctly
  from the CSV in the live DB (the override's own character field being
  `?` doesn't suppress those), which is exactly why this hid so well —
  `rtk2636`'s glyph and keyword both looked completely normal; only its
  parts were silently wrong.
  - Checked the other 9 lines in the same scratch block the same way
    (resolve each, compare against CSV/IDS) rather than assuming they're
    all broken just because they share the same `?`-placeholder pattern:
    all 9 turned out to be **coincidentally correct** — their parts
    overrides happen to match the real primitive breakdown (`rtk3`/三 =
    `一,二`; `rtk18`/冒 = `日,目`; etc.) even though the lines themselves
    are leftover drafts. Left them as-is (functionally fine, just
    stylistically confusing for a future maintainer) rather than
    "fixing" something that isn't broken.
  - Fixed `rtk2636` to `石,氏` (render/IDS-confirmed `⿰石氐`; `氐` isn't
    independently taught, so used `氏` per the established stand-in
    convention already used for `低`/`抵`/`底`).
- Verified: full rebuild; `test_regression_fixes.py` — 2 new pins
  (`榊`/`砥`) — **1075 checks**, same 4 expected hanzi-scope non-issues;
  pytest (56 passed); `audit_self_reference.py` clean.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1636/3000 (54.5%)**.
- **Next session**: continue the sequential sweep from rtk2691. Worth
  keeping an eye out for more id collisions between that scratch-draft
  block (frames 3/4/8/16/17/18/19/20/21/91, all still present) and any
  future `data.txt` edits — a collision silently wins by file order, not
  by which line is "real," so a future line reusing one of those 10
  frame numbers would silently corrupt it the same way `rtk2636` was.
  Standing list otherwise unchanged: `audit_direct_ref_overlap.py
  --min-usage 3` (~136 candidates), the `个`/`亼` family decision,
  `慶`'s bottom shape, `壷`'s top element, the 81 orphaned `rad{N}` rows
  on the live DB.

### 2026-09-05 (continued) — sequential rtk2691-3000: clean, completing the first full rtk1000-3000 pass

- Finished the sequential sweep through the end of the range: rtk2691-
  2830, rtk2831-2900, and rtk2901-3000 all checked individually against
  `cjkvi-ids` + CSV, render-verifying anything ambiguous (e.g. `rtk2962`
  薩's `艾,阝,産` looked like it might be missing a real `隡` reference,
  but render-confirmed `産`'s shape genuinely sits inside `薩`'s
  structure — not a bug). No further fixes found in this stretch.
- This completes the **first full sequential pass through rtk1000-3000**
  (the owner's original "check all kanji, don't wait for me to find
  errors" mandate from earlier in the session) — every one of the 2001
  kanji in that range has now been individually looked at, not just
  flagged by an automated detector. Total yield from the whole pass:
  roughly 130+ individual fixes across ~15 separate bug classes,
  including four newly-documented systemic detector blind spots (person-
  radical omission, net-radical omission, wild-dog-radical omission, and
  `人`-vs-`亻` wrong-reference) each affecting a double-digit number of
  kanji, plus a from-scratch closure of the project's oldest open
  finding (`audit_radicals.py`'s undefined-part-term scan, now 0/0
  dataset-wide) and a leftover scratch-draft-line data corruption bug.
- Verified: full rebuild; `test_regression_fixes.py` unchanged since the
  last commit (no new fixes this batch) — still **1075 checks**, same 4
  expected hanzi-scope non-issues; pytest (56 passed).
- Not deployed (no SSH/server access) — nothing new to deploy from this
  specific batch.
- Coverage: **1636/3000 (54.5%)** — coverage still lags the "individually
  reviewed" total substantially, since the metric only counts lines
  touched by a commit *after* the audit began, and this pass's largest
  yield (clean ranges + the radical-family fixes) mostly landed on lines
  a much earlier, unrelated commit had already touched.
- **Next session**: rtk1000-3000 has now had one full pass; the highest-
  leverage next step is almost certainly a **second pass** applying the
  now-proven recursive-aware radical-presence check to more common
  radicals across the *whole* dataset (not just this range) —
  `亻`/`罒`/`犭` all turned out to have systemic omissions once actually
  checked, so `扌`/`阝`/`礻`/`忄`/`貝`/`金` deserve the same treatment
  rather than trusting the shallow first-pass check some of them got
  earlier. Standing list otherwise unchanged: `audit_direct_ref_overlap.py
  --min-usage 3` (~136 candidates), the `个`/`亼` family decision,
  `慶`'s bottom shape, `壷`'s top element, the 81 orphaned `rad{N}` rows
  on the live DB.

### 2026-09-05 (continued) — proactive second-pass radical-presence scan: ~20 more common radicals checked, all clean

- With the sequential rtk1000-3000 pass complete, started the flagged
  "second pass" — running the recursive-aware radical-presence check
  (the one that found the `亻`/`罒`/`犭` families) proactively against
  ~20 more common radicals dataset-wide, rather than waiting to stumble
  into another one kanji at a time: `扌`(hand), `貝`(shellfish), `金`
  (gold), `阝`(mound-left, re-checked with the corrected script), `馬`
  (horse), `見`(see), `車`(car), `頁`(page), `雨`(rain), `禾`(grain),
  `虫`(insect), `魚`(fish), `鳥`(bird), `示`(altar/show), `酉`(sake),
  `隹`(short-tailed bird), `豆`(beans), `皿`(dish), `骨`(bone), `方`
  (direction), `皮`(pelt), `臣`(retainer), `矢`(dart), `辛`(spicy),
  `殳`(weapon), `攵`(rap/taskmaster).
- **All clean** — every apparent "hit" was either the atomic primitive
  matching itself (a self-reference false positive baked into how the
  check works: an atomic kanji's own IDS entry is just itself as a
  single-character leaf) or an already-confirmed transitive case
  (`鎮`/`候` referencing a compound that itself carries the radical).
  No new bugs found. This is a reassuring result after finding three
  systemic families in a row earlier this session — it confirms those
  three (`亻`/`罒`/`犭`) were a real, bounded problem from `import_rtk.py`'s
  original KRADFILE pass, not a sign that *every* common radical has
  silent gaps throughout the dataset.
- Not deployed — no data changes this pass (a scan turning up clean is
  still useful signal, recorded here rather than silently discarded).
- Coverage: unchanged (no `data.txt` edits this pass).
- **Next session**: the highest-leverage remaining items are the
  standing ones that were already hard before this session:
  `audit_direct_ref_overlap.py --min-usage 3` (~136 candidates, a
  different bug shape than the radical-omission families — worth
  working through directly rather than via more radical scans), the
  `个`/`亼` family decision (blocks `検`'s disputed-review resolution),
  `慶`'s bottom shape, `壷`'s top element, the 81 orphaned `rad{N}` rows
  on the live DB (needs production access to enumerate/audit).

### 2026-09-05 (continued) — `audit_direct_ref_overlap.py --min-usage 3`: 136 → 104 candidates, 33 kanji fixed

- Started working through the standing `audit_direct_ref_overlap.py
  --min-usage 3` worklist directly (the redundant-overlap-alongside-a-
  direct-reference bug shape from the `石`/`糸`/`頁`/`魚` families found
  in earlier sessions) rather than another radical scan, since it's the
  next-highest-leverage standing item.
- Cleared 6 primitive families in this pass, all confirmed by checking
  each referenced compound's own resolved parts before collapsing:
  - `骨`(rtk1383, 4 hosts): `滑`/`髄`/`骸` were each re-listing `骨`'s own
    `月,冖,冂` alongside referencing it directly.
  - `歯`(rtk1255, 4 hosts): `齢`/`噛`/`齟`/`齬` were each re-listing
    `歯`'s own `止,米,凵`; `齟`/`齬` also needed their *other* component
    fixed to reference `且`(rtk2190)/`吾`(rtk17) directly instead of
    flattening.
  - `風`(rtk563, 3 hosts): `繭`/`楓`/`颯` were each re-listing `風`'s own
    `几,虫,ノ` (or a subset).
  - `免`(rtk2126, 4 hosts): `逸`/`晩`/`勉`/`挽` were each re-listing
    `免`'s own `儿,勹`.
  - `尤`(rtk2232, 3 hosts): `就`/`厖` were re-listing `尤`'s own `丶,尢`;
    `鷲` was a badly mangled flatten (`口,小,鳥,丶,亠,尤,杰,尢`) that
    turned out to need a *different* fix entirely — `cjkvi-ids` shows
    `⿱就鳥`, so it should reference `就`(rtk2121, itself just cleaned up
    two lines above) directly, not flatten `尤` a second level down.
  - `亀`(rtk573, 3 hosts): `縄`/`竃`/`蝿` were each re-listing `亀`'s own
    `乙,勹` — kept the extra `田` each host also carries, since that's
    a real shared "电"-shape component `cjkvi-ids` confirms
    (`⿻日电`), not redundant with `亀` itself.
  - `高`(rtk329, 4 hosts, found continuing the sweep after the first 6):
    `稿`/`嵩`/`縞`/`膏` were each re-listing `高`'s own `口,亠,冂`.
  - Also `専`(`博`), `無`(`舞`/`撫`/`蕪`), `内`(`肉`), `斉`(`剤`/`済`),
    `黒`(`黙`/`黛`), `缶`(`鬱`) — one or two hosts each, same pattern.
- Verified: full rebuild; `test_regression_fixes.py` — 9 stale pins
  corrected (the redundant-value pins these hosts had before), 24 new
  pins added — **1099 checks**, same 4 expected hanzi-scope non-issues;
  pytest (56 passed); `audit_self_reference.py` clean;
  `audit_direct_ref_overlap.py --min-usage 3` re-run to confirm
  convergence: **104 candidates remaining, down from 136**.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1654/3000 (55.1%)**.
- **Next session**: continue working through
  `audit_direct_ref_overlap.py --min-usage 3`'s remaining ~104
  candidates directly — this session's pass showed it converges cleanly
  and steadily (136 → 104 in one sitting) without needing render
  verification for most cases, since the check itself already proves
  the redundancy structurally (the compound's own resolved parts are a
  strict subset of the host's). Standing list otherwise unchanged: the
  `个`/`亼` family decision, `慶`'s bottom shape, `壷`'s top element, the
  81 orphaned `rad{N}` rows on the live DB.

### 2026-09-05 (continued) — `audit_direct_ref_overlap.py --min-usage 2`: 104 → 79 candidates, 28 more kanji fixed

- Kept working through the worklist at `--min-usage 2` (down from `3`,
  since `3` converged): six more families, 28 kanji.
  - `井`(rtk1946, 5 hosts): `寒`/`異`/`暴`/`爆`/`丼`/`耕` were each
    re-listing `井`'s own `｜,ノ,一,二`.
  - `支`(rtk768, 6 hosts): `技`/`枝`/`肢`/`岐`/`妓`/`艘` were each
    re-listing `支`'s own `十,又`.
  - `鬼`(rtk2175, 6 hosts): `醜`/`塊`/`蒐`/`魁` were each re-listing
    `鬼`'s own `田,儿,匕,厶`; `魂` and `魔` needed their *other*
    component fixed too — `魂` was flattening a redundant `二` where
    `cjkvi-ids` (`⿰云鬼`) calls for referencing `云`(rtk2241) directly,
    and `魔` was flattening `麻`(rtk637)'s own parts instead of
    referencing it.
  - `玄`(rtk1484, 5 hosts): `畜`/`弦`/`率`/`舷`/`眩` were each
    re-listing `玄`'s own `亠,幺`.
  - `冊`(rtk1967, 5 hosts): `論`/`倫`/`輪`/`綸` correctly reference the
    compound `侖`(亼+冊, via `个`+`冊`) but redundantly re-listed `冊`'s
    own `｜,一,亅,廾`; `柵` and `珊` don't have `侖` in their real
    structure at all (`cjkvi-ids`: `⿰木冊`/`⿰王冊`) — they'd been
    carrying the same `亼`-shape parts as their `侖`-family neighbors
    by copy-paste, not by actual structure. Fixed to reference bare
    `冊` only.
- Verified: full rebuild; `test_regression_fixes.py` — 2 stale pins
  corrected, 26 new pins — **1127 checks**, same 4 expected hanzi-scope
  non-issues; pytest (56 passed); `audit_self_reference.py` clean;
  `audit_direct_ref_overlap.py --min-usage 2` confirms convergence: **79
  candidates remaining, down from 104**.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1679/3000 (56.0%)**.
- **Next session**: continue `audit_direct_ref_overlap.py --min-usage
  2`'s remaining ~79 candidates — the pattern of "correctly references
  a compound but redundantly re-lists that compound's own parts, and
  sometimes the *other* component turns out to need a fix too" has held
  up consistently across five sessions' worth of families now, so it's
  worth continuing to work through methodically rather than switching
  strategies. Standing list otherwise unchanged: the `个`/`亼` family
  decision, `慶`'s bottom shape, `壷`'s top element, the 81 orphaned
  `rad{N}` rows on the live DB.

### 2026-09-05 (continued) — `audit_direct_ref_overlap.py --min-usage 2`: 79 → 61 candidates, 21 more kanji fixed

- Cleared 3 more high-usage families: `矢`(rtk1305, "dart" — 20x usage,
  the largest single family found in this worklist): `鉄`/`迭`/`勧`/
  `矯` were each re-listing `矢`'s own `ノ` alongside referencing it
  directly. `勿`(rtk1128, "not" — also 20x usage, shared with `矢`'s
  usage count by coincidence): `傷`/`物`/`易`/`瘍`/`吻`/`忽` were each
  re-listing `勿`'s own `ノ,勹`. `辛`(rtk1612, "spicy" — 9x): `辞`/`梓`/
  `宰`/`避`/`幸`/`摯`/`蟄`/`睾` were each re-listing `辛`'s own `十,立`.
- Verified: full rebuild; `test_regression_fixes.py` — 1 stale pin
  corrected (`傷`), 17 new pins — **1144 checks**, same 4 expected
  hanzi-scope non-issues; pytest (56 passed); `audit_self_reference.py`
  clean; `audit_direct_ref_overlap.py --min-usage 2` confirms
  convergence: **61 candidates remaining, down from 79**.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1690/3000 (56.3%)**.
- **Next session**: continue `audit_direct_ref_overlap.py --min-usage
  2`'s remaining ~61 candidates — the largest families (`矢`/`勿`/`辛`)
  are now cleared, so remaining candidates are smaller usage counts
  (mostly 2-6x) with lower per-family yield but the same fix pattern.
  Standing list otherwise unchanged: the `个`/`亼` family decision,
  `慶`'s bottom shape, `壷`'s top element, the 81 orphaned `rad{N}` rows
  on the live DB.

### 2026-09-05 (continued) — `audit_direct_ref_overlap.py --min-usage 2`: 61 → ~40 candidates, 20 more kanji fixed

- Cleared 5 more families: `示`(rtk1167, 17x — `余` was re-listing
  `示`'s own `二,小`), `麻`(rtk637, 6x — `暦`/`歴`/`摩` re-listing `木,广`),
  `元`(rtk63, 6x — `頑`/`玩`/`冠`/`莞`/`翫` re-listing `二,儿`), `谷`
  (rtk851, 6x — `浴`/`欲`/`裕` re-listing `口,ハ,个`), `乃`(rtk741, 5x —
  `携`/`秀`/`透`/`孕` re-listing `｜,ノ,一`).
- Verified: full rebuild; `test_regression_fixes.py` — 2 stale pins
  corrected (`翫`, `頑`), 14 new pins — **1158 checks**, same 4 expected
  hanzi-scope non-issues; pytest (56 passed); `audit_self_reference.py`
  clean; `audit_direct_ref_overlap.py --min-usage 2` confirms
  convergence: **45 candidates remaining, down from 61**.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1702/3000 (56.7%)**.
- **Next session**: continue `audit_direct_ref_overlap.py --min-usage
  2`'s remaining ~45 candidates (mostly 2x-usage families now — lower
  yield per family but the same reliable pattern).
  Standing list otherwise unchanged: the `个`/`亼` family decision,
  `慶`'s bottom shape, `壷`'s top element, the 81 orphaned `rad{N}` rows
  on the live DB.

### 2026-09-06 — 2 disputed reviews (薬/鰯), then mining `results.jsonl`'s remaining DISJOINT flags directly

- Owner had 2 more disputed reviews queued: `薬`(rtk1873, "medicine") was
  `日,木,冫,艾` — render-confirmed the middle/bottom is actually
  `楽`(rtk1872)'s own shape (`白,木,冫`), not a bare `日`; fixed to
  `艾,楽`. `鰯`(rtk2828, "sardine") was `弓,魚,冫` — a literal flatten of
  `弱`(rtk1323)'s own parts instead of referencing it directly; fixed to
  `魚,弱`.
- Owner then flagged that `過`("overdo")'s parts (`口,込,冂`) don't work
  as a mnemonic even though they're structurally accurate — `口`+`冂`
  turned out to be a flattened `咼`("jawbone"), a real, coherent Heisig
  primitive that the original `import_rtk.py` KRADFILE pass had silently
  shattered into two disconnected-looking radical fragments,
  independently, in all four kanji built on it (`禍`/`渦`/`鍋`/`過`).
  Confirmed directly from `results.jsonl`'s AI Overview text for `過`
  (Heisig's own listed breakdown: "Jawbone . . . road"), which also
  explains *why* this survived every prior automated check: the CSV's
  own `components` column already said "jawbone; joint; hood; mouth" for
  the sibling kanji, but `data.txt`'s flattened override always wins the
  merge, so the correct wording was sitting right there, just shadowed.
  Added a real `prim-jawbone` primitive and pointed all four hosts at
  it.
- Owner then asked to mine `results.jsonl` (the owner's own Google AI
  Overview cross-check) directly rather than working from independent
  re-derivation. Built a shadow-DB variant of the existing
  `triage_google_check.py` (which normally reads the *live* `kanji.db`,
  stale relative to this session's in-progress `data.txt` edits) so the
  comparison reflects current work. Re-running it against the fully
  updated dataset: **27 DISJOINT** flags remained (down from the
  historical count, confirming several were already fixed in earlier
  sessions this weekend). Went through all 27 individually
  (`--show-text` for the actual AI Overview content, `cjkvi-ids` +
  render as the tiebreaker per this audit's standing discipline — Google's
  AI Overview is itself just another LLM's guess, not authoritative on
  its own):
  - Real bugs found and fixed: `袖`(was flattening `由`, rtk1186, instead
    of referencing it), `浄`(was flattening `争`, rtk1238), `沸`+`費`
    (both flattening/misrepresenting `弗`, "dollar sign" per Heisig's
    own text — added a real `prim-dollar-sign` primitive), `汚`+`巧`+
    `号`+`朽` (a 4-kanji family all flattening `丂`, "snare" per Heisig's
    own text, as an unlabeled `一,勹` — added a real `prim-snare`
    primitive and pointed the whole family at it).
  - False positives, confirmed and left alone: `世`/`肉`/`申` (atomic
    kanji where the flag was just unrelated "used in these words"
    chatter); `梗`/`追`/`師`/`良`/`邦` (already correctly resolved —
    Google's own text listed unrelated example characters, not real
    disagreement); `党`(render-confirmed the bottom is `兄`, matching
    `cjkvi-ids`, not bare `儿` as Google's text loosely suggested);
    `競`(both sides resolve to the same primitive set either way, so
    "two identical halves" changes nothing at the schema level);
    `脳`(Google's own text explicitly says brain has *no* connection to
    "brains"/`田`, confirming the current non-`田` decomposition is
    right, not wrong); `単`/`之`/`壷`/`斡` (already-tracked standing
    open questions, or the AI Overview text was truncated with no real
    breakdown given).
- Verified: full rebuild; `test_regression_fixes.py` — 8 new pins (the
  `results.jsonl`-mined batch) plus the 5 from the `咼`/`薬` fixes above
  — **1171 checks**, same 4 expected hanzi-scope non-issues; pytest (56
  passed); `audit_self_reference.py` clean; `audit_radicals.py` still
  0/0 (the two new `prim-jawbone`/`prim-dollar-sign`/`prim-snare` rows
  are properly defined, not orphaned).
- `review_queue.py --mark-processed 14 15` — cleared both disputed
  reviews.
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed.
- Coverage: **1713/3000 (57.1%)**.
- **Next session**: `results.jsonl` still has 584 PARTIAL flags
  un-triaged (the noisier "something in ours not echoed in Google's
  text" bucket, historically lower-yield than DISJOINT but still found
  real bugs in past sessions — e.g. the `忘`/`忙`/`盲`/`妄` `亡`-overlap
  family). Standing list otherwise unchanged: `audit_direct_ref_overlap.py
  --min-usage 2`'s ~45 remaining candidates, the `个`/`亼` family
  decision, `慶`'s bottom shape, `壷`'s top element, the 81 orphaned
  `rad{N}` rows on the live DB.

## 2026-09-05 (daily check-in): worked `audit_direct_ref_overlap.py --min-usage 2`'s worklist (45 → 37)

Pulled 5 commits of out-of-band work from a prior unattended run (示/麻/
元/谷/乃, 矢/勿/辛 families, 薬/鰯 disputed-review fixes, `咼`/`弗`/`丂`
primitive discoveries, a shadow-DB `triage_google_check.py` variant, a
new `audit_radicals.py` tool) — verified it first (full rebuild, 1171
checks/4 expected failures, pytest 56 passed, `audit_radicals.py` 0/0
clean, no pending reviews) before adding anything of my own.

Went through the `--min-usage 2` worklist (45 candidates) by hand:
for each, pulled `cjkvi-ids`'s real IDS decomposition for the host
character plus (when needed) the flagged sub-primitive, and rendered
via `render_glyphs.py` wherever the IDS entry alone was ambiguous. Most
of the 45 turned out to be genuine "double duty" — the flagged token is
a real, separately-drawn second occurrence of the same primitive shape
elsewhere in the host (e.g. 鉛=金+㕣 has its own `ハ` distinct from
`金`'s internal `ハ`; 曹=[一 over 曲]+日 has its own bottom `日` distinct
from `曲`'s internal `日`; this exact pattern was already established
for 暗/尽/棟/欄/亘 in earlier sessions) — those are correctly left
alone. Found and fixed **8 real bugs**, all `金`(gold)/`干`(dry)-family,
falling into three sub-patterns:
- **Spurious token, not present in the glyph at all** (same class as
  the `刂`/`primitive_roof` dead-token finds, but here the token *does*
  resolve — it's just wrong for this host): `鋭`(pointed, rtk539) had
  `个`(umbrella) alongside `丷`+`兄` for its `兌`-side, but `兌` is
  `⿱八兄` — no umbrella shape anywhere (confirmed against the
  already-correct sibling entries `脱`/`説`, rtk537/538, which use the
  same `兌` and correctly list only `丷,兄`). `鋏`(scissors, rtk2795)
  had the same spurious `个` next to `人,大` for `夾`=`⿻大从` — render
  confirms `夾` is just "big flanked by two people," no umbrella stroke.
- **Old flattening cruft that should collapse to a direct reference to
  an already-taught kanji**: `釜`(cauldron, rtk1367) was flattened all
  the way down to `一,干,丷,父,王,丶,ノ,金` (8 tokens, mixing `金`'s own
  sub-parts with `金` itself) when render+CSV ("father; metal; gold")
  confirm it's simply `父,金`. `鎌`(sickle, rtk1725) was similarly
  flattened to 7 raw strokes instead of referencing `兼`(rtk1723,
  already taught) directly — render confirms `鎌`=`金`+`兼` cleanly.
  `鋲`(rivet, rtk2785) used `斤`(ax) + a bare `ハ` for its right side
  instead of referencing `兵`(rtk1429, soldier, already taught,
  `⿱丘八`) directly.
- **Wrong primitive substituted for a visually-similar one that's
  already registered**: `拝`(worship, rtk1686) used `｜,一,干` for its
  right side (`⿱一丰`), but `丰`("bushes") is already a registered
  primitive (`prim-bushes`) and CSV's own component list for this frame
  names it explicitly ("finger; fingers; one; ceiling; bushes") — render
  confirms the right side has 4 horizontals + a vertical (一 + 丰's own
  3+vertical), not 干's 2+vertical. `南`(south, rtk1740) listed a
  spurious `干` alongside its real `十,丷,冂` — `cjkvi-ids` gives
  `⿱十⿵冂𢆉`: the top is plain `十`, not `干` (which needs an *extra*
  crossbar `南` simply doesn't have). `午`(noon, rtk610) listed a
  redundant `十` alongside `ノ,干` — `干` already fully contains `十`
  (`干`=`十`+`一`) with no second occurrence anywhere in `午`'s 4
  strokes (unlike the `亘`=`一`+`旦` case, where the extra `一` **is** a
  real second stroke — confirmed by comparing renders side by side).

Also spot-checked several structurally-similar candidates that turned
out to be correct as-is and are now the concrete precedent for future
double-duty calls on this list: `鉛`(rtk857, `金`'s `ハ` vs `㕣`'s own
`ハ`), `砺`(rtk2641, `石`'s `厂` vs `厉`'s own `⿸厂万`), `棟`/`欄`
(rtk544/1756, `木` vs `東`'s internal `日`+`木` — same family as the
earlier `暗` precedent), `曹`(rtk1257), `亘`(rtk32). Left the `敝`-family
(`蔽`/`弊`/`瞥`/`鼈`/`幣`, which use `尚` as a deliberate shape
stand-in for Heisig's unregistered "shredder" primitive) and `獣`/`鑿`
alone — genuinely ambiguous multi-layer cases where CSV's `components`
column doesn't cleanly map to a single correct fix; adding to the
standing deferred list below rather than guessing.

Verified: full rebuild (3000 kanji, 3007 overrides); `test_regression_fixes.py`
— 8 new/updated pins — **1178 checks**, same 4 expected hanzi-scope
non-issues; pytest (56 passed); `audit_self_reference.py` clean;
`audit_flattening.py`/`audit_flattening_subsequence.py` show only
pre-existing obscure-variant-kanji findings in the 2960s-2990s range
(unrelated to this batch, not touched); `audit_radicals.py` still 0/0.
`audit_direct_ref_overlap.py --min-usage 2`: **45 → 37** candidates.
Not deployed (no SSH/server access) — data-only change, needs
`sync_system_data.py` + reseed.

**Next session**: `audit_direct_ref_overlap.py --min-usage 2`'s
remaining 37 candidates (now with the `敝`-family and `獣`/`鑿` marked
as deliberately-deferred rather than unreviewed — see above), the 584
un-triaged PARTIAL `results.jsonl` flags, the `个`/`亼` family decision,
`慶`'s bottom shape, `壷`'s top element, the 81 orphaned `rad{N}` rows
on the live DB.

### 2026-09-05 (continued) — owner pushed the full 3000-kanji Google cross-check; started an LLM re-read of the whole file

- Owner ran `tools/heisig-google-check/check_kanji.py --all` on their
  own machine and pushed the result: `results.jsonl` is now **3005
  lines / 3000 unique kanji** (was 1812) — every RTK frame has a Google
  AI Overview record now, ~2478 with usable text.
- Owner's instruction: stop trusting the regex extractor
  (`triage_google_check.py`'s char-extraction), have an LLM actually
  *read* each AI Overview and produce a simplified decomposition JSON to
  keep as a **respected reference** alongside `cjkvi-ids`/CSV; and
  prepare a table of *real doubts* — cases where the Google data itself
  looks bad — for the owner to adjudicate.
- Approach: split the 2478 usable records into batches, hand each to a
  worker sub-agent that reads every `extracted_text` in full and writes
  `{id: {parts, primitive_names, confidence, note}}` plus a per-batch
  doubts list. Running **2 agents at a time** (an earlier attempt at 6
  parallel burned the session rate-limit and several agents mis-scoped
  themselves as orchestrators; the 2-at-a-time + explicit
  "no-sub-agents, write incrementally" instructions fixed both). Output
  accumulates in `scratchpad/results/m_*_decomp.json`. Batches 00-05
  done so far (~780 records); ~1700 remain.
- **First 5 real bugs already confirmed** from the m_00/m_01 agents'
  findings, each cross-checked against `cjkvi-ids` + a rendered-glyph
  comparison before fixing (Google's AI Overview alone is never the
  tiebreaker — same discipline as always):
  - `rtk89` 切 ("cut"): was `刀,匕` — left side is `七`(seven), not
    `匕`(spoon). `cjkvi-ids` `⿰七刀`; render confirms the leftward hook.
  - `rtk236` 株 ("stocks"): was `牛,木` — right side is `朱`(vermilion,
    rtk235), not `牛`. `cjkvi-ids` `⿰木朱`.
  - `rtk144` 泳 ("swim"): was `水,丶` — right side is the full
    `永`(eternity, rtk139), not a lone drop. `cjkvi-ids` `⿰氵永`.
  - `rtk172` 均 ("level"): was `土,冫,勹,二` — right side is `匀` (`勹`
    wrapping a single `丶`); the `冫` and `二` were spurious. →
    `土,勹,丶`.
  - `rtk124` 削 ("plane"): was `月,尚` — left side is `肖`(rtk119, "肖"
    itself `小,月`), not `尚`(esteem). `cjkvi-ids` `⿰肖刂`. → `肖,刀`.
- Verified: full rebuild; `test_regression_fixes.py` — 5 new pins —
  **1183 checks**, same 4 expected hanzi-scope non-issues; pytest (56
  passed); `audit_self_reference.py` clean.
- Not deployed (no SSH/server access) — data-only change.
- **Truncated-text list building up**: the agents are flagging every
  kanji whose Google AI Overview cut off at "Show more" with no
  breakdown given — 76 so far from the first ~840 records analyzed
  (`scratchpad/need_google_rerun_partial.json`). Once the whole file is
  read, that becomes the list the owner re-runs the scraper on.
- **Next**: finish the LLM read (batches m_06 through m_12), merge all
  `m_*_decomp.json` into `backend/google_decompositions.json`, then
  build the doubts table and the full truncated-rerun list for the
  owner.

### 2026-09-05 (continued) — LLM re-read finished: `google_decompositions.json` committed, doubts table + rerun list delivered

- All 13 batches (m_00–m_12) complete. `assemble_final.py` merged them
  into **`backend/google_decompositions.json`** — 2478 entries, one per
  kanji with usable Google text. Format per entry:
  `{character, parts: [...], primitive_names: {char: english_name}, confidence, note}`.
  1978 high / 234 medium / 266 low confidence; 229 have `parts: null`
  (Google text truncated at "Show more"). Committed 2569135, pushed.
  This is now the project's third standing reference alongside
  `cjkvi-ids` and `heisig-kanjis.csv`'s `components` column — but the
  weakest of the three (it's one more LLM's reading of one more LLM's
  summary), so `cjkvi-ids` + a rendered glyph still break every tie.
- **`backend/google_doubts.json`** — 19 rows where the Google text
  *itself* is untrustworthy (self-contradictory, about a different
  character, keyword mismatch, garbled with placeholder emoji, or a
  substantive claim that needs a primary source). Presented to the
  owner as a table for adjudication. NOT auto-applied. The one that
  actually matters if true: **`rtk766` 撃** — Google insists the
  top-left is `𠦝` ("mist"), explicitly *not* `車`; our data has `車`.
  Needs a primary-source check before any change.
- **`tools/heisig-google-check/need_rerun.json`** — 771 kanji for the
  owner to re-scrape with `check_kanji.py`: 522 where Google returned no
  usable text at all ("Searching…" / empty), + ~249 truncated at "Show
  more" before the breakdown.
- Ledger artifact rebuilt from the LLM-read data (was the old regex
  extraction): match 1083 / differ 1053 / disjoint 96 / doubt 17 /
  truncated 229 / no-text 522. `differ`/`disjoint` are mostly depth
  differences (our data one level deeper, or Google over-decomposing),
  not bugs — only `doubt` rows need a human.
- Earlier this session, 6 more real bugs fixed from the m_* agent
  findings (all cross-checked against `cjkvi-ids` + render first):
  `rtk909` 鉄 / `rtk910` 迭 were `金,矢` / `込,矢` — both use `失`(lose),
  not `矢`(dart); this was my own error from the f7d6ded 矢-family
  cleanup. Same mistake in the 雚-family: `rtk612` 歓 / `rtk613` 権 /
  `rtk614` 観 / `rtk928` 勧 had a spurious `矢`; the shared right element
  is `隹`(turkey) under a `丷` top, no dart. All 6 fixed + pinned
  (`test_regression_fixes.py` now 1186 checks, pytest 56 passed).
- Not deployed (no SSH/server access) — data-only change, needs
  `sync_system_data.py` + reseed on deploy.
- Added `check_kanji.py --from-list need_rerun.json`: re-checks exactly
  the ids in a JSON list, ignoring `progress.json` (the existing modes
  all skip anything already in `progress.json`, and every rerun id is
  already marked done). Builds each batch entry from the list file's own
  `id`/`character`/`keyword` fields, falling back to `unreviewed_kanji.json`
  only for `current_parts` — ~540 of the 771 rerun ids are no longer in
  `unreviewed_kanji.json` because they've since been reviewed, so a
  `by_id`-only lookup would silently drop them. Each rerun appends a
  fresh `results.jsonl` record; newest wins when the file is read.
- **`expand_ai_overview` → `expand_and_read` (JS-driven).** Owner
  reported the button-clicking approach still misses "Show more" — the
  first rework (scoped exact-label button scan) didn't fix it either.
  Root problem: chasing one clickable element is inherently brittle
  against Google's markup drift. New approach doesn't depend on a button
  selector at all: one `page.evaluate()` pass locates the AI Overview
  region (by `aria-label`/known ids, or by walking up from an "AI
  Overview" heading), then **both** clicks every expander-looking
  control inside it (label match or `aria-expanded=false`, a few rounds
  for chained toggles) **and** force-strips every truncation mechanism —
  `-webkit-line-clamp`, `display:-webkit-box`, `max-height`,
  `overflow:hidden` on any node whose `scrollHeight` exceeds its box —
  and opens `<details>`. So the full text is recovered from the DOM even
  when the click target has moved or is gone. `extracted_text` is now
  the region's complete `innerText`. Records `expand_clicks`,
  `unclamped_nodes`, `found_overview` per row.
- **Removed the 20–60s inter-query delay** (owner: "run without
  delay"). Now `--delay MIN MAX` (default 2–4s) / `--no-delay`. Kept a
  small default because a few hundred back-to-back Google searches from
  one residential IP is the classic CAPTCHA trigger — the script still
  pauses for a manual solve if one appears, so `--no-delay` is
  recoverable, just slower when it trips. Also dropped the fixed
  post-load `wait_for_timeout` — `expand_and_read` polls for the
  overview itself and returns the moment the text stops growing.
- Untestable here (no display; Google blocks the server IP) — owner runs
  `check_kanji.py --from-list need_rerun.json` (add `--no-delay` to go
  flat out).

### 2026-09-05 (continued) — the "Searching…" state; JS extraction verified against a headless browser

- Owner ran the rerun and pushed 123 records (`d0b3d0f`). Only 2
  (`rtk5`, `rtk42`) actually went through the new JS path — and both got
  **full 2100+ char text with `expand_clicks: 0`**: the clamp-CSS
  stripping recovered the whole overview without needing to click
  anything, which is the whole point of not depending on the button.
  The other 121 were from the old script still in the working tree at
  the time.
- Of those 121: **63 were captured as literally "Searching…"** — Google
  had not finished generating the overview when the old script
  screenshotted and read. That's a *timing* failure, not a Show-more
  failure. Added a `generating` signal to the JS (overview box present
  but body is `< 40` chars / starts with "searching|generating|
  loading|thinking") and a matching poll state in `expand_and_read`:
  `APPEAR_BUDGET_S` (12s) to wait for the box to exist at all, then
  `GENERATING_BUDGET_S` (25s) to keep polling while it's still
  streaming. A still-"Searching…" result is stored as `extracted_text:
  null` + `still_generating: true` so a re-run picks it up instead of a
  useless partial.
- **Verified the injection JS against a real headless Chromium** (the
  backend venv has `playwright` importable; `/tmp/jstest.py`) on three
  synthetic pages: a `-webkit-line-clamp` + `max-height` + `<details>`
  page (all three revealed, `unclamped: 2`, one expander click), a
  "Searching…" page (correctly `generating: true`), and a no-overview
  page (correctly `foundRoot: false`). Also added a `data-ck-clicked`
  marker so the poll loop never re-clicks a toggle it already opened.
- Rebuilt `need_rerun.json` from the whole 3000-row deduped
  `results.jsonl` (newest record wins per id): **602 still unusable**
  (539 too-short, 63 truncated-with-Show-more) — down from 771. Owner
  re-runs `check_kanji.py --from-list need_rerun.json`.
