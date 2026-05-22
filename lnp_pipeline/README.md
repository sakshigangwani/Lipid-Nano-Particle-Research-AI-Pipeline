# LNP Literature Pipeline

A full-stack literature search application for Lipid Nanoparticle (LNP) research. For one of 7 LNP-journey steps, it queries **PubMed, Europe PMC, Semantic Scholar, and CrossRef**, deduplicates, filters for quantitative + kinetic content, scores each paper, and renders a sortable results table with matched-term chips and export to CSV / JSON / Markdown.

## Layout

```
lnp_pipeline/
├── backend/         FastAPI app, 7 step modules, 4 API clients, filters/scoring
└── frontend/        Vite + React + TypeScript SPA
```

## Running the app

### Backend

```bash
cd lnp_pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

> The backend uses package-relative imports, so it must be launched as `backend.main:app` from the `lnp_pipeline/` directory (not from inside `backend/`).

The API is then served at `http://localhost:8000` (docs: `/docs`).

### Frontend

```bash
cd lnp_pipeline/frontend
npm install
npm run dev   # http://localhost:5173 — proxies /api → :8000
```

## API

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET    | `/api/steps` | Returns the 7 steps (id, name, description, strict_kinetic). |
| POST   | `/api/search` | Body: `{ "step_id": int }`. Starts a background run, returns `{ run_id }`. |
| GET    | `/api/runs/{run_id}/status` | Live PRISMA counts and run state (`running`/`done`/`error`). |
| GET    | `/api/runs/{run_id}/results` | Final paper list with scores and matched terms. |
| GET    | `/api/runs/{run_id}/export?format=csv\|json\|md` | Streams a downloadable file. |

## The 7 LNP journey steps

| ID | Name | Strict kinetic? |
| -- | ---- | --------------- |
| 1  | Protein corona | no |
| 2  | Biodistribution (whole body) | no |
| 3  | Endocytosis | **yes** |
| 4  | Cellular uptake | **yes** |
| 5  | Endosomal escape | **yes** |
| 6  | Cargo release | no |
| 7  | Translational | no |

Strict-kinetic steps drop any paper that fails the kinetic filter (rates, half-lives, time courses). Non-strict steps keep them, but score them lower.

## Pipeline (per run)

1. Issue the step's Boolean query against all 4 databases concurrently (httpx + tenacity retry/backoff).
2. Cache each raw API response on disk at `backend/storage/cache/{db}/{hash}.json`. Re-runs are served from cache.
3. Dedup by normalized DOI (primary) or normalized title (fallback: lowercase, accents stripped, punctuation stripped, whitespace collapsed). Source DBs are unioned across duplicates.
4. Apply an **LNP-focus** sanity check, then the **quantitative** filter (regex for `%`, units, ±, IC50, `particles/cell`, etc., plus step-specific keywords).
5. Apply the **kinetic** filter (`half-life`, `t1/2`, `time course`, time units, etc., plus step-specific keywords). For strict-kinetic steps, papers without any kinetic match are dropped.
6. Score 0.0–1.0 (saturating quant + kinetic + signal-phrase + multi-DB-corroboration buckets) and sort.
7. Persist the full result to `backend/storage/runs/{run_id}.json` so runs survive a backend restart.

## How to add a new step

Each step is a self-contained module exposing the same contract.

1. Create `backend/steps/step8_yourstep.py`:

   ```python
   from ._base import ProgressCb, run_step_search

   STEP_META = {
       "id": 8,
       "name": "Your step",
       "description": "What this step covers.",
       "strict_kinetic": False,  # set True to drop non-kinetic papers
   }

   KEYWORDS = ["term-a", "term-b"]

   BOOLEAN_QUERY = (
       '("lipid nanoparticle" OR "LNP") AND ("term-a" OR "term-b") AND (...)'
   )

   QUANTITATIVE_FILTERS = ["% something", "ng/mL", "fold change"]
   KINETIC_FILTERS = ["time course", "rate", "half-life"]
   SIGNAL_PHRASES = ["high-value phrase 1", "high-value phrase 2"]

   async def run_search(progress_cb: ProgressCb | None = None) -> list[dict]:
       return await run_step_search(
           boolean_query=BOOLEAN_QUERY,
           quant_keywords=QUANTITATIVE_FILTERS,
           kinetic_keywords=KINETIC_FILTERS,
           signal_phrases=SIGNAL_PHRASES,
           strict_kinetic=STEP_META["strict_kinetic"],
           progress_cb=progress_cb,
       )
   ```

2. Register it in `backend/steps/__init__.py`:

   ```python
   from . import step8_yourstep
   STEPS = {..., 8: step8_yourstep}
   ```

3. Restart the backend. The frontend's `/api/steps` call automatically picks it up — no UI change required.

### Filter authoring tips

- `QUANTITATIVE_FILTERS` and `KINETIC_FILTERS` are matched in addition to a shared regex set defined in `backend/utils/filters.py`. You only need to add **step-specific** terms here (e.g., `"% positive cells"` for cellular uptake, `"%ID/g"` for biodistribution).
- `SIGNAL_PHRASES` are high-value strings that boost a paper's score but don't affect inclusion.
- Keep the boolean query specific enough that the four databases return mostly on-topic results; the downstream filters do the strict gating.

## Caching & resets

- Raw API responses: `backend/storage/cache/{db}/*.json` — delete the directory to force a fresh fetch.
- Run records: `backend/storage/runs/{run_id}.json` — safe to delete at any time.
