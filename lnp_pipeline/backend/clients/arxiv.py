from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

from ..utils import cache

DB = "arxiv"
URL = "https://export.arxiv.org/api/query"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
ATOM_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

# arXiv's documented hard cap per request; page beyond it with `start`.
PAGE_SIZE = 200
# arXiv asks callers not to hit the API more than once every 3 seconds.
REQUEST_DELAY = 3.0


def _boolean_to_arxiv_query(q: str) -> str:
    """Convert the pipeline's PubMed-style boolean query into arXiv's
    `search_query` syntax.

    Unlike CrossRef or Semantic Scholar, arXiv's API genuinely supports
    parenthesized boolean AND/OR with field-scoped quoted phrases (confirmed
    live: `(all:"a" OR all:"b") AND (all:"c" OR all:"d")` returns a real,
    different result count than either sub-clause alone) — so the query
    structure itself doesn't need to be flattened, just each quoted phrase
    needs an `all:` field prefix, since arXiv has no unscoped free-text term.
    """
    def _quote_with_field(match: "re.Match[str]") -> str:
        phrase = match.group(1)
        return f'all:"{phrase}"'

    return re.sub(r'"([^"]+)"', _quote_with_field, q)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=15),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get_text(client: httpx.AsyncClient, params: dict) -> str:
    r = await client.get(URL, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    return " ".join(el.text.split())


def _parse_entry(entry: ET.Element) -> dict[str, Any]:
    title = _text(entry.find("a:title", ATOM_NS)) or ""
    abstract = _text(entry.find("a:summary", ATOM_NS))
    authors = [
        _text(a.find("a:name", ATOM_NS)) or ""
        for a in entry.findall("a:author", ATOM_NS)
    ]
    authors = [a for a in authors if a]

    published = entry.findtext("a:published", default="", namespaces=ATOM_NS)
    year: int | None = None
    if published[:4].isdigit():
        year = int(published[:4])

    doi = entry.findtext("arxiv:doi", default=None, namespaces=ATOM_NS)
    arxiv_id = entry.findtext("a:id", default="", namespaces=ATOM_NS)

    return {
        "title": title.strip(),
        "abstract": abstract,
        "journal": "arXiv (preprint)",
        "year": year,
        "doi": doi,
        "pmid": None,
        "authors": authors,
        "source_dbs": ["arXiv"],
        "_arxiv_id": arxiv_id,
    }


async def search(query: str) -> list[dict[str, Any]]:
    arxiv_query = _boolean_to_arxiv_query(query)
    payload = {"q": arxiv_query, "n": "all", "v": 1}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    records: list[dict[str, Any]] = []
    start = 0
    async with httpx.AsyncClient(headers={"User-Agent": "lnp-pipeline/1.0"}) as client:
        while True:
            text = await _get_text(
                client,
                {
                    "search_query": arxiv_query,
                    "start": start,
                    "max_results": PAGE_SIZE,
                },
            )
            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                break

            entries = root.findall("a:entry", ATOM_NS)
            if not entries:
                break

            records.extend(_parse_entry(e) for e in entries)

            total_el = root.find(
                "{http://a9.com/-/spec/opensearch/1.1/}totalResults"
            )
            total = int(total_el.text) if total_el is not None and total_el.text else 0
            start += len(entries)
            if start >= total or len(entries) < PAGE_SIZE:
                break

            await asyncio.sleep(REQUEST_DELAY)

    for r in records:
        r.pop("_arxiv_id", None)

    cache.save(DB, payload, records)
    return records
