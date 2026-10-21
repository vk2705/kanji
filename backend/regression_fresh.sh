#!/bin/bash
# Run test_regression_fixes.py the way CI does: against a database seeded fresh
# from the checked-in data.txt / data_from_pdf.txt / heisig-kanjis.csv, in a
# throwaway copy of backend/, never against backend/kanji.db.
#
# Why (2026-10-21): on this one-CPU dev box the same script run against the live
# kanji.db (24k rows, plus legacy rows the source files no longer have) takes
# 10-20 minutes with no output -- the daily full-review job gave up waiting and
# never committed its first chunk -- and reports 6 failures that are quirks of
# that old DB, not of the source files. Fresh, it takes about 2 minutes, and a
# failure means the source files are wrong. Exit status is the script's own.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d /tmp/regression-fresh.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
rsync -a --exclude venv --exclude 'kanji.db*' --exclude backups --exclude logs \
    --exclude uploads --exclude 'kanji.db.bak-*' "$HERE/" "$WORK/backend/"
cd "$WORK/backend"
"$HERE/venv/bin/python3" -c "import database; database.init_db(); c = database.get_db(); database.migrate_schema(c); c.close(); database.import_data()" > /dev/null
"$HERE/venv/bin/python3" test_regression_fixes.py
