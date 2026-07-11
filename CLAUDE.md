# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A web app for learners using **Remembering the Kanji (RTK)** by James W. Heisig. The method assigns each kanji a set of named visual "primitives" (building blocks) and a mnemonic story. This app lets you search kanji by those primitive names — e.g. type "sun" + "moon" to find 明 (bright).

It's grown beyond a personal RTK lookup tool into a community-editable reference: registered users can add their own kanji/hanzi, decompositions, aliases, and mnemonic stories (public or private), and the database also covers Chinese hanzi (simplified + traditional) alongside Japanese kanji.

## Stack

| Layer | Tech |
|---|---|
| Backend API | Python 3 + FastAPI + SQLite |
| Frontend | React 19 + Vite |
| CLI | Plain Python 3 (stdlib only), reads `backend/kanji.db` directly — no server needed |
| Data | `heisig-kanjis.csv` + flat text overlays → SQLite (one-time seed); user contributions written directly to SQLite thereafter |
| Auth | Cookie-based sessions, `bcrypt` password hashing — no external identity provider |

`cgi-bin/` (Perl) and `html/` are the original legacy app — reference only, not part of the active stack.

## Commands

**Backend** (port 8000):
```bash
cd backend
pip install -r requirements.txt   # fastapi, uvicorn, bcrypt
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

**One-off data/maintenance scripts** (`backend/`, not part of the app's runtime):
```bash
python3 import_rtk.py            # append new rtk{frame} entries to data.txt from kanjidic2 + KRADFILE
python3 import_hanzi.py          # one-time: seed Chinese hanzi (CJK Unified block) from Unihan.zip + cjkvi-ids
python3 backup_db.py             # online backup of kanji.db to backups/, prunes backups older than 14 days
```
`import_hanzi.py` refuses to run if any non-`ja-kanji` rows already exist (not safe to resume mid-run). `backup_db.py` is meant to run on a schedule (see Deployment).

There is no test suite in this repo currently.

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
- `id` — `rtk{n}` for kanji (6th-edition frame number) or `rad{n}` for pure primitives with no kanji form.
- `character` — UTF-8 glyph, or `?`/empty if not yet identified.
- `aliases` — comma-separated names; the first becomes the keyword.
- `parts` — comma-separated primitive names or kanji characters; alternate decompositions separated by `;`.
- Lines starting with `#` and blank lines are ignored. All ASCII field values are lowercased on import.

`import_rtk.py` is a one-off generator that appends new `rtk{frame}` entries to `data.txt` from kanjidic2 + KRADFILE (downloads them if not given local paths). `import_hanzi.py` is a separate one-off that writes Chinese hanzi (script `zh-Hans`/`zh-Hant`/`zh-Hani`) directly into `kanji.db` as system-owned public rows, reusing `expand_part_terms` for its IDS-derived decompositions — see the module docstring for scope and re-run safety.

### Database schema (SQLite, `backend/kanji.db` — generated, not committed)

```sql
kanji(id TEXT PK, character TEXT, keyword TEXT, frame INTEGER, stroke_count INTEGER, jlpt TEXT,
      owner_id INTEGER, visibility TEXT CHECK(public|private), script TEXT CHECK(ja-kanji|zh-Hans|zh-Hant|zh-Hani),
      variant_of TEXT → kanji.id)   -- simplified<->traditional link
aliases(kanji_id → kanji.id, alias TEXT, owner_id INTEGER, visibility TEXT)  -- UNIQUE(kanji_id, alias, owner_id)
parts(kanji_id → kanji.id, part_term TEXT, position INTEGER, decomposition_id → decompositions.id)
decompositions(id PK, kanji_id → kanji.id, owner_id INTEGER, visibility TEXT, label TEXT)
stories(id PK, kanji_id → kanji.id, owner_id INTEGER, visibility TEXT, story TEXT)  -- UNIQUE(kanji_id, owner_id)
users(id PK, username TEXT UNIQUE, password_hash TEXT, auth_provider TEXT, display_name TEXT)
sessions(token PK, user_id → users.id, expires_at TEXT)
```

Key points:
- `id=1` in `users` is a reserved **system** account that owns all Heisig-seeded and hanzi-seeded data; it's immutable to normal users by construction (`set_visibility` rejects `owner_id = 1`, and nothing in the write API lets a caller set `owner_id` to 1).
- A kanji can have **multiple decompositions** from different owners (the old schema assumed exactly one). `parts` rows are always scoped to a `decomposition_id`, not just a `kanji_id`.
- There is no `ambiguity` table — primitive terms resolve to a single canonical kanji id via `resolve_alias()`.
- New user-created kanji/primitive entries get ids via `next_user_entry_id()` — `usr{n}` from a dedicated `AUTOINCREMENT` counter table (`user_entry_seq`), collision-free and never reused.

### Visibility model

Every read function in `database.py` takes an optional `viewer_id: int | None`. `None` = anonymous, sees only `visibility = 'public'` rows. A logged-in viewer additionally sees their own private rows. The SQL pattern throughout is `(visibility = 'public' OR owner_id = ?)` with `viewer_id` bound — when `viewer_id` is `None`, `owner_id = NULL` is never true in SQL, so this collapses to "public only" automatically, no special-casing needed. Search (`search_by_parts`) considers a primitive "present" if it appears in *any* decomposition visible to the viewer — once a user adds their own decomposition, it participates in search too, not just the system one.

### Auth (`backend/auth.py`)

