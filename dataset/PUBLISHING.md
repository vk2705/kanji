# Putting the dataset somewhere people will find it

The CSVs in this directory are finished: complete, documented, and split by
provenance. What is not done is **publishing** them — committing a file to a
repository called `kanji` is not the same as putting a dataset where people
who want decomposition data go looking, and it earns no citable identifier.

Both remaining steps need an account, so neither can be done from a coding
session. Each is a few minutes of clicking, once.

Do Zenodo first: it costs the least and produces the DOI the other places can
then point at.

---

## 1. Zenodo — a DOI, via a GitHub release

Zenodo archives a GitHub repository every time you publish a release, and
mints a DOI for it. **Order matters: it only archives releases created after
you switch the repository on.** The repository has no releases yet, so the
first one will be captured cleanly.

- [ ] Sign in at [zenodo.org](https://zenodo.org) — "Log in with GitHub" is
      the quickest, and it is what links the two accounts.
- [ ] Go to [zenodo.org/account/settings/github](https://zenodo.org/account/settings/github)
      and flip the toggle **on** for `vk2705/kanji`. (If the repository is not
      listed, use "Sync now" — Zenodo caches the list.)
- [ ] On GitHub: Releases → "Create a new release" → new tag `dataset-v1.0`,
      target `master`, title *KumiJi character decomposition dataset v1.0*.
      For the body, the summary at the top of `dataset/README.md` is the right
      length; the key facts are 8,878 characters, 18,000 component rows,
      43,622 names, 159 Japanese decompositions corrected by hand review, and
      the Chinese half not audited.
- [ ] Publish. Within a few minutes Zenodo shows the record and the DOI.
- [ ] Put the DOI badge at the top of `dataset/README.md` and add the DOI to
      `CITATION.cff` as a `doi:` field, so the citation GitHub renders carries
      it.

Zenodo mints two DOIs: one for this specific version and a "concept" DOI that
always resolves to the newest. Cite the concept DOI in the README.

## 2. Hugging Face — where people actually search for datasets

Zenodo gives permanence; it gives almost no discovery. Hugging Face Datasets
is where someone looking for character data will search.

- [ ] Create an account at [huggingface.co](https://huggingface.co).
- [ ] New dataset → name it `kumiji-character-decomposition`, licence
      CC BY-SA 4.0, public.
- [ ] Upload `characters.csv`, `components.csv` and `names.csv` through the
      web uploader (three files, no tooling needed).
- [ ] Create a `README.md` in the dataset repository with the card below. The
      YAML block at the top is what makes the dataset browsable by language
      and licence and gives the dataset viewer its three tabs — without it the
      files are just attachments.

<details>
<summary>Dataset card to paste</summary>

```markdown
---
license: cc-by-sa-4.0
language:
  - ja
  - zh
tags:
  - kanji
  - hanzi
  - chinese-characters
  - decomposition
  - linguistics
pretty_name: KumiJi Character Decomposition Dataset
size_categories:
  - 10K<n<100K
configs:
  - config_name: characters
    data_files: characters.csv
  - config_name: components
    data_files: components.csv
  - config_name: names
    data_files: names.csv
---

# KumiJi character decomposition dataset

Which shapes each Japanese kanji and Chinese hanzi is built from: 8,878
characters, 18,000 component occurrences, 43,622 names.

The 3,000 Japanese characters have been checked by hand, one at a time: the
rendered glyph compared against Heisig's components column and against
cjkvi-ids, with a shape-family check on every correction. 2,827 confirmed,
159 corrected, 14 still open.

That was worth doing because the machine-readable sources fail silently:
an IDS with a `⿻` or `⿴` operator overlays shapes that *share strokes*, so
`蝿 = ⿰虫⿻日电` does not mean the top box is 日 (rendered, it is 田); and
components with no codepoint are written as circled numbers that are
per-entry placeholders, not identifiers — `③` is the bottom of 不, the left
of 北, the left of 印 and a 止 variant in 此.

**The 5,626 Chinese rows have never been audited.** They come straight from
Unihan and cjkvi-ids; the hand review checks against a Japanese book, which
is not ground truth for Chinese. Treat them as raw structural data.

Names are tagged by origin. Heisig's frame keywords and primitive names, and
the WaniKani radical names, are **not** included — they are copyrighted and
not redistributable. The structure is keyed by glyph, so it does not need
them.

Derived from kanjidic2 and KRADFILE (EDRDG, CC BY-SA), Unihan and
CJKRadicals.txt (Unicode Consortium), and cjkvi-ids. Share-alike propagates:
CC BY-SA 4.0.

Full column documentation, provenance table and limitations:
https://github.com/vk2705/kanji/blob/master/dataset/README.md
```

</details>

- [ ] Add the Hugging Face link to `dataset/README.md`.

## Not worth doing

**Kaggle** — a third copy to keep in sync, and its audience overlaps Hugging
Face's without adding reach for this kind of data.

**A separate repository for the dataset.** It would need the exporter, the
source files and the audit log to stay meaningful, and splitting those from
the tool that produces them creates two things to maintain. The CSVs are
regenerated by `backend/export_dataset.py` from the live database; they
belong next to it.
