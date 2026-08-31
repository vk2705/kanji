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

### 2. High — schema migrations are versioned but not atomically transactional

`migrate_schema()` committed after each migration, but each `_migrate_vN` body used
`conn.executescript()` for its DDL — which, confirmed by direct testing against a
throwaway DB, **always implicitly commits before running and doesn't honor a
manually-opened transaction**, even one opened right before calling it. So even
wrapping the old code in `BEGIN`/`COMMIT` wouldn't have helped; a crash partway
through a multi-statement migration (e.g. `_migrate_v1`, which creates several
tables and rebuilds `aliases`) really could leave `user_version` stale while some of
that version's schema already existed, breaking the next startup on a duplicate
`ALTER TABLE`/`CREATE TABLE`.

**Fixed**: replaced every `executescript()` call in every `_migrate_vN` with
individual `conn.execute()` calls (confirmed via direct testing that per-statement
`execute()` *does* honor an explicit transaction, unlike `executescript()`), and
rewrote `migrate_schema()` to open one explicit `BEGIN` per version, run that
version's migration function, bump `PRAGMA user_version` (confirmed transactional in
SQLite via direct testing), and `COMMIT` — with a `try/except: conn.rollback(); raise`
around the whole thing so any exception anywhere in that version's migration rolls
the entire version back atomically, `user_version` included. Migrations are now
registered via a small `_register(version, fn)` call after each `_migrate_vN`
definition instead of being hand-listed in `migrate_schema()`, so a future `_migrate_v6`
only needs `_register(6, _migrate_v6)` — the runner loop needs no change.
`_backfill_decompositions()` (called from inside `_migrate_v1`) no longer commits
internally, since that would have silently closed the outer transaction early; its
other caller (`import_data()`) already had its own `conn.commit()` right after, so
this changes nothing there except making that commit slightly more inclusive (in a
harmless way — it was always meant to be one atomic seed operation).

**Verified**, not just asserted: wrote `check_migration_atomicity()` in
`test_regression_fixes.py`, which runs entirely against a disposable temp-file DB
(never touches the live `kanji.db`) — creates a fresh DB, monkeypatches the v1
migration to create two tables and then raise partway through, confirms
`user_version` stays at 0 and neither table exists after the simulated crash
(previously would have been a real risk; now genuinely rolled back), then restores
the real migration and confirms a retry — simulating a service restart after the
crash — completes cleanly to the latest version with no duplicate-table error. Also
manually re-ran the same scenario as an ad hoc script before writing the permanent
test, and separately verified the ordinary paths still work: a fresh DB migrates
0→5 correctly, an already-migrated DB is a clean no-op, and a copy of the real live
DB (already at v5) round-trips through `migrate_schema()` with its data intact.
Backend restarted against the real live DB with this new runner — starts clean.

## Status: NOT YET ADDRESSED (tracked for a future session)

Numbered as in the original review.

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
3. ~~Make migrations atomic before the next schema version bump~~ — done 2026-08-31 (#2).
4. Rate limits, validation limits, `PRAGMA busy_timeout`, analytics retention (#4).
5. Off-host backup + restore rehearsal (#6).
6. Frontend request races, error presentation, empty-source handling (#7, #8).
7. Documentation pass (#9).
8. Primitive autocomplete, moderation tools, URL routing, the queued JP/ZH
   counterpart-comparison badge (#10 plus CLAUDE.md's existing queued items).
