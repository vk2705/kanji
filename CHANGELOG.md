# Changelog

Plain version history for the RTK Kanji app (web + Android). One entry per
release; newest first. The Android app's own version (`versionName` in
`android/app/build.gradle.kts`) and this file are meant to move together —
bump both in the same commit.

Format: `## <version> — <date>` then a short bullet list of what changed,
written for a user, not a commit-message summary.

## 1.1 — 2026-09-20

- Production moved to a new server (`kanji.alteon.help`, Oracle Cloud) —
  the old host (`srv.alteon.help`) is now used for development only. The
  Android app now defaults to the new address.
- Ongoing decomposition-quality audit: dozens of primitive/decomposition
  fixes across the RTK dataset (see `docs/2026-08-search-quality-audit.md`
  for the full log if you want the detail).

## 1.0 — 2026-07-11

- Initial tracked release: auth (local + Google), Chinese hanzi alongside
  Japanese kanji, English/Russian UI, user-contributed decompositions/
  aliases/stories, and the first Android WebView build.
