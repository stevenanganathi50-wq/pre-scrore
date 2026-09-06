"""Derived markets: BTTS, Over/Under, correct score.

All three are pure post-processing of the scoreline matrix the model already
builds for 1X2 (`PoissonDixonColes.score_matrix`). No new data, no new
fitting, no change to what 1X2 predicts -- these read numbers the model
already produces, they don't produce new ones. That's what makes them safe
to ship without treating it as another exception to the model freeze: the
existing H/D/A track record is untouched.

Each derivation sums its own cells directly (never `1 - other_side`) so a
result is exact even if the matrix's normalisation carries tiny floating
point slack, matching how `predict()` computes p_home/p_draw/p_away.
"""

from __future__ import annotations

import math

Matrix = list[list[float]]
_EPS = 1e-15


def btts_probability(matrix: Matrix) -> tuple[float, float]:
    """(p_yes, p_no) -- both teams score, or at least one is shut out."""
    size = len(matrix)
    p_yes = sum(matrix[x][y] for x in range(1, size) for y in range(1, size))
    p_no = sum(matrix[x][y] for x in range(size) for y in range(size)) - p_yes
    return p_yes, p_no


def over_under_probability(matrix: Matrix, line: float = 2.5) -> tuple[float, float]:
    """(p_over, p_under) for total goals against `line`.

    `line` should end in .5 -- an integer line would need a push/void case
    this model has no way to price, and the product doesn't offer one.
    """
    size = len(matrix)
    p_over = sum(
        matrix[x][y] for x in range(size) for y in range(size) if x + y > line
    )
    p_under = sum(matrix[x][y] for x in range(size) for y in range(size)) - p_over
    return p_over, p_under


def binary_log_loss(p_yes: float, actual_is_yes: bool) -> float:
    """Log loss for a 2-outcome market. `prescore.backtest.metrics.log_loss`
    is 1X2-specific (its OUTCOMES tuple is hardcoded to H/D/A), so BTTS and
    Over/Under -- genuinely different outcome labels -- need this instead."""
    p = p_yes if actual_is_yes else (1.0 - p_yes)
    return -math.log(max(p, _EPS))


def binary_brier(p_yes: float, actual_is_yes: bool) -> float:
    """Same idea as `prescore.backtest.metrics.brier`: summed squared error
    over every outcome slot, not just the one that happened."""
    o_yes = 1.0 if actual_is_yes else 0.0
    return (p_yes - o_yes) ** 2 + ((1.0 - p_yes) - (1.0 - o_yes)) ** 2


def most_likely_score(matrix: Matrix) -> tuple[tuple[int, int], float]:
    """The single most probable exact scoreline, and its probability."""
    size = len(matrix)
    best = (0, 0)
    best_p = matrix[0][0]
    for x in range(size):
        for y in range(size):
            if matrix[x][y] > best_p:
                best_p = matrix[x][y]
                best = (x, y)
    return best, best_p
