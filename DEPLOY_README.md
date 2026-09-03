# Deploy README — syncing `data.txt` fixes to the live server

For whoever (human or agent) operates the actual production box
(`srv.alteon.help`, systemd service `kanji-backend.service`). Written to be
followed mechanically, step by step, without needing the rest of this
repo's history for context. If anything below doesn't match what you see on
the server, stop and report the mismatch rather than improvising — this
procedure touches a database that holds real user accounts.

## Why this exists (read once, then skip to Steps)

`backend/kanji.db` is **not** committed to git and is **not** a rebuildable
cache — see `CLAUDE.md`'s "Architecture" section for the full reasoning.
The short version:

- The database seeds itself from `heisig-kanjis.csv` / `data_from_pdf.txt` /
  `data.txt` exactly **once**, the first time the backend starts against an
  empty database. Once it holds data, that seeding step becomes a no-op —
  there is no `/admin/reimport` endpoint, deliberately.
- This means: **a plain `git pull` + service restart does NOT pick up an
  edit to `data.txt`.** The restart only re-runs an idempotent schema
  migration, not a reseed.
- **Never delete `kanji.db` to force a reseed.** The same file holds every
  real user's account, private decompositions, and stories. Deleting it
  destroys all of that, not just the stale system data.

`backend/sync_system_data.py` (added 2026-08-14) solves this properly: it
diffs the live database's system rows against the current source files and
applies only the difference, touching nothing that belongs to a real user
— even a user's own alternate decomposition sitting on the same kanji a
system fix touches. Full design rationale and an end-to-end test log are in
`docs/2026-08-search-quality-audit.md`'s session 6 entry, if you want the
detail; you don't need to read it to run this procedure.

## Step 1 — pull

```bash
cd /path/to/kanji     # wherever this repo is checked out on the server
git pull
```

## Step 2 — sync the database

```bash
cd backend
python3 sync_system_data.py --dry-run
```

Read the output. It reports counts only, e.g.:

```
kanji:          11 inserted, 0 updated
aliases:        33 added, 0 removed
decompositions: 0 created, 1292 replaced, 1 removed (now atomic)

No changes — live DB already matches the source files.
```

A large "replaced" number is not inherently alarming — one content fix in
`data.txt` can ripple into many decompositions (e.g. naming a previously
unnamed primitive makes it auto-expand into every kanji that already used
it). If the counts look sane, apply for real:

```bash
python3 sync_system_data.py
```

This automatically backs up `kanji.db` first (as
`kanji.db.bak-<timestamp>`, next to it) and runs in a single transaction —
if anything goes wrong mid-run it rolls back and leaves the database
exactly as it was, so a partial failure is safe to just retry.

If the script reports "No changes", nothing was needed — that's the normal
case when `git pull` didn't touch `data.txt`/`data_from_pdf.txt`/
`heisig-kanjis.csv`.

**Do not run `backend/fix_kradfile_proxies.py` separately** — it's an
older one-off script that `sync_system_data.py` fully supersedes (it
already applies that exact fix, generically, alongside everything else).

## Step 3 — restart the backend

```bash
sudo systemctl restart kanji-backend.service
```

(Only needed if the backend *code* changed, e.g. `database.py`/`main.py` —
`sync_system_data.py` writes directly to `kanji.db` and takes effect
immediately, no restart required for a data-only sync. Restart anyway if
unsure; `migrate_schema()` re-running is always safe/idempotent.)

## Step 4 — verify

Pick one or two kanji the pulled commit's changelog mentions and spot-check
them, e.g.:

```bash
python3 rtk.py detail rtk355
```

or hit the live API directly:

```bash
curl -s "https://srv.alteon.help/kanji/api/kanji/rtk355" | python3 -m json.tool
```

## Scheduled backup and tested restore

`backend/backup_db.py` creates a consistent SQLite backup and a matching
`uploads-<timestamp>.tar.gz` when uploads exist. Local copies alone are not disaster
recovery: host loss would remove both production and `backend/backups/`.

