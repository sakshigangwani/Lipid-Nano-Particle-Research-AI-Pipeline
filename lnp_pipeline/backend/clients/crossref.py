from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

from ..utils import cache

DB = "crossref"
URL = "https://api.crossref.org/works"
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


def _year_from_item(item: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (ValueError, TypeError):
                continue
    return None


async def search(query: str, max_results: int = 50) -> list[dict[str, Any]]:
    payload = {"q": query, "n": max_results}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(headers={"User-Agent": "lnp-pipeline/1.0 (mailto:research@example.com)"}) as client:
        data = await _get(
            client,
            {
                "query": query,
                "rows": max_results,
                "select": "DOI,title,abstract,author,container-title,issued,published-print,published-online,created",
            },
        )

    items = ((data or {}).get("message") or {}).get("items", [])
    records: list[dict[str, Any]] = []
    for it in items:
        titles = it.get("title") or []
        title = titles[0] if titles else ""
        container = it.get("container-title") or []
        journal = container[0] if container else None
        authors = []
        for a in it.get("author") or []:
            given = a.get("given") or ""
            family = a.get("family") or ""
            name = f"{given} {family}".strip()
            if name:
                authors.append(name)
        abstract = it.get("abstract")
        if isinstance(abstract, str):
            # Crossref abstracts are often JATS-XML wrapped.
            import re

            abstract = re.sub(r"<[^>]+>", " ", abstract)
            abstract = re.sub(r"\s+", " ", abstract).strip()
        records.append(
            {
                "title": (title or "").strip(),
                "abstract": abstract,
                "journal": journal,
                "year": _year_from_item(it),
                "doi": it.get("DOI"),
                "pmid": None,
                "authors": authors,
                "source_dbs": ["CrossRef"],
            }
        )
    cache.save(DB, payload, records)
    return records
