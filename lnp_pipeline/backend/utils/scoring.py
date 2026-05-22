from __future__ import annotations


def score_paper(
    quant_matches: list[str],
    kinetic_matches: list[str],
    signal_matches: list[str],
    source_dbs: list[str],
) -> float:
    """Weighted 0.0–1.0 score.

    - Quant + kinetic each capped at 0.30 (saturating).
    - Signal phrases capped at 0.30.
    - Multi-DB corroboration capped at 0.10.
    """
    q = min(len(quant_matches), 5) / 5 * 0.30
    k = min(len(kinetic_matches), 5) / 5 * 0.30
    s = min(len(signal_matches), 4) / 4 * 0.30
    d = min(max(len(source_dbs) - 1, 0), 3) / 3 * 0.10
    return round(q + k + s + d, 4)
