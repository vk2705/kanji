# Where this database's data comes from

Written 2026-09-23. The database is a merge of sources with very different
standing, and until now nothing recorded which was which. `backend/provenance_report.py`
computes the current numbers; this file explains what they mean and what follows
from them.

Run it for live figures:

```bash
cd backend
./venv/bin/python3 provenance_report.py                # the counts
./venv/bin/python3 provenance_report.py --list-heisig  # the exact rows and strings
```

## The sources

| Source | What it gives | Standing |
|---|---|---|
| **kanjidic2** (EDRDG) | on'yomi/kun'yomi readings, the `rtk*` glyph inventory via `import_rtk.py` | Open — CC BY-SA, attribution required |
| **KRADFILE** (EDRDG) | the first-pass radical decompositions `data.txt` started from | Open — CC BY-SA, attribution required |
| **Unihan** (Unicode Consortium) | the hanzi rows, pinyin | Open — Unicode licence, attribution required |
| **cjkvi-ids** | the structural decompositions (`⿰⿱…` IDS), every `structural (cjkvi-ids)` alternate, and the ground truth the whole 2026-08/09 audit checks against | Open — attribution required |
| **Unicode `CJKRadicals.txt`** | the 69 `kangxi*` row ids and the official radical numbering | Open — Unicode licence |
| **This project** | the 146 `prim-*` rows and their descriptive names, every decomposition correction in `docs/2026-08-search-quality-audit.md` (60+ chunks), the Russian aliases, all user contributions | Ours |
| **Remembering the Kanji, James W. Heisig** | the frame numbers, the keyword for each frame, and the primitive names his components column emits | **In-print commercial book, copyrighted** |

The first five are the bulk of the structure. The last is the part that needs
thinking about, and `heisig-kanjis.csv` is where it enters: a third-party CSV of
the RTK index whose own columns are named `id_5th_ed`, `id_6th_ed`,
`keyword_5th_ed`, `keyword_6th_ed`, `components`. It was in the repository before
the audit history begins and its upstream is not recorded.

## How much of the database is Heisig's

As of 2026-09-23, of 13,832 names (keywords + aliases) on system rows:

| | |
|---|---|
| 9,422 | **mechanical** — the glyph itself, the row id, the frame number as a string |
| 2,428 | **frame keywords** from his columns — `孔 cavity`, `類 sort`, `膝 knee` |
| 1,185 | **primitive names** from his components column — `儿 human legs`, `癶 teepee`, `疒 hospital` |
| 797 | **ours or open data** — `癶 back-to-back feet`, `礻 leftside altar`, `儿 legs` |

So **3,613 names across 3,198 rows** come from his columns. `--list-heisig`
prints them, which is the point of the script: if those ever have to go, that is
one scripted edit rather than an archaeology project.

## The distinction that matters, and the one that doesn't

**Doesn't matter: invented versus ordinary, name by name.** Individual words and
short phrases are not copyrightable — in the US that is written down explicitly
(37 CFR § 202.1(a), "words and short phrases such as names, titles, and
slogans"); elsewhere the originality threshold gets to the same place. "St.
Bernard" as a phrase is not anyone's property. A first draft of the provenance
script tried to sort names into "invented" and "common" with a heuristic and put
*teepee*, *wigwam* and *spiderman* on the wrong side, which is a good
illustration of why the line is not worth drawing mechanically — and it would
not change anything if it were drawn correctly.

**Does matter: the compilation.** What has real protection is the systematic
mapping — ~2,200 kanji to keywords, and the set of primitive names, as a
selected and arranged whole. That is the *Feist* distinction: facts are not
protectable, an original selection of them can be. Any plan that keeps the whole
mapping and only relabels which column is displayed first leaves this exactly
where it was.

**Also matters: republication versus indexing.** A search box that finds 明 when
someone types "sun" + "moon" is a finding aid. `generate_seo_pages.py` writes
3,215 static HTML pages, one per kanji, each stating the character, the keyword
and the decomposition, plus a sitemap for crawlers. That is closer to publishing
an edition of the index, and it is the strongest lever on the project's
position — far more than which names sit in which column.

The distinction Heisig's *own* sources do make, and which the script therefore
reports, is **frame keyword** versus **primitive name**. His invention is
concentrated in the second (*st. bernard*, *fred astaire*, *radio caroline*,
*musashimaru*), and that is also the column this app's parts search is built on
and the 60-chunk audit validates against. Which is exactly why replacing those
names with new inventions would cost the product its reason to exist while
leaving the compilation untouched.

## What is deliberately not stored

The mnemonic **stories** from the book. That is unambiguously protected prose
and has been excluded from the start; user-written stories are a separate,
non-copyrighted addition. See CLAUDE.md, "Known limitations".

## Not done, and not to be done

Recording a different origin for this data than the one above — attributing it
to kanji.koohii.com, a public Anki deck, or an AI summary — was considered and
rejected on 2026-09-23. It does not reduce exposure and it increases it:
a documented false statement of provenance turns an arguable fair-use position
into evidence of willful infringement (in the US, treble statutory damages), and
the CSV's own column names plus this repository's history make the real source
visible immediately. The intermediate sources would not help even if the claim
were true — they are themselves unlicensed reproductions of the same index, and
search engines indexing something confers no licence on it.

## What follows from this

1. **Attribution is in place** as of this commit — the About page names the book,
   links to it, and credits the open-data sources whose licences require it
   (which, separately from Heisig, was an outstanding obligation to EDRDG,
   Unicode and cjkvi-ids).
2. **The Heisig-derived set is now enumerable** in one command, so a takedown
   would be a scripted edit.
3. **The SEO pages are the open question.** Options, safest first: do not publish
   them (the SPA works without them); publish them without the keyword in the
   title and description; publish as now. This has not been decided.
4. **A lawyer is worth an hour** before the site grows further or takes money.
   The question to ask: does the keyword index constitute a protected
   compilation, and does a searchable index plus static per-entry pages
   constitute reproduction of it.
