# Kanji RTK Search — Project Guide

## What this project is

A web app for learners using **Remembering the Kanji (RTK)** by James W. Heisig. The method assigns each kanji a set of named visual "primitives" (building blocks) and a mnemonic story. This app lets you search kanji by those primitive names — e.g. type "sun" + "moon" to find 明 (bright).

## Stack

| Layer | Tech |
|---|---|
| Backend API | Python 3 + FastAPI + SQLite |
| Frontend | React 18 + Vite |
| Data | Flat text file → SQLite (imported at startup) |

Future: Android app using the same REST API.

## Project structure

```
kanji-app/
  backend/
    main.py        # FastAPI app, all routes
    database.py    # SQLite setup, import logic, all query functions
    data.txt       # Raw kanji data (id:char:aliases:parts format)
    kanji.db       # SQLite database (generated, do not commit)
  frontend/
    src/
      App.jsx              # Root component, tab state, search dispatch
      App.css              # All styles (dark theme, CSS variables)
      api.js               # fetch wrappers for all backend endpoints
      components/
        KanjiCard.jsx      # Single result card (char + keyword + id)
        ResultsGrid.jsx    # Grid of KanjiCards with loading/empty state
        KanjiDetail.jsx    # Detail panel: aliases, parts as clickable chips
  cgi-bin/                 # Original Perl CGI app (legacy, reference only)
  html/                    # Original HTML frontend (legacy)
  RKVol1.pdf               # Remembering the Kanji Vol. 1 (Heisig, 6th ed.)
```

## Running locally

**Backend** (port 8000):
```bash
cd backend
python3 -m uvicorn main:app --reload --port 8000
```
On first run, `kanji.db` is created and data is imported from `data.txt` automatically.

**Frontend** (port 5173):
```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/search/parts` | Body: `{"parts": ["sun", "moon"]}` — find kanji containing all given primitives |
| `GET` | `/search/text?q=brig` | Find kanji whose id or any alias contains the substring |
| `GET` | `/search/char?c=明` | Look up a kanji by its character glyph |
| `GET` | `/kanji/{id}` | Full detail for one kanji (aliases + resolved parts) |
| `POST` | `/admin/reimport` | Re-parse `data.txt` and rebuild the database |

## Data format (`data.txt`)

One entry per line:
```
id:character:alias1,alias2,...:part1,part2,...;alt_decomp1,alt_decomp2
```

- `id` — internal key, e.g. `rtk20`, `rad3.2`. Prefix `rtk` = RTK frame number. Prefix `rad` = radical/primitive.
- `character` — the kanji glyph (UTF-8), or `?` if not yet filled in.
- `aliases` — comma-separated names (first one becomes the keyword).
- `parts` — comma-separated primitive names; multiple decompositions separated by `;`.
- Lines starting with `#` and blank lines are ignored.
- Field values are lowercased on import.

Example:
```
rtk20:明:bright:sun,moon
rad4.13:日:day,sun,tongue wagging in mouth,rtk12
```

## Data model (SQLite)

```sql
kanji(id TEXT PK, character TEXT, keyword TEXT)
aliases(kanji_id → kanji.id, alias TEXT)
parts(kanji_id → kanji.id, part_alias TEXT, position INT)
ambiguity(name TEXT, resolves_to TEXT)   -- e.g. "eye" → "eyeball primitive" or "eye kanji"
```

## Search logic

1. **By parts** — for each input primitive, expand ambiguities, resolve aliases to canonical ids, find all kanji that use each as a part (direct or recursive), then intersect the sets.
2. **By text** — LIKE match on `kanji.id` and `aliases.alias`.
3. **By character** — exact match on `kanji.character`.

Ambiguity table handles terms with multiple meanings (e.g. "water" = drops-of-water primitive OR water-kanji).

## Known limitations / next steps

- Most entries in `data.txt` have `?` as the character — the dataset is partial. The full RTK list has 2,200+ kanji. Filling this in is the main data task.
- No user accounts, flashcard mode, or study tracking yet.
- The mnemonic story text from the book is **not** stored (copyright). Frame numbers link to the book.
- Android app is planned; the FastAPI backend is designed as a REST API to serve it.

## Page title fix (quick win)
Change `<title>` in `frontend/index.html` from `Vite + React` to `RTK Kanji Search`.
