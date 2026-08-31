# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A web app for learners using **Remembering the Kanji (RTK)** by James W. Heisig. The method assigns each kanji a set of named visual "primitives" (building blocks) and a mnemonic story. This app lets you search kanji by those primitive names — e.g. type "sun" + "moon" to find 明 (bright).

It's grown beyond a personal RTK lookup tool into a community-editable reference: registered users can add their own kanji/hanzi, decompositions, aliases, and mnemonic stories (public or private), and the database also covers Chinese hanzi (simplified + traditional) alongside Japanese kanji. The UI supports English/Russian and a Japanese/Chinese (Simplified/Traditional) study-language filter.

## Stack

| Layer | Tech |
|---|---|
| Backend API | Python 3 + FastAPI + SQLite |
| Frontend | React 19 + Vite |
| CLI | Plain Python 3 (stdlib only), reads `backend/kanji.db` directly — no server needed |
| Data | `heisig-kanjis.csv` + flat text overlays → SQLite (one-time seed); user contributions written directly to SQLite thereafter |
| Auth | Cookie-based sessions, `bcrypt` password hashing — no external identity provider |
| Android | Kotlin, WebView shell around `frontend/` — see `android/README.md` |

`cgi-bin/` (Perl) and `html/` are the original legacy app — reference only, not part of the active stack.

## Commands

**Backend** (port 8000):
```bash
cd backend
pip install -r requirements.txt   # fastapi, uvicorn, bcrypt, google-auth
python3 -m uvicorn main:app --reload --port 8000
```
On first run, `kanji.db` is created and the RTK data is imported automatically (see import pipeline below). There is **no reimport endpoint** — the DB is the source of truth now, not a rebuildable cache (see Architecture). To pick up edits to `data.txt`/`data_from_pdf.txt`/`heisig-kanjis.csv` in local dev, delete `backend/kanji.db` and restart.

**Frontend** (port 5173):
```bash
cd frontend
npm install
npm run dev          # dev server
npm run build         # production build
npm run lint          # oxlint
```

**CLI** (no server needed — queries `backend/kanji.db` directly with stdlib `sqlite3`):
```bash
python3 rtk.py parts sun moon    # kanji containing all given primitives
python3 rtk.py text marsh        # keyword/alias substring match
python3 rtk.py char 明           # exact character lookup
python3 rtk.py detail rtk145     # full detail: aliases + parts
```
`rtk.py` predates the multi-user schema and queries `kanji`/`aliases`/`parts` directly with no `visibility`/`owner_id` filtering — it will surface private user contributions indiscriminately. Treat it as a dev/debug tool, not a user-facing surface.

**Android** (WebView shell, no backend changes needed — see `android/README.md`):
```bash
cd android
./gradlew :app:assembleDebug    # points at a local dev server (10.0.2.2:5173)
./gradlew :app:assembleRelease  # points at the live deployed site, unsigned APK
```