Configure an encrypted or otherwise access-controlled `rclone` remote outside this
repository, set `KANJI_BACKUP_REMOTE`, and schedule `backend/offsite_backup.py` after
the local backup timer. The script creates a fresh paired backup and uploads only the
new artifacts. Configure retention/versioning with the destination provider rather
than deleting remote copies from this host.

```bash
rclone config
export KANJI_BACKUP_REMOTE='encrypted-remote:kanji-production'
cd backend
./venv/bin/python3 offsite_backup.py
rclone lsf "$KANJI_BACKUP_REMOTE"
```

Restore only while the backend is stopped. Download a matching database/upload pair,
restore into the backend directory, run the integrity check, then restart and smoke
test. Omitting `--uploads` intentionally restores an empty uploads directory.

```bash
sudo systemctl stop kanji-backend.service
cd backend
./venv/bin/python3 restore_backup.py \
  /path/to/kanji-YYYYMMDD-HHMMSS.db \
  --uploads /path/to/uploads-YYYYMMDD-HHMMSS.tar.gz \
  --target-dir . --confirm
sqlite3 kanji.db 'PRAGMA integrity_check;'
sudo systemctl start kanji-backend.service
curl -fsS 'https://srv.alteon.help/kanji/api/search/text?q=one' >/dev/null
```

Practice this restore into a temporary directory periodically. A backup is not
considered healthy until the restored database passes integrity checks and a sample
upload is readable.

## Periodic anonymized export

Separately from the above (do this on whatever cadence you prefer, not
necessarily every deploy), commit an anonymized snapshot of the live
database to the repo as an audit/data-portability snapshot:

```bash
export BACKUP_ANON_SECRET=...   # pick once, store it securely, NEVER commit it
cd backend
python3 export_backup.py
cd ..
git add backend/kanji_export.jsonl
git commit -m "Update DB backup snapshot"
git push
```

`export_backup.py` dumps every kanji/alias/decomposition/part/story (public
*and* private, one JSON object per line) with every real username replaced
by an HMAC-keyed pseudonym — it never reads `password_hash` or the
`sessions` table, so it cannot leak credentials. `BACKUP_ANON_SECRET` must
stay wherever the server's other secrets already live (e.g. next to
`GOOGLE_CLIENT_ID` in the systemd unit's environment) and must never be
committed alongside the export it protects.

`export_backup.py` is not the disaster-recovery source: pseudonymization intentionally
removes the identity information needed to reconstruct real accounts, and it excludes
credentials, sessions, and upload files. Restore production from the encrypted raw
database/upload backups described above.

## SEO / getting Google to find the site (added 2026-09-01, owner request)

The frontend build now ships `/kanji/robots.txt` and `/kanji/sitemap.xml`
automatically (`frontend/public/robots.txt` / `sitemap.xml`, copied to
`dist/` by the normal `npm run build` step) — no extra action needed beyond
the usual frontend rebuild-and-copy-to-`/usr/share/nginx/html/kanji/` deploy
step described in `CLAUDE.md`'s Deployment section. `index.html` also now
has a real `<title>`/`<meta description>`/canonical URL/Open Graph tags
instead of the bare `RTK Kanji Search` title it shipped with before.

That covers everything reachable from *this* repo. Three more steps need
someone with server access and/or the owner's Google account — none of them
are things this repo (or an AI session without server/Google credentials)
can do on its own:

