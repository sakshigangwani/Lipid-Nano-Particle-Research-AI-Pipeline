from __future__ import annotations

from ._base import ProgressCb, run_step_search

STEP_META = {
    "id": 3,
    "name": "Endocytosis",
    "description": "Mechanism by which LNPs enter cells (clathrin/caveolae/macropinocytosis). Requires kinetic data.",
    "strict_kinetic": True,
}

KEYWORDS = [
    "endocytosis",
    "clathrin-mediated",
    "caveolae",
    "macropinocytosis",
    "dynasore",
    "internalization pathway",
]

BOOLEAN_QUERY = (
    '("lipid nanoparticle" OR "LNP" OR "ionizable lipid nanoparticle") '
    'AND ("endocytosis" OR "clathrin-mediated endocytosis" OR "caveolae" '
    'OR "macropinocytosis" OR "internalization pathway") '
    'AND ("inhibitor" OR "dynasore" OR "filipin" OR "chlorpromazine" OR "EIPA") '
    'AND ("kinetics" OR "time-dependent" OR "time course")'
)

QUANTITATIVE_FILTERS = [
    "% inhibition",
    "% uptake",
    "fold reduction",
    "MFI",
    "mean fluorescence intensity",
]

KINETIC_FILTERS = [
    "time-dependent",
    "time course",
    "internalization rate",
    "uptake rate",
    "rate constant",
    "min incubation",
    "h incubation",
]

SIGNAL_PHRASES = [
    "clathrin-mediated endocytosis",
    "caveolae-mediated",
    "dynasore treatment",
    "pathway-specific inhibitor",
    "co-localization with EEA1",
    "Rab5",
    "endocytic pathway",
]


async def run_search(progress_cb: ProgressCb | None = None) -> dict[str, list[dict]]:
    return await run_step_search(
        boolean_query=BOOLEAN_QUERY,
        quant_keywords=QUANTITATIVE_FILTERS,
        kinetic_keywords=KINETIC_FILTERS,
        signal_phrases=SIGNAL_PHRASES,
        strict_kinetic=STEP_META["strict_kinetic"],
        step_name=STEP_META["name"],
        step_description=STEP_META["description"],
        progress_cb=progress_cb,
    )
