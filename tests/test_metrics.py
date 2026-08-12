"""Scoring rule tests, checked against hand-computed values."""

import math
import unittest

from prescore.backtest import metrics


class TestScoringRules(unittest.TestCase):
    def test_log_loss_of_certainty(self):
        self.assertAlmostEqual(metrics.log_loss((1.0, 0.0, 0.0), "H"), 0.0, places=9)

    def test_log_loss_of_uniform(self):
        self.assertAlmostEqual(
            metrics.log_loss((1 / 3, 1 / 3, 1 / 3), "D"), math.log(3), places=9
        )

    def test_log_loss_punishes_confident_miss(self):
        confident = metrics.log_loss((0.95, 0.03, 0.02), "A")
        hedged = metrics.log_loss((0.40, 0.30, 0.30), "A")
        self.assertGreater(confident, hedged)

    def test_brier_hand_computed(self):
        # (0.6-1)^2 + (0.3-0)^2 + (0.1-0)^2 = 0.16 + 0.09 + 0.01
        self.assertAlmostEqual(metrics.brier((0.6, 0.3, 0.1), "H"), 0.26, places=9)

    def test_rps_hand_computed(self):
        # cumulative predicted (0.6, 0.9) vs observed (1, 1)
        # ((0.6-1)^2 + (0.9-1)^2) / 2 = (0.16 + 0.01) / 2
        self.assertAlmostEqual(metrics.rps((0.6, 0.3, 0.1), "H"), 0.085, places=9)

    def test_rps_respects_outcome_ordering(self):
        """Calling a home win when it was a draw beats calling it an away win."""
        probs = (0.7, 0.2, 0.1)
        self.assertLess(metrics.rps(probs, "D"), metrics.rps(probs, "A"))

    def test_perfect_prediction_scores_zero(self):
        for outcome in ("H", "D", "A"):
            probs = tuple(1.0 if o == outcome else 0.0 for o in metrics.OUTCOMES)
            self.assertAlmostEqual(metrics.rps(probs, outcome), 0.0, places=12)
            self.assertAlmostEqual(metrics.brier(probs, outcome), 0.0, places=12)


class TestDevig(unittest.TestCase):
    def test_removes_overround(self):
        probs = metrics.devig((2.0, 4.0, 4.0))
        self.assertAlmostEqual(sum(probs), 1.0, places=12)
        self.assertAlmostEqual(probs[0], 0.5, places=12)

    def test_fair_book_is_unchanged(self):
        probs = metrics.devig((2.0, 4.0, 4.0))
        self.assertAlmostEqual(probs[1], probs[2], places=12)

    def test_missing_odds_return_none(self):
        self.assertIsNone(metrics.devig((None, 3.0, 4.0)))
        self.assertIsNone(metrics.devig((1.0, 3.0, 4.0)))


class TestScorecard(unittest.TestCase):
    def test_counts_hits_by_pick(self):
        card = metrics.Scorecard("test")
        card.add((0.6, 0.3, 0.1), "H")  # hit
        card.add((0.6, 0.3, 0.1), "A")  # miss
        card.add((0.1, 0.2, 0.7), "A")  # hit
        self.assertEqual(card.n, 3)
        self.assertEqual(card.hits, 2)
        self.assertAlmostEqual(card.accuracy, 2 / 3)
        self.assertEqual(card.by_pick["H"], [2, 1])
        self.assertEqual(card.by_pick["A"], [1, 1])

    def test_empty_scorecard_is_safe(self):
        card = metrics.Scorecard("empty")
        self.assertEqual(card.accuracy, 0.0)
        self.assertEqual(card.log_loss, 0.0)


class TestCalibration(unittest.TestCase):
    def test_perfectly_calibrated_input(self):
        """Assign 0.5 to home, and let home actually win half the time."""
        records = []
        for i in range(200):
            records.append(((0.5, 0.25, 0.25), "H" if i % 2 == 0 else "D"))
        rows = metrics.calibration(records, bins=10)
        bucket = next(r for r in rows if r["range"] == "0.5-0.6")
        self.assertAlmostEqual(bucket["predicted"], 0.5, places=9)
        self.assertAlmostEqual(bucket["observed"], 0.5, places=9)

    def test_confidence_buckets_split_by_max_probability(self):
        records = [
            ((0.8, 0.1, 0.1), "H"),      # confident and right
            ((0.45, 0.30, 0.25), "A"),   # leaning home, wrong
            ((0.34, 0.33, 0.33), "H"),   # coin flip, right
        ]
        rows = metrics.confidence_buckets(records)
        by_range = {r["range"]: r for r in rows}
        self.assertEqual(by_range["0.70-1.00"]["n"], 1)
        self.assertEqual(by_range["0.70-1.00"]["accuracy"], 1.0)
        self.assertEqual(by_range["0.40-0.50"]["n"], 1)
        self.assertEqual(by_range["0.40-0.50"]["accuracy"], 0.0)
        self.assertEqual(by_range["0.00-0.40"]["n"], 1)
        self.assertEqual(by_range["0.00-0.40"]["accuracy"], 1.0)

    def test_empty_buckets_are_omitted(self):
        rows = metrics.confidence_buckets([((0.8, 0.1, 0.1), "H")])
        self.assertEqual([r["range"] for r in rows], ["0.70-1.00"])


if __name__ == "__main__":
    unittest.main()
