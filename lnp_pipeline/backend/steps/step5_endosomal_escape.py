from __future__ import annotations

from ._base import ProgressCb, run_step_search

STEP_META = {
    "id": 5,
    "name": "Endosomal escape",
    "description": "Escape of LNP cargo from the endosome into the cytoplasm. Requires kinetic data.",
    "strict_kinetic": True,
}

KEYWORDS = [
    "endosomal escape",
    "endosome",
    "proton sponge",
    "membrane fusion",
    "ionizable lipid",
    "Gal8 recruitment",
]

BOOLEAN_QUERY = (
    '("lipid nanoparticle" OR "LNP" OR "ionizable lipid nanoparticle") '
    'AND ("endosomal escape" OR "endosome escape" OR "membrane disruption" '
    'OR "proton sponge" OR "Gal8" OR "galectin-8") '
    'AND ("efficiency" OR "kinetics" OR "rate" OR "fraction") '
    'AND ("mRNA" OR "siRNA" OR "cargo" OR "cytosolic delivery")'
)

QUANTITATIVE_FILTERS = [
    "% escape",
    "escape efficiency",
    "fold increase",
    "puncta per cell",
    "Gal8-GFP",
    "cytosolic fraction",
]

KINETIC_FILTERS = [
    "time-dependent",
    "time course",
    "minutes post-uptake",
    "escape rate",
    "kinetic",
    "lag",
    "onset",
]

SIGNAL_PHRASES = [
    "Gal8 recruitment",
    "galectin-8 puncta",
    "endosomal acidification",
    "live-cell imaging of escape",
    "cytosolic delivery efficiency",
    "split-fluorescent reporter",
    "BlaM assay",
]


async def run_search(progress_cb: ProgressCb | None = None) -> list[dict]:
    return await run_step_search(
        boolean_query=BOOLEAN_QUERY,
        quant_keywords=QUANTITATIVE_FILTERS,
        kinetic_keywords=KINETIC_FILTERS,
        signal_phrases=SIGNAL_PHRASES,
        strict_kinetic=STEP_META["strict_kinetic"],
        progress_cb=progress_cb,
    )
