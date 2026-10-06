from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import steps
from ..steps._base import ProgressCb  # noqa: F401  (type re-export)
from ..utils import export
from ..utils.filters import classify_study_type
from ..utils.open_access import resolve_open_access
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
logger = logging.getLogger("lnp_pipeline.api")

RUNS_DIR = Path(__file__).resolve().parent.parent / "storage" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR = Path(__file__).resolve().parent.parent / "storage" / "exports"

StudyFilter = Literal["all", "in_vitro", "in_vivo", "unclassified"]
AccessFilter = Literal["all", "open", "closed", "unknown"]
# "supplementary_only": kinetic evidence found only in supporting/supplementary
# material — abstract and figure captions alone did not pass.
EvidenceFilter = Literal["all", "supplementary_only"]


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
        # Set for runs saved before open-access classification existed; the
        # lookup runs once, on first read, and is shared by concurrent readers.
        self.needs_access_backfill = False
        self.access_backfill: asyncio.Task | None = None


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
            _write_category_files(run)
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


def _record_from_disk(p: dict) -> PaperRecord:
    # Runs saved before study-type classification existed: classify on load.
    if "study_type" not in p:
        p = {
            **p,
            "study_type": classify_study_type(
                " ".join(filter(None, [p.get("title"), p.get("abstract"), p.get("journal")]))
            ),
        }
    return PaperRecord(**p)


def _filter_papers(
    papers: list[PaperRecord],
    study_type: StudyFilter = "all",
    access: AccessFilter = "all",
    evidence: EvidenceFilter = "all",
) -> list[PaperRecord]:
    out = papers
    # Papers reporting both in vitro and in vivo work belong in both lists.
    if study_type == "unclassified":
        out = [p for p in out if p.study_type == "unclassified"]
    elif study_type != "all":
        out = [p for p in out if p.study_type in (study_type, "both")]
    if access != "all":
        out = [p for p in out if p.access == access]
    if evidence == "supplementary_only":
        out = [p for p in out if p.supplementary_rescued]
    return out


# File name -> (study_type, access, evidence) filter for the per-category files.
_CATEGORY_FILES: dict[str, tuple[StudyFilter, AccessFilter, EvidenceFilter]] = {
    "in_vitro": ("in_vitro", "all", "all"),
    "in_vivo": ("in_vivo", "all", "all"),
    "unclassified": ("unclassified", "all", "all"),
    "open_access": ("all", "open", "all"),
    "closed_access": ("all", "closed", "all"),
    "access_unknown": ("all", "unknown", "all"),
    "supplementary_only": ("all", "all", "supplementary_only"),
}


def _write_category_files(run: _RunState) -> None:
    """Write the included papers to one CSV and one formatted .xlsx per category
    under storage/exports/{step}_{run_id}/ (see _CATEGORY_FILES)."""
    step_slug = run.step_name.lower().replace(" ", "_") or f"step{run.step_id}"
    out_dir = EXPORTS_DIR / f"{step_slug}_{run.run_id}"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, filters in _CATEGORY_FILES.items():
            papers = _filter_papers(run.papers, *filters)
            (out_dir / f"{name}.csv").write_bytes(export.csv_bytes(papers))
            (out_dir / f"{name}.xlsx").write_bytes(
                export.xlsx_bytes(papers, _export_meta(run, "included", *filters))
            )
    except OSError:
        logger.exception("Failed to write category files to %s", out_dir)


def _export_meta(
    run: _RunState,
    which: str,
    study_type: StudyFilter,
    access: AccessFilter,
    evidence: EvidenceFilter = "all",
) -> dict[str, object]:
    return {
        "Stage": f"{run.step_id} — {run.step_name}",
        "Run ID": run.run_id,
        "Exported": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "Paper set": "Included (LLM did not exclude)" if which == "included"
        else "Candidates (all papers sent to the LLM)",
        "Study type filter": study_type.replace("_", " "),
        "Access filter": access,
        "Evidence filter": "supporting materials only"
        if evidence == "supplementary_only"
        else "all",
        "Records fetched (all databases)": run.counts.total_raw,
        "After deduplication": run.counts.after_dedup,
        "After kinetic filter": run.counts.after_kinetic,
        "Final included": run.counts.final,
    }


