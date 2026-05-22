from __future__ import annotations

from . import (
    step1_protein_corona,
    step2_biodistribution,
    step3_endocytosis,
    step4_cellular_uptake,
    step5_endosomal_escape,
    step6_cargo_release,
    step7_translational,
)

STEPS = {
    1: step1_protein_corona,
    2: step2_biodistribution,
    3: step3_endocytosis,
    4: step4_cellular_uptake,
    5: step5_endosomal_escape,
    6: step6_cargo_release,
    7: step7_translational,
}


def all_meta() -> list[dict]:
    return [m.STEP_META for m in STEPS.values()]


def get(step_id: int):
    if step_id not in STEPS:
        raise KeyError(f"Unknown step_id: {step_id}")
    return STEPS[step_id]
