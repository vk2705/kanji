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
