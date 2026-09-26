from __future__ import annotations

import asyncio
import re
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

# Semantic Scholar's unauthenticated tier shares a small global rate-limit
# pool (roughly 100 req/5min across ALL unauthenticated traffic), so 429s are
# routine, not exceptional. A 429 here means "wait", not "give up" — retry
# with real backoff, honoring Retry-After when the API sends one, instead of
# abandoning the whole search on the first hit.
MAX_429_RETRIES = 6
DEFAULT_429_BACKOFF = 10.0
MAX_429_BACKOFF = 60.0


def _boolean_to_quoted_terms(q: str) -> str:
    """Convert a PubMed-style boolean query into Semantic Scholar's syntax.

    Confirmed empirically (not documented, and contrary to what Semantic
    Scholar's FAQ implies about free-text relevance ranking): the /paper/search
    endpoint's `query` behaves like an AND-of-everything filter once enough
    terms are added, the same failure mode measured directly against
    OpenAlex's `search` param. A 2-phrase query ("lipid nanoparticle"
    "cellular uptake") matched ~28,600 works; the 9-term version this step
    actually used in production matched only 66 — collapsing >400x, not
    healthy relevance-ranking behavior. Stacking every OR-alternative (the
    previous approach here) therefore makes results worse, not better.

    So, same fix as OpenAlex's adapter: take exactly one alternative per
    AND-group, preferring the shortest bare (unquoted, single-word)
    alternative when one exists, since it's a less restrictive required term.
    """
    parts = re.split(r"\bAND\b", q)
    out: list[str] = []
    for part in parts:
        part = part.strip().strip("()").strip()
        if not part:
            continue
        alternatives = [
            alt.strip().strip("()").strip('"').strip()
            for alt in re.split(r"\bOR\b", part)
        ]
        alternatives = [a for a in alternatives if a]
        if not alternatives:
            continue
        bare_single_word = [a for a in alternatives if " " not in a]
        chosen = min(bare_single_word, key=len) if bare_single_word else alternatives[0]
        out.append(f'"{chosen}"' if " " in chosen else chosen)
    return " ".join(out)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=12),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get_once(client: httpx.AsyncClient, params: dict) -> httpx.Response:
    r = await client.get(URL, params=params, timeout=TIMEOUT)
    if r.status_code != 429:
        r.raise_for_status()
    return r


async def _get(client: httpx.AsyncClient, params: dict) -> dict:
    """Fetch one page, retrying on 429 with backoff instead of bailing out.

    A 429 is not a `raise_for_status()` error here — it's handled explicitly
    so we can sleep and retry the *whole* request rather than letting
    tenacity's short 3-attempt/12s-cap retry (meant for transient network
    errors) exhaust itself against a rate limit that often needs 10-60s.
    """
    backoff = DEFAULT_429_BACKOFF
    for attempt in range(MAX_429_RETRIES):
        r = await _get_once(client, params)
        if r.status_code != 429:
            return r.json()
        retry_after = r.headers.get("Retry-After")
        try:
            wait_s = float(retry_after) if retry_after else backoff
        except ValueError:
            wait_s = backoff
        if attempt < MAX_429_RETRIES - 1:
            await asyncio.sleep(min(wait_s, MAX_429_BACKOFF))
            backoff = min(backoff * 1.5, MAX_429_BACKOFF)
    r.raise_for_status()
    return r.json()


async def search(query: str) -> list[dict[str, Any]]:
    s2_query = _boolean_to_quoted_terms(query)
    payload = {"q": s2_query, "n": "all", "v": 2}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    headers = {"User-Agent": "lnp-pipeline/1.0"}
    items: list[dict] = []
    offset = 0
    # Track whether we ever got a real response, vs. failing before the first
    # page even came back. A first-page failure means "we don't know" — that
    # must never be cached as "zero results", or every later run replays the
    # same false zero forever instead of getting a fresh attempt.
    fetched_anything = False
    async with httpx.AsyncClient(headers=headers) as client:
        while offset < MAX_OFFSET:
            try:
                data = await _get(
                    client,
                    {
                        "query": s2_query,
                        "limit": PAGE_SIZE,
                        "offset": offset,
                        "fields": FIELDS,
                    },
                )
            except httpx.HTTPError:
                # Semantic Scholar rate-limits aggressively even after our
                # own retry/backoff in _get; keep whatever we already
                # collected rather than failing the whole run.
                break
            fetched_anything = True
            page = data.get("data", []) if data else []
            if not page:
                break
            items.extend(page)
            offset += len(page)
            total = (data or {}).get("total")
            if isinstance(total, int) and offset >= total:
                break

    if not fetched_anything:
        # Every attempt failed before a single page came back — this is an
        # outage/rate-limit, not a genuine zero-result search. Don't cache it.
        return []

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
