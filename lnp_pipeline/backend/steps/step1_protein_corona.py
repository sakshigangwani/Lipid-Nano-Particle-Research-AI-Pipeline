from __future__ import annotations

from ._base import ProgressCb, run_step_search

STEP_META = {
    "id": 1,
    "name": "Protein corona",
    "description": "Protein layer formation on the LNP surface in biological fluid.",
    "strict_kinetic": False,
}

KEYWORDS = [
    "protein corona",
    "opsonization",
    "apolipoprotein",
    "ApoE",
    "serum protein adsorption",
]

BOOLEAN_QUERY = (
    '("lipid nanoparticle" OR "LNP" OR "ionizable lipid nanoparticle" OR "lipoplex") '
    'AND ("protein corona" OR "opsonization" OR "apolipoprotein" OR "ApoE" '
    'OR "serum protein adsorption") '
    'AND ("mass spectrometry" OR "proteomics" OR "LC-MS" OR "quantification" '
    'OR "abundance")'
)

KINETIC_FILTERS = [
    "incubation time",
    "exchange kinetics",
    "Vroman effect",
    "time-resolved",
    "evolution over time",
]

SIGNAL_PHRASES = [
    "ApoE binding",
    "label-free quantification",
    "LFQ intensity",
    "corona composition",
    "hard corona",
    "soft corona",
    "shotgun proteomics",
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
