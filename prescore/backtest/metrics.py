"""Scoring rules for 1X2 predictions.

Accuracy alone is a poor measure for a three-way market with a large draw
class, so every report carries proper scoring rules alongside it:

* log loss  - punishes confident mistakes hardest; the standard for probabilities
* RPS       - ranked probability score, respects that H > D > A is ordered, so
              predicting a home win when it was a draw is a smaller miss than
              predicting a home win when it was an away win
* Brier     - multiclass squared error, less sensitive to extreme errors

Lower is better for all three.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

OUTCOMES = ("H", "D", "A")
_EPS = 1e-15


def _onehot(actual: str) -> tuple[float, float, float]:
    return tuple(1.0 if o == actual else 0.0 for o in OUTCOMES)


def log_loss(probs: tuple[float, float, float], actual: str) -> float:
    p = probs[OUTCOMES.index(actual)]
    return -math.log(max(p, _EPS))


def brier(probs: tuple[float, float, float], actual: str) -> float:
    obs = _onehot(actual)
    return sum((p - o) ** 2 for p, o in zip(probs, obs))


def rps(probs: tuple[float, float, float], actual: str) -> float:
    obs = _onehot(actual)
    cum_p = cum_o = 0.0
    total = 0.0
    for i in range(len(OUTCOMES) - 1):
        cum_p += probs[i]
        cum_o += obs[i]
        total += (cum_p - cum_o) ** 2
    return total / (len(OUTCOMES) - 1)


def devig(odds: tuple[float, float, float]) -> tuple[float, float, float] | None:
    """Turn decimal odds into probabilities by removing the overround.

    Proportional normalization -- crude but standard, and good enough for a
    benchmark. The market's true implied probabilities are slightly favourite-
    biased relative to this.
    """
    if any(o is None or o <= 1.0 for o in odds):
        return None
    inv = [1.0 / o for o in odds]
    total = sum(inv)
    return tuple(i / total for i in inv)


@dataclass
class Scorecard:
    """Aggregate performance of one set of predictions."""

    label: str
    n: int = 0
    hits: int = 0
    log_loss_sum: float = 0.0
    rps_sum: float = 0.0
    brier_sum: float = 0.0
    by_pick: dict[str, list[int]] = field(default_factory=dict)
    # A baseline that emits hard 0/1 probabilities (always-home) has no
    # meaningful log loss -- every miss is clamped at -log(eps). Flag those so
    # the report shows accuracy only rather than a made-up number.
    accuracy_only: bool = False

    def add(self, probs: tuple[float, float, float], actual: str) -> None:
        pick = OUTCOMES[probs.index(max(probs))]
        self.n += 1
        hit = 1 if pick == actual else 0
        self.hits += hit
        self.log_loss_sum += log_loss(probs, actual)
        self.rps_sum += rps(probs, actual)
        self.brier_sum += brier(probs, actual)
        bucket = self.by_pick.setdefault(pick, [0, 0])
        bucket[0] += 1
        bucket[1] += hit

    @property
    def accuracy(self) -> float:
        return self.hits / self.n if self.n else 0.0

    @property
    def log_loss(self) -> float:
        return self.log_loss_sum / self.n if self.n else 0.0

    @property
    def rps(self) -> float:
        return self.rps_sum / self.n if self.n else 0.0

    @property
    def brier(self) -> float:
        return self.brier_sum / self.n if self.n else 0.0

    def summary(self) -> dict:
        return {
            "label": self.label,
            "n": self.n,
            "hits": self.hits,
            "misses": self.n - self.hits,
            "accuracy": self.accuracy,
            "accuracy_only": self.accuracy_only,
            "log_loss": None if self.accuracy_only else self.log_loss,
            "rps": None if self.accuracy_only else self.rps,
            "brier": None if self.accuracy_only else self.brier,
            "by_pick": {
                k: {"n": v[0], "hits": v[1], "accuracy": v[1] / v[0] if v[0] else 0.0}
                for k, v in sorted(self.by_pick.items())
            },
        }


def calibration(
    records: list[tuple[tuple[float, float, float], str]], bins: int = 10
) -> list[dict]:
    """How often does an event happen, given the probability we assigned it?

    Every (prediction, outcome) pair contributes three observations -- one per
    outcome -- so this measures the whole probability vector, not just the pick.
    """
    buckets = [[0, 0.0, 0.0] for _ in range(bins)]
    for probs, actual in records:
        obs = _onehot(actual)
        for p, o in zip(probs, obs):
            idx = min(int(p * bins), bins - 1)
            buckets[idx][0] += 1
            buckets[idx][1] += p
            buckets[idx][2] += o

    out = []
    for i, (n, p_sum, o_sum) in enumerate(buckets):
        if n == 0:
            continue
        out.append(
            {
                "range": f"{i / bins:.1f}-{(i + 1) / bins:.1f}",
                "n": n,
                "predicted": p_sum / n,
                "observed": o_sum / n,
            }
        )
    return out


def confidence_buckets(
    records: list[tuple[tuple[float, float, float], str]],
    edges: tuple[float, ...] = (0.0, 0.40, 0.50, 0.60, 0.70, 1.01),
) -> list[dict]:
    """Accuracy split by how confident the pick was.

    This is what lets high-confidence picks be tracked separately from
    coin-flips in the public record.
    """
    out = []
    for lo, hi in zip(edges, edges[1:]):
        n = hits = 0
        for probs, actual in records:
            conf = max(probs)
            if lo <= conf < hi:
                n += 1
                if OUTCOMES[probs.index(conf)] == actual:
                    hits += 1
        if n:
            out.append(
                {
                    "range": f"{lo:.2f}-{min(hi, 1.0):.2f}",
                    "n": n,
                    "accuracy": hits / n,
                    "hits": hits,
                }
            )
    return out
