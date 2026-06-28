# RTK Kanji Search

Search kanji by their RTK primitive elements — or by keyword. Built for learners using *Remembering the Kanji* by James W. Heisig.

## What it does

The Heisig method gives every kanji a set of named visual building blocks called *primitives* (e.g. sun, moon, mouth, water). This app lets you:

- **Search by primitives** — type `water` + `old` to find all kanji built from those elements (returns 湖 lake, 活 lively, 滴 drip, …)
- **Search by keyword** — type `marsh` to find 沼 directly
- **Search by character** — paste a glyph like 明 to look it up
- **Inspect a kanji** — click any result to see its frame number, aliases, and all component primitives as clickable chips

## Quick start

**Backend** (Python 3.10+, port 8000):
```bash
cd backend
pip install fastapi uvicorn
python3 -m uvicorn main:app --reload --port 8000
```
On first run `kanji.db` is created automatically from `heisig-kanjis.csv` and `data.txt`.

**Frontend** (Node 18+, port 5173):
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

**CLI** (no server needed, reads the DB directly):
```bash
python3 rtk.py text marsh              # find by keyword substring
python3 rtk.py parts water old         # find kanji containing those primitives
python3 rtk.py char 沼                 # look up by character glyph
python3 rtk.py detail rtk145          # full breakdown: aliases + parts
```

## Stack

| Layer | Tech |
|---|---|
| Backend API | Python 3 + FastAPI + SQLite |
| Frontend | React 18 + Vite |
| CLI | plain Python 3 (stdlib only) |
| Data | CSV + flat text → SQLite |

## Project layout

```
kanji-app/
  rtk.py                   # CLI — search without running the server
  backend/
    main.py                # FastAPI app, all routes
    database.py            # SQLite setup, import logic, all query functions
    heisig-kanjis.csv      # 6th-edition ground truth: frame / kanji / keyword / components
    data.txt               # Primitives, aliases, and decomposition overrides
    data_from_pdf.txt      # Primitives extracted from 4th-edition PDF
  frontend/
    src/
      App.jsx              # Root component, tab state, search dispatch
      App.css              # All styles (dark theme, CSS variables)
      api.js               # fetch wrappers for all backend endpoints
      components/
        KanjiCard.jsx      # Single result card
        ResultsGrid.jsx    # Grid of KanjiCards with loading/empty states
        KanjiDetail.jsx    # Detail panel: aliases + parts as clickable chips
```

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/search/parts` | `{"parts": ["water", "old"]}` — kanji containing all given primitives |
| `GET` | `/search/text?q=marsh` | Keyword/alias substring match |
| `GET` | `/search/char?c=沼` | Exact character lookup |
| `GET` | `/kanji/{id}` | Full detail for one entry |
| `POST` | `/admin/reimport` | Re-parse data files and rebuild the database |

## Data sources and import pipeline

The database is built from three sources in priority order (higher wins):

1. **`heisig-kanjis.csv`** — 2200+ kanji with recursively expanded component terms from the 6th edition. This is the baseline.
2. **`data_from_pdf.txt`** — ~650 primitive decompositions extracted from the Heisig 4th edition PDF using keyword matching. English primitive names, matched to 6th-edition frames.
3. **`data.txt`** — user-curated entries: primitive aliases, missing characters, and hand-verified decomposition overrides. These take priority over everything else.

To rebuild after editing any data file:
```bash
curl -X POST http://localhost:8000/admin/reimport
```

### `data.txt` format

```
id:character:alias1,alias2,...:part1,part2,...;alt_decomp
```

- `id` — `rtk{n}` for kanji (6th-edition frame), `rad{n}` for pure primitives
- `character` — UTF-8 glyph, or `?` if unknown
- `aliases` — comma-separated names; first becomes the keyword
- `parts` — comma-separated primitive names or kanji characters; multiple decompositions separated by `;`
- Lines starting with `#` and blank lines are ignored

Example:
```
rtk20:明:bright:sun,moon
rad4.13:日:day,sun,tongue wagging in mouth,rtk12
```

## Database schema

```sql
kanji(id TEXT PK, character TEXT, keyword TEXT, frame INT, stroke_count INT, jlpt TEXT)
aliases(kanji_id → kanji.id, alias TEXT)
parts(kanji_id → kanji.id, part_term TEXT, position INT)
```

Parts are stored as flat English terms (fully expanded). Searching for `water` will match any kanji whose parts list includes `water` at any depth.

## Search logic

**By parts**: for each input term, expand to all known aliases, find all kanji that list any of those terms as a part, then intersect the sets. If a single-term parts search returns nothing, the UI automatically falls back to a keyword search and shows a note.

**By text**: `LIKE %q%` match on `kanji.id` and `aliases.alias`.

**By character**: exact match on `kanji.character`.
