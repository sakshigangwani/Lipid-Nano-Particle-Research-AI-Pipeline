from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Awaitable, Callable

from ..clients import arxiv, biorxiv, crossref, europepmc, openalex, pubmed, semantic_scholar
from ..utils.dedup import dedup_papers
from ..utils.filters import (
    find_kinetic_matches,
    find_quant_matches,
    find_signal_phrases,
    has_in_vivo_markers,
    is_lnp_focused,
)
from ..utils.fulltext import fetch_captions_for, paper_key
from ..utils.llm import score_papers as llm_score_papers
from ..utils.scoring import score_paper

logger = logging.getLogger("lnp_pipeline.filtering")

ProgressCb = Callable[[dict], Awaitable[None] | None]


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
    in_vitro_only: bool = False,
    step_name: str = "",
    step_description: str = "",
    progress_cb: ProgressCb | None = None,
) -> dict[str, list[dict]]:
    counts: dict = {
        "pubmed": 0,
        "europepmc": 0,
        "semantic_scholar": 0,
        "crossref": 0,
        "openalex": 0,
        "biorxiv": 0,
        "arxiv": 0,
        "total_raw": 0,
        "after_dedup": 0,
        "after_quant": 0,
        "after_kinetic": 0,
        "caption_rescued": 0,
        "llm_scored": 0,
        "final": 0,
    }

    results = await asyncio.gather(
        pubmed.search(boolean_query),
        europepmc.search(boolean_query),
        semantic_scholar.search(boolean_query),
        crossref.search(boolean_query),
        openalex.search(boolean_query),
        biorxiv.search(boolean_query),
        arxiv.search(boolean_query),
        return_exceptions=True,
    )
    pm, epmc, ss, cr, oa, bx, ax = [
        r if not isinstance(r, Exception) else [] for r in results
    ]
    counts["pubmed"] = len(pm)
    counts["europepmc"] = len(epmc)
    counts["semantic_scholar"] = len(ss)
    counts["crossref"] = len(cr)
    counts["openalex"] = len(oa)
    counts["biorxiv"] = len(bx)
    counts["arxiv"] = len(ax)
    combined: list[dict] = [*pm, *epmc, *ss, *cr, *oa, *bx, *ax]
    counts["total_raw"] = len(combined)
    await _emit(progress_cb, dict(counts))

    deduped = dedup_papers(combined)
    counts["after_dedup"] = len(deduped)
    await _emit(progress_cb, dict(counts))

    # ─── Debug-only rejection tally: why did a paper NOT make it to `included`? ───
    # Every paper is bucketed into exactly one reason the first time it drops out.
    rejection_reasons: Counter[str] = Counter()

    # ─── Pass 1: abstract-only filter, also track who's LNP-focused ───
    # Some sources (notably CrossRef) frequently omit the abstract entirely.
    # In that case title+journal alone is often too little text to judge LNP
    # focus fairly, so we don't auto-reject — the paper already matched the
    # LNP-related boolean query at the source, so we trust that and let it
    # through to the quant/kinetic gates instead (which still have to pass).
    lnp_focused: list[dict] = []
    for p in deduped:
        text = _haystack(p)
        has_abstract = bool((p.get("abstract") or "").strip())
        if has_abstract and not is_lnp_focused(text):
            rejection_reasons["not_lnp_focused"] += 1
            continue
        if not has_abstract:
            rejection_reasons["no_abstract_passed_on_trust"] += 1
        # In-vitro-only steps reject papers whose abstract shows whole-animal
        # markers (mice, rats, in vivo, mg/kg dosing, IV/IP/IM routes, etc.).
        # Only applied when the abstract actually exists — a no-abstract
        # record has nothing to judge study type from, so it's trusted
        # through here too, same as the LNP-focus check above.
        if in_vitro_only and has_abstract and has_in_vivo_markers(text):
            rejection_reasons["excluded_in_vivo"] += 1
            continue
        p["_haystack_abstract"] = text
        p["_matched_quant"] = find_quant_matches(text, quant_keywords)
        p["_matched_kinetic"] = find_kinetic_matches(text, kinetic_keywords)
        lnp_focused.append(p)

    # ─── Pass 2: full-text fallback for papers that failed quant OR kinetic ───
    # We try figure/table captions first (cheap to attribute), then layer in
    # supplementary-material text. Each rescue is attributed so the UI can
    # tell the user *why* a paper survived.
    needs_captions = [
        p for p in lnp_focused
        if not p["_matched_quant"] or (strict_kinetic and not p["_matched_kinetic"])
    ]
    captions_map = await fetch_captions_for(needs_captions)
    rescued = 0
    for p in needs_captions:
        bundle = captions_map.get(paper_key(p))
        if not bundle:
            continue
        caps = bundle.get("captions") or ""
        suppl = bundle.get("supplementary") or ""
        if not caps and not suppl:
            continue

        rescued_this_paper = False
        rescue_text_parts: list[str] = []

        def _try_rescue(extra: str, source_label: str) -> bool:
            """Try the regex gates with `extra` text appended; if anything new
            matches, persist it and tag `p` with which source rescued which gate.
            Returns True if this source contributed any new match.
            """
            nonlocal rescued_this_paper
            if not extra:
                return False
            combined = p["_haystack_abstract"] + "\n\n" + extra
            contributed = False
            if not p["_matched_quant"]:
                new_q = find_quant_matches(combined, quant_keywords)
                if new_q:
                    p["_matched_quant"] = new_q
                    p[f"_{source_label}_rescued_quant"] = True
                    contributed = True
            if strict_kinetic and not p["_matched_kinetic"]:
                new_k = find_kinetic_matches(combined, kinetic_keywords)
                if new_k:
                    p["_matched_kinetic"] = new_k
                    p[f"_{source_label}_rescued_kinetic"] = True
                    contributed = True
            if contributed:
                rescued_this_paper = True
                rescue_text_parts.append(extra)
            return contributed

        # Try captions first (cheaper signal), then supplementary if still short.
        _try_rescue(caps, "caption")
        _try_rescue(suppl, "supplementary")

        if rescued_this_paper:
            p["_caption_text"] = "\n\n".join(rescue_text_parts)
            rescued += 1
    counts["caption_rescued"] = rescued
    await _emit(progress_cb, dict(counts))

    # ─── Apply gates using post-fallback matches ───
    quant_passed: list[dict] = []
    for p in lnp_focused:
        if p["_matched_quant"]:
            quant_passed.append(p)
        else:
            rejection_reasons["failed_quant_filter"] += 1
    counts["after_quant"] = len(quant_passed)
    await _emit(progress_cb, dict(counts))

    kinetic_passed: list[dict] = []
    for p in quant_passed:
        if (not strict_kinetic) or p["_matched_kinetic"]:
            kinetic_passed.append(p)
        else:
            rejection_reasons["failed_kinetic_filter"] += 1
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
    # `candidates` holds *every* paper that survived the deterministic regex
    # gates and was sent to the LLM (the pre-LLM-scored set — e.g. the 86 in
    # the funnel). `included` is the subset the LLM did not mark 'exclude'
    # (e.g. the 48). The UI exposes both as separate tabs.
    candidates: list[dict] = []
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
            "supplementary_rescued": bool(
                p.get("_supplementary_rescued_quant")
                or p.get("_supplementary_rescued_kinetic")
            ),
        }
        candidates.append(record)

    def _sort_key(r: dict) -> tuple:
        return (
            r["llm_score"] if r["llm_score"] is not None else -1.0,
            r["score"],
        )

    candidates.sort(key=_sort_key, reverse=True)
    included = []
    for r in candidates:
        if r["llm_verdict"] != "exclude":
            included.append(r)
        else:
            rejection_reasons["llm_excluded"] += 1
    counts["final"] = len(included)
    await _emit(progress_cb, dict(counts))

    _log_rejection_summary(
        step_name=step_name,
        total_raw=counts["total_raw"],
        after_dedup=counts["after_dedup"],
        rejection_reasons=rejection_reasons,
        final=counts["final"],
    )

    return {"included": included, "candidates": candidates}


