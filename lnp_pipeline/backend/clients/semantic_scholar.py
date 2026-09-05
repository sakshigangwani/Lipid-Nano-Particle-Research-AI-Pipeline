from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

from ..utils import cache

DB = "semantic_scholar"
URL = "https://api.semanticscholar.org/graph/v1/paper/search"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

FIELDS = "title,abstract,year,authors,externalIds,venue,journal"
# API hard-caps `limit` at 100/request and offset+limit at 1000 total for
# this endpoint; page with offset until either bound is hit.
PAGE_SIZE = 100
MAX_OFFSET = 1000


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=12),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get(client: httpx.AsyncClient, params: dict) -> dict:
    r = await client.get(URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


async def search(query: str) -> list[dict[str, Any]]:
    payload = {"q": query, "n": "all"}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    headers = {"User-Agent": "lnp-pipeline/1.0"}
    items: list[dict] = []
    offset = 0
    async with httpx.AsyncClient(headers=headers) as client:
        while offset < MAX_OFFSET:
            try:
                data = await _get(
                    client,
                    {
                        "query": query,
                        "limit": PAGE_SIZE,
                        "offset": offset,
                        "fields": FIELDS,
                    },
                )
            except httpx.HTTPError:
                # Semantic Scholar rate-limits aggressively; keep whatever we
                # already collected rather than failing the whole run.
                break
            page = data.get("data", []) if data else []
            if not page:
                break
            items.extend(page)
            offset += len(page)
            total = (data or {}).get("total")
            if isinstance(total, int) and offset >= total:
                break

    records: list[dict[str, Any]] = []
    for it in items:
        authors = [a.get("name") for a in (it.get("authors") or []) if a.get("name")]
        ext = it.get("externalIds") or {}
        journal_field = it.get("journal") or {}
        journal_name = (
            journal_field.get("name") if isinstance(journal_field, dict) else None
        ) or it.get("venue")
        records.append(
            {
                "title": (it.get("title") or "").strip(),
                "abstract": it.get("abstract"),
                "journal": journal_name,
                "year": it.get("year"),
                "doi": ext.get("DOI"),
                "pmid": ext.get("PubMed"),
                "authors": authors,
                "source_dbs": ["Semantic Scholar"],
            }
        )
    cache.save(DB, payload, records)
    return records
