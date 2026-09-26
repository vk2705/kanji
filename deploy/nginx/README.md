# nginx config (reference copies, not auto-deployed)

This repo runs on **two separate machines with different nginx layouts**, and
the checked-in files here are reference copies of what's actually live on
each — nginx itself does not read from this directory on either box; these
exist so the configs are version-controlled and reviewable. Keep them in sync
by hand whenever the live config changes (see "To apply an update" below).

- **`dev/`** — `srv.alteon.help`, a **shared** EC2 host that also runs other
  projects. The kanji app lives under a `/kanji/` path prefix so it doesn't
  collide with anything else nginx on that box serves. Frontend is built with
  `npm run build:dev` (vite `base=/kanji/`) and copied to
  `/usr/share/nginx/html/kanji/`. `dev/kanji.conf` is a set of `location`
  fragments meant to be `include`d into (or pasted inside) that box's own
  server block — it doesn't declare a `server {}` of its own, since the box's
  existing config already has one for the shared domain.
- **`prod/`** — `kanji.alteon.help`, a **dedicated** Oracle Cloud VM
  (161.153.96.217) that runs nothing but this app. The frontend is served
  from `/` with no path prefix, so `prod/kanji.conf` is a **complete,
  standalone `server {}` block** (including its own Certbot-managed TLS
  directives) — there's no other project's config for it to slot into.
  Frontend is built with `npm run build:prod` (vite `base=/`) and copied to
  `/opt/kanji/frontend/dist`. Only the backend API keeps the `/kanji/api/`
  path prefix on both machines — that's a `frontend/src/api.js` constant
  shared by both builds, not a per-environment choice, so it didn't need to
  change when prod moved to its own VM.

Both machines' configs declare the same rate-limit zone *names* and *values*
(`kanji_auth`, `kanji_write`, `kanji_write_nonget`, `kanji_analytics` — see
each `kanji-ratelimit.conf`) and proxy the same set of endpoints to
`127.0.0.1:8000` — the only structural difference is where the SPA is rooted
and whether the file needs its own `server {}`/TLS block or slots into an
existing one.

## Which file lives where

| Repo path | Live path | Machine |
|---|---|---|
| `dev/kanji.conf` | `/etc/nginx/default.d/kanji.conf` | srv.alteon.help (shared dev box) |
| `dev/kanji-ratelimit.conf` | `/etc/nginx/conf.d/kanji-ratelimit.conf` | srv.alteon.help (shared dev box) |
| `prod/kanji.conf` | `/etc/nginx/sites-available/kanji.conf` (symlinked from `sites-enabled/`) | kanji.alteon.help (dedicated prod VM) |
| `prod/kanji-ratelimit.conf` | `/etc/nginx/conf.d/kanji-ratelimit.conf` | kanji.alteon.help (dedicated prod VM) |
| `prod/kanjimcp.conf` | `/etc/nginx/sites-available/kanjimcp.conf` (symlinked from `sites-enabled/`) | kanjimcp.alteon.help (same prod VM — see DEPLOY_README.md's "MCP server" section) |

`kanji-ratelimit.conf` on either machine declares the `limit_req_zone`s the
matching `kanji.conf`'s `location` blocks reference, plus the
`$kanji_write_key` map that makes the shared `/kanji/api/kanji/...` zone a
no-op for GET/HEAD (nginx's `limit_except` block doesn't accept `limit_req` in
its context, so this map-based approach — an empty zone key means "don't
rate-limit this request", documented `limit_req_zone` behavior — is the
working alternative). It's declared via `conf.d/` on both machines because
`limit_req_zone` must live at the `http{}` block level; on the dev box that
also means it doesn't need editing the shared `nginx.conf` other projects
there rely on.

**To apply an update to either machine**: copy the new version into place at
the path in the table above, then `sudo nginx -t` (must pass) and
`sudo systemctl reload nginx` (reload, not restart — avoids a
connection-dropping full restart). Verify with a `curl` smoke test against a
couple of endpoints before considering the change done — the dev box serves
other projects too, so a broken reload there is not a low-stakes mistake
either.

Rate limits as of 2026-08-31 (see either `kanji-ratelimit.conf` for the exact
numbers, identical on both machines): `kanji_auth` (login/register/Google
login) is the strictest — 5 requests/minute per IP, burst 5;
`kanji_write`/`kanji_write_nonget` (contribution writes) is 30/minute, burst
15; `kanji_analytics` (the unauthenticated pageview endpoint) is 60/minute,
burst 20. All three exceed with a plain `429`, not nginx's default error page.

## Google OAuth client ID is shared across both machines

Both `dev` and `prod` use the **same** `GOOGLE_CLIENT_ID` /
`VITE_GOOGLE_CLIENT_ID` value (confirmed identical on both machines as of
2026-09-20) — it's a public OAuth client identifier, not a secret (see
`CLAUDE.md`'s "Google SSO" section), so there's no per-environment id to keep
in sync. What each origin needs is for the *same* Google Cloud Console OAuth
client to list it under "Authorized JavaScript origins":
`https://srv.alteon.help`, `https://kanji.alteon.help`, and
`http://localhost:5173` for local dev. That origins list lives in Google
Cloud Console, not in this repo, so it isn't something a code session can
verify directly — if Google Sign-In fails on one host but not the other,
check that host's origin is actually present in the console before assuming
a code/config bug.
