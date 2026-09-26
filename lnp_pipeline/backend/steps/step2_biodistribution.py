from __future__ import annotations

from ._base import ProgressCb, run_step_search

STEP_META = {
    "id": 2,
    "name": "Biodistribution (whole body)",
    "description": "LNP accumulation across organs and tissues in vivo.",
    "strict_kinetic": False,
}

KEYWORDS = [
    "biodistribution",
    "organ accumulation",
    "pharmacokinetics",
    "IVIS imaging",
    "tissue distribution",
]

BOOLEAN_QUERY = (
    '("lipid nanoparticle" OR "LNP" OR "ionizable lipid nanoparticle" OR "lipoplex") '
    'AND ("biodistribution" OR "organ accumulation" OR "pharmacokinetics" '
    'OR "tissue distribution" OR "IVIS") '
    'AND ("liver" OR "spleen" OR "lung" OR "tumor" OR "lymph node" OR "brain") '
    'AND ("in vivo" OR "mouse" OR "mice" OR "rat" OR "non-human primate")'
)

KINETIC_FILTERS = [
    "time course",
    "post-injection",
    "h post-injection",
    "AUC",
    "plasma half-life",
    "clearance",
    "elimination",
]

SIGNAL_PHRASES = [
    "ex vivo imaging",
    "IVIS Spectrum",
    "organ-level quantification",
    "luciferase expression",
    "near-infrared imaging",
    "pharmacokinetic profile",
]


async def run_search(progress_cb: ProgressCb | None = None) -> dict[str, list[dict]]:
    return await run_step_search(
        boolean_query=BOOLEAN_QUERY,
        kinetic_keywords=KINETIC_FILTERS,
        signal_phrases=SIGNAL_PHRASES,
        strict_kinetic=STEP_META["strict_kinetic"],
        step_name=STEP_META["name"],
        step_description=STEP_META["description"],
        progress_cb=progress_cb,
    )