**One-off data/maintenance scripts** (`backend/`, not part of the app's runtime). These `import database` (`X | None` syntax, Python 3.10+), so they need the venv's Python — the box's system `python3` is 3.9.25 and `TypeError`s on import. Use the venv's interpreter explicitly, or `source venv/bin/activate` first:
```bash
./venv/bin/python3 import_rtk.py            # append new rtk{frame} entries to data.txt from kanjidic2 + KRADFILE
./venv/bin/python3 import_hanzi.py          # one-time: seed Chinese hanzi (CJK Unified block) from Unihan.zip + cjkvi-ids
./venv/bin/python3 backup_db.py             # online backup of kanji.db to backups/, prunes backups older than 14 days
./venv/bin/python3 sync_system_data.py --dry-run   # reconcile live system rows with data.txt/CSV without wiping user data
./venv/bin/python3 review_queue.py          # list pending user-submitted decomposition approve/dispute votes
./venv/bin/python3 visit_stats.py           # site visit counts (today/7d/30d/all-time), or --days N for a daily breakdown
```
`import_hanzi.py` refuses to run if any non-`ja-kanji` rows already exist (not safe to resume mid-run). `backup_db.py` is meant to run on a schedule (see Deployment). `backup_db.py`, `export_public_data.py`, `fix_kradfile_proxies.py`, `sync_system_data.py`, `review_queue.py`, and `visit_stats.py` also have a shebang pointing straight at `venv/bin/python3`, so `./script.py` works directly without the `./venv/bin/python3` prefix.

**Tests** (added 2026-08-31, architecture review finding #3):
```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt   # adds pytest, httpx
./venv/bin/pytest -v
```
Runs the isolated API suite (`test_api_*.py`) — every test gets its own throwaway temp-file SQLite DB via `conftest.py`'s `db_path`/`app`/`client` fixtures (`app.dependency_overrides[db_conn]` points the real FastAPI app at it), so nothing ever touches `backend/kanji.db`. Covers auth-required checks, visibility/ownership rules (including the alias-visibility-leak class fixed the same session), migrations from each schema version, and `search_by_parts`'s depth/source/script filters. Runs in CI (`.github/workflows/ci.yml`) alongside frontend `lint`/`build` on every push/PR. `test_regression_fixes.py` and the `audit_*.py`/`coverage_status.py` scripts are a separate, deliberately-different convention — they read the live `kanji.db` directly (see "One-off data/maintenance scripts" above and each file's own docstring) and are not run via `pytest`.

## Architecture

### The database is the source of truth (not a rebuildable cache)

Originally `kanji.db` was disposable — fully rebuilt from `heisig-kanjis.csv` + text overlays via `/admin/reimport`. That endpoint is gone. Once user accounts and contributions were added, wiping and rebuilding the DB would destroy user data, so `import_data()` (`backend/database.py`) now runs **once**, only when the `kanji` table is empty (checked in `main.py`'s lifespan handler), and is a no-op if any `owner_id = 1` (system) rows already exist. Schema upgrades instead go through `migrate_schema()`, an idempotent migration gated by `PRAGMA user_version`, run on every startup — safe against both a fresh DB and a populated one.

### Import pipeline (`backend/database.py::import_data`, one-time seed only)

Seeds the system data (`owner_id = 1`, a reserved account created by `migrate_schema`) from three sources, in priority order (later wins):

1. **`heisig-kanjis.csv`** — the baseline. ~2,200 kanji from the 6th edition with `id_6th_ed`, `kanji`, `keyword_6th_ed`, `components` (already fully expanded — no recursive expansion needed at query time), `stroke_count`, `jlpt`. Each row becomes a `kanji` row with id `rtk{frame}`.
2. **`backend/data_from_pdf.txt`** — ~650 primitive decompositions extracted from the 4th-edition PDF, keyed by keyword-matched frame.
3. **`backend/data.txt`** — hand-curated overrides: primitive aliases, characters still missing from the CSV, and verified decomposition overrides. Same line format as `data_from_pdf.txt`. Takes priority over both other sources.

When editing kanji data pre-launch, prefer `data.txt` — it always wins the merge. `data_from_pdf.txt` only fills gaps `data.txt` doesn't cover. Post-launch, editing these files has no effect unless `kanji.db` is deleted and reseeded from scratch.

`data.txt` / `data_from_pdf.txt` line format:
```
id:character:alias1,alias2,...:part1,part2,...;alt_decomp1,alt_decomp2
```
- `id` — `rtk{n}` for kanji (6th-edition frame number, a real citable identifier — Heisig's book numbers kanji frames, just not primitives independently of them). For a pure primitive with no kanji frame of its own: `kangxi{n}` if its glyph is one of the 214 official Kangxi radicals (n = the official radical number, verified against Unicode's `CJKRadicals.txt` — not the legacy `rad{n}.{m}` KRADFILE-derived numbering, which turned out to be arbitrary import-order bookkeeping from the pre-rewrite Perl app, not a citable standard); otherwise `prim-{descriptive-slug}` (e.g. `prim-katakana-ha`, `prim-heki`) — Heisig's RTK has no official numbered index of non-Kangxi primitives independent of frame numbers (a third-party project's own primitive numbering explicitly calls itself a "fake Heisig number" in its source, confirming this), so a made-up number would look authoritative while actually being arbitrary — the same "resolved but misleads" anti-pattern this project's audit doc has repeatedly found and fixed. See `docs/2026-08-search-quality-audit.md`'s session on the `kangxi{n}`/`prim-{slug}` migration for the full reasoning and the id mapping.
- `character` — UTF-8 glyph, or `?`/empty if not yet identified.
- `aliases` — comma-separated names; the first becomes the keyword.
- `parts` — comma-separated primitive names or kanji characters; alternate decompositions separated by `;`.
- Lines starting with `#` and blank lines are ignored. All ASCII field values are lowercased on import.

`import_rtk.py` is a one-off generator that appends new `rtk{frame}` entries to `data.txt` from kanjidic2 + KRADFILE (downloads them if not given local paths). `import_hanzi.py` is a separate one-off that writes Chinese hanzi (script `zh-Hans`/`zh-Hant`/`zh-Hani`) directly into `kanji.db` as system-owned public rows, reusing `expand_part_terms` for its IDS-derived decompositions — see the module docstring for scope and re-run safety.

**Verifying a primitive's real identity — render it, don't just reason about it.** `backend/render_glyphs.py` renders requested characters large to a PNG via the pre-installed headless Chromium (no `playwright` package needed) for visual comparison — `python3 render_glyphs.py 个 会 谷 --out /tmp/compare.png`, then look at the PNG. Standing method (owner-mandated, 2026-08-23) for verifying whether a primitive's assigned character/keyword actually matches what's drawn inside its host kanji: reasoning from Unicode codepoint tables or keyword text alone has been independently wrong more than once in this project's history (e.g. `个`, kept as a "person radical" stand-in for decades, turned out on actual rendering to have an extra stroke the real host shape doesn't have, and CSV confirms Heisig's real name for it is "umbrella" — nothing to do with "person"). Always cross-check the rendered glyph against real host kanji (and `heisig-kanjis.csv`'s components column) before trusting a primitive's identity, not just against other Unicode data tables.

### Database schema (SQLite, `backend/kanji.db` — generated, not committed)

```sql
kanji(id TEXT PK, character TEXT, keyword TEXT, frame INTEGER, stroke_count INTEGER, jlpt TEXT,
      owner_id INTEGER, visibility TEXT CHECK(public|private), script TEXT CHECK(ja-kanji|zh-Hans|zh-Hant|zh-Hani),
      variant_of TEXT → kanji.id,   -- simplified<->traditional link
      image_url TEXT)   -- server-relative /uploads/{id}.{ext} path, for glyph-less user-invented primitives
aliases(kanji_id → kanji.id, alias TEXT, owner_id INTEGER, visibility TEXT)  -- UNIQUE(kanji_id, alias, owner_id)
parts(kanji_id → kanji.id, part_term TEXT, position INTEGER, decomposition_id → decompositions.id)
decompositions(id PK, kanji_id → kanji.id, owner_id INTEGER, visibility TEXT, label TEXT)
stories(id PK, kanji_id → kanji.id, owner_id INTEGER, visibility TEXT, story TEXT)  -- UNIQUE(kanji_id, owner_id)
decomposition_reviews(id PK, decomposition_id → decompositions.id, kanji_id → kanji.id,
      verdict TEXT CHECK(approved|disputed), reviewer_id → users.id, created_at TEXT,
      processed_at TEXT)  -- UNIQUE(decomposition_id, reviewer_id)
users(id PK, username TEXT UNIQUE, password_hash TEXT, auth_provider TEXT, display_name TEXT,
      ui_language TEXT CHECK(en|ru), study_script TEXT CHECK(ja-kanji|zh-Hans|zh-Hant))
sessions(token PK, user_id → users.id, expires_at TEXT)
page_views(id PK, visitor_id TEXT, path TEXT, viewed_at TEXT)  -- no owner_id/visibility; see Analytics below
```

`migrate_schema()` is versioned (`PRAGMA user_version`), each version's body in its own
`_migrate_vN(conn)` function gated by `if version < N` — v1 added the multi-user tables
above (minus the last two `users` columns), v2 added `users.ui_language`/`study_script`,
v3 added `kanji.image_url`, v4 added `decomposition_reviews`, v5 added `page_views`.
Adding a v6 means adding a new `_migrate_v6` + `if version < 6` block, **not** touching
the existing gated blocks (they must stay non-idempotent-safe, i.e. never re-run against
an already-migrated DB).

Key points:
- `id=1` in `users` is a reserved **system** account that owns all Heisig-seeded and hanzi-seeded data; it's immutable to normal users by construction (`set_visibility` rejects `owner_id = 1`, and nothing in the write API lets a caller set `owner_id` to 1).
- A kanji can have **multiple decompositions** from different owners (the old schema assumed exactly one). `parts` rows are always scoped to a `decomposition_id`, not just a `kanji_id`.
- There is no `ambiguity` table — primitive terms resolve to a single canonical kanji id via `resolve_alias()`.
- New user-created kanji/primitive entries get ids via `next_user_entry_id()` — `usr{n}` from a dedicated `AUTOINCREMENT` counter table (`user_entry_seq`), collision-free and never reused.

### Visibility model

Every read function in `database.py` takes an optional `viewer_id: int | None`. `None` = anonymous, sees only `visibility = 'public'` rows. A logged-in viewer additionally sees their own private rows. The SQL pattern throughout is `(visibility = 'public' OR owner_id = ?)` with `viewer_id` bound — when `viewer_id` is `None`, `owner_id = NULL` is never true in SQL, so this collapses to "public only" automatically, no special-casing needed. Search (`search_by_parts`) considers a primitive "present" if it appears in *any* decomposition visible to the viewer — once a user adds their own decomposition, it participates in search too, not just the system one.

### Auth (`backend/auth.py`)

Session-cookie auth. `POST /auth/register` / `/auth/login` / `/auth/google` all set the same `httponly`, `secure`, `samesite=lax` cookie (`kanji_session`) backed by a `sessions` row (30-day TTL, pruned on each new login). `current_user` is an optional-auth FastAPI dependency (returns `None` if not logged in) used on all read endpoints to determine `viewer_id`; `require_user` is the same but 401s, used on all write endpoints in `contributions.py`. `current_user`/`/auth/me`/`register`/`login`/`google_login` all also return `ui_language`/`study_script`, and `PATCH /auth/preferences` (behind `require_user`, using `body.model_dump(exclude_unset=True)` so `{"study_script": null}` can explicitly clear a preference vs. omitting the field to leave it alone) updates them. `register()`/`google_login()` accept optional `ui_language`/`study_script` in their body so a fresh account inherits whatever the client already had in `localStorage` instead of resetting to English.

**Google SSO**: `users.auth_provider`/`provider_user_id` (added by `_migrate_v1`, unused until now) distinguish a `'google'` account from a `'local'` one; `password_hash` is `NULL` for Google accounts, so `login()`'s `verify_password` check naturally rejects password login on them (same generic "invalid username or password" error, no separate SSO-only branch needed — see the comment above that check). Uses the client-side [Google Identity Services](https://developers.google.com/identity/gsi/web) button, not a server-redirect OAuth code flow: the frontend (`AuthBar.jsx`, dynamically loading `accounts.google.com/gsi/client`) gets a signed ID token JWT straight from Google and POSTs it as `credential` to `POST /auth/google`, which verifies it server-side via `google.oauth2.id_token.verify_oauth2_token` (checks signature, audience, expiry) before trusting any claim in it. This means there's no client secret anywhere — the `GOOGLE_CLIENT_ID` env var (`backend/auth.py`) and `VITE_GOOGLE_CLIENT_ID` build-time var (`frontend/.env`, see `.env.example`) are both just the public OAuth client id, required to be the *same* value on both sides (the frontend requests the token as that audience; the backend checks the token was issued for that audience). Get one from [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → OAuth client ID → Web application, with the app's origins (`http://localhost:5173` for dev, `https://srv.alteon.help` for prod) under "Authorized JavaScript origins" (no redirect URI needed for this flow). If `GOOGLE_CLIENT_ID` isn't set, `/auth/google` 500s and the frontend simply doesn't render the button (`AuthBar.jsx` checks `VITE_GOOGLE_CLIENT_ID` truthiness) — safe to leave unconfigured. First-time sign-in derives a username from the email local-part (deduped with a numeric suffix on collision) since the schema has no email column; a Google sign-in never merges into an existing local account with a matching username — the two provider types simply don't dedupe against each other, so the same person can end up with two separate accounts if they use both paths.

### Contributions API (`backend/contributions.py`)

All endpoints require auth (`require_user`) and always write an explicit `owner_id` — never system. Lets a logged-in user add a new kanji/hanzi entry, add a decomposition (list of parts) to any kanji visible to them, add an alias, or add/update their own mnemonic story (one story per `(kanji, owner)`, upsert on resubmit). Visibility on any owned row (kanji/alias/decomposition/story) can be toggled public/private via `PATCH .../visibility`; `set_visibility()` doubles as the "system rows are immutable" guard since it filters `owner_id != 1`.

**Frontend UI**: login/register, plus a "Sign in with Google" button when `VITE_GOOGLE_CLIENT_ID` is set (`AuthBar.jsx`); on the kanji detail page, adding a personal alias to the kanji itself or to a decomposition part, writing your own mnemonic story, uploading a picture for a glyph-less kanji, and adding an alternate decomposition (all private by default); a dedicated create-kanji flow (`CreateKanji.jsx`) and a contributions browser with per-row visibility toggles (`MyContributions.jsx`), both reachable from header nav buttons shown only when logged in.

**Decomposition review queue** (`decomposition_reviews` table, added 2026-08-25): any logged-in user can mark a decomposition on the detail page "approved" or "disputed" (`POST /decompositions/{id}/review`, `KanjiDetail.jsx`'s two buttons under each decomposition block) — this is the search-quality audit's standing "render it, don't just reason about it" verification practice (see `render_glyphs.py` above) exposed as something anyone can do from the page itself, not only inside an audit session. One row per `(decomposition, reviewer)`, upserted on a changed vote (`set_decomposition_review`). `backend/review_queue.py` is the maintainer-facing other half: lists pending (`processed_at IS NULL`) reviews so a maintainer can turn approvals into pinned `test_regression_fixes.py` entries and investigate disputes, then clear each one with `--mark-processed <id>...` — rows are marked processed, never deleted, so there's still an audit trail of what was reviewed and by whom.

### Analytics (`backend/analytics.py`, added 2026-08-29)

A minimal first-party visit counter, added after nginx access-log analysis showed the site's raw traffic is almost entirely bots/scanners (port scanners, AI/search crawlers, a residential-proxy botnet reusing one canned user-agent) with no quick way to tell how many real visitors there actually are. `POST /analytics/pageview` (no auth required, called once on app mount from `App.jsx` via `recordPageView()` in `api.js`, fire-and-forget — a failure here never affects the app) inserts one `page_views` row tagged with a `visitor_id`: read from the `kanji_visitor` cookie if present, otherwise a fresh `secrets.token_hex(16)` that gets set as a new cookie (same flags as the session cookie in `auth.py` minus `httponly`, since nothing sensitive is in it and there's no need to keep it from client JS; 1-year `max_age`). Deliberately not IP-based — a bot that only ever hits URLs directly, which is most of this site's raw traffic, never runs the frontend JS that calls this endpoint, so this naturally excludes it in a way parsing web server logs can't. `backend/visit_stats.py` is the owner-facing read side (today/7d/30d/all-time summary, or `--days N` for a daily breakdown) — same "one-off script reads `kanji.db` directly" convention as `review_queue.py`/`coverage_status.py` rather than a public HTTP stats endpoint, since there's no admin-role concept in this schema.

### Script-aware resolution (cross-script ambiguity)

Most `ja-kanji` rows share their glyph with a separate `zh-*` row from the hanzi import (e.g. `一` exists as both `rtk1` and `hanzi-4e00`, each with their own `一` alias — ~2,628 characters like this, by design, see Known limitations). `SCRIPT_VISIBILITY` (`backend/database.py`) maps a study-language choice to the `kanji.script` values it should match (a Chinese variant also includes the script-neutral `zh-Hani` rows). `resolve_alias()`/`get_all_aliases_for_term()` take an optional `script_scope` to break ties toward the active study-language filter when a term is ambiguous across scripts; `_resolve_parts_detail()` (decomposition-chip resolution) instead derives its scope from the **viewed kanji's own** script (via `_script_group`), independent of the viewer's global preference — a Chinese hanzi's decomposition always resolves within Chinese-appropriate rows.

### Search logic (`backend/database.py`, mirrored — pre-multi-user, pre-script-awareness — in `rtk.py` for the CLI)

- **By parts** (`search_by_parts`) — for each input term, a primitive counts as present if it's *reachable* within `depth` levels of a kanji's decomposition tree, via `_reachable_kanji_for_term` (BFS over the reverse decomposition graph — `_kanji_with_part_terms` finds one layer of "who directly lists this", `_terms_for_kanji_ids` turns newly-found kanji into the next layer's search terms). `depth=1` (the default, and the historical/only behavior before 2026-08-15) is a direct match only: the term must appear literally in some visible decomposition of the kanji itself, **or** the kanji *is* that term (self-identity: a kanji "is made of" itself, e.g. searching `["weep", "water"]` must still return the "weep" hanzi even though it doesn't literally list itself as one of its own parts — only "water" does). `depth > 1` also matches a part's part, recursively, through *every* alternative decomposition at each level (a kanji taught two different ways matches via either) — so at `depth=3`, searching "corpse" also finds 壁 (壁→辟→尸/corpse) even though 壁's own parts never say "corpse". This is a deliberate, large trade-off: a common primitive's reachable set grows fast with depth ("mouth" reaches ~65% of all rtk kanji at depth=5), so the API requires the caller to pass `depth` explicitly (validated to `1..MAX_DECOMPOSITION_DEPTH`) rather than defaulting to the broadest setting — the frontend exposes it as a user-facing "search depth" selector on the parts-search form, defaulting to 1. Multiple terms are still required — a per-term reachable-kanji-id set, intersected. Takes an optional `script` (one of `SCRIPT_VISIBILITY`'s keys) that both filters candidate kanji by `k.script` and scopes alias expansion for ambiguous terms, and an optional `sources` that restricts which decompositions are consulted for matching at *every* depth level, not just the first.
- **By text** (`search_by_substring`) — whole-word match against `kanji.id`, `kanji.keyword`, and `aliases.alias`: the field (commas normalised to spaces first, since keywords/aliases can be comma-separated synonym lists) is padded with a leading/trailing space and matched against `LIKE '% q %'`, so "hat" matches "hat"/"bamboo hat"/"hat, cap" but not "hate", "hatchet", "chatter", or "what". Filtered to visible rows; same optional `script` filter. Not recursive — always a flat match, independent of parts-search depth.
- **By character** (`search_by_char`) — exact match on `kanji.character`; a viewer's own private duplicate of a public glyph takes precedence over the public one for them; same optional `script` filter.
- `get_kanji_detail` returns the canonical entry plus every decomposition/alias/story visible to the viewer, each tagged with its owning username — owner-grouped, since a kanji can now have contributions from multiple people. Every decomposition (not just one) renders as its own line in `KanjiDetail.jsx` — no more tab strip forcing a pick. Each part's own sub-decomposition(s) work the same way, recursively: `_resolve_parts_detail` attaches `sub_decompositions: [{id, label, owner, parts: [...]}, ...]` per part (via the shared `_list_decompositions` helper) rather than picking one — a part with two alternative decompositions of its own (e.g. a system one and a user's own) shows both when expanded, all the way down the tree, bounded by `MAX_DECOMPOSITION_DEPTH` and an ancestor-chain cycle guard.

`frontend/src/App.jsx` adds a UX-level fallback on top of this: a single-term parts search that returns zero results automatically retries as a text search and shows a note explaining the fallback (mostly a backstop for keyword typos now that self-identity matching covers the "search for one atomic primitive by itself" case). When a kanji has more than one visible decomposition, `KanjiDetail` shows a tab strip (label, or owner, or `#N`) and renders whichever one is selected — not just `decompositions[0]`.

### Internationalization & study-language filter (frontend)

`frontend/src/i18n.js` is a flat `{en: {...}, ru: {...}}` string dictionary plus a `t(lang, key, ...args)` helper (function-valued entries handle interpolation/pluralization) — no external i18n library. `App.jsx` holds `uiLang`/`studyScript` state, initialized from `localStorage` and overridden by the account's saved values once `/auth/me` resolves for a logged-in user; changes sync back via `PATCH /auth/preferences` when logged in. The study-language `<select>` (All / Japanese / Chinese Simplified / Chinese Traditional) maps directly to the `script` param threaded through every search call — no separate two-step picker.

### Frontend

`frontend/src/api.js` picks the backend base URL from `import.meta.env.DEV`: `http://localhost:8000` in dev, `/kanji/api` in production (nginx proxies that path to the backend — see Deployment). All `fetch` calls send `credentials: 'include'` so the session cookie round-trips.

```
frontend/src/
  App.jsx              # Root component, tab state (parts/text/char), uiLang/studyScript state, search dispatch + fallback logic
  App.css              # All styles (dark theme, CSS variables)
  api.js               # fetch wrappers for all backend endpoints
  i18n.js              # en/ru string dictionary + t(lang, key, ...args)
  utils.js             # displayChar() — hides placeholder "?"/"??" glyphs for unidentified kanji
  components/
    KanjiCard.jsx        # Single result card (char/image + keyword + id)
    ResultsGrid.jsx      # Grid of KanjiCards with loading/empty state
    KanjiDetail.jsx      # Detail panel: aliases, decomposition tabs + parts as clickable chips, image upload, add-decomposition/part-name/mnemonic-story forms, per-decomposition approve/dispute review buttons — also exports ImageUpload and DecompositionForm for reuse in CreateKanji.jsx
    CreateKanji.jsx      # Create a new kanji/hanzi entry, then optionally attach a picture and/or a decomposition inline
    MyContributions.jsx  # Browse everything you've contributed (kanji/decompositions/aliases/stories) with per-row public/private toggles
    AuthBar.jsx          # Login/register popover, logged-in state (username + logout)
    AboutPage.jsx        # Static project description + links to the repo and the pre-built Android APK
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/search/parts` | Body: `{"parts": ["sun", "moon"], "script": null, "depth": 1}` — kanji containing all given primitives (or self-identical to one); optional `script`/`sources` filters; `depth` (1..`MAX_DECOMPOSITION_DEPTH`, default 1) controls how many decomposition levels to recurse through — see "Search logic" below |
| `GET` | `/search/text?q=hat&script=` | Kanji whose id, keyword, or any visible alias contains the term as a whole word; optional `script` filter |
| `GET` | `/search/char?c=明&script=` | Look up a kanji by its character glyph; optional `script` filter |
| `GET` | `/kanji/{id}` | Full detail for one kanji (aliases + decompositions + stories, owner-grouped) |
| `POST` | `/auth/register` | `{"username", "password", "ui_language"?, "study_script"?}` — creates a user, sets session cookie |
| `POST` | `/auth/login` | `{"username", "password"}` — sets session cookie |
| `POST` | `/auth/google` | `{"credential", "ui_language"?, "study_script"?}` — `credential` is a Google Identity Services ID token; verifies it, creates the account on first sign-in, sets session cookie |
| `POST` | `/auth/logout` | Clears the session |
| `GET` | `/auth/me` | Current session's user + `ui_language`/`study_script`, or `{"authenticated": false}` |
| `PATCH` | `/auth/preferences` | `{"ui_language"?, "study_script"?}` — updates only the fields present (auth required) |
| `POST` | `/kanji` | Add a new kanji/hanzi entry (auth required) |
| `POST` | `/kanji/{id}/image` | Attach/replace a picture for a kanji you own (multipart upload, gif/png/jpeg/webp, max 2MB) — for user-invented primitives with no real Unicode glyph (auth required) |
| `POST` | `/kanji/{id}/decompositions` | Add a decomposition (list of parts) to a kanji (auth required) |
| `POST` | `/aliases` | Add an alias to a kanji (auth required) |
| `POST` | `/stories` | Add/update your mnemonic story for a kanji (auth required) |
| `PATCH` | `/kanji\|aliases\|decompositions\|stories/{id}/visibility` | Toggle public/private on a row you own |
| `POST` | `/decompositions/{id}/review` | `{"verdict": "approved"\|"disputed"}` — record your own approve/dispute verdict on a decomposition (auth required); upserts on a changed vote |
| `GET` | `/me/contributions` | Everything you've contributed, across all four tables |
| `POST` | `/analytics/pageview` | `{"path"?}` — records one visit; no auth required, sets/reads the `kanji_visitor` cookie (see Analytics above) |

`script` (on the three search endpoints and `study_script`) is one of `ja-kanji`/`zh-Hans`/`zh-Hant` — an invalid value 400s. Search/detail endpoints all take the caller's session (if any) to determine which private rows are visible; there is no `/admin/reimport` anymore (see Architecture).

Uploaded images are written to `backend/uploads/{id}.{ext}` (filename always server-derived from the DB-resolved canonical kanji id, never client input) and served back at `/uploads/...` via a `StaticFiles` mount in `main.py`; `kanji.image_url` stores that server-relative path, and `frontend/src/api.js::resolveImageUrl` resolves it against the same `BASE` used for API calls. `backend/uploads/` is gitignored and, like `kanji.db`, not covered by `backup_db.py`. Note `upload_kanji_image` in `contributions.py` is a **sync** `def`, not `async def` — the `db_conn` dependency's sqlite3 connection is thread-affine (`check_same_thread=True`), and an async endpoint body runs on the event loop thread while the dependency was resolved on a threadpool thread, which throws `sqlite3.ProgrammingError`. Every other endpoint in this codebase is sync for the same reason; keep new endpoints sync unless you also rework how `conn` is obtained.

## Deployment

Live at `srv.alteon.help/kanji/` (shared EC2 box running other projects too). Frontend is a Vite build (`base: '/kanji/'`) copied to `/usr/share/nginx/html/kanji/`; backend runs as systemd service `kanji-backend.service` on `127.0.0.1:8000`, proxied by nginx at `/kanji/api/` (prefix stripped). Needs `python3.11` (backend venv) and `node-20` (build only) — the box's system Python/Node are too old. `backup_db.py` is meant to run on a systemd timer (`kanji-db-backup`) against the live `kanji.db`. Any backend code change needs `sudo systemctl restart kanji-backend.service` to take effect (unlike frontend rebuilds, which just need the new `dist/` copied over) — restarting re-runs `migrate_schema()` against the live DB, which is safe (idempotent) but back up first (`backup_db.py`) before a schema-changing deploy, same as before any direct DB script run. The `origin` remote pushes over SSH (`git@github.com:vk2705/kanji.git`), not HTTPS — GitHub has no password auth for git operations.

Google SSO needs `GOOGLE_CLIENT_ID=<the OAuth client id>` set in `kanji-backend.service`'s environment (`systemctl edit kanji-backend.service` → `[Service]` `Environment=`, then restart) and the same value baked into the frontend build via `frontend/.env`'s `VITE_GOOGLE_CLIENT_ID` (Vite inlines it at `npm run build` time — changing it needs a rebuild, not just a restart). Both are the public client id, not a secret; see the Auth section above.

## Known limitations / next steps

- `rtk.py` CLI doesn't understand `visibility`/`owner_id`/`script` — dev/debug use only.
- No moderation/review step for public user-submitted content.
- ~2,628 characters intentionally have both an `ja-kanji` row and a separate `zh-*` row for the same glyph (e.g. `rtk1701` and `hanzi-6f22` are both 漢) — this is a deliberate design choice (distinguish by `script`, don't dedupe), not a bug; see the script-aware resolution section above for how ambiguity is handled.
- The Heisig mnemonic story text from the book is still **not** stored (copyright); user-authored stories are a separate, non-copyrighted addition. Frame numbers link to the book.
- `android/` has a first-pass Android app: a WebView shell around the deployed `frontend/` (see `android/README.md`), not the from-scratch native REST client this section used to anticipate — cookie-session auth just works as-is since it's still a WebView under the hood. A true native client (own UI, talking to the FastAPI backend directly) is still a bigger future step if ever needed, and would need the persistent-`CookieJar`-or-token-auth switch this line originally flagged.
- `expand_part_terms`/`_build_char_lookup` (`backend/database.py`) resolve a character part to its keyword without regard to `script`, so a glyph shared between an `ja-kanji` row and a `zh-*` row (see above) can silently pick the wrong one — unlike `resolve_alias`, which already is script-scoped. Found while fixing rtk1495's decomposition; not yet fixed. See `docs/2026-08-search-quality-audit.md` (session 2) for details.
- Decomposition display/data is fully flattened to atomic primitives (e.g. 懸 shows `県,prefecture,糸,thread,心,heart`, not "prefecture" as a single expandable chip). The owner wants intermediate pieces shown too, with their own sub-decomposition available on demand — this needs the query-time recursive resolution described as an agreed-but-unexecuted architecture decision in `docs/2026-08-search-quality-audit.md`. Tracked there as the top-priority queued item.
- Bulk decomposition-quality audit (extending the rtk1495-style fix dataset-wide) and bulk original-mnemonic generation (via the new `ai-mnemonics` pseudo-account, not `owner_id=1`) are both queued but not started — see `docs/2026-08-search-quality-audit.md`'s session 2 entry for scope and the tooling (`audit_decomposition.py`) built for the first one.
- **Queued, non-urgent (owner request, 2026-08-22)**: on a `ja-kanji` kanji's detail page, surface a small badge/note comparing it to its Chinese counterpart(s) — e.g. viewing 降 would show "In Chinese: same glyph (jiàng / xiáng)"; viewing 強 would flag that the Simplified form 强 differs subtly (the 虫 component drops the dot present in the Japanese/Traditional form, per its own 弓+口+虫 structure) rather than being visually identical. The `variant_of` links and the shared-glyph `ja-kanji`/`zh-*` row pairing (see "~2,628 characters..." above) already carry most of the underlying data — a glyph-identical pair needs no extra lookup, and a genuinely different Simplified form is already a separate `kanji` row reachable via `hanzi-*` lookups by keyword/character; the new work is mostly UI (the comparison badge/tooltip) plus, for the "same glyph but subtly different stroke shape" case (like 強/强), a way to flag that distinction that doesn't already exist in the schema.
- **`tools/heisig-google-check/`** (added 2026-08-29): a standalone script meant to run on the *owner's own computer*, not the server — Google immediately CAPTCHA-blocked the first automated search request from the server's own IP (a shared AWS address Google already treats as a data-center/bot IP, not a rate-limit issue), so this can't run here. Opens a real, visible Chromium window via Playwright, looks up a batch of not-yet-reviewed kanji on Google, and saves whatever AI Overview text (plus a screenshot either way) appears, for later comparison against `data.txt`. See its own `README.md` for setup/usage and `docs/2026-08-search-quality-audit.md`'s 2026-08-29 entry for why this exists and what was tried first.
- **Queued, non-urgent (owner request, 2026-08-14)**: primitive-name inputs are plain free-text fields today — e.g. the parts input in `DecompositionForm` (`KanjiDetail.jsx`, reused by `CreateKanji.jsx`) and the alias-add inputs. Since primitives are a bounded, known vocabulary (existing `kanji.keyword`/`aliases.alias` values), these should offer live autocomplete/suggestions as the user types, matched by substring rather than prefix-only. Backend already has the substring-match logic to reuse (`search_by_substring`'s `LIKE '% q %'` whole-word pattern in `database.py`) — main new work is a lightweight suggestions endpoint (or reusing `/search/text` with a smaller response shape) plus the frontend dropdown/combobox UI. Also a natural way to cut down on the kind of orphaned/typo'd terms Finding 1 in `docs/2026-08-search-quality-audit.md` was about.
