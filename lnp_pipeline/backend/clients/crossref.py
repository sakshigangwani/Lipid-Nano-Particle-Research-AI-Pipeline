from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

from ..utils import cache

DB = "crossref"
URL = "https://api.crossref.org/works"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# CrossRef's hard per-request cap on `rows`; page beyond it with a deep-paging
# cursor (offset pagination is capped around 10k by the API).
PAGE_SIZE = 1000


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


async def search(query: str) -> list[dict[str, Any]]:
    payload = {"q": query, "n": "all"}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    select = "DOI,title,abstract,author,container-title,issued,published-print,published-online,created"
    items: list[dict] = []
    async with httpx.AsyncClient(headers={"User-Agent": "lnp-pipeline/1.0 (mailto:research@example.com)"}) as client:
        cursor = "*"
        while cursor:
            data = await _get(
                client,
                {
                    "query": query,
                    "rows": PAGE_SIZE,
                    "cursor": cursor,
                    "select": select,
                },
            )
            message = (data or {}).get("message") or {}
            page = message.get("items") or []
            if not page:
                break
            items.extend(page)
            next_cursor = message.get("next-cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

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
