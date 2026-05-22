from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    s = doi.strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = s.strip()
    return s or None


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def dedup_papers(papers: list[dict]) -> list[dict]:
    """Merge papers by DOI (primary) or normalized title (fallback).

    `source_dbs` lists from duplicates are unioned; richer fields win.
    """
    by_doi: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    out: list[dict] = []

    def merge(existing: dict, new: dict) -> dict:
        for key in ("abstract", "journal", "year", "pmid", "doi"):
            if not existing.get(key) and new.get(key):
                existing[key] = new[key]
        if len(new.get("authors") or []) > len(existing.get("authors") or []):
            existing["authors"] = new["authors"]
        existing_dbs = set(existing.get("source_dbs") or [])
        existing_dbs.update(new.get("source_dbs") or [])
        existing["source_dbs"] = sorted(existing_dbs)
        return existing

    for p in papers:
        doi = normalize_doi(p.get("doi"))
        if doi:
            p["doi"] = doi
            if doi in by_doi:
                merge(by_doi[doi], p)
                continue
            by_doi[doi] = p
            out.append(p)
            continue

        nt = normalize_title(p.get("title"))
        if nt and nt in by_title:
            merge(by_title[nt], p)
            continue
        if nt:
            by_title[nt] = p
        out.append(p)

    return out
