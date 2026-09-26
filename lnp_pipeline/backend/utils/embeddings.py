from __future__ import annotations

import asyncio
import math
import os

import httpx

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-3-small"

# Reference phrases spanning the many ways a paper can describe time-resolved /
# kinetic evidence without matching the regex list in filters.py verbatim
# (e.g. "biexponential decay", "washout period", "released over 24 h").
# Semantic similarity to any one of these phrases counts as a kinetic match.
KINETIC_REFERENCE_PHRASES: list[str] = [
    "half-life and time-dependent clearance measurements",
    "rate constant of uptake or release",
    "time-course experiment measuring change over time",
    "pharmacokinetic profile with time points",
    "kinetics of endosomal escape or cargo release",
    "biexponential or first-order decay of signal over time",
    "washout or chase period following treatment",
    "area under the curve (AUC) over time",
    "onset and duration of an effect measured across time points",
    "real-time or live-cell imaging tracking a process over time",
]

# Cosine similarity at/above this threshold counts as a semantic kinetic match.
SIMILARITY_THRESHOLD = 0.35

_ref_embeddings_cache: list[list[float]] | None = None
_ref_embeddings_lock = asyncio.Lock()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _embed_texts(client: httpx.AsyncClient, api_key: str, texts: list[str]) -> list[list[float]]:
    resp = await client.post(
        OPENAI_EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": EMBEDDING_MODEL, "input": texts},
        timeout=45.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]


async def _get_reference_embeddings(client: httpx.AsyncClient, api_key: str) -> list[list[float]]:
    global _ref_embeddings_cache
    if _ref_embeddings_cache is not None:
        return _ref_embeddings_cache
    async with _ref_embeddings_lock:
        if _ref_embeddings_cache is None:
            _ref_embeddings_cache = await _embed_texts(client, api_key, KINETIC_REFERENCE_PHRASES)
        return _ref_embeddings_cache


async def find_kinetic_semantic_matches(texts: list[str]) -> list[list[str]]:
    """For each input text, returns the reference kinetic phrases it's semantically
    similar to (cosine similarity >= SIMILARITY_THRESHOLD), or [] if none / on error /
    if no API key is configured. Aligned 1:1 with `texts`.
    """
    if not texts:
        return []
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return [[] for _ in texts]

    non_empty_idx = [i for i, t in enumerate(texts) if (t or "").strip()]
    if not non_empty_idx:
        return [[] for _ in texts]

    try:
        async with httpx.AsyncClient() as client:
            ref_vecs = await _get_reference_embeddings(client, api_key)
            to_embed = [texts[i][:8000] for i in non_empty_idx]
            text_vecs = await _embed_texts(client, api_key, to_embed)
    except Exception:  # noqa: BLE001
        return [[] for _ in texts]

    results: list[list[str]] = [[] for _ in texts]
    for idx, vec in zip(non_empty_idx, text_vecs):
        matches = [
            phrase
            for phrase, ref_vec in zip(KINETIC_REFERENCE_PHRASES, ref_vecs)
            if _cosine_similarity(vec, ref_vec) >= SIMILARITY_THRESHOLD
        ]
        results[idx] = matches
    return results


__all__ = ["find_kinetic_semantic_matches", "KINETIC_REFERENCE_PHRASES", "SIMILARITY_THRESHOLD"]
