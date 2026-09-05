"""Model tests: does the fitter recover ratings it was given?"""

import math
import random
import unittest
from dataclasses import dataclass
from datetime import date, timedelta

from prescore import config
from prescore.model import poisson


@dataclass
class FakeMatch:
    match_date: date
    home: str
    away: str
    home_goals: int
    away_goals: int


def _poisson_sample(rng: random.Random, rate: float) -> int:
    """Knuth's algorithm -- keeps the tests dependency-free."""
    limit = math.exp(-rate)
    k, product = 0, rng.random()
    while product > limit:
        k += 1
        product *= rng.random()
    return k


def synthetic_season(seed: int = 7, n_teams: int = 12, rounds: int = 6):
    rng = random.Random(seed)
    teams = [f"T{i:02d}" for i in range(n_teams)]
    attack = {t: rng.uniform(-0.5, 0.5) for t in teams}
    defence = {t: rng.uniform(-0.5, 0.5) for t in teams}
    # centre them, matching the identifiability constraint the fitter imposes
    a_mean = sum(attack.values()) / n_teams
    d_mean = sum(defence.values()) / n_teams
    attack = {t: v - a_mean for t, v in attack.items()}
    defence = {t: v - d_mean for t, v in defence.items()}
    base, hfa = math.log(1.35), 0.25

    matches, day = [], date(2020, 1, 1)
    for _ in range(rounds):
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                lam = math.exp(base + attack[h] - defence[a] + hfa)
                mu = math.exp(base + attack[a] - defence[h])
                matches.append(
                    FakeMatch(day, h, a, _poisson_sample(rng, lam), _poisson_sample(rng, mu))
                )
                day += timedelta(days=1)
    return matches, attack, defence, base, hfa


def two_era_league(n_rounds: int = 4):
    """A round-robin league where team X flips from weak to strong.

    Everyone else draws 1-1 forever, so X's ratings are the only thing that
    moves and the fit is well identified.
    """
    teams = ["X", "B", "C", "D", "E", "F"]
    matches = []
    for era_start, x_scores, x_concedes in (
        (date(2020, 1, 1), 1, 3),
        (date(2022, 1, 1), 3, 1),
    ):
        day = era_start
        for _ in range(n_rounds):
            for home in teams:
                for away in teams:
                    if home == away:
                        continue
                    if home == "X":
                        goals = (x_scores, x_concedes)
                    elif away == "X":
                        goals = (x_concedes, x_scores)
                    else:
                        goals = (1, 1)
                    matches.append(FakeMatch(day, home, away, *goals))
                    day += timedelta(days=1)
    return matches


class TestFit(unittest.TestCase):
    def test_recovers_known_ratings(self):
        matches, attack, defence, base, hfa = synthetic_season()
        model = poisson.fit(
            matches, half_life_days=1e9, ridge=0.0, max_iter=2000, tol=1e-12
        )

        for team in attack:
            self.assertAlmostEqual(model.attack[team], attack[team], delta=0.16)
            self.assertAlmostEqual(model.defence[team], defence[team], delta=0.16)
        self.assertAlmostEqual(model.base, base, delta=0.10)
        self.assertAlmostEqual(model.home_advantage, hfa, delta=0.10)

    def test_ratings_are_centred(self):
        matches, *_ = synthetic_season()
        model = poisson.fit(matches, half_life_days=1e9, ridge=0.0)
        n = len(model.teams)
        self.assertAlmostEqual(sum(model.attack.values()) / n, 0.0, places=6)
        self.assertAlmostEqual(sum(model.defence.values()) / n, 0.0, places=6)

    def test_likelihood_increases_monotonically(self):
        matches, *_ = synthetic_season(seed=3)
        coarse = poisson.fit(matches, half_life_days=1e9, ridge=0.0, max_iter=5)
        fine = poisson.fit(matches, half_life_days=1e9, ridge=0.0, max_iter=500)
        self.assertGreater(fine.log_likelihood, coarse.log_likelihood)

    def test_ridge_shrinks_ratings(self):
        matches, *_ = synthetic_season()
        loose = poisson.fit(matches, half_life_days=1e9, ridge=0.0)
        tight = poisson.fit(matches, half_life_days=1e9, ridge=50.0)
        spread = lambda m: sum(abs(v) for v in m.attack.values())
        self.assertLess(spread(tight), spread(loose))

    def test_time_decay_favours_recent_form(self):
        """A team that was weak long ago and strong lately rates higher under
        fast decay than under no decay."""
        matches = two_era_league()
        ref = date(2022, 7, 1)
        slow = poisson.fit(matches, ref_date=ref, half_life_days=1e9, ridge=0.05)
        fast = poisson.fit(matches, ref_date=ref, half_life_days=60, ridge=0.05)

        self.assertGreater(fast.attack["X"], slow.attack["X"])
        self.assertGreater(fast.defence["X"], slow.defence["X"])

    def test_warm_start_matches_cold_start(self):
        matches, *_ = synthetic_season(seed=11)
        cold = poisson.fit(matches, half_life_days=1e9, ridge=0.01, max_iter=2000, tol=1e-12)
        warm = poisson.fit(
            matches, half_life_days=1e9, ridge=0.01, max_iter=2000, tol=1e-12,
            warm_start=cold,
        )
        self.assertAlmostEqual(warm.log_likelihood, cold.log_likelihood, delta=0.5)

    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            poisson.fit([])


