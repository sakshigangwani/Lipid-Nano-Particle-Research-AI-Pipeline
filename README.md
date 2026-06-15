# Lipid Nanoparticle (LNP) Research AI Pipeline

A full-stack literature discovery and curation tool for lipid nanoparticle (LNP) research.
For any one of **7 stages of the LNP delivery journey**, it searches six scientific
databases in parallel, deduplicates the results, filters them for quantitative and
time-resolved (kinetic) evidence, scores each paper with an LLM, and presents a sortable,
exportable results table — with a transparent **PRISMA-style funnel** showing how many
papers survived each filtering stage.

```
Search 6 DBs ─► Deduplicate ─► LNP-focus ─► Quantitative ─► Kinetic ─► Caption
                                  filter        filter        filter    fallback
                                                                          │
                                          Final score & sort ◄─ LLM score ┘
```

---

## Features

- **Six-database search** — PubMed, Europe PMC, Semantic Scholar, CrossRef, OpenAlex, and bioRxiv/medRxiv, queried concurrently with retry/backoff.
- **7 LNP-journey stages** — each with its own boolean query and quantitative/kinetic keyword sets (see below).
- **PRISMA-style funnel** — live counts at every stage make the selection process auditable.
- **Quantitative & kinetic filtering** — regex matching for units, percentages, fold changes, IC50/EC50, half-lives, rate constants, time-courses, etc.
- **Figure/caption fallback** — papers with weak abstracts get a second chance: figure/table captions and supplementary text are fetched from Europe PMC and re-matched.
- **LLM scoring** — each candidate is scored `0–1` with an `include / borderline / exclude` verdict and a rationale.
- **Caching** — every API response is cached on disk, so re-runs are fast and free.
- **Persistence** — run results are written to disk, so they survive a backend restart.
- **Export** — download included papers or pre-LLM candidates as CSV, JSON, or Markdown.

---

## The 7 LNP-journey stages

| ID | Stage | Strict kinetic? | What it looks for |
| -- | ----- | --------------- | ----------------- |
| 1 | Protein corona | no | Protein layer formation on the LNP surface (proteomics, mass spec) |
| 2 | Biodistribution (whole body) | no | Organ/tissue accumulation in vivo (imaging, pharmacokinetics) |
| 3 | Endocytosis | **yes** | Internalization pathways (clathrin, caveolae, macropinocytosis) |
| 4 | Cellular uptake | **yes** | Rate of cell entry (flow cytometry, confocal time-courses) |
| 5 | Endosomal escape | **yes** | Cargo escape into the cytoplasm (Gal8 puncta, kinetic assays) |
| 6 | Cargo release | no | mRNA/payload release from the LNP (RiboGreen, FRET) |
| 7 | Translational | no | Protein expression from delivered mRNA (luciferase, GFP) |

For **strict-kinetic** stages (3, 4, 5), papers without time-resolved evidence are dropped.
For the others, kinetic evidence is a scoring preference rather than a hard gate.

---

## Tech stack

| Layer | Technology |
| ----- | ---------- |
| Backend | Python, FastAPI, Uvicorn, httpx, Pydantic v2, tenacity |
| LLM | OpenAI (`gpt-4o-mini` by default, configurable) |
| Frontend | React 18 + TypeScript + Vite 5 |

---

## Project layout

```
Lipid-Nano-Particle-Research-AI-Pipeline/
└── lnp_pipeline/
    ├── .env                       # OPENAI_API_KEY (and optional OPENAI_MODEL)
    ├── backend/
    │   ├── main.py                # FastAPI app entry point
    │   ├── requirements.txt
    │   ├── api/                   # routes.py, schemas.py  (5 endpoints)
    │   ├── steps/                 # step1..step7 + _base.py (the funnel)
    │   ├── clients/               # one module per database
    │   ├── utils/                 # filters, llm, scoring, dedup, cache, fulltext
    │   └── storage/
    │       ├── cache/             # cached API responses (per database)
    │       └── runs/              # persisted run results ({run_id}.json)
    └── frontend/
        └── src/
            ├── App.tsx            # main UI (select stage → search → results)
            ├── api/client.ts      # fetch wrappers
            ├── types.ts
            └── components/        # StepPicker, PrismaCounts, ResultsTable, PaperRow, ...
```

---

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 18+
- An OpenAI API key

### 1. Configure secrets

Create `lnp_pipeline/.env`:

```ini
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini   # optional; this is the default
```

### 2. Run the backend

```bash
cd lnp_pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

> The backend uses package-relative imports, so it must be launched as `backend.main:app`
> from the `lnp_pipeline/` directory — not from inside `backend/`.

The API is served at `http://localhost:8000` (interactive docs at `/docs`).

### 3. Run the frontend

```bash
cd lnp_pipeline/frontend
npm install
npm run dev          # http://localhost:5173 — proxies /api → :8000
```

Open `http://localhost:5173`, pick a stage, and start a search.

To build for production: `npm run build` (output in `dist/`).

---

## How it works

The pipeline (`backend/steps/_base.py`) processes each run through these stages:

1. **Parallel fetch** — up to 200 results from each of the 6 databases.
2. **Deduplicate** — by normalized DOI (fallback: normalized title).
3. **LNP-focus filter** — drop papers not actually about lipid nanoparticles.
4. **Quantitative filter** — keep papers with numeric measurements (units, %, fold changes, IC50/EC50, p-values, …).
5. **Kinetic filter** — keep papers with time-resolved data (half-life, rate constant, time-course, AUC, …). Hard gate for stages 3–5.
6. **Caption fallback** — for papers failing 4 or 5, fetch figure/table captions and supplementary text from Europe PMC and retry the match (flagged as `caption_rescued` / `supplementary_rescued`).
7. **LLM scoring** — score each survivor `0–1` with a verdict and rationale.
8. **Final score & sort** — combine quantitative, kinetic, signal-phrase, and multi-database-corroboration weights into a deterministic score; sort by LLM score, then deterministic score.

---

## API reference

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/api/steps` | List the 7 stages (`id`, `name`, `description`, `strict_kinetic`). |
| POST | `/api/search` | Body `{ "step_id": int }`. Starts a background run, returns `{ run_id }`. |
| GET  | `/api/runs/{run_id}/status` | Live PRISMA counts and run state (`running` / `done` / `error`). |
| GET  | `/api/runs/{run_id}/results` | Final paper list with scores and matched terms. |
| GET  | `/api/runs/{run_id}/export?format=csv\|json\|md` | Stream a downloadable export. |

---

## Notes

- **Caching:** API responses are cached under `backend/storage/cache/{database}/`. The first run of a stage hits the live APIs; subsequent runs are served from cache. Delete the cache directory to force fresh queries.
- **Cost:** Only the LLM scoring step calls a paid API. The number of LLM calls equals the number of papers that survive filtering for a given run.
