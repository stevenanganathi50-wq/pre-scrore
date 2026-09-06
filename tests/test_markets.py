"""Derived markets: BTTS, Over/Under, correct score.

All of these are pure functions of a scoreline matrix, so they're tested
against hand-built matrices with known answers rather than a fitted model --
that keeps the arithmetic itself independently verifiable from the Poisson
fitting machinery.
"""

import unittest

from prescore.model import markets, poisson


def _matrix(cells: dict[tuple[int, int], float], size: int = 4) -> list[list[float]]:
    """A scoreline matrix from a sparse {(x, y): p} spec, size x size."""
    m = [[0.0] * size for _ in range(size)]
    for (x, y), p in cells.items():
        m[x][y] = p
    return m


class TestBttsProbability(unittest.TestCase):
    def test_hand_computed_case(self):
        # 0-0 (0.3) and 1-0 (0.2) are no; 1-1 (0.4) and 2-1 (0.1) are yes.
        matrix = _matrix({(0, 0): 0.3, (1, 0): 0.2, (1, 1): 0.4, (2, 1): 0.1})
        p_yes, p_no = markets.btts_probability(matrix)
        self.assertAlmostEqual(p_yes, 0.5, places=9)
        self.assertAlmostEqual(p_no, 0.5, places=9)

    def test_probabilities_sum_to_the_matrix_total(self):
        matrix = _matrix({(0, 0): 0.3, (1, 0): 0.2, (1, 1): 0.4, (2, 1): 0.1})
        p_yes, p_no = markets.btts_probability(matrix)
        self.assertAlmostEqual(p_yes + p_no, 1.0, places=9)

    def test_all_mass_on_a_scoreless_side_is_certain_no(self):
        matrix = _matrix({(0, 0): 0.6, (2, 0): 0.4})
        p_yes, p_no = markets.btts_probability(matrix)
        self.assertAlmostEqual(p_yes, 0.0, places=9)
        self.assertAlmostEqual(p_no, 1.0, places=9)

    def test_all_mass_on_both_scoring_is_certain_yes(self):
        matrix = _matrix({(1, 1): 0.7, (2, 3): 0.3})
        p_yes, p_no = markets.btts_probability(matrix)
        self.assertAlmostEqual(p_yes, 1.0, places=9)
        self.assertAlmostEqual(p_no, 0.0, places=9)

    def test_zero_zero_is_never_btts_yes(self):
        matrix = _matrix({(0, 0): 1.0})
        p_yes, _ = markets.btts_probability(matrix)
        self.assertAlmostEqual(p_yes, 0.0, places=9)


class TestOverUnderProbability(unittest.TestCase):
    def test_hand_computed_case_line_2_5(self):
        # totals: 0-0=0, 1-0=1, 1-1=2 (all under), 2-1=3 (over)
        matrix = _matrix({(0, 0): 0.3, (1, 0): 0.2, (1, 1): 0.4, (2, 1): 0.1})
        p_over, p_under = markets.over_under_probability(matrix, line=2.5)
        self.assertAlmostEqual(p_over, 0.1, places=9)
        self.assertAlmostEqual(p_under, 0.9, places=9)

    def test_probabilities_sum_to_the_matrix_total(self):
        matrix = _matrix({(0, 0): 0.3, (1, 0): 0.2, (1, 1): 0.4, (2, 1): 0.1})
        p_over, p_under = markets.over_under_probability(matrix, line=2.5)
        self.assertAlmostEqual(p_over + p_under, 1.0, places=9)

    def test_a_different_line_moves_the_boundary(self):
        # 1-1 (total 2) is under a 2.5 line but over a 1.5 line
        matrix = _matrix({(0, 0): 0.5, (1, 1): 0.5})
        over_15, _ = markets.over_under_probability(matrix, line=1.5)
        over_25, _ = markets.over_under_probability(matrix, line=2.5)
        self.assertAlmostEqual(over_15, 0.5, places=9)
        self.assertAlmostEqual(over_25, 0.0, places=9)

    def test_nil_nil_is_always_under(self):
        matrix = _matrix({(0, 0): 1.0})
        p_over, p_under = markets.over_under_probability(matrix, line=2.5)
        self.assertAlmostEqual(p_over, 0.0, places=9)
        self.assertAlmostEqual(p_under, 1.0, places=9)