class TestPredict(unittest.TestCase):
    def setUp(self):
        matches, *_ = synthetic_season()
        self.model = poisson.fit(matches, half_life_days=1e9, ridge=0.01)

    def test_probabilities_sum_to_one(self):
        out = self.model.predict("T00", "T01")
        self.assertAlmostEqual(sum(out.as_tuple()), 1.0, places=6)

    def test_score_matrix_sums_to_one(self):
        matrix = self.model.score_matrix("T00", "T01")
        self.assertAlmostEqual(sum(sum(row) for row in matrix), 1.0, places=9)

    def test_pick_is_the_argmax(self):
        out = self.model.predict("T00", "T01")
        best = max(out.as_tuple())
        self.assertEqual(out.confidence, best)
        self.assertIn(out.pick, ("H", "D", "A"))

    def test_home_advantage_is_directional(self):
        forward = self.model.predict("T00", "T01")
        reverse = self.model.predict("T01", "T00")
        self.assertGreater(forward.p_home, reverse.p_away)

    def test_unknown_team_still_produces_valid_probabilities(self):
        self.assertFalse(self.model.knows("Newly Promoted FC"))
        out = self.model.predict("Newly Promoted FC", "T01")
        self.assertAlmostEqual(sum(out.as_tuple()), 1.0, places=6)


