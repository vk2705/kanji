#!/bin/bash
# Daily kanji decomposition worklist review, run by
# kanji-worklist-review.timer via kanji-worklist-review.service.
# See backend/kanji_worklist_daily_prompt.md for what the agent actually does.
set -euo pipefail
cd /home/ec2-user/apps/kanji
# cjkvi-ids lives in /tmp, which systemd-tmpfiles empties of anything unused
# for 10 days; the review needs it to cross-check every row.
if [ ! -s /tmp/ids.txt ]; then
    curl -fsSL https://raw.githubusercontent.com/cjkvi/cjkvi-ids/master/ids.txt -o /tmp/ids.txt.part \
        && mv /tmp/ids.txt.part /tmp/ids.txt
fi
echo "=== kanji worklist review $(date -u +%FT%TZ) ==="
exec /home/ec2-user/.local/bin/claude -p --dangerously-skip-permissions --model sonnet \
    --output-format text \
    "$(cat /home/ec2-user/apps/kanji/backend/kanji_worklist_daily_prompt.md)"
