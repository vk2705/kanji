# Deploy README — syncing `data.txt` fixes to the live server

For whoever (human or agent) operates production. **As of 2026-09-20,
production is `kanji.alteon.help`, a dedicated Oracle Cloud VM
(161.153.96.217) running nothing but this app** (repo checked out at
`/opt/kanji`, backend under `/opt/kanji/backend`, frontend built to
`/opt/kanji/frontend/dist`). `srv.alteon.help` (this repo's original EC2
host) is **dev-only now** — it's a shared box that also runs other
projects, and its own copy of `kanji-backend.service`/`kanji.db` holds only
dev data, never real user accounts. Everywhere below that says "the server"
means the prod VM unless a step says otherwise. See `deploy/nginx/README.md`
for the full dev-vs-prod layout differences (path prefix, nginx config
shape, frontend build command). Written to be followed mechanically, step
by step, without needing the rest of this repo's history for context. If
anything below doesn't match what you see on the server, stop and report
the mismatch rather than improvising — this procedure touches a database
that holds real user accounts.

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
cd /opt/kanji     # prod checkout on the dedicated VM (161.153.96.217)
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

Run the smoke test. It is not optional and it is not a ping: it checks that
**every seeding step actually ran**, because the 2026-09-20 prod move seeded the
database from `data.txt` + the CSV and stopped there. `import_hanzi.py`,
`backfill_readings.py` and `add_ru_aliases.py` never ran, the site came up,
every page rendered, every Japanese search worked — and the Chinese
study-language options returned zero results for *everything* until an owner
searched for "finger" a day later and found nothing.

```bash
cd /opt/kanji/backend
./venv/bin/python3 deploy_smoke_test.py --service kanji-backend.service
```

Thirteen checks, in four groups:

| group | what it proves |
|---|---|
| service + API | the unit is active, `日` resolves, `明`'s detail loads |
| Japanese seed | a common primitive returns 100+ kanji; `sun`+`moon` finds 明; the primitive *name* `finger` finds 扌; autocomplete offers it |
| the one-off scripts | `zh-Hans` and `zh-Hant` each return a couple of dozen rows (`import_hanzi.py`), 日 has on'yomi and a hanzi has pinyin (`backfill_readings.py`), a primitive image is attached *and* served (`make_primitive_images.py`), a Russian term hits (`add_ru_aliases.py`) |
| frontend | `index.html`'s asset paths match this target's Vite `base`, and the first one actually 200s |

Every check runs even after one fails, so you get the whole list, and each
failure prints the command that fixes it. Exits non-zero if anything failed.

To check the public nginx route and the built frontend as well:

```bash
# prod
./venv/bin/python3 deploy_smoke_test.py \
  --base-url https://kanji.alteon.help/kanji/api \
  --site-url https://kanji.alteon.help --expect-base /

# the shared dev box
./venv/bin/python3 deploy_smoke_test.py \
  --base-url https://srv.alteon.help/kanji/api \
  --site-url https://srv.alteon.help/kanji --expect-base /kanji/
```

`--expect-base` is what catches the 2026-09-20 blank-page class: the right code
built with the wrong `base` serves an `index.html` whose asset URLs 404, so the
page loads, renders nothing, and every API-only check still passes.

**As of 2026-09-23 prod fails two of the thirteen** — `backfill_readings.py` has
never been run there, so the pronunciation panel is empty on every detail page.
Run it on the prod VM and the run goes green (the dev box already passes all 13).

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
curl -fsS 'https://kanji.alteon.help/kanji/api/search/text?q=one' >/dev/null
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

## SEO / getting Google to find the site (added 2026-09-01, owner request; updated 2026-09-21 for per-kanji pages)

