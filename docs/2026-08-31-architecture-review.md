# Architecture review — 2026-08-31

Source: a design review (`review1`, in the repo root, not checked in) the owner had
done independently and asked to be read and addressed. Findings reproduced/summarized
below with their original priority, plus status as each is worked through. Follow the
project's usual rule: verify a finding against real code/behavior before trusting it,
same as every other fix in `2026-08-search-quality-audit.md` — don't take a review's
claim as ground truth without checking.

## Status: FIXED

### 1. High — alias-based contribution writes could cross a privacy boundary

Confirmed real and exploitable via a rolled-back two-user transaction test before
fixing (not just taken on the review's word): `resolve_alias()` in
`backend/database.py` checked the alias row's own visibility but not the joined
kanji's. A user could publish just an *alias* on their own private kanji (keep the
kanji itself private) and an unrelated viewer resolving that alias term got the
kanji's real id back — including through `contributions.py`'s `_visible_kanji_id()`,
which relies on `resolve_alias()` as its sole visibility gate for every write
endpoint (add alias/decomposition/story to someone else's private kanji).

Same bug class as the `_resolve_parts_detail` leak (2026-08-27) and the gap
`_self_identity_kanji_ids` already guards against (its own docstring documents that
exact fix) — `resolve_alias()` itself was apparently missed at the time.

**Fixed**: added `AND (k.visibility = 'public' OR k.owner_id = ?)` to the alias-join
query in `resolve_alias()`, mirroring `_self_identity_kanji_ids`'s existing pattern.
Added `check_alias_visibility_boundary()` to `test_regression_fixes.py` — inserts a
throwaway private kanji + public alias inside an explicit transaction, asserts an
unrelated/anonymous viewer can't resolve or write to it, asserts the owner still can,
then unconditionally rolls back so no test data persists.

## Status: NOT YET ADDRESSED (tracked for a future session)

Numbered as in the original review.

### 2. High — schema migrations are versioned but not atomically transactional

`migrate_schema()` commits after each migration; an interrupted startup mid-migration
could leave `user_version` stale while some DDL already landed, breaking the next
startup on a duplicate `ALTER TABLE`. Fix: wrap each version's migration + its
`user_version` bump in one explicit transaction; test against a throwaway copy of the
DB with a simulated interruption before trusting the fix.

### 3. High — no isolated behavioral test suite

`test_regression_fixes.py` and the `audit_*.py` scripts are valuable but all read the
live, mutable `kanji.db` — none of them exercise auth, visibility rules end-to-end,
migrations, contribution-endpoint ownership checks, request validation, upload
failure handling, or frontend behavior in isolation. Recommended: `pytest` +
temporary SQLite DB + FastAPI `TestClient`, covering (highest value first): private-
entry visibility through aliases (the class of bug #1 above lives in), anonymous/
owner/unrelated-user reads, every contribution endpoint's ownership rules, migration
from each schema version, recursive search depth/source/script filters, duplicate
usernames/aliases, image upload failure consistency. Run in CI alongside the existing
frontend lint/build.

### 4. Medium — public write endpoints have no abuse controls

No rate limiting anywhere (login, register, Google login, contributions, reviews,
`/analytics/pageview`) — analytics in particular is an easy unbounded-growth vector
since it needs no auth. Field lengths are almost entirely unconstrained (username,
password, alias, label, story, analytics path). `hash_password()` can hit a bcrypt
72-byte password limit and 500 rather than reject cleanly. Fix: nginx rate limits at
minimum; Pydantic `max_length` constraints across write bodies; a page_views
retention/aggregation policy.

### 5. Medium — upload storage and DB updates aren't atomic

`upload_kanji_image()` commits `image_url` before the file write completes — a
disk-full/permission error leaves a dangling DB path to a missing file. `uploads/` is
also excluded from `backup_db.py`. Fix: write to a temp file, verify its real format,
atomically rename, commit only after; back up `uploads/` alongside `kanji.db`.

### 6. Medium — disaster recovery is incomplete

`backup_db.py` only keeps 14 days locally — a host failure takes out prod and
backups together. The committed anonymized `public_data_export.jsonl` intentionally
excludes credentials/real ownership/uploads and has no restore tooling (already
acknowledged in `DEPLOY_README.md`). Fix: encrypted off-host backups of the real DB +
uploads, plus an actually-rehearsed restore drill; keep the anonymized export for
auditing only, not as the DR plan.

### 7. Medium — frontend requests can resolve out of order

`runSearch()` and `KanjiDetail`'s detail loading don't abort or sequence-tag
in-flight requests — a slow stale request can clobber a newer search/selection.
Search errors also collapse into "no results" instead of a real error state, hiding
outages. Fix: `AbortController` or a request-sequence guard; keep showing the
previous result while loading; a distinct localized error state.

### 8. Medium — empty content-source selection behaves inconsistently

Parts search sends `sources: []` and correctly means "match nothing." Text/character/
detail requests instead encode sources as repeated query params, so an empty array
sends zero params, which the backend reads as "no filter" (all sources) — the
opposite meaning from parts search. Fix: pick one consistent encoding/meaning for
"no sources selected" across all four endpoints, or disable search client-side when
none are selected.

### 9. Medium — root `README.md` is stale enough to mislead

Describes React 18, an old schema, old search semantics, and references the deleted
`/admin/reimport` endpoint — its own rebuild instructions could cause real data loss
if followed literally now that the DB holds user contributions. Fix: replace with a
short overview derived from `CLAUDE.md`, with the destructive-data warning up front.
(Also: `CLAUDE.md` itself has at least one stale "known limitation" note —
script-aware `expand_part_terms()` — that the review says already exists; worth a
pass to reconcile.)

### 10. Low — accessibility and mobile pass needed

`KanjiCard.jsx` result cards are clickable `div`s (not keyboard-reachable), several
controls rely on placeholder text alone, tabs lack ARIA tab semantics, expandable
sections lack `aria-expanded`, no evident responsive breakpoint despite absolutely-
positioned header controls. Fix: semantic buttons/links, visible labels, real tab
state, focus styles, mobile viewport testing. URL-based routing (bonus) would also
make results/detail pages bookmarkable and restore back-button behavior.

## Suggested order (per the review, still valid)

1. ~~Fix the alias visibility flaw + its regression test~~ — done 2026-08-31.
2. Introduce temp-DB API tests + CI (#3).
3. Make migrations atomic before the next schema version bump (#2).
4. Rate limits, validation limits, `PRAGMA busy_timeout`, analytics retention (#4).
5. Off-host backup + restore rehearsal (#6).
6. Frontend request races, error presentation, empty-source handling (#7, #8).
7. Documentation pass (#9).
8. Primitive autocomplete, moderation tools, URL routing, the queued JP/ZH
   counterpart-comparison badge (#10 plus CLAUDE.md's existing queued items).