class TestNewcomerPrior(unittest.TestCase):
    """Promoted teams score ~68% of the league-average rate and concede ~113%
    of it, so rating an unknown team at league average is a systematic error
    at every season start."""

    def setUp(self):
        self.matches, *_ = synthetic_season()

    def _fit(self, **kwargs):
        return poisson.fit(self.matches, half_life_days=1e9, ridge=0.05, **kwargs)

    def test_unknown_team_is_rated_below_average(self):
        with_prior = self._fit()
        without = self._fit(newcomer_attack=0.0, newcomer_defence=0.0)

        home_goals_prior, _ = with_prior.expected_goals("Promoted FC", "T01")
        home_goals_flat, _ = without.expected_goals("Promoted FC", "T01")
        self.assertLess(home_goals_prior, home_goals_flat)

    def test_unknown_team_concedes_more(self):
        with_prior = self._fit()
        without = self._fit(newcomer_attack=0.0, newcomer_defence=0.0)

        _, away_goals_prior = with_prior.expected_goals("T01", "Promoted FC")
        _, away_goals_flat = without.expected_goals("T01", "Promoted FC")
        # the promoted side away from home scores less than a flat model says
        self.assertLess(away_goals_prior, away_goals_flat)

    def test_established_team_is_barely_affected(self):
        """A side with a full record should be driven by its results, not the
        prior."""
        with_prior = self._fit()
        without = self._fit(newcomer_attack=0.0, newcomer_defence=0.0)
        for team in with_prior.teams:
            self.assertAlmostEqual(
                with_prior.attack[team], without.attack[team], delta=0.05
            )

    def test_prior_strength_zero_restores_flat_shrinkage(self):
        disabled = self._fit(prior_strength=0.0)
        flat = self._fit(newcomer_attack=0.0, newcomer_defence=0.0)
        for team in disabled.teams:
            self.assertAlmostEqual(disabled.attack[team], flat.attack[team], places=6)

    def test_thin_record_is_pulled_toward_the_prior(self):
        """One good result should not make a newly promoted side a title
        contender."""
        newcomer = [
            FakeMatch(date(2020, 12, 1), "Promoted FC", "T00", 3, 0),
            FakeMatch(date(2020, 12, 8), "T01", "Promoted FC", 0, 2),
        ]
        model = poisson.fit(
            self.matches + newcomer, half_life_days=1e9, ridge=0.05
        )
        flat = poisson.fit(
            self.matches + newcomer, half_life_days=1e9, ridge=0.05,
            newcomer_attack=0.0, newcomer_defence=0.0,
        )
        self.assertTrue(model.knows("Promoted FC"))
        self.assertLess(model.attack["Promoted FC"], flat.attack["Promoted FC"])

    def test_prior_fades_as_a_team_accumulates_history(self):
        """The pull toward the prior must weaken with evidence, or a promoted
        side that is genuinely good would never be recognised."""
        few = [
            FakeMatch(date(2020, 12, 1) + timedelta(days=7 * i), "Promoted FC", "T00", 3, 0)
            for i in range(2)
        ]
        many = [
            FakeMatch(date(2020, 12, 1) + timedelta(days=7 * i), "Promoted FC", "T00", 3, 0)
            for i in range(40)
        ]
        thin = poisson.fit(self.matches + few, half_life_days=1e9, ridge=0.05)
        thick = poisson.fit(self.matches + many, half_life_days=1e9, ridge=0.05)
        self.assertGreater(thick.attack["Promoted FC"], thin.attack["Promoted FC"])

    def test_dixon_coles_reshapes_low_scores(self):
        """Negative rho -- the sign real football data produces -- shifts mass
        into 0-0 and 1-1 and out of 1-0 and 0-1."""
        plain = poisson.PoissonDixonColes(
            teams=("A", "B"), attack={"A": 0.0, "B": 0.0},
            defence={"A": 0.0, "B": 0.0}, base=math.log(1.3),
            home_advantage=0.2, rho=0.0, n_matches=0,
            fitted_through=date(2024, 1, 1), half_life_days=180, ridge=0.0,
        )
        corrected = poisson.PoissonDixonColes(**{**plain.__dict__, "rho": -0.1})
        before = plain.score_matrix("A", "B")
        after = corrected.score_matrix("A", "B")

        self.assertGreater(after[0][0], before[0][0])
        self.assertGreater(after[1][1], before[1][1])
        self.assertLess(after[1][0], before[1][0])
        self.assertLess(after[0][1], before[0][1])
        # scorelines outside the corrected cells keep their relative ordering
        self.assertAlmostEqual(sum(sum(r) for r in after), 1.0, places=9)

    def test_fitted_rho_is_negative_on_draw_heavy_data(self):
        """Real football has more 0-0 and 1-1 than independent Poissons expect;
        the fitter should discover a negative rho on data shaped that way."""
        rng = random.Random(5)
        teams = [f"T{i}" for i in range(8)]
        matches, day = [], date(2021, 1, 1)
        for _ in range(6):
            for h in teams:
                for a in teams:
                    if h == a:
                        continue
                    # 45% of games are a 0-0 or 1-1; the rest are ordinary
                    roll = rng.random()
                    if roll < 0.25:
                        goals = (0, 0)
                    elif roll < 0.45:
                        goals = (1, 1)
                    else:
                        goals = (_poisson_sample(rng, 1.4), _poisson_sample(rng, 1.1))
                    matches.append(FakeMatch(day, h, a, *goals))
                    day += timedelta(days=1)

        model = poisson.fit(matches, half_life_days=1e9, ridge=0.01)
        self.assertLess(model.rho, 0.0)


@dataclass
class ShotMatch:
    """A match carrying shot counts, as store.MatchRow does."""

    match_date: date
    home: str
    away: str
    home_goals: int
    away_goals: int
    home_sot: int
    away_sot: int


@dataclass
class InjuryMatch:
    """A match carrying injury counts, as store.MatchRow does."""

    match_date: date
    home: str
    away: str
    home_goals: int
    away_goals: int
    home_injuries: int
    away_injuries: int