async def _backfill_access(run: _RunState) -> None:
    records = run.papers + run.candidates
    try:
        access = await resolve_open_access([r.model_dump() for r in records])
    except Exception:  # noqa: BLE001
        # Leave the flag set so the next read retries; serve "unknown" for now.
        logger.exception("Open-access backfill failed for run %s", run.run_id)
        run.access_backfill = None
        return
    for r, a in zip(records, access):
        r.access, r.oa_status, r.oa_url = a["access"], a["oa_status"], a["oa_url"]
    async with _LOCK:
        run.needs_access_backfill = False
        _persist(run)
        _write_category_files(run)


async def _ensure_access(run: _RunState) -> None:
    if not run.needs_access_backfill or run.state != "done":
        return
    if run.access_backfill is None:
        run.access_backfill = asyncio.create_task(_backfill_access(run))
    await asyncio.shield(run.access_backfill)


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
    state.papers = [_record_from_disk(p) for p in (data.get("papers") or [])]
    state.candidates = [_record_from_disk(p) for p in (data.get("candidates") or [])]
    state.message = data.get("message")
    state.step_name = data.get("step_name", "")
    state.needs_access_backfill = any(
        "access" not in p for p in (data.get("papers") or []) + (data.get("candidates") or [])
    )
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
    await _ensure_access(run)
    return RunResults(
        run_id=run.run_id,
        step_id=run.step_id,
        step_name=run.step_name,
        counts=run.counts,
        papers=run.papers,
        candidates=run.candidates,
    )


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
        lines.append(
            f"**Score:** {p.score}  ·  **Study type:** {p.study_type}  ·  "
            f"**Access:** {p.access}  ·  "
            f"**Sources:** {', '.join(p.source_dbs)}"
        )
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
    format: Literal["csv", "xlsx", "json", "md"] = Query("csv"),
    which: Literal["included", "candidates"] = Query("included"),
    study_type: StudyFilter = Query("all"),
    access: AccessFilter = Query("all"),
    evidence: EvidenceFilter = Query("all"),
):
    run = _load_run(run_id)
    await _ensure_access(run)
    papers = _filter_papers(
        run.candidates if which == "candidates" else run.papers, study_type, access, evidence
    )
    category = (f"_{study_type}" if study_type != "all" else "") + (
        f"_{access}_access" if access != "all" else ""
    ) + ("_supplementary_only" if evidence != "all" else "")
    suffix = ("_candidates" if which == "candidates" else "") + category
    if format == "csv":
        return StreamingResponse(
            io.BytesIO(export.csv_bytes(papers)),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="lnp_{run_id}{suffix}.csv"'
            },
        )
    if format == "xlsx":
        return StreamingResponse(
            io.BytesIO(export.xlsx_bytes(papers, _export_meta(run, which, study_type, access, evidence))),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="lnp_{run_id}{suffix}.xlsx"'
            },
        )
    if format == "json":
        payload = RunResults(
            run_id=run.run_id,
            step_id=run.step_id,
            step_name=run.step_name,
            counts=run.counts,
            papers=_filter_papers(run.papers, study_type, access, evidence),
            candidates=_filter_papers(run.candidates, study_type, access, evidence),
        ).model_dump()
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(body),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="lnp_{run_id}{category}.json"'
            },
        )
    if format == "md":
        return StreamingResponse(
            io.BytesIO(_md_bytes(run, papers)),
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="lnp_{run_id}{suffix}.md"'
            },
        )
    raise HTTPException(status_code=400, detail="format must be csv|xlsx|json|md")
