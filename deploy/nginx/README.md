# nginx config (reference copies, not auto-deployed)

The live box (`srv.alteon.help`, a shared EC2 host running other projects too) has
its own nginx config that is **not** managed by this repo — these files are
checked-in reference copies of what's actually live, kept here so the config is
version-controlled and reviewable, not the source of truth nginx itself reads from.

- `kanji.conf` → lives at `/etc/nginx/default.d/kanji.conf` on the server. Proxies
  `/kanji/api/` to the backend (`127.0.0.1:8000`), stripping the prefix. Split into
  several `location` blocks (added 2026-08-31, architecture review finding #4) so
  `auth/login|register|google`, the shared `/kanji/...` prefix (write endpoints only
  — `GET /kanji/{id}` is exempt), `aliases|stories|decompositions`, and
  `analytics/pageview` each get their own rate-limit zone; everything else still
  falls through to the original catch-all proxy block at the bottom.
- `kanji-ratelimit.conf` → lives at `/etc/nginx/conf.d/kanji-ratelimit.conf`. Declares
  the `limit_req_zone`s `kanji.conf`'s locations reference, plus the `$kanji_write_key`
  map that makes the shared `/kanji/...` zone a no-op for GET/HEAD (nginx's
  `limit_except` block doesn't accept `limit_req` in its context, so this map-based
  approach — an empty zone key means "don't rate-limit this request", documented
  `limit_req_zone` behavior — is the working alternative). Declared via `conf.d/`
  rather than editing the shared `nginx.conf` directly, since `limit_req_zone` must
  live at the `http{}` block level and this box's `nginx.conf` already
  `include`s `conf.d/*.conf` there.

**To apply an update to these files on the server**: copy the new version into place
at the paths above, then `sudo nginx -t` (must pass) and `sudo systemctl reload nginx`
(reload, not restart — avoids a connection-dropping full restart). Verify with a
`curl` smoke test against a couple of endpoints before considering the change done —
this box serves other projects too, so a broken reload here is not a low-stakes
mistake.

Rate limits as of 2026-08-31 (see `kanji-ratelimit.conf` for the exact numbers):
`kanji_auth` (login/register/Google login) is the strictest — 5 requests/minute per
IP, burst 5; `kanji_write`/`kanji_write_nonget` (contribution writes) is 30/minute,
burst 15; `kanji_analytics` (the unauthenticated pageview endpoint) is 60/minute,
burst 20. All three exceed with a plain `429`, not nginx's default error page.
