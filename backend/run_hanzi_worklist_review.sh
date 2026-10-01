#!/bin/bash
# Daily hanzi decomposition worklist review, run by
# hanzi-worklist-review.timer via hanzi-worklist-review.service.
# See backend/hanzi_worklist_daily_prompt.md for what the agent actually does.
set -euo pipefail
cd /home/ec2-user/apps/kanji
exec /home/ec2-user/.local/bin/claude -p --dangerously-skip-permissions --model sonnet \
    --output-format text \
    "$(cat /home/ec2-user/apps/kanji/backend/hanzi_worklist_daily_prompt.md)"
