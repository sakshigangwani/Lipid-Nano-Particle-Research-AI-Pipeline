from __future__ import annotations

import re

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
    # "Lipoplex(es)" — a related lipid-nucleic acid particle class (often
    # cationic-lipid based, historically the precursor term to modern
    # ionizable-lipid LNPs). Papers using this term instead of "LNP"/"lipid
    # nanoparticle" were previously invisible to every step's query and this
    # focus check (confirmed: a real paper on lipoplex-delivered mRNA uptake
    # scored 0 hits everywhere despite being squarely on-topic).
    re.compile(r"\blipoplex(?:es)?\b", re.IGNORECASE),
]


def is_lnp_focused(text: str) -> bool:
    """Sanity filter — paper must clearly be about LNPs, not another nanoparticle system."""
    if not text:
        return False
    return any(pat.search(text) for pat in LNP_FOCUS_REGEXES)


IN_VIVO_REGEXES: list[re.Pattern] = [
    # Animal models / whole-organism studies.
    re.compile(
        r"\b(?:mice|mouse|murine|rats?|rodents?|rabbits?|"
        r"non[\s-]?human primates?|nhp|zebrafish|xenograft|"
        r"in[\s-]vivo)\b",
        re.IGNORECASE,
    ),
    # Whole-animal dosing/administration routes, distinct from cell-culture
    # dosing (e.g. "treated with 10 nM" in vitro vs. "administered 1 mg/kg").
    re.compile(
        r"\b(?:intravenous(?:ly)?|intramuscular(?:ly)?|intratumoral(?:ly)?|"
        r"intraperitoneal(?:ly)?|subcutaneous(?:ly)?|"
        r"\d+(?:\.\d+)?\s?mg\s?/\s?kg)\b",
        re.IGNORECASE,
    ),
]

IN_VITRO_REGEXES: list[re.Pattern] = [
    re.compile(
        r"\b(?:in[\s-]vitro|cell\s?line|cultured\s+cells?|"
        r"hela|hek293|cho\s+cells?|primary\s+cells?)\b",
        re.IGNORECASE,
    ),
]


def has_in_vivo_markers(text: str) -> bool:
    """True if the text describes whole-animal / in vivo work."""
    if not text:
        return False
    return any(pat.search(text) for pat in IN_VIVO_REGEXES)


def has_in_vitro_markers(text: str) -> bool:
    """True if the text describes cell-culture / in vitro work."""
    if not text:
        return False
    return any(pat.search(text) for pat in IN_VITRO_REGEXES)


REVIEW_REGEXES: list[re.Pattern] = [
    # Title-level review markers ("...: A Review", "Review of...", etc.).
    re.compile(r"\breview\b", re.IGNORECASE),
    re.compile(r"\bcurrent\s+(?:knowledge|understanding|perspectives?|challenges)\b", re.IGNORECASE),
    re.compile(r"\bwe\s+(?:review|evaluate\s+current|summarize|discuss\s+current)\b", re.IGNORECASE),
    re.compile(r"\bthis\s+review\b", re.IGNORECASE),
    re.compile(r"\blessons\s+from\b", re.IGNORECASE),
]


def is_review_article(text: str) -> bool:
    """Best-effort detector for review/perspective articles (as opposed to
    primary research with original experimental data). None of our source
    APIs reliably expose an article-type field, so this leans on title and
    framing-language cues instead. Used to relax the kinetic/primary-data
    requirement for reviews, which by nature summarize others' data rather
    than reporting their own — a review can still be a genuinely useful,
    on-topic result even with zero kinetic terms of its own.
    """
    if not text:
        return False
    return any(pat.search(text) for pat in REVIEW_REGEXES)
