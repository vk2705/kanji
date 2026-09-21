"""Minimal post-deploy checks for the running Kanji API."""

import argparse
import json
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(base_url, path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def has_result(payload, entry_id):
    return any(result["id"] == entry_id for result in payload["results"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--service",
        help="Require this systemd service to be active before testing the API.",
    )
    args = parser.parse_args()

    try:
        if args.service:
            subprocess.run(
                ["systemctl", "is-active", "--quiet", args.service],
                check=True,
            )

        japanese = request_json(args.base_url, "/search/char?c=%E6%97%A5&script=ja-kanji")
        if japanese["id"] != "rtk12" or japanese["character"] != "日":
            raise ValueError("Japanese character lookup returned the wrong entry")

        detail = request_json(args.base_url, "/kanji/rtk20")
        if detail["character"] != "明":
            raise ValueError("Kanji detail lookup returned the wrong entry")

        parts = request_json(
            args.base_url,
            "/search/parts",
            method="POST",
            body={"parts": ["sun", "moon"], "script": "ja-kanji", "depth": 1},
        )
        if not has_result(parts, "rtk20"):
            raise ValueError("Japanese parts search did not return bright")

        chinese = request_json(args.base_url, "/search/text?q=finger&script=zh-Hans")
        if not has_result(chinese, "hanzi-6307"):
            raise ValueError("Chinese text search did not return finger")
    except (
        subprocess.CalledProcessError,
        HTTPError,
        URLError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as error:
        print(f"Smoke test failed: {error}", file=sys.stderr)
        return 1

    print("Smoke test passed: service, Japanese lookup/parts/detail, and Chinese search.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())