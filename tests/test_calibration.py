"""Temperature scaling: the pure math, and its fitting procedure."""

import random
import unittest

from prescore.model import calibration


class TestApplyTemperature(unittest.TestCase):
    def test_identity_is_a_no_op(self):
        probs = (0.6, 0.25, 0.15)
        self.assertEqual(calibration.apply_temperature(probs, 1.0), probs)

    def test_result_sums_to_one(self):
        for t in (0.3, 0.5, 0.8, 1.0, 1.3, 2.0):
            out = calibration.apply_temperature((0.7, 0.2, 0.1), t)
            self.assertAlmostEqual(sum(out), 1.0, places=9)

    def test_sharpening_increases_the_leading_probability(self):
        """T < 1 should push an already-favoured outcome further ahead."""
        probs = (0.6, 0.25, 0.15)
        sharpened = calibration.apply_temperature(probs, 0.5)
        self.assertGreater(sharpened[0], probs[0])
        self.assertLess(sharpened[2], probs[2])

    def test_flattening_moves_toward_uniform(self):
        """T > 1 should pull every probability closer to 1/3."""
        probs = (0.6, 0.25, 0.15)
        flattened = calibration.apply_temperature(probs, 2.0)
        self.assertLess(flattened[0], probs[0])
        self.assertGreater(flattened[2], probs[2])

    def test_uniform_input_is_unaffected_by_any_temperature(self):
        """1/3, 1/3, 1/3 has nowhere to sharpen or flatten toward."""
        uniform = (1 / 3, 1 / 3, 1 / 3)
        for t in (0.3, 0.7, 1.5):
            out = calibration.apply_temperature(uniform, t)
            for p in out:
                self.assertAlmostEqual(p, 1 / 3, places=9)

    def test_rejects_nonpositive_temperature(self):
        with self.assertRaises(ValueError):
            calibration.apply_temperature((0.5, 0.3, 0.2), 0.0)
        with self.assertRaises(ValueError):
            calibration.apply_temperature((0.5, 0.3, 0.2), -1.0)

    def test_extreme_sharpening_approaches_a_one_hot(self):
        probs = (0.5, 0.3, 0.2)
        out = calibration.apply_temperature(probs, 0.02)
        self.assertGreater(out[0], 0.99)


class TestFitTemperature(unittest.TestCase):
    def _records(self, true_temperature, n=400, seed=1):
        """Synthetic data: a model whose raw probabilities need exactly
        `true_temperature` applied to be perfectly calibrated."""
        rng = random.Random(seed)
        records = []
        base_probs = [
            (0.75, 0.15, 0.10),
            (0.55, 0.25, 0.20),
            (0.40, 0.30, 0.30),
            (0.30, 0.30, 0.40),
        ]
        for i in range(n):
            probs = base_probs[i % len(base_probs)]
            # sample the actual outcome from the TRUE (post-temperature)
            # distribution, so fitting should recover true_temperature
            true_probs = calibration.apply_temperature(probs, true_temperature)
            roll = rng.random()
            actual = (
                "H" if roll < true_probs[0]
                else "D" if roll < true_probs[0] + true_probs[1]
                else "A"
            )
            records.append((probs, actual))
        return records

    def test_recovers_a_known_sharpening_temperature(self):
        records = self._records(true_temperature=0.6, n=3000)
        fitted = calibration.fit_temperature(records)
        self.assertAlmostEqual(fitted, 0.6, delta=0.1)

    def test_recovers_a_known_flattening_temperature(self):
        records = self._records(true_temperature=1.6, n=3000)
        fitted = calibration.fit_temperature(records)
        self.assertAlmostEqual(fitted, 1.6, delta=0.15)

    def test_well_calibrated_data_fits_close_to_identity(self):
        records = self._records(true_temperature=1.0, n=3000)
        fitted = calibration.fit_temperature(records)
        self.assertAlmostEqual(fitted, 1.0, delta=0.1)

    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            calibration.fit_temperature([])

    def test_fitted_temperature_never_makes_loss_worse_than_identity(self):
        records = self._records(true_temperature=0.7, n=1000)
        fitted = calibration.fit_temperature(records)
        loss_fitted = calibration._mean_log_loss(records, fitted)
        loss_identity = calibration._mean_log_loss(records, calibration.IDENTITY)
        self.assertLessEqual(loss_fitted, loss_identity)


if __name__ == "__main__":
    unittest.main()
