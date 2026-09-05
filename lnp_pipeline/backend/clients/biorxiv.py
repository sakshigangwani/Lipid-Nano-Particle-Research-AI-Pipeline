from __future__ import annotations

import re
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ..utils import cache

DB = "biorxiv"
# Europe PMC's preprint index already covers bioRxiv + medRxiv and supports the
# same Boolean syntax as the regular Europe PMC search, so we reuse it but force
# SRC:PPR (preprints only) and split bioRxiv vs medRxiv via the journal field.
URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# Europe PMC's hard per-request cap; page beyond it via cursorMark.
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


async def _fetch_all_hits(client: httpx.AsyncClient, query: str) -> list[dict]:
    hits: list[dict] = []
    cursor = "*"
    while cursor:
        data = await _get(
            client,
            {
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": PAGE_SIZE,
                "cursorMark": cursor,
            },
        )
        result_list = (data.get("resultList") or {}) if data else {}
        page = result_list.get("result", [])
        if not page:
            break
        hits.extend(page)
        next_cursor = (data or {}).get("nextCursorMark")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return hits


def _is_biorxiv_or_medrxiv(hit: dict) -> bool:
    src = (hit.get("source") or "").upper()
    if src == "PPR":
        # Europe PMC PPR entries cover many preprint servers; restrict to
        # bioRxiv/medRxiv by the bookSeries/journalTitle/abstract markers.
        journal = (hit.get("journalTitle") or hit.get("bookOrReportDetails", {}).get("publisher") or "").lower()
        if "biorxiv" in journal or "medrxiv" in journal:
            return True
        # Fall back to DOI prefix: 10.1101 is Cold Spring Harbor (bioRxiv/medRxiv).
        doi = (hit.get("doi") or "").lower()
        if doi.startswith("10.1101/"):
            return True
    return False


async def search(query: str) -> list[dict[str, Any]]:
    payload = {"q": query, "n": "all"}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    # Constrain to preprints (source PPR) so we don't double-count Europe PMC.
    scoped_query = f"({query}) AND SRC:PPR"

    async with httpx.AsyncClient(headers={"User-Agent": "lnp-pipeline/1.0"}) as client:
        hits = await _fetch_all_hits(client, scoped_query)

    records: list[dict[str, Any]] = []
    for h in hits:
        if not _is_biorxiv_or_medrxiv(h):
            continue
        authors_str = h.get("authorString") or ""
        authors = [a.strip() for a in authors_str.split(",") if a.strip()]
        try:
            year = int(h.get("pubYear")) if h.get("pubYear") else None
        except (ValueError, TypeError):
            year = None
        doi = (h.get("doi") or "") or None
        journal = h.get("journalTitle")
        if not journal and doi and doi.lower().startswith("10.1101/"):
            journal = "bioRxiv / medRxiv"
        records.append(
            {
                "title": (h.get("title") or "").strip(),
                "abstract": h.get("abstractText"),
                "journal": journal,
                "year": year,
                "doi": doi,
                "pmid": h.get("pmid"),
                "authors": authors,
                "source_dbs": ["bioRxiv/medRxiv"],
            }
        )
    cache.save(DB, payload, records)
    return records
