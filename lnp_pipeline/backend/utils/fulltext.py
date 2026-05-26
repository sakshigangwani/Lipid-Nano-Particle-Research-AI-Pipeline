"""Fetch figure + table captions from Europe PMC full text as a fallback when
the abstract alone doesn't contain enough quantitative/kinetic evidence.

Workflow per paper:
  1. Resolve a PMCID via Europe PMC's search endpoint (by DOI, falling back to PMID).
  2. Hit `/{PMCID}/fullTextXML` and parse <fig>/<table-wrap> <caption> blocks.
  3. Return the concatenated caption text.

Both lookups are cached on disk under storage/cache/fulltext/* so re-runs are
free. Anything that fails (closed-access paper, no PMCID, parse error) returns
an empty string — the pipeline simply doesn't get a rescue for that paper.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from . import cache

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Hard cap on how many full-text fetches we'll do per run. Keeps wall-clock
# bounded even when many papers fail the abstract-only filters.
MAX_CAPTION_FETCHES = 80
# How many full-text downloads to run in parallel against Europe PMC.
CAPTION_CONCURRENCY = 5


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    r = await client.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential_jitter(initial=1, max=6),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get_text(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        return ""
    r.raise_for_status()
    return r.text


async def _resolve_pmcid(
    client: httpx.AsyncClient, doi: str | None, pmid: str | None
) -> str | None:
    if not doi and not pmid:
        return None
    if doi:
        query = f"DOI:{doi}"
    else:
        query = f"EXT_ID:{pmid} AND SRC:MED"
    try:
        data = await _get_json(
            client,
            SEARCH_URL,
            {"query": query, "format": "json", "resultType": "lite", "pageSize": 1},
        )
    except httpx.HTTPError:
        return None
    hits = (data.get("resultList") or {}).get("result", []) if data else []
    if not hits:
        return None
    pmcid = (hits[0] or {}).get("pmcid")
    return pmcid or None


def _extract_captions(xml_text: str) -> str:
    if not xml_text:
        return ""
    try:
        # Strip any namespace prefixes so simple findall paths work.
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    for tag in ("fig", "table-wrap"):
        for el in root.iter(tag):
            cap = None
            for child in el.iter("caption"):
                cap = child
                break
            if cap is None:
                continue
            text = " ".join("".join(cap.itertext()).split())
            if text:
                # Prefix so downstream regex/LLM knows this came from a figure.
                tag_label = "Figure" if tag == "fig" else "Table"
                parts.append(f"{tag_label} caption: {text}")
    return "\n\n".join(parts)


async def _fetch_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    doi: str | None,
    pmid: str | None,
) -> str:
    cache_key = {"doi": (doi or "").lower(), "pmid": pmid or ""}
    cached = cache.load("fulltext", cache_key)
    if cached is not None:
        return cached if isinstance(cached, str) else ""

    async with sem:
        try:
            pmcid = await _resolve_pmcid(client, doi, pmid)
            if not pmcid:
                cache.save("fulltext", cache_key, "")
                return ""
            xml_text = await _get_text(client, FULLTEXT_URL.format(pmcid=pmcid))
            captions = _extract_captions(xml_text)
        except Exception:  # noqa: BLE001
            captions = ""
    cache.save("fulltext", cache_key, captions)
    return captions


async def fetch_captions_for(papers: list[dict[str, Any]]) -> dict[str, str]:
    """Returns {paper_key: caption_text} for up to MAX_CAPTION_FETCHES papers.

    The key matches the value returned by `paper_key(p)` below; callers look
    captions up via that helper so the keying logic stays in one place.
    """
    if not papers:
        return {}
    selected = papers[:MAX_CAPTION_FETCHES]
    sem = asyncio.Semaphore(CAPTION_CONCURRENCY)
    async with httpx.AsyncClient(
        headers={"User-Agent": "lnp-pipeline/1.0"},
    ) as client:
        tasks = [_fetch_one(client, sem, p.get("doi"), p.get("pmid")) for p in selected]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    out: dict[str, str] = {}
    for p, r in zip(selected, results):
        if isinstance(r, Exception):
            continue
        if r:
            out[paper_key(p)] = r
    return out


def paper_key(p: dict[str, Any]) -> str:
    doi = (p.get("doi") or "").lower()
    pmid = p.get("pmid") or ""
    title = (p.get("title") or "").lower()[:120]
    return doi or pmid or title


__all__ = [
    "MAX_CAPTION_FETCHES",
    "fetch_captions_for",
    "paper_key",
]
