# Security audit plan — 2026-09-21

Owner ask: "план security audit ... чтоб плохой юзер не внес гадость" — a user
with a registered account should not be able to get abusive/spam/malicious
content or behavior live for other visitors to see.

Before adding anything new: `docs/2026-08-31-architecture-review.md` already
covers a real security pass — privacy-boundary fix (#1), transactional
migrations (#2), an isolated test suite (#3), **rate limiting + field-length
validation + analytics retention (#4)**, atomic upload writes (#5). Don't
re-audit those; this plan picks up where #10 in that doc's roadmap left off
("moderation tools" — explicitly still queued, never built) plus a few
angles that document doesn't cover at all (frontend content-escaping,
whether the existing decomposition cycle-guard actually applies to
user-submitted data, not just system data). Same rule as that doc: verify
each finding against real code/behavior before trusting the hypothesis —
two of my own initial guesses this pass (rate limiting, upload atomicity)
turned out to already be fixed once checked, so don't skip the check step.

## Priority 1 — no moderation gate before a contribution goes public

`contributions.py`: every write endpoint (`/kanji`, `/kanji/{id}/decompositions`,
`/aliases`, `/stories`, `/kanji/{id}/image`) defaults to `visibility="private"`,
but `PATCH .../visibility` flips any of the caller's own rows to `"public"`
immediately — no review step, no rate limit distinct from the general write
limit, no size/content check beyond the length caps #4 already added. Once
public, it's visible to every anonymous visitor via search/detail
(`get_kanji_detail`, `search_by_*`) same as system data.

Concretely, a registered user today can make **immediately, unreviewedly
public**: an alias (up to 200 chars), a mnemonic story (up to 20,000 chars),
an uploaded image (up to 2MB, real gif/png/jpeg/webp — format-validated but
content-unmoderated), or a whole new kanji/primitive entry with an arbitrary
keyword. `review_queue.py`/`decomposition_reviews` is a different thing
entirely — crowd-sourced *decomposition-correctness* flagging, not an
abuse/moderation gate, and it's advisory (a maintainer acts on it
out-of-band) rather than blocking publication.

Tasks:
- [ ] Decide the moderation model before building anything (owner call, not
  mine): pre-publish queue (public visibility requires approval) vs.
  post-publish (goes live immediately, flag+takedown after the fact) vs.
  trust-tier (e.g. first N contributions of a new account are queued, then
  auto-approve). Given "scale: single low-traffic app" this doesn't need to
  be elaborate, but it does need to exist in some form.
- [ ] Whatever the model, an explicit way for a maintainer to see recent
  public contributions and revoke one (set back to private, or delete) —
  check whether `set_visibility`/`get_my_contributions` already give enough
  of a primitive for this or a new endpoint is needed.
- [ ] Image uploads specifically: confirm whether a maintainer can currently
  even list "all public uploaded images" anywhere, or would have to walk
  `backend/uploads/` on disk — same gap, worse blast radius (an image is far
  more visible/shareable than a text alias).

## Priority 2 — user-generated text rendering safety (stored XSS)

Not mentioned in the 2026-08-31 review at all. Aliases/stories/keywords/labels
are free text, several with generous caps (story up to 20,000 chars), and end
up rendered back into the page for other viewers.

Tasks:
- [ ] Check every frontend component that renders alias/story/keyword/label
  text (`KanjiDetail.jsx`, `ResultsGrid.jsx`, `KanjiCard.jsx`,
  `MyContributions.jsx`, `CreateKanji.jsx`) for `dangerouslySetInnerHTML` or
  any other bypass of React's default text-escaping.
  React's default JSX text rendering already escapes this, so the expected
  finding is "nothing to fix" — but verify, don't assume, same discipline
  as everything else in this plan.
- [ ] Confirm the `image_url` field (server-derived, `/uploads/{id}.{ext}`)
  is never rendered as a raw `href`/`src` built from anything *other than*
  that server-derived string on the frontend — i.e. a malicious `label` or
  `story` couldn't smuggle in a `javascript:` URL that ends up in an `<a>`.

## Priority 3 — confirm existing guards actually cover user-submitted data

- [ ] `search_by_parts`'s decomposition traversal has a documented
  `MAX_DECOMPOSITION_DEPTH` + ancestor-cycle-guard (per
  `2026-08-search-quality-audit.md`) — confirm this guard is truly universal
  (applies to a user's own newly-submitted decomposition, not just
  system/Heisig data) by constructing a deliberate circular
  decomposition (A's parts include B, B's parts include A) as a test user
  and confirming the search/detail endpoints don't hang or blow up. If it's
  already universal, this is a five-minute confirmation, not a fix.
- [ ] `PATCH /auth/preferences`'s `set_clause = ", ".join(f"{k} = ?" for k in
  updates)` builds column names from `body.model_dump(exclude_unset=True)`
  keys — confirm Pydantic's default `extra="ignore"` on `PreferencesUpdate`
  actually rejects/drops unexpected JSON keys (it should, by default, but
  this is exactly the kind of assumption this project's own convention says
  to verify rather than trust).
- [ ] Registration abuse: rate-limited at 5/min/IP (per #4) but no CAPTCHA/
  email verification — note as accepted residual risk unless the owner
  wants more, don't build anything here without asking first (this is a
  UX-cost tradeoff, not a clear bug).

## Explicitly not re-litigating (already covered, verified live)

Rate limiting, field-length validation, analytics retention, upload
atomicity, alias-visibility-boundary fix, migration atomicity, isolated test
suite — all in `docs/2026-08-31-architecture-review.md`, all verified
against the live server at the time, not just code-reviewed.
