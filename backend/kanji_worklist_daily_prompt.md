You are running unattended, on a daily timer, with no human watching this
session. Be conservative: when genuinely unsure, record `needs-render` rather
than guessing. Do not do anything outside the scope below.

## Task

Work today's chunk of the FULL RE-REVIEW of every Japanese kanji
(`docs/kanji_full_review.json`, driven by `backend/full_review.py`), in this
repo (`/home/ec2-user/apps/kanji`).

Why it exists (owner decision, 2026-10-21): the earlier worklist only queued
kanji whose breakdown disagreed with Google's AI answer. 亀 was `日,勹,乙` in
our data and in Google's, so it was never looked at, while the real shape is
`𠂊 + 电` ("bound up" + "eel") — and 電/竜, which share that bottom, had been
fixed a month earlier without anyone checking 亀. Agreement with Google proves
nothing. This review checks every kanji against what is actually drawn.

```
cd backend && ./venv/bin/python3 full_review.py -n 50
```

For each of the (up to) 50 rows, in order:

1. **Render** the kanji and every part in its current row with
   `backend/render_glyphs.py`, batching several kanji per PNG, and look at the
   image. Standing rule: render it, don't reason about it (CLAUDE.md,
   "Verifying a primitive's real identity").
2. **Heisig's components column** (shown by full_review.py) is the list of
   names his book uses for the pieces, fully expanded. Every shape it names
   must be reachable from our row, and our row must not contain a shape that
   is not drawn. An EMPTY column means he teaches the kanji whole: that is
   positive evidence the row should be atomic, not missing data.
3. **cjkvi-ids** is a structural cross-check. Beware ⿻ and ⿴: those overlay
   shapes that share strokes, so the pieces are not separate parts (蝿's
   `⿻日电` is not a 日 plus a 电). Run `./venv/bin/python3 audit_weak_evidence.py
   --host <char>` on anything that looks wrong before changing it.
4. **Right level, not stroke soup.** Prefer the coherent primitive Heisig
   names over its strokes (`电`, not `日,乙`; `昜`, not `日,一,勿`).
5. **No lookalikes.** The correct codepoint, never a better-supported
   lookalike (𠂊 is not 勹; 丰 is not 龶). CLAUDE.md lists the traps.
6. Google's answer is shown as a hint only. Never decide on it alone.

Decide each row:
- `keep` — the current row is right.
- `fixed` — you changed `data.txt` (below); `--parts` is the new primary.
- `needs-render` — you could not decide (tofu glyph, ambiguous evidence).

Record every row, always with a one-line reason, because it is shown to the
owner in the kanji's history:
```
./venv/bin/python3 full_review.py --decide rtkNNN --status keep|fixed|needs-render \
    [--parts "a,b"] --note "why" --by claude
```

## Applying fixes

1. Before editing: `./venv/bin/python3 backup_db.py`, and record the baselines
   of `./venv/bin/pytest -q`, `./venv/bin/python3 test_regression_fixes.py`
   and `./venv/bin/python3 audit_radicals.py`.
2. Edit the `rtkNNN:` line in `backend/data.txt` (format in CLAUDE.md; keep `;`
   alternates that are still right) and put a short `#` comment above it
   saying what it was and why it changed — the history page shows it.
3. If a new part is a compound that has no row of its own, give it one
   (`prim-{slug}`, or `kangxi{n}` for the 214 radicals) or it will silently
   not resolve.
4. **Shape-family check (the 亀 lesson):** when you fix how a shape is
   written, find every other kanji whose row or Heisig components use the same
   shape or name (`grep` data.txt and heisig-kanjis.csv) and list them in your
   doc entry. Fix the ones that are clearly the same mistake in this run; the
   rest are decided when their own frame comes up.
5. Apply to this machine's DB: `./venv/bin/python3 sync_system_data.py --dry-run`,
   check the counts are sane, then run it for real.
6. Re-run the three checks. If a regression pin fails *because of a correct
   fix*, update the pin in place with a comment saying why. If anything else
   newly fails, revert that data.txt edit, re-sync, and record the row as
   `needs-render` with a note.

No production deploys from here: say in the doc entry that a deployer needs
`git pull` + `sync_system_data.py` on prod.

## Documentation

Append one dated `## YYYY-MM-DD — full re-review: frames N–M` section to
`docs/2026-08-search-quality-audit.md` (today's date from `date`): how many
kept / fixed / needs-render, every fix and why (cite the render and Heisig's
column), the shape-family follow-ups, the test numbers, and
`full_review.py --pending-count`.

## Commit and push

Stage only what this job changed: `docs/2026-08-search-quality-audit.md`,
`docs/kanji_full_review.json`, and when you made fixes, `backend/data.txt`
and `backend/test_regression_fixes.py`. Never stage `backend/kanji.db` or
anything else. Commit message: what range was reviewed and what changed,
ending with:

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

Then `git push origin master`.

## Guardrails

- Never touch anything outside `/home/ec2-user/apps/kanji`. Never restart
  services, change systemd units, or touch nginx/deploy config.
- Only safe, additive git commands: add, commit, pull with a real merge, push.
  Never discard or overwrite history or local changes.
- This is a shared dev box; the working tree always has unrelated uncommitted
  files (including `docs/decomposition_worklist.json`, rebuilt nightly).
  Ignore them.
- The "previous run died midway" signal is `backend/data.txt` or
  `docs/kanji_full_review.json` already showing uncommitted changes before you
  have touched them. Then stop, and write a doc entry describing the diff
  instead of building on it or discarding it.
- Other routines push to this repo: a cloud audit routine (around 09:00 UTC,
  edits data.txt and the audit doc) and the hanzi worklist job (10:00 UTC).
  Start with `git pull` (ordinary merge). If a push is rejected, pull with a
  merge and retry; if the audit doc conflicts, keep both entries in full.
- If `backend/kanji.db` does not exist, or pytest fails before you changed
  anything, stop and leave a note in the doc.
- If there are 0 pending rows, say so in the doc entry and stop.
- Japanese kanji only: do not touch the hanzi worklist or
  `docs/decomposition_worklist.json` (the old Google-disagreement list, now
  superseded by this review).
