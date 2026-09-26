from __future__ import annotations

import asyncio
import re
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
# CrossRef's free-text `query.bibliographic` has no real precision (confirmed
# live: quotes/AND/OR are not honored, it's pure token relevance ranking), so
# a query built from common biomedical terms can match millions of records.
# Relevance score drops off fast — records past the first few thousand are
# essentially noise — so we sort by relevance and stop well short of trying
# to page through the entire match set, which would otherwise never finish
# in practice for a broad query.
MAX_RECORDS = 5000
# CrossRef's "polite pool" (much higher rate limits, ~3 req/s vs. the strict
# anonymous pool) is granted based on a `mailto` QUERY PARAMETER, not just a
# mailto in the User-Agent string — without it, requests land in the public
# pool and get hard 429'd (confirmed live: identical request with `mailto` in
# the query got x-rate-limit-limit: 3 / x-api-pool: polite-array; without it,
# 429 with no body or rate-limit headers at all).
POLITE_MAILTO = "gangwani.sakshi15@gmail.com"


def _boolean_to_bibliographic_query(q: str) -> str:
    """Convert a PubMed-style boolean query into terms for CrossRef's
    `query.bibliographic` field.

    CrossRef's REST API documents no boolean operators at all (confirmed via
    the official rest-api-doc README): `query`/`query.bibliographic` are pure
    relevance-ranked free-text token matching, and quotes/AND/OR in the string
    are not honored as operators — they're just more tokens diluting the
    match. Separate `query.X` parameters DO get ANDed together server-side,
    but there's only one bibliographic field to put terms in here.

    So, same approach as OpenAlex's adapter: take the first (most specific)
    quoted phrase from each AND-group and join them as plain terms — this
    biases the free-text ranking toward records containing the query's most
    distinctive phrases, instead of every OR-alternative across all groups
    diluting the match evenly.
    """
    parts = re.split(r"\bAND\b", q)
    out: list[str] = []
    for part in parts:
        part = part.strip().strip("()").strip()
        if not part:
            continue
        first = re.split(r"\bOR\b", part)[0].strip()
        first = first.strip('"').strip()
        if first:
            out.append(first)
    return " ".join(out)


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=30),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get(client: httpx.AsyncClient, params: dict) -> dict:
    r = await client.get(URL, params={**params, "mailto": POLITE_MAILTO}, timeout=TIMEOUT)
    if r.status_code == 429:
        # CrossRef doesn't always send Retry-After, but honor it when present
        # instead of relying solely on tenacity's generic backoff.
        retry_after = r.headers.get("Retry-After")
        if retry_after:
            try:
                await asyncio.sleep(float(retry_after))
            except ValueError:
                pass
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
    bibliographic_query = _boolean_to_bibliographic_query(query)
    payload = {"q": bibliographic_query, "n": "all", "v": 2}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    select = "DOI,title,abstract,author,container-title,issued,published-print,published-online,created"
    items: list[dict] = []
    # Track whether any page ever came back successfully. A failure on the
    # very first page (rate-limited, outage, etc.) must not be cached as a
    # genuine "zero results" — that would poison every future run with a
    # false empty result for this query, even after the outage passes.
    fetched_anything = False
    async with httpx.AsyncClient(
        headers={"User-Agent": f"lnp-pipeline/1.0 (mailto:{POLITE_MAILTO})"}
    ) as client:
        cursor = "*"
        while cursor and len(items) < MAX_RECORDS:
            page_size = min(PAGE_SIZE, MAX_RECORDS - len(items))
            try:
                data = await _get(
                    client,
                    {
                        "query.bibliographic": bibliographic_query,
                        "rows": page_size,
                        "cursor": cursor,
                        "select": select,
                        "sort": "relevance",
                        "order": "desc",
                    },
                )
            except httpx.HTTPError:
                # A later page failing (e.g. rate-limited mid-pagination)
                # shouldn't discard pages already fetched — return what we
                # have rather than losing it all to the caller's blanket
                # except-and-treat-as-empty handling.
                break
            fetched_anything = True
            message = (data or {}).get("message") or {}
            page = message.get("items") or []
            if not page:
                break
            items.extend(page)
            next_cursor = message.get("next-cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

    if not fetched_anything:
        return []

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
