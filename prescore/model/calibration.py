"""Post-hoc probability calibration: temperature scaling.

v1.2's shots-on-target blend compresses team ratings toward the middle, which
improved the aggregate scores (RPS, log loss both dropped) but left the
confidence figure itself slightly wrong at the extremes: over-confident just
below a coin flip, under-confident at the top of the range. Measured on the
standard 3,040-prediction backtest window:

    bucket     predicted   observed   gap
    0.1-0.2    0.160       0.135      -0.025   (over-confident)
    0.7-0.8    0.742       0.803      +0.061   (under-confident)
    0.8-0.9    0.838       0.900      +0.062   (under-confident)

That shape -- probabilities too close to uniform, symmetrically, growing with
distance from 1/3 -- is exactly what temperature scaling exists to fix. It is
deliberately not fit inside `poisson.fit()`: attack/defence/home-advantage/rho
describe the data-generating process and are correctly fit in-sample, but
calibration is fundamentally an out-of-sample phenomenon -- fitting it on the
same predictions the ratings were trained on would be circular, since a
maximum-likelihood fit is already calibrated on its own training data by
construction. `temperature` is fit once, externally, against genuinely
held-out walk-forward predictions (see `fit_temperature`), then carried as a
plain chosen hyperparameter like `xg_weight` or `half_life_days`.
"""

from __future__ import annotations

import math

from ..backtest import metrics

OUTCOMES = metrics.OUTCOMES  # ("H", "D", "A")

# T < 1 sharpens (pushes probabilities away from 1/3); T > 1 flattens.
# T == 1 is the identity -- no calibration applied.
IDENTITY = 1.0


def apply_temperature(
    probs: tuple[float, float, float], temperature: float
) -> tuple[float, float, float]:
    """Rescale a 3-way probability simplex by a temperature.

    p_i' = p_i^(1/T), renormalised. Works on any (p_home, p_draw, p_away),
    regardless of what produced it -- this has no dependency on the Poisson
    model's internals.
    """
    if temperature == IDENTITY:
        return probs
    if temperature <= 0:
        raise ValueError("temperature must be positive")

    inv_t = 1.0 / temperature
    powered = [max(p, 1e-15) ** inv_t for p in probs]
    total = sum(powered)
    return tuple(p / total for p in powered)


def _mean_log_loss(
    records: list[tuple[tuple[float, float, float], str]], temperature: float
) -> float:
    total = 0.0
    for probs, actual in records:
        total += metrics.log_loss(apply_temperature(probs, temperature), actual)
    return total / len(records)


def fit_temperature(
    records: list[tuple[tuple[float, float, float], str]],
    bounds: tuple[float, float] = (0.3, 2.0),
    steps: int = 400,
) -> float:
    """Grid-search the temperature that minimises mean log loss.

    A grid search, not gradient descent, matching how `rho` is fit in
    `poisson.py` -- one bounded scalar, deterministic, trivial to test.
    `records` must be genuinely held-out predictions (e.g. from a walk-forward
    backtest), never predictions the model was trained on.
    """
    if not records:
        raise ValueError("cannot fit a temperature on zero records")

    lo, hi = bounds
    best_t, best_loss = IDENTITY, _mean_log_loss(records, IDENTITY)
    for i in range(steps + 1):
        t = lo + (hi - lo) * i / steps
        loss = _mean_log_loss(records, t)
        if loss < best_loss:
            best_t, best_loss = t, loss
    return best_t
