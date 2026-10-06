from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
MAX_CONCURRENCY = 5
ABSTRACT_CHAR_CAP = 8000
STUDY_TYPES = {"in_vitro", "in_vivo", "both", "unclassified"}
CAPTIONS_CHAR_CAP = 6000
SUPPLEMENTARY_CHAR_CAP = 2000


def _system_prompt(step_name: str, step_description: str, strict_kinetic: bool) -> str:
    kinetic_clause = (
        "The paper MUST contain time-resolved/kinetic data (rates, half-lives, "
        "time courses, t1/2). Papers without explicit time-dependent measurements "
        "are 'exclude'. EXCEPTION: if the user message marks the paper as a "
        "REVIEW ARTICLE, this kinetic requirement does not apply — judge it only "
        "on topical relevance to the step, since a review synthesizes other "
        "papers' data rather than reporting its own."
        if strict_kinetic
        else "Time-resolved data is a strong plus but not strictly required."
    )
    return (
        "You are a biomedical literature screener for a Lipid Nanoparticle (LNP) "
        "delivery-journey review. Decide whether the paper is on-topic for the "
        f"step '{step_name}' ({step_description}).\n\n"
        "A paper is 'include' only if it (a) is about lipid nanoparticles "
        "specifically (not generic nanoparticles, liposomes for other purposes, "
        f"polymeric NPs, etc.), and (b) studies the '{step_name}' "
        f"step of the LNP journey. {kinetic_clause}\n\n"
        "Evidence may come from the abstract OR, when provided, the figure/table "
        "captions and supplementary material taken from the paper's full text. "
        "Abstracts often omit experimental detail that only appears in figures, "
        "so treat measurements described in captions (e.g. 'uptake measured at "
        "1, 6 and 24 h by flow cytometry', 'fluorescence over 18 h') as valid "
        "evidence, including valid time-resolved/kinetic evidence.\n\n"
        "Separately, classify the paper's study type (independent of the verdict):\n"
        "- 'in_vitro': experiments in cultured cells, cell lines, primary cells, "
        "organoids, ex vivo tissue, or biological fluids such as plasma/serum "
        "outside a living organism.\n"
        "- 'in_vivo': experiments in living animals (mice, rats, NHPs, zebrafish, "
        "etc.) or humans/patients, including dosing, biodistribution, efficacy or "
        "expression measured in the organism. Infer this from context even if no "
        "species is named (e.g. delivery to the retina, liver, or tumors after "
        "injection).\n"
        "- 'both': the paper reports both in vitro and in vivo experiments.\n"
        "- 'unclassified': no biological experiments (purely computational, "
        "simulation, physicochemical or formulation characterization), or too "
        "little information to tell (e.g. title only).\n"
        "For a REVIEW ARTICLE, classify by the kind of evidence it mainly "
        "discusses. With no abstract, use the title and captions if they make "
        "the study type clear; otherwise 'unclassified'.\n\n"
        "Return JSON ONLY in this exact shape:\n"
        '{"score": <float 0..1>, "verdict": "include"|"borderline"|"exclude", '
        '"study_type": "in_vitro"|"in_vivo"|"both"|"unclassified", '
        '"rationale": "<<=240 chars, plain English, cite specific evidence from '
        'the abstract or captions>"}'
    )


def _truncate(text: str, cap: int) -> str:
    text = (text or "").strip()
    return text[:cap] + " …[truncated]" if len(text) > cap else text


def _user_prompt(paper: dict) -> str:
    title = paper.get("title") or "(no title)"
    abstract = _truncate(paper.get("abstract") or "", ABSTRACT_CHAR_CAP)
    captions = _truncate(paper.get("captions") or "", CAPTIONS_CHAR_CAP)
    supplementary = _truncate(paper.get("supplementary") or "", SUPPLEMENTARY_CHAR_CAP)
    journal = paper.get("journal") or ""
    year = paper.get("year") or ""
    review_line = "Article type: REVIEW ARTICLE\n" if paper.get("_is_review") else ""
    if paper.get("_kinetic_unverified"):
        review_line += (
            "Note: FULL TEXT UNAVAILABLE. Kinetic data could not be checked because "
            "only the abstract is accessible, and abstracts often omit time courses "
            "shown in figures. If the abstract shows this step was measured, "
            "do not 'exclude' solely for lacking time-resolved data in the "
            "abstract; use 'borderline' (or 'include' if other evidence is strong).\n"
        )
    return (
        f"Title: {title}\n"
        f"{review_line}"
        f"Journal: {journal}  Year: {year}\n"
        f"Abstract: {abstract or '(no abstract)'}"
        + (f"\n\nFigure/table captions (from full text):\n{captions}" if captions else "")
        + (f"\n\nSupplementary material (from full text):\n{supplementary}" if supplementary else "")
    )


async def _score_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    api_key: str,
    model: str,
    system: str,
    paper: dict,
) -> dict:
    async with sem:
        try:
            resp = await client.post(
                OPENAI_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": _user_prompt(paper)},
                    ],
                },
                timeout=45.0,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            parsed = json.loads(raw)
            score = float(parsed.get("score", 0.0))
            score = max(0.0, min(1.0, score))
            verdict = str(parsed.get("verdict", "borderline")).lower()
            if verdict not in {"include", "borderline", "exclude"}:
                verdict = "borderline"
            rationale = str(parsed.get("rationale", "")).strip()[:400]
            study_type = str(parsed.get("study_type", "")).lower().replace("-", "_").replace(" ", "_")
            return {
                "llm_score": round(score, 3),
                "llm_verdict": verdict,
                "llm_rationale": rationale,
                # None = no usable answer; the pipeline falls back to keywords.
                "llm_study_type": study_type if study_type in STUDY_TYPES else None,
            }
        except Exception as e:  # noqa: BLE001
            return {
                "llm_score": None,
                "llm_verdict": "error",
                "llm_rationale": f"{type(e).__name__}: {e}"[:400],
            }


def _skipped_record(reason: str) -> dict:
    return {
        "llm_score": None,
        "llm_verdict": "skipped",
        "llm_rationale": reason,
    }


async def score_papers(
    papers: list[dict],
    *,
    step_name: str,
    step_description: str,
    strict_kinetic: bool,
) -> list[dict]:
    """Returns a list aligned with `papers`, each {llm_score, llm_verdict,
    llm_rationale, llm_study_type} (llm_study_type absent on skip/error).

    If OPENAI_API_KEY is missing or the list is empty, returns 'skipped' entries
    so the pipeline still produces a valid response.
    """
    if not papers:
        return []
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return [_skipped_record("OPENAI_API_KEY not set") for _ in papers]

    system = _system_prompt(step_name, step_description, strict_kinetic)
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        tasks = [
            _score_one(client, sem, api_key, DEFAULT_MODEL, system, p) for p in papers
        ]
        return await asyncio.gather(*tasks)


__all__ = ["score_papers"]