The frontend build ships `robots.txt` and `sitemap.xml` automatically
(`frontend/public/robots.txt` / `sitemap.xml`, copied to `dist/` by the
normal build step) — no extra action needed beyond the usual frontend
rebuild-and-deploy step (`npm run build:prod` on the dedicated VM; see
`CLAUDE.md`'s Deployment section and `deploy/nginx/README.md`). `index.html`
also has a real `<title>`/`<meta description>`/canonical URL/Open Graph
tags. Since prod (`kanji.alteon.help`) is now a **dedicated** VM serving the
app from the domain root (not a `/kanji/` path prefix on a shared box), both
files already sit at the real domain root — `https://kanji.alteon.help/robots.txt`
and `.../sitemap.xml` — with no path-prefix rewriting and no other project's
config to coordinate with. That resolves what used to be the hard part of
this section on the old shared srv.alteon.help box (a domain-root
`robots.txt` that repo's nginx config didn't own); it's a non-issue now.

Every frontend build now runs `backend/generate_seo_pages.py` first. It writes a
static, crawlable page for every public kanji/hanzi to `/kanji/{id}.html`, including
its public decomposition, and regenerates the sitemap with those canonical URLs.
For example, `https://kanji.alteon.help/kanji/rtk207.html` is the crawlable page for
the RTK "tree" entry. The output is generated from the live database and deliberately
is not committed. Rebuild the frontend after any public decomposition change to update
Google's crawl surface.

That covers everything reachable from *this* repo. Two more steps need
someone with server access and/or the owner's Google account — none of them
are things this repo (or an AI session without server/Google credentials)
can do on its own:

1. **Google Search Console.** Needs the owner's Google account, so has to be
   done by a human:
   - console.google.com/search-console → Add property → Domain (or URL
     prefix) → `kanji.alteon.help`.
   - Verify ownership — easiest is the "HTML tag" method: paste the
     `<meta name="google-site-verification" content="...">` tag Search
     Console gives you into `frontend/index.html`'s `<head>` (ask a future
     session to add it and redeploy, or add it directly) and reload the
     verification page. The "HTML file upload" method also works too now
     that the app owns the whole domain root (drop the given file into
     `frontend/public/`).
   - Once verified: Sitemaps → submit `https://kanji.alteon.help/sitemap.xml`.
   - URL Inspection tool → paste `https://kanji.alteon.help/` → "Request
     Indexing" — this is the fastest way to get the first crawl to happen,
     rather than waiting for Google to discover the site organically.
   - If Search Console already had a verified property for the old
     `srv.alteon.help/kanji/` URL prefix from before the move, that
     property is now stale (dev-only) — add `kanji.alteon.help` as a new
     property rather than trying to migrate the old one; Search Console
     doesn't have a clean "this site moved to a different domain" flow
     for a URL-prefix property, only for a Domain property.

