from __future__ import annotations

import asyncio
import csv
import io
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import steps
from ..steps._base import ProgressCb  # noqa: F401  (type re-export)
from .schemas import (
    PaperRecord,
    PrismaCounts,
    RunResults,
    RunStatus,
    SearchRequest,
    SearchStartResponse,
    StepInfo,
)

router = APIRouter(prefix="/api")

RUNS_DIR = Path(__file__).resolve().parent.parent / "storage" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)


class _RunState:
    def __init__(self, run_id: str, step_id: int) -> None:
        self.run_id = run_id
        self.step_id = step_id
        self.state: Literal["running", "done", "error"] = "running"
        self.counts: PrismaCounts = PrismaCounts()
        self.papers: list[PaperRecord] = []
        self.candidates: list[PaperRecord] = []
        self.message: str | None = None
        self.step_name: str = ""


_RUNS: dict[str, _RunState] = {}
_LOCK = asyncio.Lock()


def _persist(run: _RunState) -> None:
    payload = {
        "run_id": run.run_id,
        "step_id": run.step_id,
        "step_name": run.step_name,
        "state": run.state,
        "counts": run.counts.model_dump(),
        "papers": [p.model_dump() for p in run.papers],
        "candidates": [p.model_dump() for p in run.candidates],
        "message": run.message,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    (RUNS_DIR / f"{run.run_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def _execute_run(run_id: str, step_id: int) -> None:
    run = _RUNS[run_id]
    try:
        step_mod = steps.get(step_id)
        run.step_name = step_mod.STEP_META["name"]

        async def progress(counts: dict) -> None:
            async with _LOCK:
                run.counts = PrismaCounts(**counts)
                _persist(run)

        result = await step_mod.run_search(progress_cb=progress)
        async with _LOCK:
            run.papers = [PaperRecord(**p) for p in result["included"]]
            run.candidates = [PaperRecord(**p) for p in result["candidates"]]
            run.state = "done"
            _persist(run)
    except Exception as e:  # noqa: BLE001
        async with _LOCK:
            run.state = "error"
            run.message = f"{type(e).__name__}: {e}"
            _persist(run)


@router.get("/steps", response_model=list[StepInfo])
async def list_steps() -> list[StepInfo]:
    return [StepInfo(**m) for m in steps.all_meta()]


@router.post("/search", response_model=SearchStartResponse)
async def start_search(body: SearchRequest) -> SearchStartResponse:
    try:
        steps.get(body.step_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid step_id: {body.step_id}")
    run_id = uuid.uuid4().hex[:12]
    state = _RunState(run_id=run_id, step_id=body.step_id)
    _RUNS[run_id] = state
    _persist(state)
    asyncio.create_task(_execute_run(run_id, body.step_id))
    return SearchStartResponse(run_id=run_id)


def _load_run(run_id: str) -> _RunState:
    if run_id in _RUNS:
        return _RUNS[run_id]
    # Try disk (e.g., after restart).
    fp = RUNS_DIR / f"{run_id}.json"
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Unknown run_id")
    data = json.loads(fp.read_text(encoding="utf-8"))
    state = _RunState(run_id=run_id, step_id=data["step_id"])
    state.state = data.get("state", "done")
    state.counts = PrismaCounts(**(data.get("counts") or {}))
    state.papers = [PaperRecord(**p) for p in (data.get("papers") or [])]
    state.candidates = [PaperRecord(**p) for p in (data.get("candidates") or [])]
    state.message = data.get("message")
    state.step_name = data.get("step_name", "")
    _RUNS[run_id] = state
    return state


@router.get("/runs/{run_id}/status", response_model=RunStatus)
async def run_status(run_id: str) -> RunStatus:
    run = _load_run(run_id)
    return RunStatus(
        run_id=run.run_id,
        step_id=run.step_id,
        state=run.state,
        counts=run.counts,
        message=run.message,
    )


@router.get("/runs/{run_id}/results", response_model=RunResults)
async def run_results(run_id: str) -> RunResults:
    run = _load_run(run_id)
    return RunResults(
        run_id=run.run_id,
        step_id=run.step_id,
        step_name=run.step_name,
        counts=run.counts,
        papers=run.papers,
        candidates=run.candidates,
    )


def _csv_bytes(papers: list[PaperRecord]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "score",
            "title",
            "year",
            "journal",
            "authors",
            "doi",
            "pmid",
            "source_dbs",
            "matched_kinetic_terms",
            "matched_signal_phrases",
            "abstract",
        ]
    )
    for p in papers:
        writer.writerow(
            [
                p.score,
                p.title,
                p.year if p.year is not None else "",
                p.journal or "",
                "; ".join(p.authors),
                p.doi or "",
                p.pmid or "",
                "; ".join(p.source_dbs),
                "; ".join(p.matched_kinetic_terms),
                "; ".join(p.matched_signal_phrases),
                (p.abstract or "").replace("\n", " "),
            ]
        )
    return buf.getvalue().encode("utf-8")


def _md_bytes(run: _RunState, papers: list[PaperRecord]) -> bytes:
    lines: list[str] = []
    lines.append(f"# LNP literature run — {run.step_name}")
    lines.append("")
    lines.append(f"Run ID: `{run.run_id}`  ·  Step: {run.step_id} — {run.step_name}")
    lines.append("")
    c = run.counts
    lines.append("## PRISMA counts")
    lines.append("")
    lines.append(
        f"- PubMed: {c.pubmed}  ·  Europe PMC: {c.europepmc}  ·  "
        f"Semantic Scholar: {c.semantic_scholar}  ·  CrossRef: {c.crossref}"
    )
    lines.append(f"- After dedup: **{c.after_dedup}**")
    lines.append(f"- After kinetic filter: **{c.after_kinetic}**")
    lines.append(f"- Final: **{c.final}**")
    lines.append("")
    lines.append("## Papers")
    lines.append("")
    for i, p in enumerate(papers, start=1):
        link = f"https://doi.org/{p.doi}" if p.doi else ""
        title_md = f"[{p.title}]({link})" if link else p.title
        lines.append(f"### {i}. {title_md}")
        meta = []
        if p.year:
            meta.append(str(p.year))
        if p.journal:
            meta.append(p.journal)
        if p.authors:
            meta.append(", ".join(p.authors[:6]) + (" et al." if len(p.authors) > 6 else ""))
        if meta:
            lines.append(" · ".join(meta))
        lines.append("")
        lines.append(f"**Score:** {p.score}  ·  **Sources:** {', '.join(p.source_dbs)}")
        if p.matched_kinetic_terms:
            lines.append(f"**Kinetic:** {', '.join(p.matched_kinetic_terms)}")
        if p.matched_signal_phrases:
            lines.append(f"**Signal:** {', '.join(p.matched_signal_phrases)}")
        if p.abstract:
            lines.append("")
            lines.append(p.abstract)
        lines.append("")
    return "\n".join(lines).encode("utf-8")


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    format: Literal["csv", "json", "md"] = Query("csv"),
    which: Literal["included", "candidates"] = Query("included"),
):
    run = _load_run(run_id)
    papers = run.candidates if which == "candidates" else run.papers
    suffix = "_candidates" if which == "candidates" else ""
    if format == "csv":
        return StreamingResponse(
            io.BytesIO(_csv_bytes(papers)),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="lnp_{run_id}{suffix}.csv"'
            },
        )
    if format == "json":
        payload = RunResults(
            run_id=run.run_id,
            step_id=run.step_id,
            step_name=run.step_name,
            counts=run.counts,
            papers=run.papers,
            candidates=run.candidates,
        ).model_dump()
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(body),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="lnp_{run_id}.json"'},
        )
    if format == "md":
        return StreamingResponse(
            io.BytesIO(_md_bytes(run, papers)),
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="lnp_{run_id}{suffix}.md"'
            },
        )
    raise HTTPException(status_code=400, detail="format must be csv|json|md")