Session-cookie auth, no external identity provider. `POST /auth/register` / `/auth/login` set an `httponly`, `secure`, `samesite=lax` cookie (`kanji_session`) backed by a `sessions` row (30-day TTL, pruned on each new login). `current_user` is an optional-auth FastAPI dependency (returns `None` if not logged in) used on all read endpoints to determine `viewer_id`; `require_user` is the same but 401s, used on all write endpoints in `contributions.py`.

### Contributions API (`backend/contributions.py`)

All endpoints require auth (`require_user`) and always write an explicit `owner_id` — never system. Lets a logged-in user add a new kanji/hanzi entry, add a decomposition (list of parts) to any kanji visible to them, add an alias, or add/update their own mnemonic story (one story per `(kanji, owner)`, upsert on resubmit). Visibility on any owned row (kanji/alias/decomposition/story) can be toggled public/private via `PATCH .../visibility`; `set_visibility()` doubles as the "system rows are immutable" guard since it filters `owner_id != 1`.

**Frontend has no UI for any of this yet** — no login form, no contribution forms, and `frontend/src/api.js`'s `fetch` calls don't pass `credentials: 'include'`, so the session cookie wouldn't even be sent cross-origin in dev. Auth/contributions are backend-only so far.

### Search logic (`backend/database.py`, mirrored — pre-multi-user — in `rtk.py` for the CLI)

- **By parts** (`search_by_parts`) — for each input term, expand to its full alias set (`get_all_aliases_for_term`), then require each kanji to have *some* visible decomposition containing an alias from *every* input term's set (flat AND across sets, no recursion — components are pre-expanded at import/contribution time via `expand_part_terms`).
- **By text** (`search_by_substring`) — `LIKE %q%` against `kanji.id`, `kanji.keyword`, and `aliases.alias`, filtered to visible rows.
- **By character** (`search_by_char`) — exact match on `kanji.character`; a viewer's own private duplicate of a public glyph takes precedence over the public one for them.
- `get_kanji_detail` returns the canonical entry plus every decomposition/alias/story visible to the viewer, each tagged with its owning username — owner-grouped, since a kanji can now have contributions from multiple people.

`frontend/src/App.jsx` adds a UX-level fallback on top of this: a single-term parts search that returns zero results automatically retries as a text search and shows a note explaining the fallback. (It only ever renders `decompositions[0]` — the first visible decomposition — since the frontend predates multi-decomposition support.)

### Frontend

`frontend/src/api.js` picks the backend base URL from `import.meta.env.DEV`: `http://localhost:8000` in dev, `/kanji/api` in production (nginx proxies that path to the backend — see Deployment).

```
frontend/src/
  App.jsx              # Root component, tab state (parts/text/char), search dispatch + fallback logic
  App.css              # All styles (dark theme, CSS variables)
  api.js               # fetch wrappers for all backend endpoints
  components/
    KanjiCard.jsx       # Single result card (char + keyword + id)
    ResultsGrid.jsx      # Grid of KanjiCards with loading/empty state
    KanjiDetail.jsx      # Detail panel: aliases, parts as clickable chips (drills into other kanji)
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/search/parts` | Body: `{"parts": ["sun", "moon"]}` — kanji containing all given primitives |
| `GET` | `/search/text?q=brig` | Kanji whose id, keyword, or any visible alias contains the substring |
| `GET` | `/search/char?c=明` | Look up a kanji by its character glyph |
| `GET` | `/kanji/{id}` | Full detail for one kanji (aliases + decompositions + stories, owner-grouped) |
| `POST` | `/auth/register` | `{"username", "password"}` — creates a user, sets session cookie |
| `POST` | `/auth/login` | `{"username", "password"}` — sets session cookie |
| `POST` | `/auth/logout` | Clears the session |
| `GET` | `/auth/me` | Current session's user, or `{"authenticated": false}` |
| `POST` | `/kanji` | Add a new kanji/hanzi entry (auth required) |
| `POST` | `/kanji/{id}/decompositions` | Add a decomposition (list of parts) to a kanji (auth required) |
| `POST` | `/aliases` | Add an alias to a kanji (auth required) |
| `POST` | `/stories` | Add/update your mnemonic story for a kanji (auth required) |
| `PATCH` | `/kanji\|aliases\|decompositions\|stories/{id}/visibility` | Toggle public/private on a row you own |
| `GET` | `/me/contributions` | Everything you've contributed, across all four tables |

Search/detail endpoints all take the caller's session (if any) to determine which private rows are visible; there is no `/admin/reimport` anymore (see Architecture).

## Deployment

Live at `srv.alteon.help/kanji/` (shared EC2 box running other projects too). Frontend is a Vite build (`base: '/kanji/'`) copied to `/usr/share/nginx/html/kanji/`; backend runs as systemd service `kanji-backend.service` on `127.0.0.1:8000`, proxied by nginx at `/kanji/api/` (prefix stripped). Needs `python3.11` (backend venv) and `node-20` (build only) — the box's system Python/Node are too old. `backup_db.py` is meant to run on a systemd timer (`kanji-db-backup`) against the live `kanji.db`.

## Known limitations / next steps

- No frontend UI for auth or contributions yet (backend-only — see Contributions API above).
- `rtk.py` CLI doesn't understand `visibility`/`owner_id` — dev/debug use only.
- No moderation/review step for public user-submitted content.
- The Heisig mnemonic story text from the book is still **not** stored (copyright); user-authored stories are a separate, non-copyrighted addition. Frame numbers link to the book.
- Android app is planned; the FastAPI backend is designed as a REST API to serve it.
