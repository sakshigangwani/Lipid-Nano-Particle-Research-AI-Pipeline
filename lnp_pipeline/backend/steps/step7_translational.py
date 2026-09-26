from __future__ import annotations

from ._base import ProgressCb, run_step_search

STEP_META = {
    "id": 7,
    "name": "Translational",
    "description": "Protein expression from mRNA delivered by LNPs.",
    "strict_kinetic": False,
}

KEYWORDS = [
    "protein expression",
    "translation",
    "mRNA translation",
    "luciferase",
    "GFP expression",
    "transfection efficiency",
]

BOOLEAN_QUERY = (
    '("lipid nanoparticle" OR "LNP" OR "ionizable lipid nanoparticle" OR "lipoplex") '
    'AND ("protein expression" OR "translation" OR "luciferase" '
    'OR "GFP" OR "transfection efficiency") '
    'AND ("mRNA" OR "modified mRNA" OR "self-amplifying RNA") '
    'AND ("quantification" OR "expression level" OR "duration of expression")'
)

KINETIC_FILTERS = [
    "duration of expression",
    "time course",
    "peak expression",
    "h post-transfection",
    "days post-injection",
    "expression kinetics",
    "decay",
    "half-life",
]

SIGNAL_PHRASES = [
    "luciferase reporter",
    "in vivo bioluminescence",
    "EPO expression",
    "duration of protein expression",
    "self-amplifying RNA",
    "transfection efficiency",
    "expression kinetics",
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