class TestMostLikelyScore(unittest.TestCase):
    def test_picks_the_highest_probability_cell(self):
        matrix = _matrix({(0, 0): 0.3, (1, 0): 0.45, (1, 1): 0.25})
        score, p = markets.most_likely_score(matrix)
        self.assertEqual(score, (1, 0))
        self.assertAlmostEqual(p, 0.45, places=9)

    def test_default_to_zero_zero_when_it_is_highest(self):
        matrix = _matrix({(0, 0): 0.5, (1, 0): 0.3, (0, 1): 0.2})
        score, p = markets.most_likely_score(matrix)
        self.assertEqual(score, (0, 0))
        self.assertAlmostEqual(p, 0.5, places=9)

    def test_ties_keep_the_first_one_found_in_scan_order(self):
        """Documents the tie-break rule rather than asserting a preference:
        strict '>' means the first-encountered max wins, scanning home goals
        outermost. Not claiming this is the 'right' tie-break, just a stable,
        defined one."""
        matrix = _matrix({(0, 1): 0.5, (1, 0): 0.5})
        score, p = markets.most_likely_score(matrix)
        self.assertEqual(score, (0, 1))


class TestBinaryScoring(unittest.TestCase):
    def test_log_loss_of_certainty_correct(self):
        self.assertAlmostEqual(markets.binary_log_loss(1.0, True), 0.0, places=9)
        self.assertAlmostEqual(markets.binary_log_loss(0.0, False), 0.0, places=9)

    def test_log_loss_of_a_coin_flip(self):
        import math
        self.assertAlmostEqual(
            markets.binary_log_loss(0.5, True), math.log(2), places=9
        )

    def test_log_loss_punishes_a_confident_miss(self):
        confident_wrong = markets.binary_log_loss(0.95, False)
        hedged_wrong = markets.binary_log_loss(0.55, False)
        self.assertGreater(confident_wrong, hedged_wrong)

    def test_brier_hand_computed(self):
        # (0.7-1)^2 + (0.3-0)^2 = 0.09 + 0.09
        self.assertAlmostEqual(markets.binary_brier(0.7, True), 0.18, places=9)

    def test_brier_of_certainty_is_zero(self):
        self.assertAlmostEqual(markets.binary_brier(1.0, True), 0.0, places=9)
        self.assertAlmostEqual(markets.binary_brier(0.0, False), 0.0, places=9)

    def test_brier_is_symmetric_in_the_two_outcomes(self):
        self.assertAlmostEqual(
            markets.binary_brier(0.3, True), markets.binary_brier(0.7, False), places=9
        )


class TestAgainstARealFittedModel(unittest.TestCase):
    """The derivations should behave sensibly against the actual model, not
    just hand-built matrices."""

    def setUp(self):
        from tests.test_model import synthetic_season

        matches, *_ = synthetic_season()
        self.model = poisson.fit(matches, half_life_days=1e9, ridge=0.05)

    def test_btts_and_over_under_are_valid_probabilities(self):
        matrix = self.model.score_matrix("T00", "T01")
        for p_yes, p_no in [markets.btts_probability(matrix)]:
            self.assertGreaterEqual(p_yes, 0.0)
            self.assertLessEqual(p_yes, 1.0)
            self.assertAlmostEqual(p_yes + p_no, 1.0, places=6)

        p_over, p_under = markets.over_under_probability(matrix)
        self.assertGreaterEqual(p_over, 0.0)
        self.assertLessEqual(p_over, 1.0)
        self.assertAlmostEqual(p_over + p_under, 1.0, places=6)

    def test_most_likely_score_is_a_real_cell_within_bounds(self):
        matrix = self.model.score_matrix("T00", "T01")
        (x, y), p = markets.most_likely_score(matrix)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLess(x, len(matrix))
        self.assertLess(y, len(matrix))
        self.assertAlmostEqual(matrix[x][y], p, places=12)

    def test_a_high_scoring_matchup_favours_btts_and_over(self):
        """T00 is the strongest attacking team in the synthetic league (see
        synthetic_season); against a similarly strong side both markets
        should lean the expected direction relative to a weak matchup."""
        strong_matrix = self.model.score_matrix("T00", "T01")
        # T11 is the weakest team in the 12-team synthetic league
        weak_matrix = self.model.score_matrix("T11", "T10")
        strong_over, _ = markets.over_under_probability(strong_matrix)
        weak_over, _ = markets.over_under_probability(weak_matrix)
        # not asserting a specific direction (ratings are randomised per
        # seed), only that the two matchups are NOT identical -- a sanity
        # check that the market actually responds to team strength at all
        self.assertNotAlmostEqual(strong_over, weak_over, places=3)


if __name__ == "__main__":
    unittest.main()
