"""ELO rating and ordered-logit link tests."""

import math
import unittest
from dataclasses import dataclass
from datetime import date, timedelta

from prescore.model import elo, ensemble, poisson


@dataclass
class FakeMatch:
    match_date: date
    home: str
    away: str
    home_goals: int
    away_goals: int


def league(rounds=8):
    """Strong beats Weak consistently; Middle sits between them.

    Includes drawn matches on purpose. With a draw-free fixture the ordered
    logit correctly learns that draws never happen and collapses P(draw) to
    zero -- which says nothing useful about the link.
    """
    teams = ["Strong", "Middle", "Weak"]
    goals = {("Strong", "Middle"): (2, 1), ("Strong", "Weak"): (3, 0),
             ("Middle", "Weak"): (1, 1), ("Middle", "Strong"): (1, 2),
             ("Weak", "Strong"): (0, 2), ("Weak", "Middle"): (1, 1)}
    matches, day = [], date(2023, 1, 1)
    for _ in range(rounds):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                hg, ag = goals[(home, away)]
                matches.append(FakeMatch(day, home, away, hg, ag))
                day += timedelta(days=2)
    return matches


class TestRatingUpdates(unittest.TestCase):
    def test_winner_gains_and_loser_loses(self):
        matches = [FakeMatch(date(2024, 1, 1), "A", "B", 2, 0)]
        model = elo.fit(matches, k_factor=20, home_advantage=0)
        self.assertGreater(model.rating("A"), elo.DEFAULT_RATING)
        self.assertLess(model.rating("B"), elo.DEFAULT_RATING)

    def test_updates_are_zero_sum(self):
        matches = [FakeMatch(date(2024, 1, 1), "A", "B", 2, 0)]
        model = elo.fit(matches, k_factor=20, home_advantage=0)
        total = model.rating("A") + model.rating("B")
        self.assertAlmostEqual(total, 2 * elo.DEFAULT_RATING, places=9)

    def test_bigger_margin_moves_ratings_further(self):
        narrow = elo.fit([FakeMatch(date(2024, 1, 1), "A", "B", 1, 0)], home_advantage=0)
        wide = elo.fit([FakeMatch(date(2024, 1, 1), "A", "B", 5, 0)], home_advantage=0)
        self.assertGreater(wide.rating("A"), narrow.rating("A"))

    def test_margin_scaling_can_be_disabled(self):
        wide = elo.fit(
            [FakeMatch(date(2024, 1, 1), "A", "B", 5, 0)],
            home_advantage=0, use_margin=False,
        )
        narrow = elo.fit(
            [FakeMatch(date(2024, 1, 1), "A", "B", 1, 0)],
            home_advantage=0, use_margin=False,
        )
        self.assertAlmostEqual(wide.rating("A"), narrow.rating("A"), places=9)

    def test_a_draw_between_equals_changes_nothing(self):
        matches = [FakeMatch(date(2024, 1, 1), "A", "B", 1, 1)]
        model = elo.fit(matches, home_advantage=0)
        self.assertAlmostEqual(model.rating("A"), elo.DEFAULT_RATING, places=6)

    def test_beating_a_stronger_team_gains_more(self):
        """An upset is more surprising, so it should move ratings further."""
        setup = [FakeMatch(date(2024, 1, 1) + timedelta(days=i), "Strong", "Weak", 3, 0)
                 for i in range(10)]
        upset = setup + [FakeMatch(date(2024, 3, 1), "Other", "Strong", 1, 0)]
        expected = setup + [FakeMatch(date(2024, 3, 1), "Other", "Weak", 1, 0)]

        upset_model = elo.fit(upset, home_advantage=0)
        expected_model = elo.fit(expected, home_advantage=0)
        self.assertGreater(
            upset_model.rating("Other"), expected_model.rating("Other")
        )

    def test_ordering_reflects_strength(self):
        model = elo.fit(league(), home_advantage=0)
        table = [name for name, _ in model.ratings_table()]
        self.assertEqual(table, ["Strong", "Middle", "Weak"])

    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            elo.fit([])


