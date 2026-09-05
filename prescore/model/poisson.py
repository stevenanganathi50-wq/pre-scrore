"""Poisson goals model with a Dixon-Coles low-score correction.

Each team carries an attack and a defence rating. For a fixture:

    log(home goals) = base + attack[home] - defence[away] + home_advantage
    log(away goals) = base + attack[away] - defence[home]

Ratings are fit by weighted maximum likelihood. The likelihood of a Poisson
GLM is concave in these parameters, so plain gradient ascent with a
backtracking step converges to the global optimum -- no external optimizer
needed.

Two adjustments to the textbook version:

* Time decay. A match `d` days old is weighted 0.5 ** (d / half_life), so the
  model tracks form rather than treating a 2016 result as current evidence.
* Dixon-Coles `rho`. Independent Poissons underrate 0-0 and 1-1 and overrate
  1-0 and 0-1. `rho` corrects those four cells and is fit after the ratings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Protocol, Sequence

from .. import config

_MAX_LOG_GOALS = 2.5  # exp(2.5) ~ 12 goals; a hard cap purely for stability
_RHO_BOUND = 0.25


class Match(Protocol):
    """The shape the model needs from a historical match."""

    match_date: date
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class Outcome:
    """1X2 probabilities for a single fixture."""

    p_home: float
    p_draw: float
    p_away: float
    expected_home_goals: float
    expected_away_goals: float

    @property
    def pick(self) -> str:
        best = max(
            (self.p_home, "H"), (self.p_draw, "D"), (self.p_away, "A")
        )
        return best[1]

    @property
    def confidence(self) -> float:
        """Probability assigned to the pick."""
        return max(self.p_home, self.p_draw, self.p_away)

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.p_home, self.p_draw, self.p_away)


@dataclass
class PoissonDixonColes:
    teams: tuple[str, ...]
    attack: dict[str, float]
    defence: dict[str, float]
    base: float
    home_advantage: float
    rho: float
    n_matches: int
    fitted_through: date
    half_life_days: float
    ridge: float
    log_likelihood: float = 0.0
    iterations: int = 0
    newcomer_attack: float = config.NEWCOMER_ATTACK
    newcomer_defence: float = config.NEWCOMER_DEFENCE
    xg_weight: float = config.XG_WEIGHT
    sot_conversion: float | None = None
    # Net effect of the injury differential (away count minus home count) on
    # the home side's linear predictor, and its mirror image on the away
    # side. Zero unless `fit()` was called with `fit_injury_weight=True` --
    # see the module docstring note on why that defaults off.
    injury_weight: float = 0.0
    version: str = field(default=config.MODEL_VERSION)

    # -- prediction -------------------------------------------------------

    def knows(self, team: str) -> bool:
        return team in self.attack

    def expected_goals(
        self,
        home: str,
        away: str,
        home_injuries: float = 0.0,
        away_injuries: float = 0.0,
    ) -> tuple[float, float]:
        """Expected goals for each side.

        A team with no history falls back to the newcomer prior rather than to
        league average: a side with no top-flight record is almost always newly
        promoted, and promoted teams are measurably worse than average.
        Callers that want to flag the uncertainty should check `knows()`.

        `*_injuries` is a count of players listed injured for this fixture.
        Only the *differential* affects the linear predictor -- a team down
        two players against an opponent also down two players cancels out,
        since what matters is relative disadvantage, not the raw count. The
        coefficient is zero (a no-op) unless the model was fit with
        `fit_injury_weight=True`.
        """
        atk_h = self.attack.get(home, self.newcomer_attack)
        atk_a = self.attack.get(away, self.newcomer_attack)
        def_h = self.defence.get(home, self.newcomer_defence)
        def_a = self.defence.get(away, self.newcomer_defence)
        injury_term = self.injury_weight * (away_injuries - home_injuries)

        log_home = min(
            self.base + atk_h - def_a + self.home_advantage + injury_term,
            _MAX_LOG_GOALS,
        )
        log_away = min(self.base + atk_a - def_h - injury_term, _MAX_LOG_GOALS)
        return math.exp(log_home), math.exp(log_away)

    def score_matrix(
        self,
        home: str,
        away: str,
        max_goals: int = config.MAX_GOALS,
        home_injuries: float = 0.0,
        away_injuries: float = 0.0,
    ) -> list[list[float]]:
        """Joint probability of every scoreline up to `max_goals` each."""
        lam, mu = self.expected_goals(home, away, home_injuries, away_injuries)
        home_pmf = _poisson_pmf(lam, max_goals)
        away_pmf = _poisson_pmf(mu, max_goals)

        matrix = [
            [home_pmf[x] * away_pmf[y] for y in range(max_goals + 1)]
            for x in range(max_goals + 1)
        ]
        for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
            matrix[x][y] *= max(_tau(x, y, lam, mu, self.rho), 1e-12)

        total = sum(sum(row) for row in matrix)
        return [[cell / total for cell in row] for row in matrix]

    def predict(
        self,
        home: str,
        away: str,
        home_injuries: float = 0.0,
        away_injuries: float = 0.0,
    ) -> Outcome:
        matrix = self.score_matrix(home, away, home_injuries=home_injuries, away_injuries=away_injuries)
        p_home = p_draw = p_away = 0.0
        for x, row in enumerate(matrix):
            for y, cell in enumerate(row):
                if x > y:
                    p_home += cell
                elif x == y:
                    p_draw += cell
                else:
                    p_away += cell
        lam, mu = self.expected_goals(home, away, home_injuries, away_injuries)
        return Outcome(p_home, p_draw, p_away, lam, mu)

    # -- reporting --------------------------------------------------------

    def ratings_table(self) -> list[tuple[str, float, float]]:
        """Teams sorted by overall strength (attack + defence)."""
        rows = [(t, self.attack[t], self.defence[t]) for t in self.teams]
        rows.sort(key=lambda r: r[1] + r[2], reverse=True)
        return rows

    def params(self) -> dict:
        return {
            "version": self.version,
            "base": self.base,
            "home_advantage": self.home_advantage,
            "injury_weight": self.injury_weight,
            "rho": self.rho,
            "half_life_days": self.half_life_days,
            "ridge": self.ridge,
            "n_matches": self.n_matches,
            "n_teams": len(self.teams),
            "fitted_through": self.fitted_through.isoformat(),
        }


# --- fitting --------------------------------------------------------------


@dataclass
class _Design:
    """Match data packed into parallel arrays, indexed by team position.

    `*_goals` are the real scorelines and `*_target` is what the ratings are
    actually fit to. They differ when the expected-goals proxy is in use: the
    ratings learn from chances created, while the Dixon-Coles low-score
    correction still has to be fit against scorelines that really happened.
    """

    home_idx: list[int]
    away_idx: list[int]
    home_goals: list[int]
    away_goals: list[int]
    home_target: list[float]
    away_target: list[float]
    weight: list[float]
    n_teams: int
    # Injury counts default to 0.0 for any match whose source object doesn't
    # carry them, so callers who never touch injuries see no behaviour change.
    home_injuries: list[float] = field(default_factory=list)
    away_injuries: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.home_idx)


def season_index(day: date) -> int:
    """Which season a date belongs to, by its starting year.

    European seasons run August to May, so July is the natural boundary.
    """
    return day.year if day.month >= 7 else day.year - 1


def _effective_age_days(match_day: date, ref: date, season_break_days: float) -> float:
    """Age of a match in decay terms.

    Calendar age understates how stale a result is across a summer: squads are
    rebuilt, managers change, and a team's rating should not carry into August
    as if May never ended. Each season boundary crossed adds extra age.
    """
    age = max((ref - match_day).days, 0)
    if season_break_days:
        seasons_crossed = max(season_index(ref) - season_index(match_day), 0)
        age += season_break_days * seasons_crossed
    return age


def _fit_targets(
    matches: Sequence[Match], weights: list[float], xg_weight: float
) -> tuple[list[float], list[float], float | None]:
    """Build what the ratings are fit to, blending goals with a shots proxy.

    A team's goals in one match are a noisy draw from the chances it created.
    Shots on target are a steadier measure of the same thing, so fitting on
    them partly filters out finishing luck.

    The conversion rate is estimated from the training matches themselves --
    total goals over total shots on target -- so the proxy carries the same
    total as the goals it replaces, and no future information enters the fit.
    Matches with no shot data keep their real goals.

    `xg_weight` of 0 is pure goals; 1 is pure proxy.
    """
    home_goals = [float(m.home_goals) for m in matches]
    away_goals = [float(m.away_goals) for m in matches]
    if xg_weight <= 0:
        return home_goals, away_goals, None

    total_goals = total_sot = 0.0
    for m, w in zip(matches, weights):
        home_sot = getattr(m, "home_sot", None)
        away_sot = getattr(m, "away_sot", None)
        if home_sot is None or away_sot is None:
            continue
        total_goals += w * (m.home_goals + m.away_goals)
        total_sot += w * (home_sot + away_sot)

    if total_sot <= 0:
        return home_goals, away_goals, None

    conversion = total_goals / total_sot
    blended_home, blended_away = [], []
    for i, m in enumerate(matches):
        home_sot = getattr(m, "home_sot", None)
        away_sot = getattr(m, "away_sot", None)
        if home_sot is None or away_sot is None:
            blended_home.append(home_goals[i])
            blended_away.append(away_goals[i])
            continue
        blended_home.append(
            (1 - xg_weight) * home_goals[i] + xg_weight * home_sot * conversion
        )
        blended_away.append(
            (1 - xg_weight) * away_goals[i] + xg_weight * away_sot * conversion
        )
    return blended_home, blended_away, conversion


def _poisson_pmf(rate: float, max_goals: int) -> list[float]:
    pmf = []
    term = math.exp(-rate)
    for k in range(max_goals + 1):
        pmf.append(term)
        term = term * rate / (k + 1)
    return pmf


def _tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _injury_term(d: _Design, k: int, injury_weight: float) -> float:
    if not injury_weight or not d.home_injuries:
        return 0.0
    return injury_weight * (d.away_injuries[k] - d.home_injuries[k])


def _log_likelihood(
    d: _Design,
    atk: list[float],
    dfn: list[float],
    base: float,
    hfa: float,
    ridge: float,
    prior_atk: list[float] | None = None,
    prior_dfn: list[float] | None = None,
    injury_weight: float = 0.0,
) -> float:
    total = 0.0
    for k in range(len(d)):
        h = d.home_idx[k]
        a = d.away_idx[k]
        inj = _injury_term(d, k, injury_weight)
        eta_h = min(base + atk[h] - dfn[a] + hfa + inj, _MAX_LOG_GOALS)
        eta_a = min(base + atk[a] - dfn[h] - inj, _MAX_LOG_GOALS)
        total += d.weight[k] * (
            d.home_target[k] * eta_h - math.exp(eta_h)
            + d.away_target[k] * eta_a - math.exp(eta_a)
        )
    if ridge:
        pa = prior_atk or [0.0] * d.n_teams
        pd = prior_dfn or [0.0] * d.n_teams
        total -= ridge * sum((atk[i] - pa[i]) ** 2 for i in range(d.n_teams))
        total -= ridge * sum((dfn[i] - pd[i]) ** 2 for i in range(d.n_teams))
    return total


def _log_likelihood_grad(
    d: _Design,
    atk: list[float],
    dfn: list[float],
    base: float,
    hfa: float,
    ridge: float,
    prior_atk: list[float] | None = None,
    prior_dfn: list[float] | None = None,
    injury_weight: float = 0.0,
    fit_injury_weight: bool = False,
):
    n = d.n_teams
    g_atk = [0.0] * n
    g_dfn = [0.0] * n
    g_base = 0.0
    g_hfa = 0.0
    g_injury = 0.0
    total = 0.0

    for k in range(len(d)):
        h = d.home_idx[k]
        a = d.away_idx[k]
        w = d.weight[k]
        diff = d.away_injuries[k] - d.home_injuries[k] if d.home_injuries else 0.0
        inj = injury_weight * diff
        eta_h = min(base + atk[h] - dfn[a] + hfa + inj, _MAX_LOG_GOALS)
        eta_a = min(base + atk[a] - dfn[h] - inj, _MAX_LOG_GOALS)
        lam = math.exp(eta_h)
        mu = math.exp(eta_a)

        total += w * (d.home_target[k] * eta_h - lam + d.away_target[k] * eta_a - mu)

        res_h = w * (d.home_target[k] - lam)
        res_a = w * (d.away_target[k] - mu)

        g_atk[h] += res_h
        g_dfn[a] -= res_h
        g_atk[a] += res_a
        g_dfn[h] -= res_a
        g_base += res_h + res_a
        g_hfa += res_h
        # d(eta_h)/d(injury_weight) = diff, d(eta_a)/d(injury_weight) = -diff
        if fit_injury_weight:
            g_injury += diff * (res_h - res_a)

    if ridge:
        pa = prior_atk or [0.0] * n
        pd = prior_dfn or [0.0] * n
        for i in range(n):
            da = atk[i] - pa[i]
            dd = dfn[i] - pd[i]
            total -= ridge * (da * da + dd * dd)
            g_atk[i] -= 2.0 * ridge * da
            g_dfn[i] -= 2.0 * ridge * dd

    return total, g_atk, g_dfn, g_base, g_hfa, g_injury


def _recenter(atk: list[float], dfn: list[float], base: float) -> float:
    """Pin mean attack and mean defence to zero without changing any rate.

    Shifting attack down by `ca` and defence down by `cd` leaves every linear
    predictor unchanged provided `base` absorbs `ca - cd`.
    """
    n = len(atk)
    ca = sum(atk) / n
    cd = sum(dfn) / n
    for i in range(n):
        atk[i] -= ca
        dfn[i] -= cd
    return base + ca - cd


def _fit_rho(
    d: _Design, atk: list[float], dfn: list[float], base: float, hfa: float
) -> float:
    """Grid-search rho over the low-scoring matches it actually affects."""
    cells = []
    for k in range(len(d)):
        x, y = d.home_goals[k], d.away_goals[k]
        if x > 1 or y > 1:
            continue
        h, a = d.home_idx[k], d.away_idx[k]
        lam = math.exp(min(base + atk[h] - dfn[a] + hfa, _MAX_LOG_GOALS))
        mu = math.exp(min(base + atk[a] - dfn[h], _MAX_LOG_GOALS))
        cells.append((x, y, lam, mu, d.weight[k]))

    if not cells:
        return 0.0

    best_rho, best_ll = 0.0, -math.inf
    steps = 400
    for i in range(steps + 1):
        rho = -_RHO_BOUND + 2.0 * _RHO_BOUND * i / steps
        ll = 0.0
        ok = True
        for x, y, lam, mu, w in cells:
            t = _tau(x, y, lam, mu, rho)
            if t <= 1e-9:
                ok = False
                break
            ll += w * math.log(t)
        if ok and ll > best_ll:
            best_ll, best_rho = ll, rho
    return best_rho


def fit(
    matches: Sequence[Match],
    *,
    ref_date: date | None = None,
    half_life_days: float = config.DEFAULT_HALF_LIFE_DAYS,
    ridge: float = config.DEFAULT_RIDGE,
    max_iter: int = 300,
    tol: float = 1e-9,
    warm_start: PoissonDixonColes | None = None,
    fit_rho: bool = True,
    newcomer_attack: float = config.NEWCOMER_ATTACK,
    newcomer_defence: float = config.NEWCOMER_DEFENCE,
    prior_strength: float = config.NEWCOMER_PRIOR_STRENGTH,
    season_break_days: float = config.SEASON_BREAK_DAYS,
    xg_weight: float = config.XG_WEIGHT,
    fit_injury_weight: bool = False,
) -> PoissonDixonColes:
    """Fit ratings by weighted maximum likelihood.

    `ref_date` is the point in time the model is fit *as of*; match weights
    decay relative to it. In a backtest this must be the date of the fixture
    being predicted, never the end of the dataset.

    `fit_injury_weight` defaults off, and should stay off. Validated against
    real API-Football injury data (2021-2025, matched to specific fixtures):
    RPS moved in opposite directions on two separate windows (-0.0003 on
    2021-08..2023-05, +0.0010 on 2023-08..2025-05), the same "sign flips
    between windows" signature that sank the ELO/ensemble experiment
    (see the README). That is not a real, generalising effect -- it is an
    extra free parameter finding whatever it can in each window's own noise.
    The mechanism is kept, tested, and available for a future attempt at a
    better-shaped signal (player importance, not raw headcount), but it must
    not be turned on by default without a fresh validation showing a
    consistent effect.
    """
    if not matches:
        raise ValueError("cannot fit a model on zero matches")

    ref = ref_date or max(m.match_date for m in matches)
    teams = tuple(sorted({m.home for m in matches} | {m.away for m in matches}))
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    weights = [
        0.5
        ** (_effective_age_days(m.match_date, ref, season_break_days) / half_life_days)
        for m in matches
    ]
    home_target, away_target, conversion = _fit_targets(matches, weights, xg_weight)

    d = _Design(
        home_idx=[index[m.home] for m in matches],
        away_idx=[index[m.away] for m in matches],
        home_goals=[m.home_goals for m in matches],
        away_goals=[m.away_goals for m in matches],
        home_target=home_target,
        away_target=away_target,
        weight=weights,
        n_teams=n,
        home_injuries=[float(getattr(m, "home_injuries", 0) or 0) for m in matches],
        away_injuries=[float(getattr(m, "away_injuries", 0) or 0) for m in matches],
    )

    total_weight = sum(d.weight)
    weighted_home = sum(w * g for w, g in zip(d.weight, d.home_target))
    weighted_away = sum(w * g for w, g in zip(d.weight, d.away_target))

    # Shrinkage targets. A team with no history is pulled all the way to the
    # newcomer prior; one with a full record is pulled toward league average.
    # Everything in between blends, so a promoted side's rating converges on
    # its own results as it plays its way into the season.
    appearances = [0.0] * n
    for k in range(len(d)):
        appearances[d.home_idx[k]] += d.weight[k]
        appearances[d.away_idx[k]] += d.weight[k]

    if prior_strength > 0:
        pull = [prior_strength / (prior_strength + w) for w in appearances]
    else:
        pull = [0.0] * n
    prior_atk = [newcomer_attack * p for p in pull]
    prior_dfn = [newcomer_defence * p for p in pull]

    if warm_start is not None:
        atk = [warm_start.attack.get(t, 0.0) for t in teams]
        dfn = [warm_start.defence.get(t, 0.0) for t in teams]
        base = warm_start.base
        hfa = warm_start.home_advantage
        # Forced to 0 unless this call explicitly asks for it: a caller must
        # not silently inherit a nonzero coefficient from an earlier fit that
        # happened to have fit_injury_weight=True.
        injury_weight = warm_start.injury_weight if fit_injury_weight else 0.0
    else:
        atk = [0.0] * n
        dfn = [0.0] * n
        mean_goals = (weighted_home + weighted_away) / (2.0 * total_weight)
        base = math.log(max(mean_goals, 0.1))
        hfa = math.log(max(weighted_home, 1e-6) / max(weighted_away, 1e-6))
        injury_weight = 0.0

    base = _recenter(atk, dfn, base)

    ll, g_atk, g_dfn, g_base, g_hfa, g_injury = _log_likelihood_grad(
        d, atk, dfn, base, hfa, ridge, prior_atk, prior_dfn,
        injury_weight, fit_injury_weight,
    )
    step = 1.0 / max(total_weight, 1.0)
    iterations = 0

    for _ in range(max_iter):
        accepted = False
        for _ in range(40):
            t_atk = [atk[i] + step * g_atk[i] for i in range(n)]
            t_dfn = [dfn[i] + step * g_dfn[i] for i in range(n)]
            t_base = base + step * g_base
            t_hfa = hfa + step * g_hfa
            t_injury = injury_weight + step * g_injury if fit_injury_weight else injury_weight
            t_base = _recenter(t_atk, t_dfn, t_base)

            ll_new = _log_likelihood(
                d, t_atk, t_dfn, t_base, t_hfa, ridge, prior_atk, prior_dfn, t_injury
            )
            if ll_new > ll:
                accepted = True
                break
            step *= 0.4
            if step < 1e-16:
                break

        if not accepted:
            break

        improvement = ll_new - ll
        atk, dfn, base, hfa, injury_weight, ll = t_atk, t_dfn, t_base, t_hfa, t_injury, ll_new
        iterations += 1
        step *= 1.3

        if improvement < tol * (1.0 + abs(ll)):
            break

        _, g_atk, g_dfn, g_base, g_hfa, g_injury = _log_likelihood_grad(
            d, atk, dfn, base, hfa, ridge, prior_atk, prior_dfn,
            injury_weight, fit_injury_weight,
        )

    rho = _fit_rho(d, atk, dfn, base, hfa) if fit_rho else 0.0

    return PoissonDixonColes(
        teams=teams,
        attack={t: atk[i] for t, i in index.items()},
        defence={t: dfn[i] for t, i in index.items()},
        base=base,
        home_advantage=hfa,
        rho=rho,
        n_matches=len(matches),
        fitted_through=ref,
        half_life_days=half_life_days,
        ridge=ridge,
        log_likelihood=ll,
        iterations=iterations,
        newcomer_attack=newcomer_attack,
        newcomer_defence=newcomer_defence,
        xg_weight=xg_weight,
        sot_conversion=conversion,
        injury_weight=injury_weight,
    )
