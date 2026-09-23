"""Post-deploy checks for a running Kanji deployment.

## Why this is more than a ping

The 2026-09-20 prod move seeded the new VM's database from `data.txt` +
`heisig-kanjis.csv` and stopped there. That is only part of the pipeline: the
Chinese rows come from the separate one-off `import_hanzi.py`, the readings
from `backfill_readings.py`, the Russian search terms from `add_ru_aliases.py`.
None of them ran. The site came up, every page rendered, every Japanese search
worked — and selecting "Chinese" in the study-language selector returned zero
results for *everything*, for a day, until an owner searched for "finger" and
found nothing (2026-09-21).

Nothing was broken in a way any test then in the repo could see, because every
check was about the *code* being up. So these checks are about the **data being
complete**: one cheap probe per seeding step, each failure naming the script
that fixes it.

## Two rules this file follows

**Every check runs, even after one fails.** A deploy operator wants the whole
list, not the first line of it — finding out about the missing readings on the
*next* deploy because the Chinese check aborted the run is how a half-seeded
database survives a week.

**No check asserts a single hardcoded id where a count will do.** `q=one` under
`zh-Hans` returning exactly `hanzi-4e00` proves one row exists; requiring a
couple of dozen proves the import actually ran to completion rather than dying
partway. Spot-checking a handful of well-known entries is deliberate — this is
not a data audit (`test_regression_fixes.py` and the `audit_*.py` scripts are),
it is a "did all the pieces get installed" check.

## Usage

    # on the VM, against the local backend, with the unit checked too
    ./venv/bin/python3 deploy_smoke_test.py --service kanji-backend.service

    # through nginx, from anywhere
    ./venv/bin/python3 deploy_smoke_test.py \
        --base-url https://kanji.alteon.help/kanji/api

    # also verify the frontend bundle is the build for this target
    ./venv/bin/python3 deploy_smoke_test.py \
        --base-url https://kanji.alteon.help/kanji/api \
        --site-url https://kanji.alteon.help --expect-base /

Exits 0 only if every check passed.
"""

import argparse
import json
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TIMEOUT = 15


