from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from ..clients import crossref, europepmc, pubmed, semantic_scholar
from ..utils.dedup import dedup_papers
from ..utils.filters import (
    find_kinetic_matches,
    find_quant_matches,
    find_signal_phrases,
    is_lnp_focused,
)
from ..utils.scoring import score_paper

ProgressCb = Callable[[dict], Awaitable[None] | None]
MAX_RESULTS_PER_DB = 50


def _haystack(p: dict) -> str:
    return " ".join(filter(None, [p.get("title"), p.get("abstract"), p.get("journal")]))


async def _emit(cb: ProgressCb | None, counts: dict) -> None:
    if cb is None:
        return
    res = cb(counts)
    if asyncio.iscoroutine(res):
        await res


async def run_step_search(
    *,
    boolean_query: str,
    quant_keywords: list[str],
    kinetic_keywords: list[str],
    signal_phrases: list[str],
    strict_kinetic: bool,
    progress_cb: ProgressCb | None = None,
) -> list[dict]:
    counts: dict = {
        "pubmed": 0,
        "europepmc": 0,
        "semantic_scholar": 0,
        "crossref": 0,
        "total_raw": 0,
        "after_dedup": 0,
        "after_quant": 0,
        "after_kinetic": 0,
        "final": 0,
    }

    results = await asyncio.gather(
        pubmed.search(boolean_query, MAX_RESULTS_PER_DB),
        europepmc.search(boolean_query, MAX_RESULTS_PER_DB),
        semantic_scholar.search(boolean_query, MAX_RESULTS_PER_DB),
        crossref.search(boolean_query, MAX_RESULTS_PER_DB),
        return_exceptions=True,
    )
    pm, epmc, ss, cr = [r if not isinstance(r, Exception) else [] for r in results]
    counts["pubmed"] = len(pm)
    counts["europepmc"] = len(epmc)
    counts["semantic_scholar"] = len(ss)
    counts["crossref"] = len(cr)
    combined: list[dict] = [*pm, *epmc, *ss, *cr]
    counts["total_raw"] = len(combined)
    await _emit(progress_cb, dict(counts))

    deduped = dedup_papers(combined)
    counts["after_dedup"] = len(deduped)
    await _emit(progress_cb, dict(counts))

    # LNP focus + quant filter
    quant_passed: list[dict] = []
    for p in deduped:
        text = _haystack(p)
        if not is_lnp_focused(text):
            continue
        q = find_quant_matches(text, quant_keywords)
        if not q:
            continue
        p["_matched_quant"] = q
        quant_passed.append(p)
    counts["after_quant"] = len(quant_passed)
    await _emit(progress_cb, dict(counts))

    # Kinetic filter
    kinetic_passed: list[dict] = []
    for p in quant_passed:
        text = _haystack(p)
        k = find_kinetic_matches(text, kinetic_keywords)
        if strict_kinetic and not k:
            continue
        p["_matched_kinetic"] = k
        kinetic_passed.append(p)
    counts["after_kinetic"] = len(kinetic_passed)
    await _emit(progress_cb, dict(counts))

    # Score + finalize
    final: list[dict] = []
    for p in kinetic_passed:
        text = _haystack(p)
        sigs = find_signal_phrases(text, signal_phrases)
        record = {
            "title": p.get("title") or "",
            "authors": p.get("authors") or [],
            "year": p.get("year"),
            "journal": p.get("journal"),
            "doi": p.get("doi"),
            "pmid": p.get("pmid"),
            "source_dbs": p.get("source_dbs") or [],
            "abstract": p.get("abstract"),
            "matched_quant_terms": p.get("_matched_quant") or [],
            "matched_kinetic_terms": p.get("_matched_kinetic") or [],
            "matched_signal_phrases": sigs,
            "score": score_paper(
                p.get("_matched_quant") or [],
                p.get("_matched_kinetic") or [],
                sigs,
                p.get("source_dbs") or [],
            ),
        }
        final.append(record)

    final.sort(key=lambda r: r["score"], reverse=True)
    counts["final"] = len(final)
    await _emit(progress_cb, dict(counts))
    return final
