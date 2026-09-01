# RTK Kanji Search

Search Japanese kanji and Chinese hanzi by their named visual components. Built for learners using *Remembering the Kanji* by James W. Heisig and extended as a community-editable reference.

## What it does

The Heisig method gives every kanji a set of named visual building blocks called *primitives* (e.g. sun, moon, mouth, water). This app lets you:

- **Search by primitives** — type `water` + `old` to find all kanji built from those elements (returns 湖 lake, 活 lively, 滴 drip, …)
- **Search by keyword** — type `marsh` to find 沼 directly
- **Search by character** — paste a glyph like 明 to look it up
- **Inspect a kanji** — see aliases, mnemonic stories, alternate decompositions, and recursively expandable component chips
- **Choose a study language** — Japanese, Chinese Simplified, Chinese Traditional, or all scripts
- **Contribute** — registered users can add private or public entries, aliases, decompositions, images, and original mnemonic stories

## Quick start

**Backend** (Python 3.11 recommended, port 8000):
```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -r requirements-dev.txt
python3 -m uvicorn main:app --reload --port 8000
```
On first run `kanji.db` is seeded automatically. After that it is the source of truth and also contains user accounts and contributions. Do not delete it to pick up source-data changes; use `backend/sync_system_data.py`.

**Frontend** (Node 20.19+ or 22.12+, port 5173):
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
| Frontend | React 19 + Vite |
| CLI | plain Python 3 (stdlib only) |
| Data | SQLite source of truth; CSV + text files provide the initial system seed |

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
| `POST` | `/search/parts` | `{"parts": ["water", "old"], "depth": 1}` — entries containing all named parts |
| `GET` | `/search/text?q=marsh` | Whole-word keyword/alias match |
| `GET` | `/search/char?c=沼` | Exact character lookup |
| `GET` | `/kanji/{id}` | Full detail for one entry |
| `POST` | `/auth/register` | Create an account and session |
| `POST` | `/kanji`, `/aliases`, `/stories` | Authenticated community contributions |
| `POST` | `/kanji/{id}/decompositions` | Add an alternate decomposition |
| `GET` | `/me/contributions` | List the current user's contributions |

## Data sources and import pipeline

An empty database is seeded once from three sources in priority order (higher wins):

1. **`heisig-kanjis.csv`** — 2200+ kanji with recursively expanded component terms from the 6th edition. This is the baseline.
2. **`data_from_pdf.txt`** — ~650 primitive decompositions extracted from the Heisig 4th edition PDF using keyword matching. English primitive names, matched to 6th-edition frames.
3. **`data.txt`** — user-curated entries: primitive aliases, missing characters, and hand-verified decomposition overrides. These take priority over everything else.

On a populated database, preview and apply system-data changes without deleting user data:
```bash
cd backend
./venv/bin/python3 sync_system_data.py --dry-run
./venv/bin/python3 sync_system_data.py
```

There is deliberately no reimport HTTP endpoint. See `DEPLOY_README.md` before operating on production data.

### `data.txt` format

```
id:character:alias1,alias2,...:part1,part2,...;alt_decomp
```

- `id` — `rtk{n}` for kanji, `kangxi{n}` for official Kangxi radicals, or `prim-{slug}` for other primitives
- `character` — UTF-8 glyph, or `?` if unknown
- `aliases` — comma-separated names; first becomes the keyword
- `parts` — comma-separated primitive names or kanji characters; multiple decompositions separated by `;`
- Lines starting with `#` and blank lines are ignored

Example:
```
rtk20:明:bright:sun,moon
kangxi72:日:day,sun:
```

## Database schema

```sql
kanji(id TEXT PK, character TEXT, keyword TEXT, owner_id INT, visibility TEXT, script TEXT, image_url TEXT)
aliases(kanji_id → kanji.id, alias TEXT, owner_id INT, visibility TEXT)
decompositions(id INTEGER PK, kanji_id → kanji.id, owner_id INT, visibility TEXT, label TEXT)
parts(kanji_id → kanji.id, decomposition_id → decompositions.id, part_term TEXT, position INT)
stories(kanji_id → kanji.id, owner_id INT, visibility TEXT, story TEXT)
users(...)
sessions(...)
```

Every read is visibility-aware: anonymous users see public rows; authenticated users additionally see their own private rows. System data is owned by a reserved immutable account.

## Search logic

**By parts**: expand each term through visible aliases, walk the reverse decomposition graph up to the selected depth, and intersect the resulting entry sets. Source and script filters apply throughout the search. A single-term miss falls back to text search.

**By text**: whole-word match against ids, keywords, and visible aliases.

**By character**: exact match on `kanji.character`.

## Tests and operations

```bash
cd backend && ./venv/bin/pytest -v
cd frontend && npm run lint && npm run build
```

CI runs the isolated temporary-database API suite plus frontend lint/build. Local database and upload backups are created together by `backend/backup_db.py`; `backend/offsite_backup.py` copies new artifacts to an operator-configured encrypted `rclone` remote, and `backend/restore_backup.py` performs a staged, integrity-checked restore. See `DEPLOY_README.md` for the production procedure.
