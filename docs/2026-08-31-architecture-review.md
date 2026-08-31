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

### 3. High — no isolated behavioral test suite

`test_regression_fixes.py` and the `audit_*.py` scripts are valuable but all read the
live, mutable `kanji.db` — none of them exercise auth, visibility rules end-to-end,
migrations, contribution-endpoint ownership checks, or search filters in isolation.

**Fixed** (partially — see "not covered" below): added a `pytest` + temp-SQLite-DB +
FastAPI `TestClient` suite. `backend/conftest.py` gives every test its own throwaway
temp-file DB (`db_path` fixture — a real file, not `:memory:`, since `get_db()`
always opens by path and the app's `db_conn()` dependency opens a fresh connection
per request, so different `:memory:` connections wouldn't share data the way a real
temp file does) and wires the real FastAPI app to it via
`app.dependency_overrides[db_conn]` (the `app`/`client` fixtures) — no test ever
touches `backend/kanji.db`. One non-obvious gotcha documented in `conftest.py`:
`TestClient` needs `base_url="https://testserver"`, not the default `http://`, or
the app's `secure=True` session/visitor cookies silently fail to round-trip and
every login-dependent test would 401 with no obvious cause — confirmed this
concretely with a minimal reproduction before writing the fixture.

Four test files, 27 tests total, covering the review's own priority list:
- `test_api_visibility.py` (4 tests) — private-entry visibility through aliases
  (direct, isolated re-coverage of finding #1's exact bug class), anonymous/owner/
  unrelated-user reads. **Caught a real bug in the test itself while writing it**:
  the first draft of the alias-leak test still passed with the bug deliberately
  reintroduced, because it addressed the victim kanji by its *real id* in the
  write-endpoint assertions instead of by the *alias* — the actual exploit path.
  Fixed the test, reran the before/after check (fails with the bug reintroduced,
  passes with the fix) to confirm it now genuinely detects the vulnerability rather
  than trivially always passing.
- `test_api_contributions.py` (8 tests) — auth requirements on every write endpoint,
  ownership checks on all four `PATCH .../visibility` endpoints, system-row (`owner_
  id=1`) immutability, duplicate username rejection, duplicate alias-from-different-
  owners *acceptance* (the `_migrate_v1` schema change this enables), story upsert-
  not-duplicate behavior, and the `create_kanji_entry` missing-alias regression.
- `test_api_migrations.py` (6 tests) — fresh-DB migration to latest, idempotent
  re-run, the full 0→latest sequence, and (the review's specific ask) migrating
  from each individual intermediate version by advancing a temp DB to exactly
  version N-1 (using a filtered view of the same `_MIGRATIONS` registry the real
  runner uses) and confirming the rest completes cleanly — plus two DB-level
  sanity checks (the reserved system user, the relaxed `aliases` UNIQUE constraint).
- `test_api_search.py` (9 tests) — `search_by_parts`'s depth (direct-only at
  depth=1 vs. recursing to grandparents at depth=3), script, and source filters,
  self-identity matching, whole-word text search, and private-decomposition
  isolation. Two of these needed real debugging, not just writing assertions and
  moving on: a `depth=1` test's own expected-result set was wrong (didn't account
  for a direct, one-level match that legitimately isn't self-identity), and a
  `sources` test's fixture accidentally entangled "which kanji rows are eligible"
  with "which decomposition gets consulted" (both keyed off the same `sources` set)
  — redesigned around a system-owned kanji with two decompositions so the kanji's
  own eligibility stays constant across the scopes compared, isolating what the
  test actually meant to check.

**A genuine bug surfaced by writing these tests, fixed in passing**: two of the
`test_api_search.py` tests initially failed with `sqlite3.OperationalError: database
is locked` — not a test bug, but `get_db()` never set `PRAGMA busy_timeout`, a gap
CLAUDE.md already listed as a known, accepted, low-priority limitation ("cheap fix
if it comes up"). It came up: a fixture connection left open across an API call (a
second, independent connection under the hood) hit exactly this. Added `PRAGMA
busy_timeout = 5000` to `get_db()` — cheap, harmless in WAL mode (readers still
never block writers), and directly useful for real concurrent-write contention in
production too, not just this test suite. Confirmed `test_regression_fixes.py`'s
full live-DB suite still passes unchanged with this added.

**Also added**: `backend/requirements-dev.txt` (`pytest`, `httpx` — not bundled into
the production `requirements.txt`) and `.github/workflows/ci.yml`, a new GitHub
Actions workflow (this repo had no CI at all before) running the backend pytest
suite and the existing frontend `lint`/`build` on every push to `master` and every
PR — the "run in CI" half of the review's own recommendation. Confirmed `npm run
lint` and `npm run build` both pass locally under node-20 before trusting the
workflow file.

**Not covered** (explicitly out of scope for this pass, left for later): request
validation edge cases, upload failure-path consistency (review finding #5, not yet
fixed either), and frontend behavior — the review's own list included these but
they're either a different finding's territory or meaningfully more work (Playwright/
frontend test tooling doesn't exist in this repo yet at all) than the temp-DB API
suite above. Coverage can grow incrementally in future sessions; this pass
establishes the harness and the four highest-value files, not full breadth.

## Status: NOT YET ADDRESSED (tracked for a future session)

Numbered as in the original review.

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
2. ~~Introduce temp-DB API tests + CI~~ — done 2026-08-31 (#3; upload failure-path
   and frontend coverage still not included, see #3's "not covered" note above).
3. ~~Make migrations atomic before the next schema version bump~~ — done 2026-08-31 (#2).
4. Rate limits, validation limits, analytics retention (#4; `PRAGMA busy_timeout`
   already done 2026-08-31 as a side effect of #3 — see #3 above).
5. Off-host backup + restore rehearsal (#6).
6. Frontend request races, error presentation, empty-source handling (#7, #8).
7. Documentation pass (#9).
8. Primitive autocomplete, moderation tools, URL routing, the queued JP/ZH
   counterpart-comparison badge (#10 plus CLAUDE.md's existing queued items).
