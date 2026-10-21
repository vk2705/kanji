#!/usr/bin/env python3
"""Build backend/decomposition_history.json: every past version of each kanji's
decomposition, and every review it has had.

Owner request (2026-10-21), after 亀 turned out to have been wrong all along
with nothing scheduled to look at it: "for each kanji I want to keep history of
decomposition -- has it been reviewed? was it degraded by a review?"

Sources:
- `git log` of backend/data.txt. Every rtk* row's decomposition lives on one
  line there, so each commit that changed a line is one version of that kanji:
  date, author, commit subject, the parts, and the `#` comment block written
  directly above the line at that point (where this project records *why*).
- docs/kanji_full_review.json: the from-scratch re-review (full_review.py).
- docs/decomposition_worklist.json: decisions from the earlier, Google-
  disagreement worklist (worklist_next.py), which only ever covered part of
  the kanji -- the gap that let 亀 through.

The output is generated (gitignored). The frontend build runs this before
generate_seo_pages.py, so every deploy refreshes it; GET /kanji/{id}/history
serves it. Hanzi rows are edited directly in the database, not in data.txt,
so they have no history here.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_TXT = "backend/data.txt"
OUT = ROOT / "backend" / "decomposition_history.json"
FULL_REVIEW = ROOT / "docs" / "kanji_full_review.json"
OLD_WORKLIST = ROOT / "docs" / "decomposition_worklist.json"
REPO_URL = "https://github.com/vk2705/kanji"

LINE = re.compile(r"^(rtk\d+):")


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout


def who(author: str, email: str) -> str:
    """Who made a change, in the owner's terms. Commits as "Claude" come from
    the daily cloud audit routine and cloud sessions; "EC2 Default User" ones
    were made on the dev box, by Claude sessions and the daily worklist jobs."""
    if author == "Claude" or email == "noreply@anthropic.com":
        return "claude (cloud)"
    if author == "EC2 Default User":
        return "claude (dev box)"
    return author


def parse(text: str) -> dict[str, tuple[str, str]]:
    """rtk id -> (parts field, the comment block directly above the line)."""
    rows: dict[str, tuple[str, str]] = {}
    comment: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            comment.append(line.lstrip("#").strip())
            continue
        match = LINE.match(line)
        if match:
            fields = line.split(":", 3)
            parts = fields[3] if len(fields) > 3 else ""
            rows[match.group(1)] = (parts, " ".join(c for c in comment if c))
        comment = []
    return rows


def main() -> None:
    log = git("log", "--reverse", "--format=%H%x1f%ad%x1f%an%x1f%ae%x1f%s",
              "--date=short", "--", DATA_TXT)
    history: dict[str, dict] = {}
    previous: dict[str, tuple[str, str]] = {}
    for entry in log.splitlines():
        sha, day, author, email, subject = entry.split("\x1f", 4)
        try:
            text = git("show", f"{sha}:{DATA_TXT}")
        except subprocess.CalledProcessError:
            continue  # the file was deleted or renamed in this commit
        current = parse(text)
        for kanji_id, (parts, comment) in current.items():
            before = previous.get(kanji_id)
            if before and before[0] == parts:
                continue
            versions = history.setdefault(kanji_id, {"versions": [], "reviews": []})["versions"]
            versions.append({
                "date": day,
                "commit": sha[:10],
                "url": f"{REPO_URL}/commit/{sha}",
                "by": who(author, email),
                "subject": subject,
                "parts": parts,
                "previous": before[0] if before else None,
                "note": comment if comment and (not before or comment != before[1]) else "",
            })
        for kanji_id in previous.keys() - current.keys():
            history[kanji_id]["versions"].append({
                "date": day, "commit": sha[:10], "url": f"{REPO_URL}/commit/{sha}",
                "by": who(author, email), "subject": subject, "parts": None,
                "previous": previous[kanji_id][0], "note": "line removed from data.txt",
            })
        previous = current

    for path, source in [(OLD_WORKLIST, "google-disagreement worklist"),
                         (FULL_REVIEW, "full re-review")]:
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row.get("status") in (None, "pending") and source != "full re-review":
                continue
            review = {
                "source": source,
                "status": row.get("status"),
                "by": row.get("reviewed_by"),
                "date": row.get("reviewed_at"),
                "note": row.get("note") or "",
                "decision": row.get("decision"),
            }
            history.setdefault(row["id"], {"versions": [], "reviews": []})["reviews"].append(review)

    OUT.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    changed = sum(1 for h in history.values() if len(h["versions"]) > 1)
    print(f"Wrote {OUT.name}: {len(history)} kanji, {changed} changed at least once, "
          f"{sum(len(h['versions']) for h in history.values())} versions from {len(log.splitlines())} commits")


if __name__ == "__main__":
    main()
