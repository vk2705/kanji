# KumiJi character decomposition dataset

Which shapes each Japanese kanji and Chinese hanzi is built from, as flat CSVs.

Exported from the live [KumiJi Glyph Explorer](https://kumiji.kermit.is-a.dev)
database. Regenerate at any time with `backend/export_dataset.py` (see
*Reproducing this* below).

| | |
|---|---|
| Characters | 8,878 |
| — Japanese kanji (`rtk*`) | 3,000 |
| — Chinese hanzi (`hanzi-*`, Simplified + Traditional) | 5,626 |
| — primitives and radicals (`prim-*`, `kangxi*`) | 252 |

## What makes this different from the sources it started from

The Japanese half has been checked by hand, character by character. Every one
of the 3,000 kanji went back through a full re-review in 2026: the rendered
glyph compared against Heisig's components column and against cjkvi-ids, with
a shape-family check on every correction (if a fix changed one shape, every
other character containing that shape was checked too).

| Outcome | Count |
|---|---|
| Confirmed unchanged | 2,827 |
| Corrected | 159 |
| Still open (needs a careful render) | 14 |

The reason that was worth doing is that the obvious machine-readable sources
each fail in a specific, silent way, and none of them tells you when it has:

- **An Ideographic Description Sequence is not a parts list.** When the
  operator is `⿻` or `⿴` the shapes *overlap and share strokes*, so cjkvi's
  `蝿 = ⿰虫⿻日电` does not mean the visible top box is 日 — rendered, it is 田.
- **Components with no codepoint are written as circled numbers, and those are
  per-entry placeholders, not identifiers.** `③` is the bottom of 不, the left
  of 北, the left of 印 and a 止 variant in 此 — four different shapes. Joining
  on them produces confident nonsense.
- **A missing component column can mean "atomic" or "no data", depending on
  where you are in the book**, and nothing marks which.

Full working log, 30,000+ lines with the reasoning for each decision:
[`docs/2026-08-search-quality-audit.md`](https://github.com/vk2705/kanji/blob/master/docs/2026-08-search-quality-audit.md).

## Files

### `characters.csv` — one row per character

| Column | Notes |
|---|---|
| `id` | stable row id: `rtk{n}`, `hanzi-{codepoint}`, `kangxi{n}`, `prim-{slug}` |
| `character` | the glyph; empty for a few primitives with no usable codepoint |
| `codepoint` | `U+XXXX` |
| `script` | `ja-kanji`, `zh-Hans`, `zh-Hant`, `zh-Hani` |
| `stroke_count`, `jlpt` | from kanjidic2 where known |
| `rtk_frame` | frame number in *Remembering the Kanji* — see the note under *Licence* |
| `onyomi`, `kunyomi` | kanjidic2, comma-separated, its own ordering |
| `pinyin` | Unihan `kMandarin`, toned |
| `variant_of` | links a Simplified form to its Traditional counterpart |
| `is_primitive` | a component taught in its own right, with no kanji frame |
| `decomposition_count` | how many breakdowns this character has (see below) |

### `components.csv` — one row per component occurrence

A character may have more than one breakdown: the primary one, plus any
labelled `alternative` (usually a structural reading from cjkvi-ids alongside
a pedagogical one, or an older reading of the same character). `decomposition`
numbers them; `position` is the order within one breakdown.

`component_character` is the component's glyph, and `component_id` the row it
resolves to — so the structure is keyed by **shape**, not by anyone's English
name for it, and is usable without the name files at all.

### `names.csv` — one row per searchable name, tagged by origin

| `source` | Meaning |
|---|---|
| `identifier` | the glyph itself, the row id, the frame number as a string |
| `project-or-open` | this project's own naming, or derived from open data |
| `ru-machine` | Russian, machine-translated by this project |

Two further classes exist in the database and are **withheld from this
export** — see below.

## Licence, attribution, and what is withheld

This export is produced with `--open-only`, which omits the two name sets that
cannot be redistributed:

- **Heisig's frame keywords and primitive names.** *Remembering the Kanji* is
  an in-print commercial book. The names are identified mechanically and
  dropped. If you own the book, its vocabulary is what the search UI on the
  live site uses; it is not in this file.
- **WaniKani radical names** (`tsunami`, `triceratops`, …). Tofugu's own
  content, used on the live site with attribution, not ours to republish.

**The structural data itself** — which shape sits inside which character — is
factual and is the core of this dataset. It derives from:

| Source | Contributes | Terms |
|---|---|---|
| [kanjidic2](https://www.edrdg.org/wiki/index.php/KANJIDIC_Project) (EDRDG) | readings, stroke counts, JLPT levels, the kanji inventory | CC BY-SA, attribution required |
| [KRADFILE](https://www.edrdg.org/krad/kradinf.html) (EDRDG) | the first-pass decompositions this started from | CC BY-SA, attribution required |
| [Unihan](https://unicode.org/charts/unihan.html) (Unicode Consortium) | the hanzi rows, pinyin | Unicode licence, attribution required |
| [cjkvi-ids](https://github.com/cjkvi/cjkvi-ids) | structural IDS decompositions | attribution required |
| Unicode `CJKRadicals.txt` | the `kangxi*` ids and official radical numbering | Unicode licence |
| This project | the `prim-*` rows and their names, every audit correction, the Russian names | — |

Because kanjidic2 and KRADFILE are **CC BY-SA**, share-alike propagates:
distribute this dataset, or anything derived from it, under
**CC BY-SA 4.0**, and keep the attributions above.

**One judgement call worth knowing about.** `characters.csv` keeps
`rtk_frame`, Heisig's frame number. A frame number is an index into a book —
a citation rather than content, and the column is what makes the dataset
useful to anyone working through RTK. It is nonetheless the one remaining
Heisig-derived field. Drop the column if you would rather have a file with no
connection to the book at all; nothing else depends on it.

## Known limitations — read before relying on this

- **The 5,626 Chinese rows have never been audited by anything.** They come
  straight from Unihan plus cjkvi-ids, and the audit described above is
  Japanese-only by construction — it checks against a Japanese book, which is
  not ground truth for Chinese. Expect the cjkvi failure modes listed earlier
  to be present and uncorrected in this half of the data. Treat the Chinese
  decompositions as raw structural data, not as verified.
- **14 Japanese rows are flagged `needs-render`** — known-uncertain, not yet
  resolved. They are not marked in the CSVs; see the review log.
- **The Japanese decomposition *choices* were informed by Heisig's components
  column** as one of three cross-checked sources. Which shape is inside which
  character is a fact, but the granularity — how far to break a shape down —
  partly follows his pedagogical choices rather than a purely structural rule.
- **Public rows only.** Registered users can add private decompositions and
  names on the live site; none of that is here.
- A character can legitimately have several breakdowns. If you need exactly
  one per character, take `decomposition = 1`.

## Reproducing this

From a checkout, with no server access:

```bash
cd backend
python3 export_dataset.py --from-api --out ../dataset --open-only
```

On the server, straight from SQLite (faster, same output):

```bash
./venv/bin/python3 export_dataset.py --from-db kanji.db --out ../dataset --open-only
```

Dropping `--open-only` includes the withheld name sets. Do that only for a
local copy.

## Citation

```
KumiJi character decomposition dataset.
https://github.com/vk2705/kanji — dataset/
Structural data CC BY-SA 4.0; incorporates kanjidic2 and KRADFILE (EDRDG,
CC BY-SA), Unihan and CJKRadicals.txt (Unicode Consortium), and cjkvi-ids.
```