1. **Domain-root `robots.txt`.** Crawlers check `https://srv.alteon.help/robots.txt`
   at the domain root by default — a path this repo's nginx config doesn't
   own (the box is shared with other projects; see `deploy/nginx/README.md`).
   Check whether a root `robots.txt` already exists (`curl -s
   https://srv.alteon.help/robots.txt`). If it doesn't exist yet, or exists
   and doesn't already disallow `/kanji/`, add (coordinate with whoever owns
   the other projects on this box before overwriting an existing one):
   ```
   User-agent: *
   Allow: /kanji/
   Sitemap: https://srv.alteon.help/kanji/sitemap.xml
   ```
   If a root `robots.txt` already exists and disallows everything (or
   disallows `/kanji/` specifically), that alone would fully block Google
   regardless of anything else here — check this first.
2. **Google Search Console.** Needs the owner's Google account, so has to be
   done by a human:
   - console.google.com/search-console → Add property → URL prefix →
     `https://srv.alteon.help/kanji/`.
   - Verify ownership — easiest is the "HTML tag" method: paste the
     `<meta name="google-site-verification" content="...">` tag Search
     Console gives you into `frontend/index.html`'s `<head>` (ask a future
     session to add it and redeploy, or add it directly) and reload the
     verification page. The "HTML file upload" method also works if Search
     Console accepts a subpath property served from `/kanji/<file>` (drop
     the given file into `frontend/public/`) — if it insists on a
     domain-root path instead, that needs the same shared-box coordination
     as the robots.txt step above.
   - Once verified: Sitemaps → submit `https://srv.alteon.help/kanji/sitemap.xml`.
   - URL Inspection tool → paste `https://srv.alteon.help/kanji/` → "Request
     Indexing" — this is the fastest way to get the first crawl to happen,
     rather than waiting for Google to discover the site organically.
3. **Known limitation: only one URL exists to index.** The frontend is a
   single-page app with no client-side routing (`App.jsx` has no
   react-router or URL-based state) — every kanji search happens without
   the URL ever changing, so Google can only ever index
   `https://srv.alteon.help/kanji/` itself, not individual kanji. That's
   fine for "can people find the site at all", but it means there's no way
   to rank for e.g. a specific kanji search term, and the sitemap above is
   necessarily a single `<url>` entry. Giving each kanji (or at least the
   detail view) its own URL — e.g. `/kanji/k/明` — would be a real,
   separate feature project (routing, server-side meta tags or
   prerendering per kanji for the crawler to see actual content instead of
   an empty `<div id="root">`) if deeper discoverability is wanted later;
   not attempted here.

`backend/visit_stats.py` (see `CLAUDE.md`'s Analytics section) is how to
check afterward whether any of this actually brought real visitors — it
already excludes bots that only ever hit URLs directly without running the
frontend JS, so a genuine uptick there is a genuine uptick, not crawler noise.

## Google Sign-In button not appearing (added 2026-09-02, owner report)

If the "Sign in with Google" button doesn't show up on the login popover at
all (not "shows an error", just entirely absent), this is almost always a
missing build-time config value, not a code bug — `AuthBar.jsx` skips
loading the Google script entirely when `VITE_GOOGLE_CLIENT_ID` is falsy
(`frontend/.env`), by design (see the comment right above that check).
Vite bakes this in at **build time**, not runtime, so setting the value
alone does nothing until the frontend is rebuilt and redeployed.

Needs the owner's own Google account — can't be done by an AI session:

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   → Create OAuth client ID → Web application → Authorized JavaScript
   origins: `https://srv.alteon.help` (and `http://localhost:5173` for local
   dev). No redirect URI needed (this uses Google Identity Services'
   client-side token flow, not a server redirect).
2. The resulting Client ID is a public identifier, not a secret — set the
   *same* value in two places:
   - Backend: `sudo systemctl edit kanji-backend.service` → add
     `Environment=GOOGLE_CLIENT_ID=<id>` under `[Service]` → restart.
   - Frontend: `frontend/.env` → `VITE_GOOGLE_CLIENT_ID=<id>`.
3. Rebuild the frontend (`npm run build`) and copy `dist/` to
   `/usr/share/nginx/html/kanji/` — a `.env` edit alone does not take
   effect without this step.
4. Verify: reload the live site, open the login popover, confirm the
   Google button now renders. If it renders but sign-in itself fails,
   that's a *different* problem (client ID mismatch between frontend/
   backend, or wrong authorized origin) — check the backend logs for the
   actual `verify_oauth2_token` exception rather than guessing.

