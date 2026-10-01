You are running unattended, on a daily cron job, with no human watching this
session. Be conservative: when genuinely unsure, record `needs-render` or
leave a row `pending` rather than guessing. Do not do anything outside the
scope below.

## Task

Work one daily chunk of the HANZI decomposition-quality worklist in this repo
(`/home/ec2-user/apps/kanji`), the same way the first manual chunk did — see
`docs/2026-08-search-quality-audit.md`'s "hanzi worklist, chunk 1" entry
(2026-09-30) for the exact method, reasoning style, and tone to match.

```
cd backend && ./venv/bin/python3 hanzi_worklist_next.py -n 20
```

For each of the (up to) 20 rows (each is either an `overlay` or `opaque`
finding — see `backend/audit_hanzi_weak_evidence.py`'s docstring for what
each kind means):

- Render the host character and every component glyph referenced in its
  cjkvi-ids reading via `backend/render_glyphs.py` (batch several at once
  into one PNG, then actually look at the image — this project's standing
  rule is "render it, don't just reason about it", see CLAUDE.md's
  "Verifying a primitive's real identity" section).
- Decide: does the CURRENT decomposition in this database already describe
  what's actually drawn, even though cjkvi-ids' own reading technically uses
  an overlay/enclosure operator, or stops at an opaque intermediate? If yes,
  `keep-ours` — a finding here means the EVIDENCE is weaker than a normal
  ⿰/⿱ case, not that the row is necessarily wrong (most rows in chunk 1 were
  exactly this: visibly-correct parts resting on technically-overlapping
  cjkvi strokes). If the render clearly shows the current parts are wrong
  (missing a visible piece, a lookalike substitution, or — as with 乕 in
  chunk 1 — a previously-investigated correct reading that was never applied
  to this specific row), record `use-cjkvi` or `custom` with the correct
  parts.
- If a component glyph renders as a tofu box / placeholder on this machine's
  font stack (no real outline, not just a small/stylized one — compare
  against a sibling that uses the same component if unsure), or the evidence
  is genuinely ambiguous, record `needs-render` and move on. Do not guess at
  something you can't actually see. Before concluding something is a tofu
  box, double check with a direct render of just that one glyph at large
  size — chunk 1's 临 is the known example (its inner component 𫩏 has no
  real glyph on this machine, confirmed, not just assumed).
- Record every decision via `--decide` (`--status
  keep-ours|use-cjkvi|custom|needs-render`, `--parts "a,b,c"` when the
  decision changes the data, `--by claude`).

## Applying real fixes

A `keep-ours`/`needs-render` decision only touches the worklist JSON — no
further action needed. A `use-cjkvi`/`custom` decision that changes the
actual decomposition must be applied DIRECTLY to `backend/kanji.db` — there
is no `data.txt` line for hanzi rows (they were seeded straight into the DB
by `import_hanzi.py`). Use
`database.expand_part_terms(conn, [...], char_lookup, script_group='zh')` to
build the correctly-expanded parts list (glyph followed by its keyword, same
convention as existing rows), then replace that row's existing system
decomposition's `parts` rows: `DELETE FROM parts WHERE decomposition_id = ?`
then re-`INSERT` the new list at sequential `position`s starting from 0. See
chunk 1's 乕 fix in the audit doc for the exact worked example.

**Always back up first**: `cd backend && ./venv/bin/python3 backup_db.py`.
Before writing: confirm `./venv/bin/pytest -v` currently passes, so a later
failure is attributable to your change. After writing: run it again — if
anything newly fails, restore the backup you just took and record the row as
`needs-render` with a note instead of leaving a broken DB.

## Documentation (required, doc-per-commit rule)

Append one dated `## YYYY-MM-DD — ...` section to
`docs/2026-08-search-quality-audit.md` (use today's actual date, check with
`date`), matching the style, depth, and honesty of the "hanzi worklist,
chunk 1" entry — not a changelog one-liner. Include: how many rows reviewed,
the overlay/opaque breakdown, any real `kanji.db` fixes applied and why they
were right (cite the render / cross-check, not just "looked correct"),
anything deferred and why, and the new pending count
(`hanzi_worklist_next.py --pending-count`).

## Commit and push

Stage exactly: `docs/2026-08-search-quality-audit.md` and
`docs/hanzi_decomposition_worklist.json`. Do NOT stage `backend/kanji.db`
(gitignored, generated — direct hanzi fixes live only in the live DB file on
this machine, which is correct and expected; a maintainer re-applies them to
prod separately, same as every other direct-DB one-off script in this
project). Do NOT stage anything else you didn't intentionally change (check
`git status` — this directory accumulates unrelated stray files and DB
backups; leave them alone). Commit with a message describing what was
reviewed and what changed, ending with:

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

Then `git push origin master`.

## Guardrails

- Never touch anything outside `/home/ec2-user/apps/kanji`.
- Never restart services, modify systemd units, or touch nginx/deploy
  config.
- Only use safe, additive git commands: add, commit, pull with a real
  merge, push. Never use any git command that discards or overwrites
  history or local changes.
- This is a shared dev box with other unrelated work routinely left
  uncommitted in this same working tree (stray scripts, image exports, a
  constantly-regenerated sitemap file, etc.) — that is normal and not your
  concern. Check `git status` only for the two files this job itself
  writes: the hanzi worklist JSON and the audit log doc (see paths below).
  Only stop if one of those two specific files already shows an
  uncommitted change before you've made any edit yourself this run (that
  means a prior invocation of THIS job got interrupted after writing but
  before committing — a real "incomplete prior run" worth investigating
  rather than silently building on or discarding). Do not look at, judge,
  or mention any other file's status.
- If `backend/kanji.db` doesn't exist, or pytest fails before you've made
  any change — stop and leave a note in the doc explaining what you found,
  rather than proceeding.
- If the worklist has 0 pending rows, just say so in the doc entry and stop.
- This is the HANZI worklist only. Do not touch
  `docs/decomposition_worklist.json` or run `worklist_next.py` — that is a
  separate daily job for a separate, independent routine already running on
  its own schedule. Expect `backend/data.txt` and
  `docs/2026-08-search-quality-audit.md` to sometimes change out from under
  you between runs (that routine's own commits) — this is normal
  concurrent work on a shared repo, not an error. If a plain `git push` is
  rejected because the remote has commits you don't have, bring them in
  with an ordinary merge (never discard local or remote history to force
  past this) before retrying the push; if that produces a merge conflict in
  the audit log doc (both routines append dated entries near the file's
  end), resolve it by keeping both entries in full, one after the other,
  removing only the conflict markers — never drop either side's content.
