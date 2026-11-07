# TODO — finish the move to kumiji.kermit.is-a.dev

Written 2026-11-07. The repo side is **done and pushed** (commits `0af6458`,
`785dc43`). Everything in this file is server/console work that needs access
nobody had from the session that prepared it.

Goal: `kumiji.kermit.is-a.dev` serves the site; `kanji.alteon.help` and
`kumiji.alteon.help` 301 to it; nothing depends on `alteon.help` any more, so
the domain can be dropped.

Work top to bottom — step 4 needs the certs from steps 2–3, and step 7 only
means anything after 5 and 6. Steps 1–7 are one sitting (~20 min). Steps 8–10
can wait. If a step's check fails, stop there rather than carrying on.

Delete this file once everything but the "later" section is ticked.

---

## ⚠️ Read before starting: the one step that is easy to get wrong

The certificate that covers `kumiji.kermit.is-a.dev` today was issued as a
**single lineage over both** `kumiji.alteon.help` and `kumiji.kermit.is-a.dev`
(that's how `certbot --nginx -d kumiji.alteon.help -d kumiji.kermit.is-a.dev`
was run on 2026-10-31).

If the canonical host is left on that cert: once `alteon.help` stops resolving,
certbot's renewal fails the challenge for its `alteon.help` name, and **a failed
renewal fails the whole lineage** — so the cert for the *new* canonical host
expires too. The site then goes down with a TLS error weeks after the domain
lapsed, with nothing obviously pointing at the cause.

Step 2 fixes this by issuing a cert that covers only is-a.dev names. Do not
skip it, and do not drop the `--cert-name` flag.

---

## Step 1 — pull the repo on the prod VM

```bash
cd /opt/kanji && git pull
```

- [ ] Done. `git log --oneline -2` shows `785dc43` / `0af6458`.

The frontend is not rebuilt until step 5; the new canonical tag and sitemap
come from that build.

---

## Step 2 — issue an is-a.dev-only cert for the canonical host

Do this **before** touching nginx, so the config installed in step 4 has a cert
to point at.

```bash
sudo certbot certonly --nginx \
  --cert-name kumiji.kermit.is-a.dev \
  -d kumiji.kermit.is-a.dev
```

`--cert-name` is load-bearing: without it, certbot may offer to *expand* the
existing `kumiji.alteon.help` lineage instead of creating a separate one —
which is the exact coupling this step exists to break. If it asks whether to
expand, say no and re-run with the flag.

Check:

```bash
sudo certbot certificates | grep -A3 kumiji
```

- [ ] There is a `kumiji.kermit.is-a.dev` lineage whose **Domains** line lists
      `kumiji.kermit.is-a.dev` and **nothing else**.
- [ ] `sudo ls /etc/letsencrypt/live/kumiji.kermit.is-a.dev/` shows
      `fullchain.pem` and `privkey.pem` — this is the path the new nginx config
      references.

---

## Step 3 — same for the MCP host

Its DNS record already points at this VM, but it has no cert or vhost yet.

```bash
sudo certbot certonly --nginx \
  --cert-name kanjimcp.kermit.is-a.dev \
  -d kanjimcp.kermit.is-a.dev
```

- [ ] `/etc/letsencrypt/live/kanjimcp.kermit.is-a.dev/` exists.

---

## Step 4 — install the nginx configs

`kumiji.conf` and `kanji.conf` **swapped roles**: `kumiji.conf` now holds the
full app server block, `kanji.conf` only the redirects. Copy **both**, or the
site will redirect to itself in a loop.

```bash
sudo cp /opt/kanji/deploy/nginx/prod/kumiji.conf   /etc/nginx/sites-available/kumiji.conf
sudo cp /opt/kanji/deploy/nginx/prod/kanji.conf    /etc/nginx/sites-available/kanji.conf
sudo cp /opt/kanji/deploy/nginx/prod/kanjimcp.conf /etc/nginx/sites-available/kanjimcp.conf
sudo nginx -t && sudo systemctl reload nginx
```

