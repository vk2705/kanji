#!/bin/bash
# Back-to-back kanji full-review batches (owner request 2026-11-03: "do batches
# until out of credits"). Each batch is one run_kanji_worklist_review.sh.
# Stops when a batch fails (e.g. credits exhausted), when a batch makes no
# progress (e.g. the dead-run guardrail tripped), or when nothing is pending.
set -uo pipefail
cd /home/ec2-user/apps/kanji/backend
pending() { ./venv/bin/python3 full_review.py --pending-count | awk '{print $1}'; }
while :; do
    before=$(pending)
    echo "=== loop: $before pending $(date -u +%FT%TZ) ==="
    [ "$before" -eq 0 ] && { echo "nothing pending, done"; exit 0; }
    if ! timeout 3h ./run_kanji_worklist_review.sh; then
        echo "batch failed (credits out?), stopping"; exit 1
    fi
    after=$(pending)
    if [ "$after" -ge "$before" ]; then
        echo "no progress ($before -> $after), stopping"; exit 1
    fi
done
