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

DB = "openalex"
URL = "https://api.openalex.org/works"
TIMEOUT = httpx.Timeout(45.0, connect=10.0)
# OpenAlex caps per-page at 200; we paginate via cursor for larger pulls.
PER_PAGE = 200
SELECT_FIELDS = (
    "id,doi,title,abstract_inverted_index,authorships,"
    "publication_year,primary_location,ids"
)


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


def _boolean_to_phrase_search(q: str) -> str:
    """Convert a PubMed-style Boolean query into something OpenAlex's `search`
    parameter can actually use.

    Confirmed empirically (not documented): OpenAlex's `search` has NO OR
    operator at all. Every quoted phrase or bare word added to the query
    becomes its own required AND-filter under the hood — 2 phrases matched
    ~19,900 works, adding a 3rd dropped it to ~700, a 4th to ~50. An earlier
    version of this function tried to preserve every OR-alternative from the
    boolean query (e.g. all of "lipid nanoparticle"/"LNP"/"LNPs"/...), which
    only made this worse: stacking ~18 required terms drove real queries to
    zero results.

    So, same constraint as CrossRef's adapter: take exactly one alternative
    per AND-group. Within a group we prefer the shortest *bare* (unquoted,
    single-word) alternative when one exists — e.g. bare "LNP" over
    "lipid nanoparticle" — since a shorter, more common term is a less
    restrictive required filter and yields more matches.

        ("lipid nanoparticle" OR "LNP") AND ("cellular uptake" OR "internalization")
        → LNP "cellular uptake"
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


def _reconstruct_abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pairs: list[tuple[int, str]] = []
    for word, positions in inv.items():
        for p in positions:
            pairs.append((p, word))
    if not pairs:
        return None
    pairs.sort(key=lambda t: t[0])
    return " ".join(w for _, w in pairs)


def _author_names(authorships: list[dict] | None) -> list[str]:
    out: list[str] = []
    for a in authorships or []:
        name = ((a or {}).get("author") or {}).get("display_name")
        if name:
            out.append(name)
    return out


def _convert(w: dict) -> dict[str, Any]:
    doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
    journal = None
    prim = (w.get("primary_location") or {}).get("source") or {}
    if prim.get("display_name"):
        journal = prim.get("display_name")
    pmid = (w.get("ids") or {}).get("pmid") or ""
    pmid = pmid.rsplit("/", 1)[-1] if pmid else None
    return {
        "title": (w.get("title") or "").strip(),
        "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
        "journal": journal,
        "year": w.get("publication_year"),
        "doi": doi,
        "pmid": pmid,
        "authors": _author_names(w.get("authorships")),
        "source_dbs": ["OpenAlex"],
    }


async def search(query: str) -> list[dict[str, Any]]:
    phrase_query = _boolean_to_phrase_search(query)
    payload = {"q": phrase_query, "n": "all", "v": 2}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    records: list[dict[str, Any]] = []
    cursor: str | None = "*"

    async with httpx.AsyncClient(
        headers={"User-Agent": "lnp-pipeline/1.0 (mailto:lnp-pipeline@local)"},
    ) as client:
        while cursor:
            data = await _get(
                client,
                {
                    "search": phrase_query,
                    "per-page": PER_PAGE,
                    "cursor": cursor,
                    "select": SELECT_FIELDS,
                },
            )
            page = data.get("results") or []
            if not page:
                break
            records.extend(_convert(w) for w in page)
            cursor = ((data.get("meta") or {}).get("next_cursor")) or None

    cache.save(DB, payload, records)
    return records