All three should already be symlinked into `sites-enabled/` from previous
setup; if `kumiji.conf` is not, add it:

```bash
ls -l /etc/nginx/sites-enabled/
sudo ln -sfn /etc/nginx/sites-available/kumiji.conf /etc/nginx/sites-enabled/kumiji.conf
```

- [ ] `nginx -t` passes and nginx reloaded.

If `nginx -t` complains about a missing certificate file, step 2 or 3 did not
produce the lineage name the config expects. Fix the cert — do **not** edit the
cert path in the config, or the repo's reference copy stops matching the live
file, which is the thing `deploy/nginx/README.md` exists to prevent.

---

## Step 5 — rebuild and redeploy the frontend

The redirect is live from step 4, but the built bundle still carries the old
canonical URL and the old sitemap.

```bash
cd /opt/kanji/frontend
npm install
npm run build:prod
```

`build:prod` (**not** `build:dev` — the wrong one renders a blank page) runs
`generate_seo_pages.py` first, so all ~3,200 per-character pages and the sitemap
chunks are rewritten with the new host.

On this VM nginx serves `/opt/kanji/frontend/dist` directly, so building in
place *is* the deploy — no copy step. Verify it actually rebuilt:

```bash
ls -la /opt/kanji/frontend/dist/assets/ | head
curl -s https://kumiji.kermit.is-a.dev/ | grep -i 'canonical\|og:url'
```

- [ ] Asset filenames carry fresh timestamps (Vite content-hashes them, so a
      real rebuild always changes the names).
- [ ] The canonical/og:url tags say `kumiji.kermit.is-a.dev`.

If the browser still shows the old site after this, hard-refresh
(Ctrl/Cmd+Shift+R) before suspecting anything else.

---

## Step 6 — add the Google OAuth origin

**Google Sign-In is broken on the new host until this is done.** A redirect does
not help: the browser sends the origin it is actually running on, so the
canonical name has to be listed in its own right.

Google Cloud Console → APIs & Services → Credentials → the OAuth client →
**Authorized JavaScript origins** → add:

```
https://kumiji.kermit.is-a.dev
```

- [ ] Added and saved.
- [ ] The "Sign in with Google" button appears on the new host and a sign-in
      completes. (Changes can take a few minutes to propagate.)

Leave the `alteon.help` origins in place for now; remove them in step 10.

---

## Step 7 — verify the whole thing

Runnable from anywhere, not just the VM.

```bash
# the canonical host serves the app, API included, with the right build
cd /opt/kanji/backend && ./venv/bin/python3 deploy_smoke_test.py \
  --base-url https://kumiji.kermit.is-a.dev/kanji/api \
  --site-url https://kumiji.kermit.is-a.dev --expect-base /

# the old names redirect, keeping the path
curl -sI https://kanji.alteon.help/kanji/rtk207.html | head -3
curl -sI https://kumiji.alteon.help/ | head -3

# the MCP server on its new name
curl -s https://kanjimcp.kermit.is-a.dev/mcp -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoketest","version":"1"}}}'
```

- [ ] Smoke test exits 0 (it prints a fixing command for every failure).
- [ ] Both `curl -sI` calls return **301** with a `Location:` on
      `kumiji.kermit.is-a.dev` and the path intact — `/kanji/rtk207.html` must
      survive, not collapse to `/`.
- [ ] The MCP call returns a JSON-RPC `result`, not a 502 or a connection error.

### Expected fallout — not bugs, no action needed

- **Everyone is signed out**, including you. The session cookie is scoped to the
  hostname it was set on and cookies do not cross domains.
- **Analytics visitor ids reset** the same way, so `visit_stats.py` will show a
  burst of apparently-new visitors and the all-time unique count is inflated
  from here on. A known artifact of the move, not a broken counter.

---

## Step 8 — tell the search engines (can wait a day)

```bash
cd /opt/kanji/backend
./venv/bin/python3 indexnow_submit.py --dist /opt/kanji/frontend/dist
```

Every URL looks new after a host change, so this resubmits the whole site —
that is the intended behaviour here, and no `--all` is needed.

