"""Fetch figure/table captions and supplementary-material text from Europe PMC
full text as a fallback when the abstract alone doesn't contain enough
quantitative/kinetic evidence.

Workflow per paper:
  1. Resolve a PMCID via Europe PMC's search endpoint (by DOI, falling back to PMID).
  2. Hit `/{PMCID}/fullTextXML` (falling back to NCBI efetch db=pmc for
     non-open-access PMC articles such as author manuscripts) and parse <fig>/<table-wrap> <caption> blocks
     and <supplementary-material> blocks.
  3. Return both bundles separately so downstream can attribute the rescue.

Both lookups are cached on disk under storage/cache/fulltext_v3/* so re-runs are
free. Anything that fails (closed-access paper, no PMCID, parse error) returns
empty strings — the pipeline simply doesn't get a rescue for that paper.

Note: Europe PMC's fullTextXML endpoint only serves papers with a PMCID.
Strictly closed-access papers with no PMC mirror remain abstract-only.
"""

from __future__ import annotations

import asyncio
import os
import time
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
# Fallback: Europe PMC's fullTextXML only serves its open-access subset and
# returns HTTP 500 for everything else — including NIH author manuscripts that
# have a PMCID and are freely readable in PMC. NCBI's efetch (db=pmc) serves
# those, so we try it whenever Europe PMC won't give us the XML.
NCBI_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
# NCBI allows 3 requests/s without an API key, 10/s with one.
NCBI_MIN_INTERVAL = 0.11 if NCBI_API_KEY else 0.35
CACHE_NS = "fulltext_v3"
LEGACY_CACHE_NS = "fulltext_v2"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Hard cap on how many full-text fetches we'll do per run. Keeps wall-clock
# bounded even when many papers fail the abstract-only filters.
#
# Was 80, which silently dropped genuinely rescuable papers whose abstract
# lacks quant/kinetic evidence that only appears in a figure/table caption
# (confirmed: a real paper sitting at position 549+ in the needs-rescue list
# was never attempted at all, even though its actual caption text would have
# passed both the quant and kinetic gates). With `needs_captions` routinely
# running into the thousands for a broad step query, 80 covered only a small,
# arbitrarily-ordered slice. Raised substantially so far more candidates get
# a real shot — this does mean more Europe PMC full-text calls per run.
MAX_CAPTION_FETCHES = 10000
# How many full-text downloads to run in parallel against Europe PMC.
CAPTION_CONCURRENCY = 10


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


async def _get_epmc_fulltext(client: httpx.AsyncClient, pmcid: str) -> str:
    """Europe PMC full-text XML, or "" when it isn't in their open-access
    subset. Europe PMC signals that with HTTP 500 (not 404), so a 500 here is
    an expected miss, not a transient error — no retry."""
    r = await client.get(FULLTEXT_URL.format(pmcid=pmcid), timeout=TIMEOUT)
    if r.status_code in (404, 500):
        return ""
    r.raise_for_status()
    return r.text


_ncbi_lock = asyncio.Lock()
_ncbi_last_call = 0.0