See `CLAUDE.md`'s "Google SSO" section for the full design (why both a
frontend and backend value are needed, and why they must match).

## Frontend change deployed but the live site still shows old behavior (added 2026-09-04, recurring owner report)

This has now come up more than once (SEO tags, the decomposition dispute
button) — the fix is committed and pushed, the owner redeploys, and the
live site still behaves like before. This is a **frontend build/deploy**
issue, not a backend or data issue — nothing here touches `sync_system_data.py`
or the database. Frontend code changes (anything under `frontend/src/`,
e.g. `AuthBar.jsx`, `KanjiDetail.jsx`) need their own separate deploy step
that's easy to skip or get wrong:

1. **Rebuild, don't just `git pull`.** `git pull` only updates the source
   files on the server; it does **not** regenerate `frontend/dist/`. You
   must run `cd frontend && npm install && npm run build` after pulling,
   then copy the *new* `dist/` output to wherever nginx serves it from
   (per `CLAUDE.md`'s Deployment section: `/usr/share/nginx/html/kanji/`)
   — copying the whole directory (overwriting old files), not merging.
   The single most common cause of "I redeployed but nothing changed" is
   this step being skipped or copying to the wrong path.
2. **Verify the copy actually landed** before blaming the browser: `ls -la
   /usr/share/nginx/html/kanji/assets/` on the server and check the
   filenames/timestamps are from *just now*, not from an earlier deploy.
   Vite fingerprints each JS/CSS file's name with a content hash, so a
   real rebuild always produces different filenames — if the filenames
   in that directory match what a previous deploy already had, the build
   either didn't run or didn't get copied.
3. **Then, and only then, suspect the browser.** A hard refresh
   (Ctrl+Shift+R / Cmd+Shift+R) or a private/incognito window rules out
   stale cached `index.html`/JS in one step. If the deployed files are
   confirmed fresh (step 2) but a normal reload still shows old behavior,
   check whether nginx is serving `index.html` itself with a long
   `Cache-Control`/`Expires` header — content-hashed asset files (the
   `.js`/`.css` under `assets/`) are safe to cache forever, but
   `index.html` (which references those filenames) should not be, or
   browsers can keep using an old `index.html` pointing at old assets
   indefinitely. This project's own nginx config isn't tracked in this
   repo (see `deploy/nginx/README.md`), so check the live config directly
   for an overly broad cache rule covering `index.html`.
4. **A feature needing login** (like the dispute button) also needs a
   real logged-in session and a kanji that actually has a decomposition
   to review — the review buttons render per-decomposition, so a kanji
   with none yet (e.g. a user-created one nobody has decomposed) won't
   show them; that's expected, not a bug. Confirmed working end-to-end
   locally (register/login → search a normal kanji like 明 → the
   ✓ Approve / ✗ Dispute buttons appear under "Made from") as of the
   2026-09-04 session — if it's still missing on the live site after
   confirming steps 1-3 above, the deploy genuinely hasn't picked up the
   current frontend build yet.

## If something looks wrong

- `sync_system_data.py` refuses to run against a database file that
  doesn't exist yet (it syncs an *already-seeded* live DB; a brand-new
  install seeds itself automatically on first backend startup instead —
  don't run this script before that first startup has happened).
- If a sync applied something you don't want, the timestamped backup it
  took (Step 2) is a plain SQLite file — stop the service, swap it back in
  as `kanji.db`, restart.
- For anything not covered here, `CLAUDE.md`'s "Architecture" and
  "Deployment" sections are the source of truth for how this project is
  meant to run; `docs/2026-08-search-quality-audit.md` has the full history
  of why these scripts exist.
