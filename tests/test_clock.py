"""Timestamp handling.

The 'prediction was made before kickoff' guarantee is a SQL string comparison,
so these tests are about that format holding.
"""

import unittest
from datetime import datetime, timedelta, timezone

from prescore import clock


class TestFormat(unittest.TestCase):
    def test_canonical_shape(self):
        moment = datetime(2026, 8, 21, 19, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(clock.to_iso(moment), "2026-08-21T19:00:00Z")

    def test_naive_input_is_treated_as_utc(self):
        naive = datetime(2026, 8, 21, 19, 0, 0)
        self.assertEqual(clock.to_iso(naive), "2026-08-21T19:00:00Z")

    def test_non_utc_input_is_converted(self):
        plus_two = timezone(timedelta(hours=2))
        moment = datetime(2026, 8, 21, 21, 0, 0, tzinfo=plus_two)
        self.assertEqual(clock.to_iso(moment), "2026-08-21T19:00:00Z")

    def test_round_trip(self):
        original = "2026-08-21T19:00:00Z"
        self.assertEqual(clock.to_iso(clock.parse_iso(original)), original)


class TestParsing(unittest.TestCase):
    def test_accepts_provider_variants(self):
        expected = "2026-08-21T19:00:00Z"
        for variant in (
            "2026-08-21T19:00:00",
            "2026-08-21T19:00:00Z",
            "2026-08-21T19:00:00+00:00",
            "2026-08-21 19:00:00",
        ):
            self.assertEqual(clock.normalize(variant), expected, variant)

    def test_offset_is_respected(self):
        self.assertEqual(
            clock.normalize("2026-08-21T21:00:00+02:00"), "2026-08-21T19:00:00Z"
        )

    def test_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            clock.parse_iso("")


class TestOrdering(unittest.TestCase):
    def test_string_order_matches_chronological_order(self):
        """This is what the before-kickoff trigger relies on."""
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        stamps = [clock.to_iso(base + timedelta(hours=7 * i)) for i in range(400)]
        self.assertEqual(stamps, sorted(stamps))

    def test_fixed_width_across_the_year(self):
        base = datetime(2026, 1, 1, 5, 4, 3, tzinfo=timezone.utc)
        widths = {len(clock.to_iso(base + timedelta(days=d))) for d in range(0, 365, 17)}
        self.assertEqual(widths, {20})

    def test_now_is_in_canonical_format(self):
        self.assertEqual(clock.to_iso(clock.parse_iso(clock.now_iso())), clock.now_iso())


if __name__ == "__main__":
    unittest.main()
