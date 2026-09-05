# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A full-stack literature discovery tool for lipid nanoparticle (LNP) research. For any one of
7 stages of the LNP delivery journey (protein corona, biodistribution, endocytosis, cellular
uptake, endosomal escape, cargo release, translational), it searches 6 scientific databases in
parallel, deduplicates, filters for quantitative + kinetic evidence, scores each survivor with
an LLM, and presents a sortable, exportable results table with a PRISMA-style funnel.

The actual project lives in `lnp_pipeline/` (this repo root is one level above it).

## Commands

All commands assume `cd lnp_pipeline` first.

```bash
# Backend — must be launched from lnp_pipeline/, not from inside backend/,
# because it uses package-relative imports (backend.main:app).
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000    # http://localhost:8000, docs at /docs

# Frontend
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api -> :8000
npm run build       # tsc -b && vite build, output in dist/
```

Secrets go in `lnp_pipeline/.env` (loaded by `backend/main.py` via `dotenv`):
```ini
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini   # optional, this is the default
```

There is no test suite in this repository currently.

## Architecture

### The per-run pipeline (`backend/steps/_base.py::run_step_search`)

This is the one function that matters most — every step module (`step1_*.py` .. `step7_*.py`)
is just a thin config wrapper that calls it with a boolean query and keyword lists. Read
`_base.py` before touching any step-specific behavior. The pipeline processes each run through
these stages in order, emitting a `PrismaCounts` snapshot via `progress_cb` after each one (this
is what the frontend polls to animate the funnel):

1. **Parallel fetch** across `backend/clients/`: PubMed, Europe PMC, Semantic Scholar, CrossRef,
   OpenAlex, bioRxiv (bioRxiv/medRxiv reuses the Europe PMC endpoint scoped to `SRC:PPR`). Each
   client paginates to exhaustion using that API's own native mechanism (cursor, offset, or
   retstart depending on the source) — there is no artificial per-database cap. A source that
   throws is swallowed and treated as empty (`return_exceptions=True`), so one API being down
   doesn't fail the whole run.
2. **Deduplicate** (`utils/dedup.py`) — merge by normalized DOI first, normalized title as
   fallback; richer fields and unioned `source_dbs` win on merge.
3. **LNP-focus filter** (`utils/filters.py::is_lnp_focused`) — drop papers whose title+abstract+
   journal text doesn't mention LNPs specifically. Papers with **no abstract at all** (common
   from CrossRef, which frequently omits it) skip this check rather than being auto-rejected —
   they're trusted through since they already matched the LNP-related boolean query at the
   source, but still have to pass the quant/kinetic gates below.
4. **Quantitative filter** (`utils/filters.py::find_quant_matches`) — regex + step-specific
   keywords for numeric evidence (%, units, fold-change, IC50/EC50, p-values, ± error bars, …).
5. **Kinetic filter** (`find_kinetic_matches`) — regex + keywords for time-resolved evidence
   (half-life, rate constant, time-course, AUC, …). For `strict_kinetic` steps (3 Endocytosis,
   4 Cellular uptake, 5 Endosomal escape) this is a hard gate; for the others it's scoring signal
   only.
6. **Caption/supplementary fallback** (`utils/fulltext.py`) — for papers still failing quant or
   kinetic after step 3-5, resolve a PMCID via Europe PMC, fetch full-text XML, and re-run the
   regex gates against figure/table captions and supplementary-material text. A successful rescue
   is attributed (`caption_rescued` / `supplementary_rescued`) so the UI can show *why* a paper
   survived, and the LLM in the next step sees the same rescued text.
7. **LLM scoring** (`utils/llm.py`) — each survivor goes to `gpt-4o-mini` (concurrency-capped at
   5) and gets back `{score 0-1, verdict: include|borderline|exclude, rationale}`. Missing
   `OPENAI_API_KEY` degrades to `verdict: "skipped"` for every paper rather than failing the run.
8. **Score + finalize** — a separate deterministic 0-1 `score` (`utils/scoring.py`) combines
   quant/kinetic/signal-phrase matches (each capped at 0.30) plus a multi-database corroboration
   bonus (capped at 0.10). Results are sorted by `(llm_score, score)` descending. `candidates`
   = everything that passed the regex gates and was sent to the LLM; `included` = the subset
   where `llm_verdict != "exclude"` (i.e. `include` *and* `borderline` both count as included —
   only a hard `exclude` verdict drops a paper from the final list).

### Debug rejection report

`_base.py::_log_rejection_summary` tallies why papers didn't make it to `included` (not
LNP-focused, failed quant, failed kinetic, LLM-excluded) and writes a formatted JSON snapshot to
`backend/storage/debug/{step_name}_filter_report.json`, overwritten each run. Use this when the
final paper count for a stage looks off — it pinpoints which gate is doing the rejecting instead
of requiring a re-read of the whole funnel.

### Persistence and caching

- Every raw API response is cached at `backend/storage/cache/{database}/{hash}.json`, keyed by
  the query payload — re-running a stage with an unchanged query is served from cache and costs
  nothing. Delete the relevant subdirectory to force a fresh fetch.
- Full run results (`PrismaCounts`, `papers`, `candidates`) are persisted to
  `backend/storage/runs/{run_id}.json` on every progress callback, so a run survives a backend
  restart and `_load_run` in `api/routes.py` can rehydrate it from disk.
- Search runs execute as a detached `asyncio.create_task` in `api/routes.py::start_search`; the
  frontend polls `/api/runs/{run_id}/status` until `state == "done"`.

### Adding a new step

Each `backend/steps/stepN_*.py` module exposes the same contract: `STEP_META` (id, name,
description, `strict_kinetic`), `BOOLEAN_QUERY`, `QUANTITATIVE_FILTERS`, `KINETIC_FILTERS`,
`SIGNAL_PHRASES`, and an `async def run_search(progress_cb)` that just forwards everything to
`run_step_search`. `backend/steps/__init__.py` is the registry new steps must be added to.

### Frontend

Single-page flow in `frontend/src/App.tsx`: pick a stage (`StepPicker`) → start a search
(`RunButton`) → poll status and render the live funnel (`PrismaCounts`) → render results
(`ResultsTable` / `PaperRow` / `MatchedTerms`) once done. All backend calls go through
`api/client.ts`. Dev server proxies `/api` to `:8000` (see `vite.config.ts`).