- [ ] IndexNow submit accepted.

Google does not take part in IndexNow, so it needs Search Console separately
(full detail in `DEPLOY_README.md`'s SEO section):

- [ ] Add `kumiji.kermit.is-a.dev` as a new Search Console property and verify
      it (easiest: the HTML-file method — drop the given file into
      `frontend/public/` and rebuild).
- [ ] Submit `https://kumiji.kermit.is-a.dev/sitemap.xml`.
- [ ] URL Inspection → `https://kumiji.kermit.is-a.dev/` → Request Indexing.
- [ ] **If** the old `kanji.alteon.help` property is a *Domain* property:
      Settings → Change of Address → point it at the new property. That is what
      transfers the ranking signal instead of treating the new host as an
      unrelated site. If it is a URL-prefix property there is no Change of
      Address for it — the 301 plus the sitemap submission is all you get, and
      it does work, just more slowly.

---

## Step 9 — rebuild and republish the Android APK

Needed, not optional: an APK built before this change **bounces the user out to
their system browser on launch**. It loads `kanji.alteon.help`, and the 301 to a
different host reads as an off-host link to the WebView's own link handler.

Already done in the repo: `APP_URL` is now `https://kumiji.kermit.is-a.dev/`,
version 1.2 / `versionCode` 3.

```bash
cd /opt/kanji/android   # or wherever you build; needs an Android SDK
./gradlew :app:assembleRelease
```

- [ ] APK built and published over `android/releases/rtk-kanji-latest.apk`.
- [ ] **On a device**: the app opens the actual app, not a plain list page — and
      check the **Dispute button** and **decomposition history** are present.

That last check is the point of this step. The old `APP_URL` pointed at
`/kanji/`, which on this VM is the static "Browse kanji" SEO hub rather than the
app, so the APK had been loading a plain HTML page since the September server
move. That is almost certainly the cause of the 2026-10-23 report that the app
was missing those two features. This confirms it or rules it out.

---

## Step 10 — later, when alteon.help actually lapses

Cleanup, so certbot stops trying to renew names that no longer resolve (a
failing renewal timer is noisy and eventually masks a real failure).

```bash
sudo rm /etc/nginx/sites-enabled/kanji.conf
sudo rm /etc/nginx/sites-available/kanji.conf
sudo certbot delete --cert-name kanji.alteon.help
sudo certbot delete --cert-name kumiji.alteon.help
sudo certbot delete --cert-name kanjimcp.alteon.help
sudo nginx -t && sudo systemctl reload nginx
```

- [ ] Done.
- [ ] Delete the retiring `kanjimcp.alteon.help` server block from
      `deploy/nginx/prod/kanjimcp.conf` (it is marked in the file), and delete
      `deploy/nginx/prod/kanji.conf` from the repo, so the reference copies keep
      matching the live files. Commit that.
- [ ] Remove the `alteon.help` origins from the Google OAuth client.
- [ ] `srv.alteon.help`, the old shared dev box, dies with the domain too. The
      Android `legacy` build type and a few dev-only mentions in
      `android/README.md` and `DEPLOY_README.md` point at it and become dead
      references — worth a tidy-up pass, nothing urgent.

---

## Background, if you want it

- `kumiji.kermit.is-a.dev` is an **A record straight to 161.153.96.217**, not a
  CNAME to `kanji.alteon.help` — which is what makes this move safe at all. It
  keeps resolving once the old zone is gone.
- The **MCP server is deliberately not redirected**. Streamable HTTP speaks
  POST, and many HTTP clients downgrade a redirected POST to GET rather than
  replaying it, so a 301 would break already-configured MCP clients instead of
  moving them. Both names serve until step 10 deletes the old one.
- `applicationId` stays `help.alteon.kanji` on purpose, even though the domain
  it was named after is going: it is only an identifier, it never has to
  resolve, and changing it stops installed apps updating in place.

Fuller write-up: `DEPLOY_README.md` → "Canonical host move", and the 2026-11-07
entry in `docs/2026-08-search-quality-audit.md`.
