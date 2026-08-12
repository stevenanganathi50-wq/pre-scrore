"""Parsing tests for TheSportsDB event payloads."""

import unittest

from prescore.ingest import thesportsdb as tsdb

SCHEDULED = {
    "idEvent": "2494000",
    "strTimestamp": "2026-08-21T19:00:00",
    "dateEvent": "2026-08-21",
    "strTime": "19:00:00",
    "strHomeTeam": "Arsenal",
    "strAwayTeam": "Coventry City",
    "intHomeScore": None,
    "intAwayScore": None,
    "intRound": "1",
    "strSeason": "2026-2027",
    "strStatus": "NS",
    "strPostponed": "no",
}

FINISHED = {
    "idEvent": "2400001",
    "strTimestamp": "2026-05-24T15:00:00",
    "strHomeTeam": "West Ham United",
    "strAwayTeam": "Leeds United",
    "intHomeScore": "3",
    "intAwayScore": "0",
    "intRound": "38",
    "strSeason": "2025-2026",
    "strStatus": "FT",
    "strPostponed": "no",
}


class TestSeasonHelpers(unittest.TestCase):
    def test_season_string(self):
        self.assertEqual(tsdb.season_string(2026), "2026-2027")

    def test_season_start_year(self):
        self.assertEqual(tsdb.season_start_year("2026-2027"), 2026)

    def test_season_start_year_handles_junk(self):
        self.assertIsNone(tsdb.season_start_year("not-a-season"))
        self.assertIsNone(tsdb.season_start_year(None))


class TestParseEvent(unittest.TestCase):
    def test_scheduled_event(self):
        parsed = tsdb.parse_event(SCHEDULED)
        self.assertEqual(parsed["status"], "scheduled")
        self.assertEqual(parsed["kickoff_utc"], "2026-08-21T19:00:00Z")
        self.assertEqual(parsed["match_date"], "2026-08-21")
        self.assertEqual(parsed["kickoff_time"], "19:00")
        self.assertEqual(parsed["round"], 1)
        self.assertEqual(parsed["season"], 2026)
        self.assertIsNone(parsed["result"])
        self.assertIsNone(parsed["home_goals"])

    def test_finished_event(self):
        parsed = tsdb.parse_event(FINISHED)
        self.assertEqual(parsed["status"], "finished")
        self.assertEqual(parsed["home_goals"], 3)
        self.assertEqual(parsed["away_goals"], 0)
        self.assertEqual(parsed["result"], "H")

    def test_draw_is_derived(self):
        event = dict(FINISHED, intHomeScore="1", intAwayScore="1")
        self.assertEqual(tsdb.parse_event(event)["result"], "D")

    def test_away_win_is_derived(self):
        event = dict(FINISHED, intHomeScore="0", intAwayScore="2")
        self.assertEqual(tsdb.parse_event(event)["result"], "A")

    def test_zero_zero_counts_as_finished(self):
        """0-0 is falsy in a naive check; it must still be a finished match."""
        event = dict(FINISHED, intHomeScore="0", intAwayScore="0")
        parsed = tsdb.parse_event(event)
        self.assertEqual(parsed["status"], "finished")
        self.assertEqual(parsed["result"], "D")

    def test_empty_string_scores_mean_not_played(self):
        event = dict(FINISHED, intHomeScore="", intAwayScore="")
        self.assertEqual(tsdb.parse_event(event)["status"], "scheduled")

    def test_falls_back_to_date_and_time_when_timestamp_missing(self):
        event = dict(SCHEDULED, strTimestamp="")
        self.assertEqual(tsdb.parse_event(event)["kickoff_utc"], "2026-08-21T19:00:00Z")

    def test_rejects_event_without_teams(self):
        self.assertIsNone(tsdb.parse_event(dict(SCHEDULED, strHomeTeam="")))

    def test_rejects_event_without_any_date(self):
        event = dict(SCHEDULED, strTimestamp="", dateEvent="")
        self.assertIsNone(tsdb.parse_event(event))

    def test_missing_round_becomes_none(self):
        self.assertIsNone(tsdb.parse_event(dict(SCHEDULED, intRound=None))["round"])

    def test_postponed_flag_is_carried(self):
        self.assertTrue(tsdb.parse_event(dict(SCHEDULED, strPostponed="yes"))["postponed"])


class TestSyncReport(unittest.TestCase):
    def test_reports_unresolved_names_loudly(self):
        report = tsdb.SyncReport()
        report.unresolved_teams.add("Hornchurch")
        self.assertIn("UNRESOLVED", report.as_text())
        self.assertIn("Hornchurch", report.as_text())

    def test_counts_add_up(self):
        report = tsdb.SyncReport()
        report.scheduled, report.finished = 7, 3
        self.assertEqual(report.total, 10)
        self.assertIn("fixtures 10", report.as_text())


if __name__ == "__main__":
    unittest.main()
