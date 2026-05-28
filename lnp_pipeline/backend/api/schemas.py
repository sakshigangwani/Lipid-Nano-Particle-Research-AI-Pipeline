from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class StepInfo(BaseModel):
    id: int
    name: str
    description: str
    strict_kinetic: bool


class SearchRequest(BaseModel):
    step_id: int = Field(..., ge=1, le=7)


class SearchStartResponse(BaseModel):
    run_id: str


class PrismaCounts(BaseModel):
    pubmed: int = 0
    europepmc: int = 0
    semantic_scholar: int = 0
    crossref: int = 0
    openalex: int = 0
    biorxiv: int = 0
    total_raw: int = 0
    after_dedup: int = 0
    after_quant: int = 0
    after_kinetic: int = 0
    caption_rescued: int = 0
    llm_scored: int = 0
    final: int = 0


class RunStatus(BaseModel):
    run_id: str
    step_id: int
    state: Literal["running", "done", "error"]
    counts: PrismaCounts
    message: Optional[str] = None


class PaperRecord(BaseModel):
    title: str
    authors: list[str] = []
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    source_dbs: list[str] = []
    abstract: Optional[str] = None
    matched_quant_terms: list[str] = []
    matched_kinetic_terms: list[str] = []
    matched_signal_phrases: list[str] = []
    score: float = 0.0
    llm_score: Optional[float] = None
    llm_verdict: Literal["include", "borderline", "exclude", "skipped", "error"] = "skipped"
    llm_rationale: str = ""
    caption_rescued: bool = False
    supplementary_rescued: bool = False


class RunResults(BaseModel):
    run_id: str
    step_id: int
    step_name: str
    counts: PrismaCounts
    papers: list[PaperRecord]
