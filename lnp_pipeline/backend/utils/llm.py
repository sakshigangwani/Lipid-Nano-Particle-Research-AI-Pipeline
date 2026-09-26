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
        "Return JSON ONLY in this exact shape:\n"
        '{"score": <float 0..1>, "verdict": "include"|"borderline"|"exclude", '
        '"rationale": "<<=240 chars, plain English, cite specific evidence from '
        'the abstract>"}'
    )


def _user_prompt(paper: dict) -> str:
    title = paper.get("title") or "(no title)"
    abstract = (paper.get("abstract") or "").strip()
    if len(abstract) > ABSTRACT_CHAR_CAP:
        abstract = abstract[:ABSTRACT_CHAR_CAP] + " …[truncated]"
    journal = paper.get("journal") or ""
    year = paper.get("year") or ""
    review_line = "Article type: REVIEW ARTICLE\n" if paper.get("_is_review") else ""
    return (
        f"Title: {title}\n"
        f"{review_line}"
        f"Journal: {journal}  Year: {year}\n"
        f"Abstract: {abstract or '(no abstract)'}"
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
            return {
                "llm_score": round(score, 3),
                "llm_verdict": verdict,
                "llm_rationale": rationale,
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
    """Returns a list aligned with `papers`, each {llm_score, llm_verdict, llm_rationale}.

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