def _get(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urlopen(request, timeout=TIMEOUT) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read()


def api(base_url, path, params=None, method="GET", body=None):
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    _status, _ctype, raw = _get(url, method=method, body=body)
    return json.loads(raw)


def ids(payload):
    return [r["id"] for r in payload["results"]]


class Checks:
    """Collects results so every check runs and the whole list is reported."""

    def __init__(self):
        self.results = []

    def run(self, name, fix, fn):
        """`fix` is the command that repairs this check, shown on failure."""
        try:
            detail = fn()
        except Exception as error:  # noqa: BLE001 - any failure is a failed check
            self.results.append((name, False, f"{type(error).__name__}: {error}", fix))
        else:
            self.results.append((name, True, detail, fix))

    def report(self):
        failed = [r for r in self.results if not r[1]]
        for name, ok, detail, _fix in self.results:
            print(f"  {'PASS' if ok else 'FAIL'}  {name:<34} {detail}")
        if not failed:
            print(f"\nSmoke test passed: {len(self.results)} checks.")
            return 0
        print(f"\nSmoke test FAILED: {len(failed)} of {len(self.results)} checks.\n")
        for name, _ok, detail, fix in failed:
            print(f"  {name}\n      {detail}\n      fix: {fix}")
        return 1


def expect(condition, detail):
    if not condition:
        raise AssertionError(detail)
    return detail


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--service",
                        help="systemd unit that must be active (checked first)")
    parser.add_argument("--site-url",
                        help="also fetch the frontend at this origin and check its "
                             "asset paths match --expect-base")
    parser.add_argument("--expect-base", default="/",
                        help="the Vite base the frontend at --site-url was built with "
                             "('/' for prod, '/kanji/' for the shared dev box)")
    args = parser.parse_args()
    base = args.base_url
    print(f"Smoke-testing {base}\n")
    c = Checks()

    if args.service:
        c.run(
            "systemd unit active", f"sudo systemctl status {args.service}",
            lambda: (subprocess.run(["systemctl", "is-active", "--quiet", args.service],
                                    check=True), args.service)[1],
        )

    # --- the app answers at all -------------------------------------------------
    c.run("API reachable", "check the backend is running and nginx proxies /kanji/api/",
          lambda: expect(api(base, "/search/char", {"c": "日"})["id"] == "rtk12",
                         "GET /search/char?c=日 -> rtk12"))

    c.run("kanji detail", "sync_system_data.py, then restart the backend",
          lambda: expect(api(base, "/kanji/rtk20")["character"] == "明",
                         "GET /kanji/rtk20 -> 明"))

    # --- the Japanese seed (database.import_data, run once at first startup) -----
    def japanese_bulk():
        got = api(base, "/search/parts", method="POST",
                  body={"parts": ["mouth"], "script": "ja-kanji", "depth": 1})
        n = got["count"]
        return expect(n >= 100, f'parts ["mouth"] ja-kanji -> {n} (want >= 100)')

    c.run("Japanese rows seeded", "delete kanji.db and restart, or run sync_system_data.py",
          japanese_bulk)

    c.run("parts search", "sync_system_data.py",
          lambda: expect("rtk20" in ids(api(base, "/search/parts", method="POST",
                                            body={"parts": ["sun", "moon"],
                                                  "script": "ja-kanji", "depth": 1})),
                         'parts ["sun","moon"] -> includes 明'))

    # A primitive *name*, not a keyword: this is the search the 2026-09-21 report
    # came in about, and the one that silently returned nothing under a Chinese
    # study language for a day.
    c.run("primitive-name search", "sync_system_data.py",
          lambda: expect("kangxi64" in ids(api(base, "/search/text", {"q": "finger"})),
                         'text "finger" -> includes 扌'))

    c.run("autocomplete", "restart the backend (suggest_terms is code, not data)",
          lambda: expect("finger" in api(base, "/search/suggest", {"q": "finge"})["suggestions"],
                         'suggest "finge" -> offers "finger"'))

    # --- import_hanzi.py --------------------------------------------------------
    def chinese(script):
        n = api(base, "/search/text", {"q": "one", "script": script})["count"]
        return expect(n >= 10, f'text "one" {script} -> {n} (want >= 10)')

    c.run("Chinese simplified rows", "./venv/bin/python3 import_hanzi.py",
          lambda: chinese("zh-Hans"))
    c.run("Chinese traditional rows", "./venv/bin/python3 import_hanzi.py",
          lambda: chinese("zh-Hant"))

    # --- backfill_readings.py ---------------------------------------------------
    c.run("Japanese readings", "./venv/bin/python3 backfill_readings.py",
          lambda: expect(bool(api(base, "/kanji/rtk12").get("onyomi")),
                         "GET /kanji/rtk12 -> onyomi present"))

    def pinyin():
        # Via the detail endpoint, not the search one: search results carry no
        # pinyin field at all, so reading it there fails whether or not the
        # backfill ran. (Found on the first real run, 2026-09-23.)
        hits = api(base, "/search/text", {"q": "one", "script": "zh-Hans"})["results"]
        expect(hits, 'no zh-Hans hits for "one" to check readings on')
        row = api(base, f"/kanji/{hits[0]['id']}")
        return expect(row.get("pinyin"),
                      f"GET /kanji/{hits[0]['id']} -> pinyin {row.get('pinyin')!r}")

    c.run("Chinese readings", "./venv/bin/python3 backfill_readings.py", pinyin)

    # --- make_primitive_images.py + attach_primitive_images ---------------------
    def primitive_image():
        row = api(base, "/kanji/prim-umbrella")
        url = row.get("image_url") or ""
        expect(url, "prim-umbrella has no image_url")
        status, ctype, _ = _get(f"{base.rstrip('/')}{url}")
        return expect(status == 200 and ctype.startswith("image/"),
                      f"{url} -> {status} {ctype}")

    c.run("primitive images served",
          "./venv/bin/python3 make_primitive_images.py, then sync_system_data.py",
          primitive_image)

    # --- add_ru_aliases.py ------------------------------------------------------
    c.run("Russian search terms", "./venv/bin/python3 add_ru_aliases.py",
          lambda: expect(api(base, "/search/text", {"q": "один"})["count"] >= 1,
                         'text "один" -> at least one hit'))

    # --- the frontend bundle actually built for this target ---------------------
    # The 2026-09-20 incident: the right code, built with the wrong Vite `base`,
    # serves an index.html whose asset URLs 404. The page loads and renders blank,
    # so nothing that only talks to the API notices.
    if args.site_url:
        def frontend():
            status, _ctype, raw = _get(args.site_url.rstrip("/") + "/")
            expect(status == 200, f"GET {args.site_url} -> {status}")
            html = raw.decode("utf-8", "replace")
            assets = re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', html)
            expect(assets, "index.html references no js/css assets at all")
            wrong = [a for a in assets if a.startswith("/") and not a.startswith(args.expect_base)]
            if wrong:
                # Built lazily: `expect(cond, f"...{wrong[0]}...")` evaluates its
                # message *before* checking the condition, so an empty `wrong`
                # raised IndexError out of a passing check. Caught on the first
                # real run of this file against prod, 2026-09-23.
                which = "build:prod" if args.expect_base == "/" else "build:dev"
                raise AssertionError(
                    f"built with the wrong Vite base: {wrong[0]} does not start "
                    f"with {args.expect_base!r} -- rebuild with npm run {which}")
            # Absolute asset paths are relative to the *origin*, not to the
            # site path: joining them onto --site-url gave /kanji/kanji/assets/…
            # and a 404 that looked like a broken deploy.
            origin = "://".join(args.site_url.split("://")[:1] + [
                args.site_url.split("://", 1)[-1].split("/", 1)[0]])
            first = assets[0]
            url = first if first.startswith("http") else origin + first
            status, _ctype, _ = _get(url)
            return expect(status == 200, f"{len(assets)} assets, first one -> {status}")

        c.run("frontend assets resolve",
              "rebuild with the target's own npm run build:prod / build:dev",
              frontend)

    return c.report()


if __name__ == "__main__":
    raise SystemExit(main())
