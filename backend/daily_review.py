#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
daily_review.py -- nightly "check the database for problems" routine for both
kanji and hanzi (owner-requested, 2026-10-02; there was no scheduled routine
of this kind before this script -- the audit_*.py scripts are a manual,
run-by-hand backlog, not something anything invoked daily).

## What this runs, and why each one

1. review_queue.py        -- pending user-submitted decomposition approve/dispute
                              votes on the LIVE kanji.db. Genuinely time-sensitive:
                              this is new user activity, not a static backlog.
2. build_decomp_worklist.py  -- regenerates docs/decomposition_worklist.json
   build_hanzi_worklist.py     and docs/hanzi_decomposition_worklist.json from
                              the current audit_*.py findings. Both builders
                              preserve already-decided rows by id and only
                              add/refresh undecided ones (see their own
                              docstrings), so this is safe to run every night.
3. Every audit_*.py script (kanji + hanzi) that runs standalone with no
   required args and no external API key -- see EXCLUDED below for the one
   that needs an OpenAI key and isn't run here. Each one's full report is
   appended to the dated log; this script's own stdout is just a summary
   (finding count per script, or "ERROR" if a script exited non-zero) so a
   human can skim one screen instead of reading every report end to end.

## EXCLUDED: audit_decomposition.py

Needs `pip install openai` (not in requirements.txt) and `OPENAI_API_KEY` --
neither is set up on this box, and it would cost money per run. Left out of
the nightly routine deliberately; run it by hand if/when that's wanted.
coverage_status.py and suggest_heisig_aliases.py are informational trackers,
not problem-finders, so they're also left out of this routine specifically
(they still exist as their own manual commands -- see CLAUDE.md).

## Output

Writes backend/logs/daily_review_YYYY-MM-DD.log (full reports, for whoever
wants the detail) and prints a short summary to stdout (for cron/systemd
journal and for a quick skim). Keeps 30 days of logs, pruning older ones on
each run -- same reasoning as backup_db.py's retention, just simpler (no
database rollup needed, these are disposable reports regenerable from
source files + kanji.db at any time).

Usage:
    ./venv/bin/python3 daily_review.py
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
LOG_DIR = HERE / "logs"
RETAIN_DAYS = 30
# Invoked as `PYTHON script.py`, not by exec bit -- several of these scripts
# aren't individually chmod +x (confirmed 2026-10-02: only 6 of 16 are), so
# relying on their own shebang would make this fail on exactly the ones that
# happen not to be executable.
PYTHON = str(HERE / "venv" / "bin" / "python3")

# (label, argv, timeout_seconds). Order: fast live-DB check first, then the
# two worklist builders, then the slower source-file audits, kanji before hanzi.
#
# Per-script timeouts tuned from single isolated measurements proved unreliable
# in practice (2026-10-02/03): audit_weak_evidence timed out at 300s despite
# measuring 391s standalone, then audit_missing_children timed out at 300s on
# a run where it had previously finished -- that one turned out to be a real
# O(rows x identities) quadratic bug in row_for_glyph (fixed the same day, see
# audit_missing_children.py's build_glyph_index), which explains why its
# runtime swung so wildly between runs. Rather than keep chasing individual
# numbers, every non-trivial step gets the same generous ceiling: this job
# runs overnight unattended (kanji-daily-review.timer fires at 02:00, 75
# minutes before the 03:15 db backup) with no tight deadline, so a long
# timeout costs nothing on a normal night and only matters if a script is
# truly stuck -- in which case 15 minutes is already far past any measured
# runtime (the slowest confirmed so far, audit_weak_evidence, took 6m31s).
FAST = 120
SLOW = 900
STEPS = [
    ("review_queue", [PYTHON, str(HERE / "review_queue.py")], FAST),
    ("build_decomp_worklist", [PYTHON, str(HERE / "build_decomp_worklist.py")], SLOW),
    ("build_hanzi_worklist", [PYTHON, str(HERE / "build_hanzi_worklist.py")], SLOW),
    ("audit_radicals", [PYTHON, str(HERE / "audit_radicals.py")], FAST),
    ("audit_self_reference", [PYTHON, str(HERE / "audit_self_reference.py")], SLOW),
    ("audit_phantom_parts", [PYTHON, str(HERE / "audit_phantom_parts.py")], SLOW),
    ("audit_missing_children", [PYTHON, str(HERE / "audit_missing_children.py"), "--summary"], SLOW),
    ("audit_overflatten", [PYTHON, str(HERE / "audit_overflatten.py")], SLOW),
    ("audit_csv_regressions", [PYTHON, str(HERE / "audit_csv_regressions.py")], SLOW),
    ("audit_anachronistic_names", [PYTHON, str(HERE / "audit_anachronistic_names.py"), "--all"], SLOW),
    ("audit_flattening", [PYTHON, str(HERE / "audit_flattening.py")], SLOW),
    ("audit_flattening_subsequence", [PYTHON, str(HERE / "audit_flattening_subsequence.py")], SLOW),
    ("audit_direct_ref_overlap", [PYTHON, str(HERE / "audit_direct_ref_overlap.py")], SLOW),
    ("audit_primary_choice", [PYTHON, str(HERE / "audit_primary_choice.py"), "--all"], SLOW),
    ("audit_weak_evidence", [PYTHON, str(HERE / "audit_weak_evidence.py")], SLOW),
    ("audit_hanzi_weak_evidence", [PYTHON, str(HERE / "audit_hanzi_weak_evidence.py")], SLOW),
]


