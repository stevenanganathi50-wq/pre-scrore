"""ELO ratings with an ordered-logit link to 1X2 probabilities.

ELO is a different kind of model to the Poisson one: it tracks a single
strength number per team, updated after every match by how surprising the
result was. It knows nothing about goals scored and conceded separately, so it
carries genuinely different information -- which is the point of building it.
An ensemble only helps when its members make different mistakes.

Plain ELO produces an expected *score* (a number between 0 and 1), not three
probabilities. The draw has to come from somewhere, so a small ordered logit
maps the rating gap onto home/draw/away:

    P(away)        = sigmoid(t1 - beta * d)
    P(away or draw)= sigmoid(t2 - beta * d)
    P(home)        = 1 - sigmoid(t2 - beta * d)

with d the rating gap including home advantage, and t1 < t2 enforced by
parameterising t2 = t1 + exp(gap).

The link is fit on *pre-match* rating gaps recorded during the walk through
history, never on final ratings. Fitting it on hindsight ratings would make it
look far better than it is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from .. import config
from .poisson import Match, Outcome

DEFAULT_RATING = 1500.0


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    exp_z = math.exp(z)
    return exp_z / (1.0 + exp_z)


def _margin_multiplier(margin: int) -> float:
    """Bigger wins move ratings further, with diminishing returns.

    The World Football Elo convention: a three-goal win is worth more than a
    one-goal win, but not three times as much.
    """
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    return (11.0 + margin) / 8.0


@dataclass
class EloModel:
    ratings: dict[str, float]
    beta: float
    threshold_low: float
    threshold_high: float
    k_factor: float
    home_advantage: float
    n_matches: int
    fitted_through: date
    log_likelihood: float = 0.0
    version: str = field(default="elo-1.0")

    def knows(self, team: str) -> bool:
        return team in self.ratings

    def rating(self, team: str) -> float:
        return self.ratings.get(team, DEFAULT_RATING)

    def rating_gap(self, home: str, away: str) -> float:
        return self.rating(home) + self.home_advantage - self.rating(away)

    def predict(self, home: str, away: str) -> Outcome:
        gap = self.rating_gap(home, away) / 400.0
        p_away = _sigmoid(self.threshold_low - self.beta * gap)
        p_not_home = _sigmoid(self.threshold_high - self.beta * gap)
        p_draw = max(p_not_home - p_away, 1e-9)
        p_home = max(1.0 - p_not_home, 1e-9)

        total = p_home + p_draw + p_away
        return Outcome(
            p_home / total,
            p_draw / total,
            p_away / total,
            # ELO has no goal model; expected goals are not meaningful here.
            float("nan"),
            float("nan"),
        )

    def ratings_table(self) -> list[tuple[str, float]]:
        return sorted(self.ratings.items(), key=lambda kv: kv[1], reverse=True)


def _link_log_likelihood(
    samples: list[tuple[float, str, float]],
    beta: float,
    t_low: float,
    spread: float,
) -> float:
    t_high = t_low + math.exp(spread)
    total = 0.0
    for gap, result, weight in samples:
        s_low = _sigmoid(t_low - beta * gap)
        s_high = _sigmoid(t_high - beta * gap)
        if result == "A":
            p = s_low
        elif result == "D":
            p = s_high - s_low
        else:
            p = 1.0 - s_high
        total += weight * math.log(max(p, 1e-12))
    return total


def _fit_link(
    samples: list[tuple[float, str, float]],
    start: tuple[float, float, float],
    max_iter: int = 200,
    tol: float = 1e-8,
) -> tuple[float, float, float, float]:
    """Fit (beta, t_low, spread) by gradient ascent with a backtracking step."""
    beta, t_low, spread = start
    if not samples:
        return beta, t_low, spread, 0.0

    ll = _link_log_likelihood(samples, beta, t_low, spread)
    step = 1.0 / max(sum(w for _, _, w in samples), 1.0)

    for _ in range(max_iter):
        t_high = t_low + math.exp(spread)
        g_beta = g_low = g_high = 0.0

        for gap, result, weight in samples:
            s_low = _sigmoid(t_low - beta * gap)
            s_high = _sigmoid(t_high - beta * gap)
            d_low = s_low * (1.0 - s_low)
            d_high = s_high * (1.0 - s_high)

            if result == "A":
                p = max(s_low, 1e-12)
                g_low += weight * d_low / p
                g_beta += weight * (-gap) * d_low / p
            elif result == "D":
                p = max(s_high - s_low, 1e-12)
                g_low += weight * (-d_low) / p
                g_high += weight * d_high / p
                g_beta += weight * (-gap) * (d_high - d_low) / p
            else:
                p = max(1.0 - s_high, 1e-12)
                g_high += weight * (-d_high) / p
                g_beta += weight * gap * d_high / p

        # t_high = t_low + exp(spread), so t_low moves both thresholds.
        grad_beta = g_beta
        grad_low = g_low + g_high
        grad_spread = g_high * math.exp(spread)

        accepted = False
        for _ in range(40):
            trial = (
                beta + step * grad_beta,
                t_low + step * grad_low,
                spread + step * grad_spread,
            )
            ll_new = _link_log_likelihood(samples, *trial)
            if ll_new > ll:
                beta, t_low, spread = trial
                accepted = True
                break
            step *= 0.4
            if step < 1e-15:
                break

        if not accepted:
            break
        improvement = ll_new - ll
        ll = ll_new
        step *= 1.3
        if improvement < tol * (1.0 + abs(ll)):
            break

    return beta, t_low, spread, ll


def fit(
    matches: Sequence[Match],
    *,
    ref_date: date | None = None,
    k_factor: float = 20.0,
    home_advantage: float = 65.0,
    half_life_days: float = config.DEFAULT_HALF_LIFE_DAYS,
    use_margin: bool = True,
    warm_start: EloModel | None = None,
) -> EloModel:
    """Walk history in order, updating ratings, then fit the link.

    Matches must be chronological. Ratings are inherently sequential, so unlike
    the Poisson fit there is no optimisation over the whole set -- the walk is
    the fit.
    """
    if not matches:
        raise ValueError("cannot fit ELO on zero matches")

    ordered = sorted(matches, key=lambda m: m.match_date)
    ref = ref_date or ordered[-1].match_date

    ratings: dict[str, float] = {}
    samples: list[tuple[float, str, float]] = []

    for m in ordered:
        home_rating = ratings.setdefault(m.home, DEFAULT_RATING)
        away_rating = ratings.setdefault(m.away, DEFAULT_RATING)

        gap = home_rating + home_advantage - away_rating
        expected_home = 1.0 / (1.0 + 10.0 ** (-gap / 400.0))

        if m.home_goals > m.away_goals:
            actual, result = 1.0, "H"
        elif m.home_goals < m.away_goals:
            actual, result = 0.0, "A"
        else:
            actual, result = 0.5, "D"

        # Recorded before the update, so the link is fit on what the model
        # actually knew going into the match.
        age = max((ref - m.match_date).days, 0)
        weight = 0.5 ** (age / half_life_days)
        samples.append((gap / 400.0, result, weight))

        multiplier = (
            _margin_multiplier(abs(m.home_goals - m.away_goals)) if use_margin else 1.0
        )
        change = k_factor * multiplier * (actual - expected_home)
        ratings[m.home] = home_rating + change
        ratings[m.away] = away_rating - change

    start = (
        (warm_start.beta, warm_start.threshold_low,
         math.log(max(warm_start.threshold_high - warm_start.threshold_low, 1e-6)))
        if warm_start is not None
        else (1.0, -0.6, math.log(1.2))
    )
    beta, t_low, spread, ll = _fit_link(samples, start)

    return EloModel(
        ratings=ratings,
        beta=beta,
        threshold_low=t_low,
        threshold_high=t_low + math.exp(spread),
        k_factor=k_factor,
        home_advantage=home_advantage,
        n_matches=len(ordered),
        fitted_through=ref,
        log_likelihood=ll,
    )