class TestProbabilities(unittest.TestCase):
    def setUp(self):
        self.model = elo.fit(league())

    def test_probabilities_sum_to_one(self):
        out = self.model.predict("Strong", "Weak")
        self.assertAlmostEqual(sum(out.as_tuple()), 1.0, places=9)

    def test_stronger_team_is_favoured(self):
        strong = self.model.predict("Strong", "Weak")
        weak = self.model.predict("Weak", "Strong")
        self.assertGreater(strong.p_home, weak.p_home)

    def test_home_advantage_is_directional(self):
        forward = self.model.predict("Strong", "Middle")
        reverse = self.model.predict("Middle", "Strong")
        self.assertGreater(forward.p_home, reverse.p_away)

    def test_evenly_matched_teams_get_a_real_draw_probability(self):
        """Middle and Weak draw every time they meet, so the link should put
        substantial mass on the draw at a small rating gap."""
        out = self.model.predict("Middle", "Weak")
        self.assertGreater(out.p_draw, 0.15)
        self.assertLess(out.p_draw, 0.95)

    def test_draw_is_likelier_between_evenly_matched_teams(self):
        even = self.model.predict("Middle", "Weak").p_draw
        lopsided = self.model.predict("Strong", "Weak").p_draw
        self.assertGreater(even, lopsided)

    def test_unknown_team_uses_the_default_rating(self):
        self.assertFalse(self.model.knows("Newcomer"))
        self.assertEqual(self.model.rating("Newcomer"), elo.DEFAULT_RATING)
        out = self.model.predict("Strong", "Newcomer")
        self.assertAlmostEqual(sum(out.as_tuple()), 1.0, places=9)

    def test_thresholds_stay_ordered(self):
        self.assertLess(self.model.threshold_low, self.model.threshold_high)

    def test_link_fit_beats_its_starting_point(self):
        matches = league()
        model = elo.fit(matches)
        samples = []
        for m in matches:
            result = (
                "H" if m.home_goals > m.away_goals
                else "A" if m.away_goals > m.home_goals else "D"
            )
            samples.append((0.1, result, 1.0))
        naive = elo._link_log_likelihood(samples, 1.0, -0.6, math.log(1.2))
        self.assertGreater(model.log_likelihood, naive * 3)


class TestEnsemble(unittest.TestCase):
    def setUp(self):
        matches = league()
        self.poisson = poisson.fit(matches, half_life_days=1e9, ridge=0.05)
        self.elo = elo.fit(matches)

    def _blend(self, weight):
        return ensemble.Ensemble(
            primary=self.poisson, secondary=self.elo,
            weight=weight, fitted_through=date(2024, 1, 1),
        )

    def test_blend_sums_to_one(self):
        out = self._blend(0.5).predict("Strong", "Weak")
        self.assertAlmostEqual(sum(out.as_tuple()), 1.0, places=9)

    def test_weight_one_is_the_primary(self):
        blended = self._blend(1.0).predict("Strong", "Weak")
        direct = self.poisson.predict("Strong", "Weak")
        self.assertAlmostEqual(blended.p_home, direct.p_home, places=9)

    def test_weight_zero_is_the_secondary(self):
        blended = self._blend(0.0).predict("Strong", "Weak")
        direct = self.elo.predict("Strong", "Weak")
        self.assertAlmostEqual(blended.p_home, direct.p_home, places=9)

    def test_blend_lies_between_its_members(self):
        a = self.poisson.predict("Strong", "Middle").p_home
        b = self.elo.predict("Strong", "Middle").p_home
        mid = self._blend(0.5).predict("Strong", "Middle").p_home
        self.assertGreaterEqual(mid, min(a, b) - 1e-9)
        self.assertLessEqual(mid, max(a, b) + 1e-9)

    def test_knows_a_team_either_member_knows(self):
        blend = self._blend(0.5)
        self.assertTrue(blend.knows("Strong"))
        self.assertFalse(blend.knows("Nobody"))


if __name__ == "__main__":
    unittest.main()