`backend/visit_stats.py` (see `CLAUDE.md`'s Analytics section) is how to
check afterward whether any of this actually brought real visitors — it
already excludes bots that only ever hit URLs directly without running the
frontend JS, so a genuine uptick there is a genuine uptick, not crawler noise.

## MCP server — kanjimcp.alteon.help (added 2026-09-26)

A public, read-only MCP (Model Context Protocol) server exposing kanji/hanzi
shape search and decomposition lookup as MCP tools, so an MCP-capable client
(Claude, another agent) can query this project's data directly instead of
scraping the website. Lives at `backend/mcp_server.py`, importing
`database.py` the same way `main.py` does, but as its **own process** on its
**own subdomain** — deliberately separate from `kanji-backend.service` so an
MCP protocol issue or client flood can't take down the main site, and so it
can be restarted independently. No auth, same visibility rules as an
anonymous website visitor (`viewer_id=None` everywhere — only public rows,
never private user contributions).

Tools exposed: `search_by_parts` (shape search — the site's parts-search tab),
`get_decomposition` (a character's own breakdown, recursive), `search_by_text`
(keyword/alias search — the site's text-search tab). See the module docstring
and each tool's own docstring in `mcp_server.py` for exact parameters.

**One-time setup on the prod VM** (161.153.96.217 — same dedicated machine as
the main app; this is not a new server):

1. **DNS**: point `kanjimcp.alteon.help` at 161.153.96.217 (same A/AAAA
   records as `kanji.alteon.help`, different name) — needs whoever owns the
   `alteon.help` DNS zone; not something done from this repo.
2. **Install the new dependency**: `cd /opt/kanji/backend && source venv/bin/activate && pip install -r requirements.txt` (adds `mcp`, pinned in `requirements.txt`).
3. **systemd unit** — create `/etc/systemd/system/kanji-mcp.service`:
   ```ini
   [Unit]
   Description=Kanji MCP server
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=/opt/kanji/backend
   Environment=KANJI_MCP_PORT=8100
   ExecStart=/opt/kanji/backend/venv/bin/python3 mcp_server.py
   Restart=on-failure
   User=ec2-user

   [Install]
   WantedBy=multi-user.target
   ```
   Then `sudo systemctl daemon-reload && sudo systemctl enable --now kanji-mcp.service`.
   Match `User=`/paths to however `kanji-backend.service` is actually configured
   on the box (`systemctl cat kanji-backend.service` to check) — this should
   mirror it, just on a different port and entry point.
4. **nginx**: copy `deploy/nginx/prod/kanjimcp.conf` to
   `/etc/nginx/sites-available/kanjimcp.conf`, symlink it into
   `sites-enabled/`, same as the main `kanji.conf` (see
   `deploy/nginx/README.md`'s file-mapping table).
5. **TLS**: `sudo certbot --nginx -d kanjimcp.alteon.help` (same tool/flow
   already used for `kanji.alteon.help`) — this fills in the
   `ssl_certificate`/`ssl_certificate_key` paths `kanjimcp.conf` already
   references and sets up the HTTP->HTTPS redirect block, same as Certbot did
   for the main domain.
6. `sudo nginx -t && sudo systemctl reload nginx`.
7. **Verify**: `curl -s https://kanjimcp.alteon.help/mcp -X POST -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoketest","version":"1"}}}'`
   should return a `200` with a JSON-RPC `result` (server info + capabilities),
   not a connection error or 502.

**Ongoing deploys**: a `data.txt`/`database.py` change that affects search or
decomposition output needs `kanji-mcp.service` restarted too, same as
`kanji-backend.service` (Step 3 above) — they read the same `kanji.db` but are
two separate running processes with their own Python import state. A change to
`mcp_server.py` itself only needs `kanji-mcp.service` restarted, not the main
backend.

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
   origins: **both** `https://kanji.alteon.help` (prod) and
   `https://srv.alteon.help` (dev), plus `http://localhost:5173` for local
   dev — one OAuth client, three origins, since dev and prod deliberately
   share the same client id (see `deploy/nginx/README.md`'s "Google OAuth
   client ID is shared across both machines"). No redirect URI needed (this
   uses Google Identity Services' client-side token flow, not a server
   redirect).
2. The resulting Client ID is a public identifier, not a secret — set the
   *same* value in two places, **on each machine you want it working on**:
   - Backend: `sudo systemctl edit kanji-backend.service` → add
     `Environment=GOOGLE_CLIENT_ID=<id>` under `[Service]` → restart.
   - Frontend: `frontend/.env` → `VITE_GOOGLE_CLIENT_ID=<id>`.
3. Rebuild the frontend and redeploy: `npm run build:prod` on the prod VM
   (copy `dist/` to `/opt/kanji/frontend/dist`) or `npm run build:dev` on
   the shared dev box (copy `dist/` to `/usr/share/nginx/html/kanji/`) — a
   `.env` edit alone does not take effect without this step, and using the
   wrong build script on either machine reintroduces the same "blank page"
   asset-path bug the 2026-09-20 prod migration hit (see git history on
   `frontend/vite.config.js`/`package.json`).
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
   must run `cd frontend && npm install` after pulling, then the build
   command for **that specific machine** — they are not interchangeable
   (see `deploy/nginx/README.md`):
   - Prod (`kanji.alteon.help`, dedicated VM): `npm run build:prod`, then
     copy `dist/` to `/opt/kanji/frontend/dist`.
   - Dev (`srv.alteon.help`, shared box): `npm run build:dev`, then copy
     `dist/` to `/usr/share/nginx/html/kanji/`.

   Copy the whole directory (overwriting old files), not merging. The
   single most common cause of "I redeployed but nothing changed" is this
   step being skipped or copying to the wrong path — and running the
   *other* machine's build script is a second, sneakier variant of the
   same mistake: the page loads but renders completely blank, because the
   built `index.html` references asset paths (`/assets/...` vs.
   `/kanji/assets/...`) that don't match where nginx actually serves them
   on that machine. That exact bug took prod down on 2026-09-20 right
   after the move off the shared box, before `build:dev`/`build:prod`
   existed as separate scripts.
2. **Verify the copy actually landed** before blaming the browser:
   `ls -la /opt/kanji/frontend/dist/assets/` (prod) or
   `ls -la /usr/share/nginx/html/kanji/assets/` (dev) and check the
   filenames/timestamps are from *just now*, not from an earlier deploy.
   Vite fingerprints each JS/CSS file's name with a content hash, so a
   real rebuild always produces different filenames — if the filenames
   in that directory match what a previous deploy already had, the build
   either didn't run or didn't get copied. Also load the site itself and
   view-source on `index.html`: its `<script src=...>`/`<link
   rel="stylesheet" href=...>` paths should start with `/assets/` on prod
   or `/kanji/assets/` on dev — the wrong prefix means the wrong build
   script ran.
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