class TestExpectedGoalsProxy(unittest.TestCase):
    """Ratings can be fit to a shots-on-target proxy instead of raw goals.

    Real xG is unavailable -- both free providers refuse automated access -- so
    the proxy is built from shot counts we already ingest legally.
    """

    def _league(self, lucky_finisher=False):
        """Two teams create identical chances; one converts far better."""
        matches = []
        day = date(2023, 1, 1)
        for i in range(30):
            # Lucky scores 3 from 5 on target; Steady scores 1 from 5.
            matches.append(ShotMatch(day, "Lucky", "Filler", 3, 1, 5, 5))
            day += timedelta(days=3)
            matches.append(ShotMatch(day, "Steady", "Filler", 1, 1, 5, 5))
            day += timedelta(days=3)
        return matches

    def test_proxy_preserves_the_overall_goal_total(self):
        """The conversion rate is fit from the data, so the blended target
        carries the same weight of goals it replaces."""
        matches = self._league()
        weights = [1.0] * len(matches)
        home, away, conversion = poisson._fit_targets(matches, weights, 1.0)
        actual = sum(m.home_goals + m.away_goals for m in matches)
        proxied = sum(home) + sum(away)
        self.assertAlmostEqual(proxied, actual, places=6)
        self.assertGreater(conversion, 0)

    def test_weight_zero_is_pure_goals(self):
        matches = self._league()
        home, away, conversion = poisson._fit_targets(matches, [1.0] * len(matches), 0.0)
        self.assertEqual(home, [float(m.home_goals) for m in matches])
        self.assertIsNone(conversion)

    def test_proxy_discounts_a_lucky_finisher(self):
        """Lucky and Steady create the same chances; the proxy should rate them
        closer together than raw goals do."""
        matches = self._league()
        goals_model = poisson.fit(matches, half_life_days=1e9, ridge=0.01, xg_weight=0.0)
        proxy_model = poisson.fit(matches, half_life_days=1e9, ridge=0.01, xg_weight=1.0)

        goals_spread = goals_model.attack["Lucky"] - goals_model.attack["Steady"]
        proxy_spread = proxy_model.attack["Lucky"] - proxy_model.attack["Steady"]
        self.assertGreater(goals_spread, 0)
        self.assertLess(proxy_spread, goals_spread)

    def test_blend_sits_between_the_two(self):
        matches = self._league()
        spreads = []
        for weight in (0.0, 0.5, 1.0):
            model = poisson.fit(
                matches, half_life_days=1e9, ridge=0.01, xg_weight=weight
            )
            spreads.append(model.attack["Lucky"] - model.attack["Steady"])
        self.assertGreater(spreads[0], spreads[1])
        self.assertGreater(spreads[1], spreads[2])

    def test_matches_without_shot_data_fall_back_to_goals(self):
        """Backfilled history may lack shot counts; it must still fit."""
        matches, *_ = synthetic_season()  # FakeMatch has no shot fields
        model = poisson.fit(matches, half_life_days=1e9, ridge=0.01, xg_weight=1.0)
        self.assertIsNone(model.sot_conversion)
        out = model.predict("T00", "T01")
        self.assertAlmostEqual(sum(out.as_tuple()), 1.0, places=6)

    def test_mixed_data_uses_the_proxy_only_where_available(self):
        with_shots = self._league()
        without = [
            FakeMatch(date(2022, 1, 1) + timedelta(days=i), "Filler", "Steady", 1, 1)
            for i in range(10)
        ]
        home, _, conversion = poisson._fit_targets(
            with_shots + without, [1.0] * (len(with_shots) + len(without)), 1.0
        )
        self.assertIsNotNone(conversion)
        # the shotless tail keeps its real goals
        self.assertEqual(home[-1], 1.0)

    def test_rho_is_still_fit_against_real_scorelines(self):
        """The low-score correction describes actual results, so it must not be
        fit to fractional proxy values."""
        matches = self._league()
        model = poisson.fit(matches, half_life_days=1e9, ridge=0.01, xg_weight=1.0)
        self.assertGreaterEqual(model.rho, -0.25)
        self.assertLessEqual(model.rho, 0.25)


