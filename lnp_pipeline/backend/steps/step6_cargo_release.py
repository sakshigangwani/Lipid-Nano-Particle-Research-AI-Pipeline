from __future__ import annotations

from ._base import ProgressCb, run_step_search

STEP_META = {
    "id": 6,
    "name": "Cargo release",
    "description": "Release of mRNA/payload from the LNP after delivery.",
    "strict_kinetic": False,
}

KEYWORDS = [
    "cargo release",
    "mRNA release",
    "payload release",
    "disassembly",
    "release kinetics",
]

BOOLEAN_QUERY = (
    '("lipid nanoparticle" OR "LNP" OR "ionizable lipid nanoparticle" OR "lipoplex") '
    'AND ("cargo release" OR "mRNA release" OR "payload release" '
    'OR "RNA release" OR "disassembly") '
    'AND ("efficiency" OR "fraction" OR "kinetics" OR "rate") '
    'AND ("RiboGreen" OR "FRET" OR "stopped-flow" OR "release assay")'
)

QUANTITATIVE_FILTERS = [
    "% released",
    "release efficiency",
    "fraction released",
    "fold increase",
    "ng RNA",
    "encapsulation efficiency",
]

KINETIC_FILTERS = [
    "release kinetics",
    "release rate",
    "time course",
    "stopped-flow",
    "t1/2",
    "half-life",
    "minutes",
    "hours",
]

SIGNAL_PHRASES = [
    "RiboGreen assay",
    "FRET-based release",
    "pH-dependent release",
    "anionic lipid mixing",
    "stopped-flow fluorescence",
    "mRNA accessibility",
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
