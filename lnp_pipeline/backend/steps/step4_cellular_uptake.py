from __future__ import annotations

from ._base import ProgressCb, run_step_search

STEP_META = {
    "id": 4,
    "name": "Cellular uptake",
    "description": "Quantity and rate of LNP uptake by cells. Requires time-course + a quant metric + imaging/flow method.",
    "strict_kinetic": True,
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
    '("lipid nanoparticle" OR "LNP" OR "ionizable lipid nanoparticle") '
    'AND ("cellular uptake" OR "internalization" OR "endocytosis") '
    'AND ("kinetics" OR "time course" OR "time-dependent" OR "time-resolved" '
    'OR "rate constant") '
    'AND ("flow cytometry" OR "confocal microscopy" OR "live cell imaging" '
    'OR "fluorescence microscopy")'
)

QUANTITATIVE_FILTERS = [
    "% positive cells",
    "percentage of positive cells",
    "MFI",
    "mean fluorescence intensity",
    "ng/cell",
    "particles/cell",
    "molecules per cell",
    "uptake efficiency",
]

KINETIC_FILTERS = [
    "time-dependent",
    "time course",
    "time-resolved",
    "rate constant",
    "lag time",
    "uptake rate",
    "min incubation",
    "h incubation",
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


async def run_search(progress_cb: ProgressCb | None = None) -> list[dict]:
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
