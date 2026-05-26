from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from ..clients import biorxiv, crossref, europepmc, openalex, pubmed, semantic_scholar
from ..utils.dedup import dedup_papers
from ..utils.filters import (
    find_kinetic_matches,
    find_quant_matches,
    find_signal_phrases,
    is_lnp_focused,
)
from ..utils.fulltext import fetch_captions_for, paper_key
from ..utils.llm import score_papers as llm_score_papers
from ..utils.scoring import score_paper

ProgressCb = Callable[[dict], Awaitable[None] | None]
MAX_RESULTS_PER_DB = 200


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
    step_name: str = "",
    step_description: str = "",
    progress_cb: ProgressCb | None = None,
) -> list[dict]:
    counts: dict = {
        "pubmed": 0,
        "europepmc": 0,
        "semantic_scholar": 0,
        "crossref": 0,
        "openalex": 0,
        "biorxiv": 0,
        "total_raw": 0,
        "after_dedup": 0,
        "after_quant": 0,
        "after_kinetic": 0,
        "caption_rescued": 0,
        "llm_scored": 0,
        "final": 0,
    }

    results = await asyncio.gather(
        pubmed.search(boolean_query, MAX_RESULTS_PER_DB),
        europepmc.search(boolean_query, MAX_RESULTS_PER_DB),
        semantic_scholar.search(boolean_query, MAX_RESULTS_PER_DB),
        crossref.search(boolean_query, MAX_RESULTS_PER_DB),
        openalex.search(boolean_query, MAX_RESULTS_PER_DB),
        biorxiv.search(boolean_query, MAX_RESULTS_PER_DB),
        return_exceptions=True,
    )
    pm, epmc, ss, cr, oa, bx = [
        r if not isinstance(r, Exception) else [] for r in results
    ]
    counts["pubmed"] = len(pm)
    counts["europepmc"] = len(epmc)
    counts["semantic_scholar"] = len(ss)
    counts["crossref"] = len(cr)
    counts["openalex"] = len(oa)
    counts["biorxiv"] = len(bx)
    combined: list[dict] = [*pm, *epmc, *ss, *cr, *oa, *bx]
    counts["total_raw"] = len(combined)
    await _emit(progress_cb, dict(counts))

    deduped = dedup_papers(combined)
    counts["after_dedup"] = len(deduped)
    await _emit(progress_cb, dict(counts))

    # ─── Pass 1: abstract-only filter, also track who's LNP-focused ───
    lnp_focused: list[dict] = []
    for p in deduped:
        text = _haystack(p)
        if not is_lnp_focused(text):
            continue
        p["_haystack_abstract"] = text
        p["_matched_quant"] = find_quant_matches(text, quant_keywords)
        p["_matched_kinetic"] = find_kinetic_matches(text, kinetic_keywords)
        lnp_focused.append(p)

    # ─── Pass 2: caption-fallback for papers that failed quant OR kinetic ───
    needs_captions = [
        p for p in lnp_focused
        if not p["_matched_quant"] or (strict_kinetic and not p["_matched_kinetic"])
    ]
    captions_map = await fetch_captions_for(needs_captions)
    rescued = 0
    for p in needs_captions:
        caps = captions_map.get(paper_key(p))
        if not caps:
            continue
        combined_text = p["_haystack_abstract"] + "\n\n" + caps
        rescued_this_paper = False
        if not p["_matched_quant"]:
            new_q = find_quant_matches(combined_text, quant_keywords)
            if new_q:
                p["_matched_quant"] = new_q
                p["_caption_rescued_quant"] = True
                rescued_this_paper = True
        if strict_kinetic and not p["_matched_kinetic"]:
            new_k = find_kinetic_matches(combined_text, kinetic_keywords)
            if new_k:
                p["_matched_kinetic"] = new_k
                p["_caption_rescued_kinetic"] = True
                rescued_this_paper = True
        if rescued_this_paper:
            p["_caption_text"] = caps
            rescued += 1
    counts["caption_rescued"] = rescued
    await _emit(progress_cb, dict(counts))

    # ─── Apply gates using post-fallback matches ───
    quant_passed = [p for p in lnp_focused if p["_matched_quant"]]
    counts["after_quant"] = len(quant_passed)
    await _emit(progress_cb, dict(counts))

    kinetic_passed = [
        p for p in quant_passed
        if (not strict_kinetic) or p["_matched_kinetic"]
    ]
    counts["after_kinetic"] = len(kinetic_passed)
    await _emit(progress_cb, dict(counts))

    # ─── OpenAI LLM relevance pass over the surviving set ───
    # If a paper was caption-rescued, give the LLM the captions too so its
    # verdict is consistent with the regex evidence.
    llm_inputs = []
    for p in kinetic_passed:
        if p.get("_caption_text"):
            joined = (p.get("abstract") or "") + "\n\n" + p["_caption_text"]
            llm_inputs.append({**p, "abstract": joined})
        else:
            llm_inputs.append(p)
    llm_results = await llm_score_papers(
        llm_inputs,
        step_name=step_name,
        step_description=step_description,
        strict_kinetic=strict_kinetic,
    )
    counts["llm_scored"] = sum(1 for r in llm_results if r.get("llm_score") is not None)
    await _emit(progress_cb, dict(counts))

    # ─── Score + finalize ───
    final: list[dict] = []
    for p, llm in zip(kinetic_passed, llm_results):
        sigs_text = p["_haystack_abstract"]
        if p.get("_caption_text"):
            sigs_text = sigs_text + "\n\n" + p["_caption_text"]
        sigs = find_signal_phrases(sigs_text, signal_phrases)
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
            "llm_score": llm.get("llm_score"),
            "llm_verdict": llm.get("llm_verdict", "skipped"),
            "llm_rationale": llm.get("llm_rationale", ""),
            "caption_rescued": bool(
                p.get("_caption_rescued_quant") or p.get("_caption_rescued_kinetic")
            ),
        }
        final.append(record)

    final = [r for r in final if r["llm_verdict"] != "exclude"]
    final.sort(
        key=lambda r: (
            r["llm_score"] if r["llm_score"] is not None else -1.0,
            r["score"],
        ),
        reverse=True,
    )
    counts["final"] = len(final)
    await _emit(progress_cb, dict(counts))
    return final
