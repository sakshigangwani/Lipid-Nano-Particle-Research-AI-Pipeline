from __future__ import annotations


def score_paper(
    kinetic_matches: list[str],
    signal_matches: list[str],
    source_dbs: list[str],
) -> float:
    """Weighted 0.0–1.0 score.

    - Kinetic matches capped at 0.45 (saturating).
    - Signal phrases capped at 0.45.
    - Multi-DB corroboration capped at 0.10.
    """
    k = min(len(kinetic_matches), 5) / 5 * 0.45
    s = min(len(signal_matches), 4) / 4 * 0.45
    d = min(max(len(source_dbs) - 1, 0), 3) / 3 * 0.10
    return round(k + s + d, 4)
