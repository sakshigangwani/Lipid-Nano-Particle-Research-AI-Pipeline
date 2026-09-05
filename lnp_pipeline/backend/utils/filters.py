from __future__ import annotations

import re

QUANT_REGEXES: list[re.Pattern] = [
    re.compile(r"\b\d+(?:\.\d+)?\s?%", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:nm|nM|µM|uM|mM|µg|ug|mg|ng|pg|kDa|Da)\b"),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:fold|-fold)\b", re.IGNORECASE),
    re.compile(r"\bIC50\b|\bEC50\b|\bKd\b|\bKa\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:particles|molecules|copies)\s?/\s?cell\b", re.IGNORECASE),
    re.compile(r"\bp\s?[<>=]\s?0?\.\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s?±\s?\d+(?:\.\d+)?\b"),
]

KINETIC_REGEXES: list[re.Pattern] = [
    re.compile(r"\bt[\s\-]?1/2\b|\bhalf[-\s]?life\b", re.IGNORECASE),
    re.compile(r"\brate\s+constant\b|\bk\s?on\b|\bk\s?off\b", re.IGNORECASE),
    re.compile(r"\btime[-\s]?(?:course|dependent|resolved|lapse)\b", re.IGNORECASE),
    re.compile(r"\bkinetics?\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:s|sec|min|h|hr|hour|hours|day|days)\b"),
    re.compile(r"\bAUC\b|\bclearance\b|\bplasma half[-\s]?life\b", re.IGNORECASE),
    re.compile(r"\bover\s+time\b|\bas\s+a\s+function\s+of\s+time\b", re.IGNORECASE),
]


def _scan(text: str, patterns: list[re.Pattern]) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        for m in pat.finditer(text):
            token = m.group(0).strip()
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(token)
    return found


def _scan_keywords(text: str, keywords: list[str]) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        key = kw.lower()
        if key in seen:
            continue
        if key in lowered:
            seen.add(key)
            found.append(kw)
    return found


def find_quant_matches(text: str, extra_keywords: list[str] | None = None) -> list[str]:
    matches = _scan(text or "", QUANT_REGEXES)
    if extra_keywords:
        matches += [m for m in _scan_keywords(text or "", extra_keywords) if m not in matches]
    return matches


def find_kinetic_matches(text: str, extra_keywords: list[str] | None = None) -> list[str]:
    matches = _scan(text or "", KINETIC_REGEXES)
    if extra_keywords:
        matches += [m for m in _scan_keywords(text or "", extra_keywords) if m not in matches]
    return matches


def find_signal_phrases(text: str, phrases: list[str]) -> list[str]:
    return _scan_keywords(text or "", phrases)


LNP_FOCUS_REGEXES: list[re.Pattern] = [
    # "lipid nanoparticle(s)" / "lipid-nanoparticle" / "lipid nano-particle" / "lipidnanoparticle",
    # optionally with an inserted qualifier like "mRNA-" or "siRNA-" in either order,
    # e.g. "lipid-mRNA nanoparticle", "mRNA-lipid nanoparticle", "ionizable lipid nanoparticles".
    re.compile(
        r"\b(?:ionizable|ionisable)?[\s-]*"
        r"(?:lipid[\s-]*(?:m?rna|si[\s-]?rna)?[\s-]*|(?:m?rna|si[\s-]?rna)[\s-]*lipid[\s-]*)"
        r"nano[\s-]*particles?\b",
        re.IGNORECASE,
    ),
    # Bare "LNP"/"LNPs" as a standalone token, regardless of surrounding punctuation
    # (e.g. "LNPs,", "(LNP)", "LNP-mediated", "mRNA-LNP").
    re.compile(r"(?<![A-Za-z])LNPs?(?![A-Za-z])"),
    re.compile(r"\bionizable lipid\b|\bionisable lipid\b", re.IGNORECASE),
]


def is_lnp_focused(text: str) -> bool:
    """Sanity filter — paper must clearly be about LNPs, not another nanoparticle system."""
    if not text:
        return False
    return any(pat.search(text) for pat in LNP_FOCUS_REGEXES)