def prune_old_logs():
    cutoff = datetime.now() - timedelta(days=RETAIN_DAYS)
    for f in LOG_DIR.glob("daily_review_*.log"):
        try:
            day = datetime.strptime(f.stem.removeprefix("daily_review_"), "%Y-%m-%d")
        except ValueError:
            continue
        if day < cutoff:
            f.unlink()


def run_step(label, argv, timeout, log):
    log.write(f"\n{'=' * 70}\n{label}\n{'=' * 70}\n")
    start = time.monotonic()
    try:
        result = subprocess.run(
            argv, cwd=HERE, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        log.write(f"TIMED OUT after {timeout}s\n")
        if e.stdout:
            log.write(e.stdout)
        elapsed = time.monotonic() - start
        return f"{label}: TIMEOUT ({elapsed:.0f}s)"

    elapsed = time.monotonic() - start
    log.write(result.stdout)
    if result.stderr:
        log.write("\n--- stderr ---\n")
        log.write(result.stderr)

    # audit_self_reference.py deliberately exits 1 when it finds a real
    # self-reference bug (its own docstring: "so it can be used as a pass/
    # fail gate") -- that is success for a problem-finding routine, not a
    # crash, and treating it as ERROR here is a false alarm (caught
    # 2026-10-03: it reported 2 genuine bugs and still got flagged as
    # failed). A script crashing outright (traceback, no report at all) is
    # the only thing this should flag -- stderr with no stdout report is
    # the signal for that, not the exit code alone.
    if result.returncode != 0 and label != "audit_self_reference":
        return f"{label}: ERROR (exit {result.returncode}, {elapsed:.0f}s)"

    # Best-effort finding count: most scripts end their report with a line
    # like "N phantom part(s) across M kanji" or "N row(s)" -- not worth a
    # per-script parser, so just surface the last non-empty output line.
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    tail = lines[-1].strip() if lines else "(no output)"
    return f"{label}: {tail} [{elapsed:.0f}s]"


def main():
    LOG_DIR.mkdir(exist_ok=True)
    prune_old_logs()

    cjkvi_path = Path(os.environ.get("CJKVI_IDS", "/tmp/ids.txt"))
    if not cjkvi_path.exists():
        print(
            f"CJKVI_IDS data file not found at {cjkvi_path} -- most audit steps below "
            "need it and will fail. It lives outside the repo (third-party cjkvi-ids "
            "data, not committed) and /tmp can be cleared on reboot; re-fetch it and "
            "either place it back at that path or set CJKVI_IDS to wherever it lives. "
            "Continuing anyway so the few steps that don't need it (review_queue, "
            "audit_radicals) still run.",
            file=sys.stderr,
        )

    today = datetime.now().strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"daily_review_{today}.log"

    summary_lines = [f"Daily kanji/hanzi review -- {datetime.now().isoformat(timespec='seconds')}"]
    had_error = False
    with open(log_path, "w") as log:
        log.write(summary_lines[0] + "\n")
        for label, argv, timeout in STEPS:
            line = run_step(label, argv, timeout, log)
            summary_lines.append(line)
            if "ERROR" in line or "TIMEOUT" in line:
                had_error = True

    summary = "\n".join(summary_lines)
    print(summary)
    print(f"\nFull reports: {log_path}")
    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