async def _ncbi_throttle() -> None:
    global _ncbi_last_call
    async with _ncbi_lock:
        wait = NCBI_MIN_INTERVAL - (time.monotonic() - _ncbi_last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _ncbi_last_call = time.monotonic()


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get_ncbi_fulltext(client: httpx.AsyncClient, pmcid: str) -> str:
    await _ncbi_throttle()
    params = {"db": "pmc", "id": pmcid.removeprefix("PMC"), "rettype": "xml"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    r = await client.get(NCBI_EFETCH_URL, params=params, timeout=TIMEOUT)
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
    # HTTP errors propagate so the caller can skip caching a transient failure.
    data = await _get_json(
        client,
        SEARCH_URL,
        {"query": query, "format": "json", "resultType": "lite", "pageSize": 1},
    )
    hits = (data.get("resultList") or {}).get("result", []) if data else []
    if not hits:
        return None
    pmcid = (hits[0] or {}).get("pmcid")
    return pmcid or None


def _extract_from_xml(xml_text: str) -> dict[str, str]:
    """Pull figure/table captions and supplementary-material text out of a
    JATS full-text XML document.

    Returns {"captions": ..., "supplementary": ...}. Either side can be an
    empty string. Kept separate so the pipeline can attribute *which* type
    of evidence rescued a given paper.
    """
    empty = {"captions": "", "supplementary": ""}
    if not xml_text:
        return empty
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return empty

    caption_parts: list[str] = []
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
                tag_label = "Figure" if tag == "fig" else "Table"
                caption_parts.append(f"{tag_label} caption: {text}")

    suppl_parts: list[str] = []
    for el in root.iter("supplementary-material"):
        # Grab label, caption, and any inline <p> bodies — publishers vary
        # on what they include, so be permissive.
        chunks: list[str] = []
        for sub_tag in ("label", "caption", "p"):
            for sub in el.iter(sub_tag):
                text = " ".join("".join(sub.itertext()).split())
                if text:
                    chunks.append(text)
        if chunks:
            # Deduplicate adjacent repeats (caption often nests <p>).
            seen: set[str] = set()
            uniq = [c for c in chunks if not (c in seen or seen.add(c))]
            suppl_parts.append("Supplementary material: " + " | ".join(uniq))

    return {
        "captions": "\n\n".join(caption_parts),
        "supplementary": "\n\n".join(suppl_parts),
    }


def _cache_key(doi: str | None, pmid: str | None) -> dict[str, str]:
    return {"doi": (doi or "").lower(), "pmid": pmid or ""}


def _as_bundle(cached: Any) -> dict[str, str] | None:
    if isinstance(cached, dict) and "captions" in cached and "supplementary" in cached:
        return {
            "captions": cached.get("captions") or "",
            "supplementary": cached.get("supplementary") or "",
        }
    return None


def _load_cached(doi: str | None, pmid: str | None) -> dict[str, str] | None:
    key = _cache_key(doi, pmid)
    hit = _as_bundle(cache.load(CACHE_NS, key))
    if hit is not None:
        return hit
    # Reuse non-empty results from the pre-NCBI-fallback cache. Empty ones are
    # ignored on purpose: many were author manuscripts Europe PMC refused to
    # serve, which the NCBI fallback can now retrieve.
    legacy = _as_bundle(cache.load(LEGACY_CACHE_NS, key))
    if legacy and (legacy["captions"] or legacy["supplementary"]):
        return legacy
    return None


async def _fetch_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    doi: str | None,
    pmid: str | None,
) -> dict[str, str]:
    cached = _load_cached(doi, pmid)
    if cached is not None:
        return cached

    result = {"captions": "", "supplementary": ""}
    async with sem:
        try:
            pmcid = await _resolve_pmcid(client, doi, pmid)
            if pmcid:
                result = _extract_from_xml(await _get_epmc_fulltext(client, pmcid))
                if not (result["captions"] or result["supplementary"]):
                    result = _extract_from_xml(await _get_ncbi_fulltext(client, pmcid))
        except Exception:  # noqa: BLE001
            # Transient failure (timeout, 5xx, rate limit): don't cache it, or
            # the paper would be marked "no full text" forever. Only genuine
            # misses (no PMCID, 404, unparseable XML) get cached as empty.
            return result
    cache.save(CACHE_NS, _cache_key(doi, pmid), result)
    return result


async def fetch_captions_for(
    papers: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Returns {paper_key: {"captions": ..., "supplementary": ...}}. Either side
    of the inner dict can be empty.

    Papers already in the on-disk cache are always included — a cache hit costs
    nothing, so only papers that need a real network fetch count toward
    MAX_CAPTION_FETCHES. (Previously the cap was applied to the raw list, so a
    paper whose captions were already cached could still be skipped purely
    because of its position in the list.)

    The key matches the value returned by `paper_key(p)` below; callers look
    results up via that helper so the keying logic stays in one place.
    """
    if not papers:
        return {}
    cached: list[dict[str, Any]] = []
    uncached: list[dict[str, Any]] = []
    for p in papers:
        hit = _load_cached(p.get("doi"), p.get("pmid")) is not None
        (cached if hit else uncached).append(p)
    selected = cached + uncached[:MAX_CAPTION_FETCHES]
    sem = asyncio.Semaphore(CAPTION_CONCURRENCY)
    async with httpx.AsyncClient(
        headers={"User-Agent": "lnp-pipeline/1.0"},
    ) as client:
        tasks = [_fetch_one(client, sem, p.get("doi"), p.get("pmid")) for p in selected]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    out: dict[str, dict[str, str]] = {}
    for p, r in zip(selected, results):
        if isinstance(r, Exception):
            continue
        if not isinstance(r, dict):
            continue
        if r.get("captions") or r.get("supplementary"):
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
