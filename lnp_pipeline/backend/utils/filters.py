from __future__ import annotations

import re

KINETIC_REGEXES: list[re.Pattern] = [
    re.compile(r"\bt[\s\-]?1/2\b|\bhalf[-\s]?life\b", re.IGNORECASE),
    re.compile(r"\brate\s+constant\b|\bk\s?on\b|\bk\s?off\b", re.IGNORECASE),
    re.compile(r"\btime[-\s]?(?:course|dependent|resolved|lapse)\b", re.IGNORECASE),
    # No leading \b: must also match compounds like "pharmacokinetics",
    # "toxicokinetics" ("cellular pharmacokinetics" is a common way uptake
    # papers describe time-resolved uptake/release measurements).
    re.compile(r"kinetics?\b|kinetically\b", re.IGNORECASE),
    # Numeric durations. Allows a hyphen ("24-h incubation", "10-min"), full
    # and plural unit words ("10 minutes", "48 hrs"), and weeks/months.
    re.compile(
        r"\b\d+(?:\.\d+)?\s?-?\s?(?:s|secs?|seconds?|min|mins|minutes?|h|hrs?|hours?|"
        r"days?|wks?|weeks?|months?)\b",
        re.IGNORECASE,
    ),
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


# A reported quantitative result: "3-fold", "65%", "2.5 fold".
_QUANT_RESULT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:-?\s?fold\b|%)", re.IGNORECASE)


# Words indicating the topic was actually measured/studied, not just mentioned
# in passing ("...was not due to impaired cellular uptake" after mechanistic
# studies, "uptake was assessed by flow cytometry").
_MEASUREMENT_CUE_RE = re.compile(
    r"flow\s+cytometr|confocal|microscop|measur|assess|quantif|evaluat|examin|"
    r"investigat|analy[sz]|reveal|track|monitor|determin",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def reports_topic_measurement(text: str, topic_patterns: list[re.Pattern]) -> bool:
    """True if the text shows the step's topic was actually measured: either it
    mentions the topic and reports a numeric result (fold-change or %), or a
    single sentence pairs the topic with a measurement word. Used to decide
    whether a paper whose abstract lacks kinetic wording is still worth an LLM
    look when its full text can't be checked."""
    if not text or not any(p.search(text) for p in topic_patterns):
        return False
    if _QUANT_RESULT_RE.search(text):
        return True
    return any(
        _MEASUREMENT_CUE_RE.search(s) and any(p.search(s) for p in topic_patterns)
        for s in _SENTENCE_SPLIT_RE.split(text)
    )


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


# Study-type classification (separate from the in_vitro_only gate above, which
# is deliberately aggressive). Here "mouse"/"murine"/"rat" alone don't count as
# in vivo — they routinely describe cell sources ("murine macrophage cell line
# RAW 264.7", "mouse BMDCs") — only plural animal subjects, dosing routes and
# explicit in vivo wording do.
_STUDY_IN_VIVO_REGEXES: list[re.Pattern] = [
    re.compile(
        r"\b(?:in[\s-]vivo|mice|rats|rabbits|pigs|dogs|animals?\s+models?|"
        r"non[\s-]?human\s+primates?|nhps?|macaques?|zebrafish|xenografts?|"
        r"tumou?r[\s-]bearing|biodistribution|clinical\s+trials?|patients|"
        r"healthy\s+volunteers|participants)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:intravenous(?:ly)?|intramuscular(?:ly)?|intratumou?ral(?:ly)?|"
        r"intraperitoneal(?:ly)?|subcutaneous(?:ly)?|intranasal(?:ly)?|"
        r"intradermal(?:ly)?|intratracheal(?:ly)?|i\.v\.|i\.m\.|i\.p\.|s\.c\.|"
        r"tail[\s-]vein|\d+(?:\.\d+)?\s?mg\s?/\s?kg)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:mouse|murine|rat|rodent|animal|porcine|primate)\s+models?|"
        r"orthotopic|tumou?r\s+(?:growth|regression|inhibition)|"
        r"survival\s+(?:rate|time|benefit)|systemic(?:ally)?\s+administ\w*)\b",
        re.IGNORECASE,
    ),
]

_STUDY_IN_VITRO_REGEXES: list[re.Pattern] = [
    re.compile(
        r"\b(?:in[\s-]vitro|ex[\s-]vivo|cell[\s-]?lines?|cultured\s+(?:cells?|\w+\s+cells?)|"
        r"cell\s+cultures?|primary\s+(?:human\s+|murine\s+|mouse\s+)?"
        r"(?:cells?|hepatocytes|macrophages|t[\s-]cells|neurons)|transfected\s+cells|"
        r"organoids?|spheroids?|(?:human\s+)?(?:plasma|serum)\s+incubation|"
        r"incubat\w*\s+(?:in|with)\s+(?:human\s+|mouse\s+|fetal\s+bovine\s+)?(?:plasma|serum))\b",
        re.IGNORECASE,
    ),
    # Cell-level assays and readouts.
    re.compile(
        r"\b(?:bone[\s-]marrow[\s-]derived|(?:macrophage|cellular|cell)\s+uptake|"
        r"uptake\s+(?:by|in|into)\s+(?:\w+\s+){0,2}cells|transfection\s+efficiency|"
        r"cytotoxicity|cell\s+viability|mtt|cck[\s-]?8|flow\s+cytometry|"
        r"confocal|live[\s-]cell\s+imaging)\b",
        re.IGNORECASE,
    ),
    # Common named cell lines in LNP work.
    re.compile(
        r"\b(?:hela|hek[\s-]?293t?|hepg2|huh[\s-]?7|a549|raw\s?264\.7|jurkat|dc2\.4|"
        r"thp[\s-]?1|mcf[\s-]?7|caco[\s-]?2|cho(?:[\s-]k1)?\s+cells|bmdcs?|bmdms?|"
        r"ipscs?|huvecs?|b16(?:[\s-]?f10)?|ct26|4t1|nih[\s-]?3t3|vero)\b",
        re.IGNORECASE,
    ),
]

def classify_study_type(text: str) -> str:
    """Classify text as "in_vitro", "in_vivo", "both" or "unclassified"."""
    if not text:
        return "unclassified"
    vivo = any(p.search(text) for p in _STUDY_IN_VIVO_REGEXES)
    vitro = any(p.search(text) for p in _STUDY_IN_VITRO_REGEXES)
    if vivo and vitro:
        return "both"
    if vivo:
        return "in_vivo"
    if vitro:
        return "in_vitro"
    return "unclassified"


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
