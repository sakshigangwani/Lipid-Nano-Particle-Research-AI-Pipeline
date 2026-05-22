from __future__ import annotations

import asyncio
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

from ..utils import cache

DB = "pubmed"
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


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


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _get_text(client: httpx.AsyncClient, url: str, params: dict) -> str:
    r = await client.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def _parse_pubmed_xml(xml_text: str) -> list[dict[str, Any]]:
    # Minimal XML parsing; avoid heavy deps.
    import xml.etree.ElementTree as ET

    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out

    for art in root.findall(".//PubmedArticle"):
        title_el = art.find(".//ArticleTitle")
        abstract_parts = [
            (e.text or "") for e in art.findall(".//Abstract/AbstractText")
        ]
        abstract = " ".join(p for p in abstract_parts if p).strip() or None
        journal = art.findtext(".//Journal/Title")
        year_text = art.findtext(".//JournalIssue/PubDate/Year") or art.findtext(
            ".//PubDate/Year"
        )
        try:
            year = int(year_text) if year_text else None
        except ValueError:
            year = None
        pmid = art.findtext(".//PMID")
        doi = None
        for aid in art.findall(".//ArticleId"):
            if aid.attrib.get("IdType") == "doi":
                doi = aid.text
                break
        if not doi:
            for eid in art.findall(".//ELocationID"):
                if eid.attrib.get("EIdType") == "doi":
                    doi = eid.text
                    break

        authors: list[str] = []
        for au in art.findall(".//AuthorList/Author"):
            last = au.findtext("LastName") or ""
            fore = au.findtext("ForeName") or au.findtext("Initials") or ""
            name = (f"{fore} {last}").strip()
            if name:
                authors.append(name)

        out.append(
            {
                "title": (title_el.text or "").strip() if title_el is not None else "",
                "abstract": abstract,
                "journal": journal,
                "year": year,
                "doi": doi,
                "pmid": pmid,
                "authors": authors,
                "source_dbs": ["PubMed"],
            }
        )
    return out


async def search(query: str, max_results: int = 50) -> list[dict[str, Any]]:
    payload = {"q": query, "n": max_results}
    cached = cache.load(DB, payload)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(headers={"User-Agent": "lnp-pipeline/1.0"}) as client:
        esearch = await _get_json(
            client,
            ESEARCH,
            {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": max_results,
                "sort": "relevance",
            },
        )
        ids = (
            esearch.get("esearchresult", {}).get("idlist", []) if esearch else []
        )
        if not ids:
            cache.save(DB, payload, [])
            return []

        # Be polite to NCBI rate limits.
        await asyncio.sleep(0.2)
        xml_text = await _get_text(
            client,
            EFETCH,
            {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
        )

    records = _parse_pubmed_xml(xml_text)
    cache.save(DB, payload, records)
    return records
