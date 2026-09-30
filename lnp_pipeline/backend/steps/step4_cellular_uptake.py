from __future__ import annotations

import re

from ._base import ProgressCb, run_step_search

STEP_META = {
    "id": 4,
    "name": "Cellular uptake",
    "description": "Quantity and rate of LNP uptake by cells. Requires time-course + a quant metric + imaging/flow method.",
    "strict_kinetic": True,
    "in_vitro_only": False,
}

KEYWORDS = [
    "cellular uptake",
    "internalization",
    "endocytosis",
    "kinetics",
    "time course",
    "time-dependent",
    "time-resolved",
    "rate constant",
    "flow cytometry",
    "confocal microscopy",
    "live cell imaging",
    "fluorescence microscopy",
]

BOOLEAN_QUERY = (
    '("lipid nanoparticle" OR "LNP" OR "LNPs" OR "lipid nanoparticles" OR "ionizable lipid nanoparticle" OR "lipoplex") '
    'AND ("cellular uptake" OR "internalization" OR "endocytosis" OR "transfection" '
    'OR "endosomal escape" OR "endosome escape" OR "internalization pathway")'
)

KINETIC_FILTERS = [
    "time-dependent",
    "time course",
    "time-resolved",
    "rate constant",
    "lag time",
    "uptake rate",
    "min incubation",
    "h incubation",
    "h after",
    "h post",
]

# When a paper has no full text to check, it can still reach the LLM (flagged
# kinetics-unverified) if its abstract shows one of these topics was measured —
# a numeric result, or the topic paired with a measurement word like "assessed"
# or "flow cytometry". See run_step_search.
UNVERIFIED_TOPIC_PATTERNS = [
    re.compile(r"\b(?:cellular|cell)\s+uptake\b", re.IGNORECASE),
    re.compile(r"\binternali[sz]ation\b|\binternali[sz]ed\b", re.IGNORECASE),
    re.compile(r"\buptake\s+(?:by|in|into|of)\b", re.IGNORECASE),
]

SIGNAL_PHRASES = [
    "time-dependent cellular uptake",
    "fluorescence intensity",
    "mean fluorescence intensity (MFI)",
    "confocal microscopy",
    "live cell imaging",
    "intracellular trafficking",
    "lag time",
    "percentage of positive cells",
    "flow cytometry analysis",
    "time course quantification of LNP uptake",
    "LNP-positive",
]


async def run_search(progress_cb: ProgressCb | None = None) -> dict[str, list[dict]]:
    return await run_step_search(
        boolean_query=BOOLEAN_QUERY,
        kinetic_keywords=KINETIC_FILTERS,
        signal_phrases=SIGNAL_PHRASES,
        strict_kinetic=STEP_META["strict_kinetic"],
        in_vitro_only=STEP_META["in_vitro_only"],
        step_name=STEP_META["name"],
        step_description=STEP_META["description"],
        unverified_topic_patterns=UNVERIFIED_TOPIC_PATTERNS,
        progress_cb=progress_cb,
    )