class TestTemperatureWiring(unittest.TestCase):
    """`temperature` is a pure passthrough -- never fit inside `fit()`, see
    prescore/model/calibration.py. Defaults to the externally-fit production
    value (config.CALIBRATION_TEMPERATURE), same lifecycle as xg_weight;
    identity (1.0, a true no-op) is available by passing it explicitly.
    These only check the wiring, not whether the production value is a good
    one -- that is what tests/test_calibration.py and the README's validation
    numbers are for."""

    def setUp(self):
        matches, *_ = synthetic_season()
        self.matches = matches

    def test_default_is_the_production_value(self):
        model = poisson.fit(self.matches, half_life_days=1e9, ridge=0.05)
        self.assertEqual(model.temperature, config.CALIBRATION_TEMPERATURE)

    def test_default_matches_explicitly_requesting_the_production_value(self):
        default = poisson.fit(self.matches, half_life_days=1e9, ridge=0.05)
        explicit = poisson.fit(
            self.matches, half_life_days=1e9, ridge=0.05,
            temperature=config.CALIBRATION_TEMPERATURE,
        )
        self.assertEqual(
            default.predict("T00", "T01").as_tuple(),
            explicit.predict("T00", "T01").as_tuple(),
        )

    def test_identity_is_available_explicitly(self):
        """1.0 must still give the true, uncalibrated raw probabilities --
        needed by anything (like the calibration validation script) that
        wants the model's output before any correction is applied."""
        calibrated = poisson.fit(self.matches, half_life_days=1e9, ridge=0.05)
        raw = poisson.fit(
            self.matches, half_life_days=1e9, ridge=0.05, temperature=1.0
        )
        self.assertEqual(raw.temperature, 1.0)
        self.assertNotEqual(
            raw.predict("T00", "T01").as_tuple(),
            calibrated.predict("T00", "T01").as_tuple(),
        )

    def test_sharpening_moves_the_pick_probability_up(self):
        model = poisson.fit(
            self.matches, half_life_days=1e9, ridge=0.05, temperature=0.6
        )
        baseline = poisson.fit(self.matches, half_life_days=1e9, ridge=0.05)
        out = model.predict("T00", "T01")
        base_out = baseline.predict("T00", "T01")
        self.assertGreater(out.confidence, base_out.confidence)

    def test_does_not_affect_expected_goals(self):
        """Calibration corrects the 1X2 probability, not the underlying rate."""
        baseline = poisson.fit(self.matches, half_life_days=1e9, ridge=0.05)
        calibrated = poisson.fit(
            self.matches, half_life_days=1e9, ridge=0.05, temperature=0.5
        )
        b_out = baseline.predict("T00", "T01")
        c_out = calibrated.predict("T00", "T01")
        self.assertAlmostEqual(
            b_out.expected_home_goals, c_out.expected_home_goals, places=9
        )
        self.assertAlmostEqual(
            b_out.expected_away_goals, c_out.expected_away_goals, places=9
        )

    def test_does_not_affect_the_raw_score_matrix(self):
        """score_matrix stays raw/uncalibrated -- only predict()'s aggregated
        H/D/A gets the correction, since exact-score markets aren't in scope."""
        baseline = poisson.fit(self.matches, half_life_days=1e9, ridge=0.05)
        calibrated = poisson.fit(
            self.matches, half_life_days=1e9, ridge=0.05, temperature=0.5
        )
        m1 = baseline.score_matrix("T00", "T01")
        m2 = calibrated.score_matrix("T00", "T01")
        self.assertEqual(m1, m2)

    def test_reported_in_params(self):
        model = poisson.fit(
            self.matches, half_life_days=1e9, ridge=0.05, temperature=0.7
        )
        self.assertEqual(model.params()["temperature"], 0.7)

    def test_warm_start_does_not_leak_a_temperature(self):
        """Same footgun class as injury_weight: a caller that doesn't specify
        temperature must get THIS call's default, not whatever an earlier,
        differently-configured warm_start happened to carry."""
        warm = poisson.fit(
            self.matches, half_life_days=1e9, ridge=0.05, temperature=0.5
        )
        cold_again = poisson.fit(
            self.matches, half_life_days=1e9, ridge=0.05, warm_start=warm
        )
        self.assertEqual(cold_again.temperature, config.CALIBRATION_TEMPERATURE)
        self.assertNotEqual(cold_again.temperature, warm.temperature)


