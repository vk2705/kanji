You are running unattended, on a daily timer, with no human watching this
session. Be conservative: when genuinely unsure, record `needs-render` or
leave a row `pending` rather than guessing. Do not do anything outside the
scope below.

## Task

Work one daily chunk of the KANJI decomposition-quality worklist
(`docs/decomposition_worklist.json`) in this repo (`/home/ec2-user/apps/kanji`),
the same way the manual chunks did — see `docs/2026-08-search-quality-audit.md`'s
"worklist loop, day 1" (2026-09-05) and "kanji worklist chunk" (2026-10-01)
entries for the method, the reasoning style and the tone to match.

Each row is an `rtk*` kanji whose current `backend/data.txt` decomposition
disagrees with Google's AI-Overview breakdown. Google is often right (our data
over-decomposes, flattening a coherent RTK primitive into its strokes), but it
is just another LLM: cjkvi-ids and a rendered glyph break ties.

```
cd backend && ./venv/bin/python3 worklist_next.py -n 20
```

For each of the (up to) 20 rows:

- Render the host kanji and every component glyph in both readings (ours and
  Google's) with `backend/render_glyphs.py` — batch several into one PNG, then
  actually look at the image. Standing rule: "render it, don't just reason
  about it" (CLAUDE.md, "Verifying a primitive's real identity"). Cross-check
  `/tmp/ids.txt` (cjkvi-ids) and `heisig-kanjis.csv`'s components column.
- Compare at the same depth, not token by token: Google often expands a
  compound (場 → 土,日,一,勿) that our row correctly keeps whole (土,昜). That
  is `keep-ours`.
- If the render shows our parts are wrong (a misread shape, a stray stroke
  double-counting a piece already inside another part, a lookalike
  codepoint), record `use-google` or `custom` with the correct parts.
- If a glyph renders as a tofu box on this machine, or the evidence is
  genuinely ambiguous, record `needs-render` and move on.
- Record every decision: `./venv/bin/python3 worklist_next.py --decide rtkNNN
  --status keep-ours|use-google|custom|needs-render [--parts "a,b"] --by claude`.

## Applying real fixes

A `use-google`/`custom` decision changes `backend/data.txt` (the `rtkNNN:` line;
format in CLAUDE.md — keep any `;` alternates after the primary). Then:

1. Before editing anything: `./venv/bin/python3 backup_db.py`, and confirm
   `./venv/bin/pytest -q` and `./venv/bin/python3 test_regression_fixes.py`
   pass (or note their baseline failures), so a later failure is attributable.
2. If a new part names a compound that has never had its own row (e.g. 楚
   used as one piece where data.txt only ever flattened it), give it a row
   first (`prim-{slug}`, or `kangxi{n}` if it is one of the 214) — otherwise it
   is silently unresolvable. `audit_radicals.py` catches this; run it.
3. Apply to this machine's DB: `./venv/bin/python3 sync_system_data.py --dry-run`,
   check the counts are small and sane, then without `--dry-run`.
4. Re-run `pytest -q`, `test_regression_fixes.py` and `audit_radicals.py`.
   If a regression pin fails *because of a correct fix*, update that pin in
   place with a comment explaining why the new value is right. If anything
   else newly fails, revert your `data.txt` edit, re-run `sync_system_data.py`,
   and record that row as `needs-render` with a note.
5. `./venv/bin/python3 build_decomp_worklist.py` — drops rows whose fixed
   decomposition now agrees with Google.

Do not deploy to production — no server access from here. Say in the doc
entry that a deployer needs `git pull` + `sync_system_data.py` on prod.

## Documentation (required, doc-per-commit rule)

Append one dated `## YYYY-MM-DD — kanji worklist chunk: ...` section to
`docs/2026-08-search-quality-audit.md` (today's date from `date`), matching the
depth and honesty of the 2026-10-01 kanji chunk entry: rows reviewed, every
real fix and why it is right (cite the render and the cross-check), anything
deferred and why, the test numbers, and the new pending count
(`worklist_next.py --pending-count`).

## Commit and push

Stage only what this job changed: `docs/2026-08-search-quality-audit.md`,
`docs/decomposition_worklist.json`, and — only if you made a real fix —
`backend/data.txt` and `backend/test_regression_fixes.py`. Never stage
`backend/kanji.db` or anything else. Commit with a message saying what was
reviewed and what changed, ending with:

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

Then `git push origin master`.

## Guardrails

- Never touch anything outside `/home/ec2-user/apps/kanji`. Never restart
  services, change systemd units, or touch nginx/deploy config.
- Only safe, additive git commands: add, commit, pull with a real merge, push.
  Never discard or overwrite history or local changes.
- This is a shared dev box; the working tree always has unrelated uncommitted
  files. Ignore them. In particular **`docs/decomposition_worklist.json` being
  modified before you start is normal**: the nightly `kanji-daily-review` job
  rebuilds it at 02:00 and does not commit. Build on it and commit it with
  your chunk.
- The one real "incomplete prior run" signal is `backend/data.txt` already
  showing an uncommitted change before you have edited it. Only this job edits
  data.txt on this machine, so that means a previous run died mid-fix. In that
  case stop, and write a doc entry describing the diff instead of building on
  it or discarding it.
- Other routines push to this repo too: a cloud audit routine (around 09:00
  UTC, edits data.txt and the audit doc) and the hanzi worklist job (10:00
  UTC). Start with `git pull` (ordinary merge). If a push is rejected, pull
  with a merge and retry; if the audit doc conflicts, keep both sides' entries
  in full, one after the other.
- If `backend/kanji.db` does not exist, or pytest fails before you changed
  anything, stop and leave a note in the doc.
- If the worklist has 0 pending rows, say so in the doc entry and stop.
- This is the KANJI worklist only. Do not touch
  `docs/hanzi_decomposition_worklist.json` or run `hanzi_worklist_next.py`.
