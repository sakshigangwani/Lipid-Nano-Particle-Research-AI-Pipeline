from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

from ..utils import cache

DB = "europepmc"
URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get(client: httpx.AsyncClient, params: dict) -> dict:
    r = await client.get(URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


async def search(query: str, max_results: int = 50) -> list[dict[str, Any]]:
    payload = {"q": query, "n": max_results}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(headers={"User-Agent": "lnp-pipeline/1.0"}) as client:
        data = await _get(
            client,
            {
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": max_results,
            },
        )

    hits = (data.get("resultList") or {}).get("result", []) if data else []
    records: list[dict[str, Any]] = []
    for h in hits:
        authors_str = h.get("authorString") or ""
        authors = [a.strip() for a in authors_str.split(",") if a.strip()]
        try:
            year = int(h.get("pubYear")) if h.get("pubYear") else None
        except (ValueError, TypeError):
            year = None
        records.append(
            {
                "title": (h.get("title") or "").strip(),
                "abstract": h.get("abstractText"),
                "journal": h.get("journalTitle"),
                "year": year,
                "doi": h.get("doi"),
                "pmid": h.get("pmid"),
                "authors": authors,
                "source_dbs": ["Europe PMC"],
            }
        )
    cache.save(DB, payload, records)
    return records