class TestInjuryWeight(unittest.TestCase):
    """A per-fixture injury-count covariate on the linear predictor.

    Validated against real 2021-2025 API-Football data and rejected: RPS
    moved in opposite directions on two separate windows (-0.0003 held-out,
    +0.0010 tuned-on), the same "sign flips between windows" signature that
    sank the ELO/ensemble experiment. `fit_injury_weight` defaults False for
    that reason. These tests only cover the mechanism -- that it fits, stays
    off unless asked, and moves predictions the intuitive direction on data
    with a known planted effect -- not that it should be relied on.
    """

    def _league(self, rng_seed=3):
        """Home and Away are equal quality. Home scores fewer goals in
        matches where it is missing more players -- a planted, known effect
        the fitter should be able to recover."""
        rng = random.Random(rng_seed)
        matches = []
        day = date(2023, 1, 1)
        for _ in range(200):
            injuries = rng.choice([0, 0, 2, 5])
            # each missing player knocks the scoring rate down a bit
            rate = max(1.6 - 0.12 * injuries, 0.2)
            hg = _poisson_sample(rng, rate)
            ag = _poisson_sample(rng, 1.6)
            matches.append(InjuryMatch(day, "Home", "Away", hg, ag, injuries, 0))
            day += timedelta(days=2)
        return matches

    def test_off_by_default(self):
        matches = self._league()
        model = poisson.fit(matches, half_life_days=1e9, ridge=0.05)
        self.assertEqual(model.injury_weight, 0.0)

    def test_stays_off_even_with_a_warm_start(self):
        """A caller that never asks for it must never get it by accident."""
        matches = self._league()
        warm = poisson.fit(
            matches, half_life_days=1e9, ridge=0.05, fit_injury_weight=True
        )
        self.assertNotEqual(warm.injury_weight, 0.0)
        cold_again = poisson.fit(
            matches, half_life_days=1e9, ridge=0.05,
            warm_start=warm, fit_injury_weight=False,
        )
        self.assertEqual(cold_again.injury_weight, 0.0)

    def test_recovers_the_planted_direction(self):
        """More home injuries should mean fewer home goals, so the fitted
        coefficient must come out positive under this module's sign
        convention (see expected_goals)."""
        matches = self._league()
        model = poisson.fit(
            matches, half_life_days=1e9, ridge=0.05, fit_injury_weight=True
        )
        self.assertGreater(model.injury_weight, 0.0)

    def test_predictions_shift_with_the_injury_count(self):
        matches = self._league()
        model = poisson.fit(
            matches, half_life_days=1e9, ridge=0.05, fit_injury_weight=True
        )
        healthy = model.predict("Home", "Away", home_injuries=0, away_injuries=0)
        weakened = model.predict("Home", "Away", home_injuries=5, away_injuries=0)
        self.assertGreater(healthy.p_home, weakened.p_home)
        self.assertLess(healthy.p_away, weakened.p_away)

    def test_only_the_differential_matters(self):
        """Both sides down the same number of players should cancel out."""
        matches = self._league()
        model = poisson.fit(
            matches, half_life_days=1e9, ridge=0.05, fit_injury_weight=True
        )
        even_0 = model.predict("Home", "Away", home_injuries=0, away_injuries=0)
        even_3 = model.predict("Home", "Away", home_injuries=3, away_injuries=3)
        self.assertAlmostEqual(even_0.p_home, even_3.p_home, places=9)

    def test_probabilities_still_sum_to_one(self):
        matches = self._league()
        model = poisson.fit(
            matches, half_life_days=1e9, ridge=0.05, fit_injury_weight=True
        )
        out = model.predict("Home", "Away", home_injuries=4, away_injuries=1)
        self.assertAlmostEqual(sum(out.as_tuple()), 1.0, places=6)

    def test_matches_without_injury_data_are_unaffected(self):
        """Backfilled history has no injury fields at all; fitting must not
        crash and must behave as if every count were zero."""
        matches, *_ = synthetic_season()  # FakeMatch has no injury fields
        model = poisson.fit(
            matches, half_life_days=1e9, ridge=0.01, fit_injury_weight=True
        )
        out = model.predict("T00", "T01")
        self.assertAlmostEqual(sum(out.as_tuple()), 1.0, places=6)

    def test_warm_start_carries_the_weight_forward(self):
        matches = self._league()
        first = poisson.fit(
            matches, half_life_days=1e9, ridge=0.05, fit_injury_weight=True
        )
        second = poisson.fit(
            matches, half_life_days=1e9, ridge=0.05,
            warm_start=first, fit_injury_weight=True, max_iter=1,
        )
        # one more iteration from an already-converged start should barely move
        self.assertAlmostEqual(first.injury_weight, second.injury_weight, delta=0.01)


class TestPoissonPmf(unittest.TestCase):
    def test_pmf_matches_closed_form(self):
        pmf = poisson._poisson_pmf(1.7, 12)
        for k in range(13):
            expected = math.exp(-1.7) * 1.7**k / math.factorial(k)
            self.assertAlmostEqual(pmf[k], expected, places=12)

    def test_pmf_nearly_sums_to_one(self):
        self.assertAlmostEqual(sum(poisson._poisson_pmf(2.0, 25)), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