def _log_rejection_summary(
    *,
    step_name: str,
    total_raw: int,
    after_dedup: int,
    rejection_reasons: Counter[str],
    final: int,
) -> None:
    """Debug-only breakdown of why papers were filtered out at each stage.

    Writes a formatted report to backend/storage/debug/{step_name}_filter_report.json
    (overwritten each run) so it's easy to open and review, in addition to
    logging a summary line.
    """
    reasons_labeled = {
        "not_lnp_focused": "Rejected: had an abstract, but abstract/title/journal text never mentions LNPs specifically",
        "excluded_in_vivo": "Rejected: in_vitro_only step, abstract shows whole-animal/in vivo markers (mice, mg/kg dosing, IV/IP/IM route, etc.)",
        "failed_quant_filter": "Rejected: no quantitative evidence found (even after caption/supplementary rescue)",
        "failed_kinetic_filter": "Rejected: no time-course/kinetic evidence found (strict_kinetic step, even after rescue)",
        "llm_excluded": "Rejected: passed all regex gates, but the LLM judged it off-topic/irrelevant",
    }
    total_rejected = sum(rejection_reasons.get(k, 0) for k in reasons_labeled)
    no_abstract_passed = rejection_reasons.get("no_abstract_passed_on_trust", 0)
    report = {
        "step_name": step_name,
        "total_raw_fetched": total_raw,
        "after_dedup": after_dedup,
        "total_rejected": total_rejected,
        "final_included": final,
        "not_a_rejection": {
            "no_abstract_passed_on_trust": {
                "count": no_abstract_passed,
                "description": (
                    "NOT rejected: source gave no abstract, so the LNP-focus text "
                    "check was skipped and the paper was trusted through to the "
                    "quant/kinetic gates (it still had to pass those to survive)."
                ),
            }
        },
        "rejected_by_reason": {
            reason: {
                "count": rejection_reasons.get(reason, 0),
                "description": label,
            }
            for reason, label in reasons_labeled.items()
        },
    }

    logger.info(
        "Filter summary for '%s': raw=%d dedup=%d rejected=%d final=%d | breakdown=%s",
        step_name,
        total_raw,
        after_dedup,
        total_rejected,
        final,
        dict(rejection_reasons),
    )

    try:
        import json
        from pathlib import Path

        debug_dir = Path(__file__).resolve().parent.parent / "storage" / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = step_name.lower().replace(" ", "_") or "step"
        report_path = debug_dir / f"{safe_name}_filter_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Wrote filter debug report to %s", report_path)
    except OSError:
        logger.exception("Failed to write filter debug report")
