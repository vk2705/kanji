"""
export_backup.py — anonymized flat-file backup of kanji.db, safe to commit to git.

Dumps every kanji row plus its aliases/decompositions/parts/stories (public
AND private — visibility is preserved in the output, so a re-import can
still tell them apart) to one JSON object per line. Real usernames are never
written anywhere in the output: every owner_id is replaced with either the
literal "system" (owner_id=1, the Heisig/hanzi seed data) or a per-user
pseudonym — HMAC-SHA256(secret, username), truncated to 16 hex chars — so the
same real user gets the same stable pseudonym everywhere without the
username itself, or anything reversible to it, ever appearing.

password_hash and the sessions table (active session tokens) are never read
at all — there is no flag to include them. This tool cannot leak them.

The secret is read from BACKUP_ANON_SECRET and must NOT be committed
alongside the export it protects (a leaked secret + this script would let
someone re-derive who owns which pseudonym for any username they guess) —
keep it wherever `env`/`mcp_remote.env` already live, gitignored.

Usage:
    export BACKUP_ANON_SECRET=...   # pick once, keep it, never commit it
    python3 export_backup.py [--db kanji.db] [--out kanji_export.jsonl] [--limit N]
"""
import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import sys
from pathlib import Path

DB_PATH  = Path(__file__).parent / "kanji.db"
OUT_PATH = Path(__file__).parent / "kanji_export.jsonl"


def pseudonym(secret: bytes, username: str) -> str:
    return hmac.new(secret, username.strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def build_owner_map(conn, secret: bytes) -> dict[int, str]:
    """user id -> 'system' (owner_id=1) or a stable per-user pseudonym. Only
    ever reads id/username from `users` — never password_hash, never
    provider_user_id, never touches `sessions`."""
    owners = {}
    for row in conn.execute("SELECT id, username FROM users"):
        owners[row["id"]] = "system" if row["id"] == 1 else pseudonym(secret, row["username"])
    return owners


def export_kanji(conn, owners: dict[int, str], limit: int | None) -> list[dict]:
    sql = ("SELECT id, character, keyword, frame, stroke_count, jlpt, "
           "owner_id, visibility, script, variant_of, image_url FROM kanji ORDER BY id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    kanji_rows = conn.execute(sql).fetchall()

    entries = []
    for k in kanji_rows:
        aliases = [
            {"alias": a["alias"], "owner": owners.get(a["owner_id"], "unknown"), "visibility": a["visibility"]}
            for a in conn.execute(
                "SELECT alias, owner_id, visibility FROM aliases WHERE kanji_id = ? ORDER BY id", (k["id"],)
            )
        ]

        decompositions = []
        for d in conn.execute(
            "SELECT id, owner_id, visibility, label FROM decompositions WHERE kanji_id = ? ORDER BY id", (k["id"],)
        ):
            parts = [
                p["part_term"] for p in conn.execute(
                    "SELECT part_term FROM parts WHERE decomposition_id = ? ORDER BY position", (d["id"],)
                )
            ]
            decompositions.append({
                "owner": owners.get(d["owner_id"], "unknown"),
                "visibility": d["visibility"],
                "label": d["label"],
                "parts": parts,
            })

        stories = [
            {"owner": owners.get(s["owner_id"], "unknown"), "visibility": s["visibility"], "story": s["story"]}
            for s in conn.execute(
                "SELECT owner_id, visibility, story FROM stories WHERE kanji_id = ? ORDER BY id", (k["id"],)
            )
        ]

        entries.append({
            "id": k["id"], "character": k["character"], "keyword": k["keyword"], "frame": k["frame"],
            "stroke_count": k["stroke_count"], "jlpt": k["jlpt"],
            "owner": owners.get(k["owner_id"], "unknown"), "visibility": k["visibility"],
            "script": k["script"], "variant_of": k["variant_of"], "image_url": k["image_url"],
            "aliases": aliases, "decompositions": decompositions, "stories": stories,
        })
    return entries


def main():
    parser = argparse.ArgumentParser(description="Anonymized flat-file export of kanji.db")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--limit", type=int, default=None, help="Only export the first N kanji rows (testing)")
    args = parser.parse_args()

    secret = os.environ.get("BACKUP_ANON_SECRET")
    if not secret:
        print("BACKUP_ANON_SECRET is not set — refusing to run. A default secret would make the "
              "pseudonyms trivially reversible, which defeats the point.", file=sys.stderr)
        sys.exit(1)
    secret = secret.encode("utf-8")

    if not args.db.exists():
        print(f"No database at {args.db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    owners = build_owner_map(conn, secret)
    entries = export_kanji(conn, owners, args.limit)
    conn.close()

    with open(args.out, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    private_kanji = sum(1 for e in entries if e["visibility"] == "private")
    private_stories = sum(1 for e in entries for s in e["stories"] if s["visibility"] == "private")
    print(f"Exported {len(entries)} kanji ({private_kanji} private) to {args.out}. "
          f"{private_stories} private stories included, owners pseudonymized. "
          f"No password_hash or session tokens were read.")


if __name__ == "__main__":
    main()
