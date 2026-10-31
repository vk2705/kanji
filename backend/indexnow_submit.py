#!/usr/bin/env python3
"""Tell IndexNow search engines (Bing, Yandex, Seznam, Naver; DuckDuckGo and
ChatGPT search via Bing) which pages of the deployed site are new or changed.

Added 2026-10-31: Google has never fetched the submitted sitemaps (see
docs/2026-08-search-quality-audit.md, 2026-10-30), so this pushes URLs to the
engines that accept a push instead of waiting to be crawled. Google does not
take part in IndexNow.

Run it on prod after copying a fresh build into place, against that built
directory: it reads the sitemap index the build generated, hashes the file
behind each URL, and submits only the URLs whose file is new or changed since
the last successful submit (recorded in STATE_PATH, which is per-machine and
gitignored). The generated pages carry no build date, so an unchanged kanji
hashes the same from one build to the next. --all resubmits everything.

Never run it from the dev box: it would announce prod URLs from a build that
was not deployed there.

The key is public by design: IndexNow proves site ownership by fetching
https://kanji.alteon.help/{KEY}.txt, which lives in frontend/public/. The
script checks that file is live before submitting, since the API answers 403
for every URL otherwise.

Stdlib only, so the system python3 works.

Usage:
    ./indexnow_submit.py --dist /opt/kanji/frontend/dist --dry-run
    ./indexnow_submit.py --dist /opt/kanji/frontend/dist
    ./indexnow_submit.py --dist /opt/kanji/frontend/dist --all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

SITE_URL = "https://kanji.alteon.help"
HOST = "kanji.alteon.help"
KEY = "4159b1e0528bf4cd388f532c71252e4d"
KEY_URL = f"{SITE_URL}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10000  # the protocol's per-request maximum
STATE_PATH = Path(__file__).parent / "indexnow_state.json"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def sitemap_urls(dist: Path) -> list[str]:
    """Every page URL listed by dist/sitemap.xml's chunk files."""
    index = ET.parse(dist / "sitemap.xml").getroot()
    urls: list[str] = []
    for loc in index.findall("sm:sitemap/sm:loc", SITEMAP_NS):
        chunk = dist / loc.text.strip().removeprefix(f"{SITE_URL}/")
        urls += [u.text.strip() for u in ET.parse(chunk).getroot().findall("sm:url/sm:loc", SITEMAP_NS)]
    return urls


def file_for(dist: Path, url: str) -> Path:
    path = url.removeprefix(SITE_URL).lstrip("/")
    if path == "" or path.endswith("/"):
        path += "index.html"
    return dist / path


def changed_urls(dist: Path, urls: list[str], state: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    hashes = {}
    for url in urls:
        f = file_for(dist, url)
        if not f.is_file():
            sys.exit(f"{url} is in the sitemap but {f} does not exist; is --dist a full build?")
        hashes[url] = hashlib.sha256(f.read_bytes()).hexdigest()
    return [u for u in urls if state.get(u) != hashes[u]], hashes


def key_is_live() -> bool:
    try:
        with urllib.request.urlopen(KEY_URL, timeout=15) as r:
            return r.read().decode().strip() == KEY
    except urllib.error.URLError:
        return False


def submit(urls: list[str]) -> None:
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": KEY_URL, "urlList": urls}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        # 200 = accepted, 202 = accepted, key validation pending
        print(f"  submitted {len(urls)} URLs: HTTP {r.status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dist", type=Path, required=True, help="the deployed frontend build directory")
    parser.add_argument("--all", action="store_true", help="submit every sitemap URL, not just changed ones")
    parser.add_argument("--dry-run", action="store_true", help="report what would be submitted, send nothing")
    args = parser.parse_args()

    if not (args.dist / f"{KEY}.txt").is_file():
        sys.exit(f"{args.dist}/{KEY}.txt missing; this build predates IndexNow or --dist is wrong")
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    urls = sitemap_urls(args.dist)
    todo, hashes = changed_urls(args.dist, urls, state)
    if args.all:
        todo = urls
    print(f"{len(urls)} URLs in the sitemap, {len(todo)} to submit")
    if args.dry_run:
        for u in todo[:20]:
            print(f"  {u}")
        if len(todo) > 20:
            print(f"  ... and {len(todo) - 20} more")
        return
    if not todo:
        return
    if not key_is_live():
        sys.exit(f"{KEY_URL} does not serve the key; deploy the build before submitting")

    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            submit(batch)
        except urllib.error.HTTPError as e:
            sys.exit(f"IndexNow refused the batch: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")
        # Record each accepted batch as it goes, so a failure later resubmits only the rest.
        state.update({u: hashes[u] for u in batch})
        STATE_PATH.write_text(json.dumps(state, indent=0, sort_keys=True))
    # Forget URLs that left the sitemap, so they are submitted again if they come back.
    for u in set(state) - set(urls):
        del state[u]
    STATE_PATH.write_text(json.dumps(state, indent=0, sort_keys=True))


if __name__ == "__main__":
    main()
