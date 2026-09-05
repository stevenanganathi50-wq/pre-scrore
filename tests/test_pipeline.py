"""End-to-end tests for the publish/grade loop and its database guarantees."""

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from prescore import clock, config, export, publish, store, teams

TEAMS = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]


def seed_history(conn, seasons=4):
    """A synthetic league with enough finished matches for the model to fit.

    Alpha wins a lot and Foxtrot loses a lot, so predictions are directional
    and the tests can assert on them. Each season needs its own `season` value
    -- matches are unique on (league, season, home, away), so reusing one would
    make every season upsert over the last.
    """
    strength = {t: i for i, t in enumerate(reversed(TEAMS))}
    for offset in range(seasons):
        season = 2022 + offset
        day = date(season, 8, 1)
        for home in TEAMS:
            for away in TEAMS:
                if home == away:
                    continue
                hg = 1 + max(0, strength[home] - strength[away])
                ag = 1 + max(0, strength[away] - strength[home])
                result = "H" if hg > ag else "A" if ag > hg else "D"
                store.upsert_match(
                    conn,
                    source="test",
                    league="EPL",
                    season=season,
                    match_date=day.isoformat(),
                    kickoff_time="15:00",
                    home_team_id=store.team_id(conn, home),
                    away_team_id=store.team_id(conn, away),
                    status="finished",
                    home_goals=hg,
                    away_goals=ag,
                    result=result,
                )
                day += timedelta(days=1)
    conn.commit()


def add_fixture(conn, home, away, kickoff_utc, season=2026):
    store.upsert_match(
        conn,
        source="test",
        league="EPL",
        season=season,
        match_date=kickoff_utc[:10],
        kickoff_time=kickoff_utc[11:16],
        kickoff_utc=kickoff_utc,
        round_no=1,
        home_team_id=store.team_id(conn, home),
        away_team_id=store.team_id(conn, away),
        status="scheduled",
        home_goals=None,
        away_goals=None,
        result=None,
    )
    conn.commit()
    row = conn.execute(
        """SELECT m.id FROM matches m
           JOIN teams h ON h.id = m.home_team_id
           JOIN teams a ON a.id = m.away_team_id
           WHERE h.name = ? AND a.name = ? AND m.season = ?""",
        (home, away, season),
    ).fetchone()
    return int(row["id"])


def finish_match(conn, match_id, home_goals, away_goals):
    """Record a result without touching kickoff_utc."""
    result = (
        "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D"
    )
    conn.execute(
        """UPDATE matches SET status = 'finished', home_goals = ?,
           away_goals = ?, result = ? WHERE id = ?""",
        (home_goals, away_goals, result, match_id),
    )
    conn.commit()


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        self.conn = store.connect(self.db_path)
        store.init_schema(self.conn)
        seed_history(self.conn)

        now = clock.utc_now()
        self.soon = clock.to_iso(now + timedelta(days=2))
        self.later = clock.to_iso(now + timedelta(days=30))
        self.past = clock.to_iso(now - timedelta(days=2))

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()


class TestImmutabilityGuarantees(PipelineTestCase):
    """The claims the product is built on, enforced by the database."""

    def test_prediction_after_kickoff_is_rejected(self):
        match_id = add_fixture(self.conn, "Alpha", "Bravo", self.past)
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            store.insert_prediction(
                self.conn,
                match_id=match_id,
                model_version="test",
                probs=(0.5, 0.3, 0.2),
                pick="H",
                confidence=0.5,
                created_at=clock.now_iso(),
            )
        self.assertIn("kickoff", str(ctx.exception).lower())

    def test_prediction_exactly_at_kickoff_is_rejected(self):
        match_id = add_fixture(self.conn, "Alpha", "Bravo", self.soon)
        with self.assertRaises(sqlite3.IntegrityError):
            store.insert_prediction(
                self.conn, match_id=match_id, model_version="test",
                probs=(0.5, 0.3, 0.2), pick="H", confidence=0.5,
                created_at=self.soon,
            )

    def test_prediction_before_kickoff_is_accepted(self):
        match_id = add_fixture(self.conn, "Alpha", "Bravo", self.soon)
        pid = store.insert_prediction(
            self.conn, match_id=match_id, model_version="test",
            probs=(0.5, 0.3, 0.2), pick="H", confidence=0.5,
            created_at=clock.now_iso(),
        )
        self.assertGreater(pid, 0)

    def test_predictions_cannot_be_updated(self):
        match_id = add_fixture(self.conn, "Alpha", "Bravo", self.soon)
        pid = store.insert_prediction(
            self.conn, match_id=match_id, model_version="test",
            probs=(0.5, 0.3, 0.2), pick="H", confidence=0.5,
            created_at=clock.now_iso(),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE predictions SET pick = 'A' WHERE id = ?", (pid,))

    def test_predictions_cannot_be_deleted(self):
        match_id = add_fixture(self.conn, "Alpha", "Bravo", self.soon)
        pid = store.insert_prediction(
            self.conn, match_id=match_id, model_version="test",
            probs=(0.5, 0.3, 0.2), pick="H", confidence=0.5,
            created_at=clock.now_iso(),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM predictions WHERE id = ?", (pid,))

    def test_kickoff_cannot_move_once_predicted(self):
        match_id = add_fixture(self.conn, "Alpha", "Bravo", self.soon)
        store.insert_prediction(
            self.conn, match_id=match_id, model_version="test",
            probs=(0.5, 0.3, 0.2), pick="H", confidence=0.5,
            created_at=clock.now_iso(),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE matches SET kickoff_utc = ? WHERE id = ?",
                (self.later, match_id),
            )

    def test_kickoff_can_move_before_any_prediction(self):
        match_id = add_fixture(self.conn, "Alpha", "Bravo", self.soon)
        self.conn.execute(
            "UPDATE matches SET kickoff_utc = ? WHERE id = ?", (self.later, match_id)
        )
        row = self.conn.execute(
            "SELECT kickoff_utc FROM matches WHERE id = ?", (match_id,)
        ).fetchone()
        self.assertEqual(row["kickoff_utc"], self.later)

    def test_prediction_on_match_without_kickoff_is_rejected(self):
        """Backfilled history has no kickoff_utc, so 'before kickoff' cannot be
        proven for it. That must fail closed, not open."""
        row = self.conn.execute(
            "SELECT id FROM matches WHERE kickoff_utc IS NULL LIMIT 1"
        ).fetchone()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            store.insert_prediction(
                self.conn, match_id=int(row["id"]), model_version="test",
                probs=(0.5, 0.3, 0.2), pick="H", confidence=0.5,
                created_at=clock.now_iso(),
            )
        self.assertIn("no kickoff time", str(ctx.exception))


class TestPublish(PipelineTestCase):
    def test_publishes_fixtures_inside_the_horizon(self):
        add_fixture(self.conn, "Alpha", "Foxtrot", self.soon)
        result = publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        self.assertEqual(result["written"], 1)

    def test_ignores_fixtures_beyond_the_horizon(self):
        add_fixture(self.conn, "Alpha", "Foxtrot", self.later)
        result = publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        self.assertEqual(result["written"], 0)

    def test_does_not_republish(self):
        add_fixture(self.conn, "Alpha", "Foxtrot", self.soon)
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        second = publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        self.assertEqual(second["written"], 0)
        self.assertEqual(second["skipped_already_published"], 1)

    def test_dry_run_writes_nothing(self):
        add_fixture(self.conn, "Alpha", "Foxtrot", self.soon)
        result = publish.publish(
            self.conn, horizon_days=8, dry_run=True, log=lambda *a: None
        )
        self.assertEqual(result["written"], 1)
        n = self.conn.execute("SELECT count(*) AS n FROM predictions").fetchone()["n"]
        self.assertEqual(n, 0)

    def test_probabilities_are_normalised_and_directional(self):
        add_fixture(self.conn, "Alpha", "Foxtrot", self.soon)
        result = publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        fixture = result["fixtures"][0]
        total = fixture["p_home"] + fixture["p_draw"] + fixture["p_away"]
        self.assertAlmostEqual(total, 1.0, places=6)
        # Alpha is the strongest team and is at home against the weakest.
        self.assertGreater(fixture["p_home"], fixture["p_away"])
        self.assertEqual(fixture["pick"], "H")

    def test_flags_teams_without_history(self):
        add_fixture(self.conn, "Alpha", "Newcomer FC", self.soon)
        result = publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        self.assertIn("Newcomer FC", result["teams_without_history"])

    def test_published_timestamp_precedes_kickoff(self):
        match_id = add_fixture(self.conn, "Alpha", "Foxtrot", self.soon)
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        row = self.conn.execute(
            "SELECT created_at FROM predictions WHERE match_id = ?", (match_id,)
        ).fetchone()
        self.assertLess(row["created_at"], self.soon)


class TestGrade(PipelineTestCase):
    def _publish_and_finish(self, home_goals, away_goals):
        match_id = add_fixture(self.conn, "Alpha", "Foxtrot", self.soon)
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        finish_match(self.conn, match_id, home_goals, away_goals)
        return match_id

    def test_grades_a_hit(self):
        self._publish_and_finish(3, 0)  # Alpha predicted to win, and did
        summary = publish.grade(self.conn, log=lambda *a: None)
        self.assertEqual(summary["graded"], 1)
        self.assertEqual(summary["hits"], 1)

    def test_grades_a_miss(self):
        self._publish_and_finish(0, 3)  # Alpha predicted to win, and lost
        summary = publish.grade(self.conn, log=lambda *a: None)
        self.assertEqual(summary["graded"], 1)
        self.assertEqual(summary["misses"], 1)

    def test_grading_is_idempotent(self):
        self._publish_and_finish(3, 0)
        publish.grade(self.conn, log=lambda *a: None)
        again = publish.grade(self.conn, log=lambda *a: None)
        self.assertEqual(again["graded"], 0)

    def test_unfinished_matches_are_not_graded(self):
        add_fixture(self.conn, "Alpha", "Foxtrot", self.soon)
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        summary = publish.grade(self.conn, log=lambda *a: None)
        self.assertEqual(summary["graded"], 0)

    def test_accuracy_counts_losses(self):
        """The headline number must not be able to quietly drop misses."""
        pairs = [("Alpha", "Foxtrot"), ("Foxtrot", "Alpha"), ("Bravo", "Echo")]
        match_ids = [add_fixture(self.conn, h, a, self.soon) for h, a in pairs]
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)

        # Every match ends as an away win, so any home pick is a recorded loss.
        for match_id in match_ids:
            finish_match(self.conn, match_id, 0, 3)
        publish.grade(self.conn, log=lambda *a: None)

        picks = {r["match_id"]: r["pick"] for r in store.track_record(self.conn, "EPL")}
        expected_hits = sum(1 for mid in match_ids if picks[mid] == "A")

        summary = publish.accuracy(self.conn)
        self.assertEqual(summary["overall"]["n"], 3)
        self.assertEqual(summary["overall"]["hits"], expected_hits)
        self.assertLess(expected_hits, 3, "test needs at least one miss to be meaningful")
        self.assertAlmostEqual(summary["overall"]["accuracy"], expected_hits / 3)


class TestExport(PipelineTestCase):
    def test_payload_separates_upcoming_from_graded(self):
        add_fixture(self.conn, "Alpha", "Bravo", self.soon)
        match_id = add_fixture(self.conn, "Charlie", "Delta", self.soon)
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        finish_match(self.conn, match_id, 2, 1)
        publish.grade(self.conn, log=lambda *a: None)

        payload = export.build(self.conn)
        self.assertEqual(len(payload["upcoming"]), 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["actual"], "H")

    def test_thin_history_is_flagged(self):
        add_fixture(self.conn, "Alpha", "Newcomer FC", self.soon)
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        payload = export.build(self.conn)
        self.assertIn("Newcomer FC", payload["upcoming"][0]["thin_history"])
        self.assertNotIn("Alpha", payload["upcoming"][0]["thin_history"])

    def test_writes_both_json_and_js(self):
        add_fixture(self.conn, "Alpha", "Bravo", self.soon)
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        target = Path(self._tmp.name) / "data.json"
        export.write(self.conn, path=target)

        self.assertTrue(target.exists())
        twin = target.with_suffix(".js")
        self.assertTrue(twin.exists())
        self.assertTrue(twin.read_text(encoding="utf-8").startswith("window.PRESCORE_DATA ="))

    def test_disclaimer_is_present(self):
        payload = export.build(self.conn)
        self.assertIn("Not betting advice", payload["disclaimer"])


class TestModelVersioning(PipelineTestCase):
    """An improved model is published alongside the old one, never over it.

    The two must be reported separately: averaging two different predictors
    into one accuracy figure would misrepresent both.
    """

    def setUp(self):
        super().setUp()
        self.match_id = add_fixture(self.conn, "Alpha", "Foxtrot", self.soon)
        now = clock.now_iso()
        # v1 called it wrong, v2 called it right
        store.insert_prediction(
            self.conn, match_id=self.match_id, model_version="v1",
            probs=(0.2, 0.3, 0.5), pick="A", confidence=0.5, created_at=now,
        )
        store.insert_prediction(
            self.conn, match_id=self.match_id, model_version="v2",
            probs=(0.7, 0.2, 0.1), pick="H", confidence=0.7, created_at=now,
        )
        finish_match(self.conn, self.match_id, 3, 0)
        publish.grade(self.conn, log=lambda *a: None)

    def test_both_versions_are_stored(self):
        record = store.track_record(self.conn, "EPL")
        self.assertEqual(len(record), 2)

    def test_track_record_scopes_to_one_version(self):
        v1 = store.track_record(self.conn, "EPL", "v1")
        v2 = store.track_record(self.conn, "EPL", "v2")
        self.assertEqual(len(v1), 1)
        self.assertEqual(len(v2), 1)
        self.assertEqual(v1[0]["pick"], "A")
        self.assertEqual(v2[0]["pick"], "H")

    def test_accuracy_is_not_averaged_across_versions(self):
        v1 = publish.accuracy(self.conn, "EPL", "v1")["overall"]
        v2 = publish.accuracy(self.conn, "EPL", "v2")["overall"]
        self.assertEqual(v1["n"], 1)
        self.assertEqual(v1["hits"], 0)
        self.assertEqual(v2["n"], 1)
        self.assertEqual(v2["hits"], 1)

    def test_both_versions_are_graded(self):
        """The superseded version keeps being scored -- it is not erased."""
        record = store.track_record(self.conn, "EPL")
        self.assertTrue(all(r["is_hit"] is not None for r in record))

    def test_model_versions_are_listed(self):
        versions = store.model_versions(self.conn, "EPL")
        names = {v["version"] for v in versions}
        self.assertEqual(names, {"v1", "v2"})
        self.assertTrue(all(v["published"] == 1 for v in versions))
        self.assertTrue(all(v["graded"] == 1 for v in versions))

    def test_export_groups_every_version_onto_its_match(self):
        """One match, two predictions -- v1 is not hidden, just not primary."""
        payload = export.build(self.conn, "EPL", model_version="v2")
        self.assertEqual(len(payload["results"]), 1)
        match = payload["results"][0]
        self.assertEqual(payload["model_version"], "v2")

        preds = match["predictions"]
        self.assertEqual(len(preds), 2)
        self.assertEqual({p["model_version"] for p in preds}, {"v1", "v2"})

        disclosed = {v["version"] for v in payload["model_versions"]}
        self.assertIn("v1", disclosed)

    def test_current_version_sorts_first(self):
        """The active model leads the comparison regardless of version string
        ordering -- 'v2' is not alphabetically or numerically special here."""
        payload = export.build(self.conn, "EPL", model_version="v2")
        preds = payload["results"][0]["predictions"]
        self.assertTrue(preds[0]["is_current"])
        self.assertEqual(preds[0]["model_version"], "v2")
        self.assertFalse(preds[1]["is_current"])
        self.assertEqual(preds[1]["model_version"], "v1")

    def test_each_version_keeps_its_own_pick_and_grade(self):
        """v1 called this wrong, v2 called it right -- both facts must survive
        being grouped onto the same match."""
        payload = export.build(self.conn, "EPL", model_version="v2")
        by_version = {
            p["model_version"]: p for p in payload["results"][0]["predictions"]
        }
        self.assertEqual(by_version["v2"]["pick"], "H")
        self.assertTrue(by_version["v2"]["is_hit"])
        self.assertEqual(by_version["v1"]["pick"], "A")
        self.assertFalse(by_version["v1"]["is_hit"])

    def test_match_level_facts_are_not_duplicated_per_version(self):
        """The actual result belongs to the match, not to any one predictor."""
        payload = export.build(self.conn, "EPL", model_version="v2")
        match = payload["results"][0]
        self.assertEqual(match["actual"], "H")
        self.assertEqual(match["home_goals"], 3)
        self.assertEqual(match["away_goals"], 0)

    def test_accuracy_by_version_covers_every_graded_version(self):
        payload = export.build(self.conn, "EPL", model_version="v2")
        self.assertIn("v1", payload["accuracy_by_version"])
        self.assertIn("v2", payload["accuracy_by_version"])
        self.assertEqual(payload["accuracy_by_version"]["v1"]["overall"]["hits"], 0)
        self.assertEqual(payload["accuracy_by_version"]["v2"]["overall"]["hits"], 1)

    def test_superseded_version_cannot_be_deleted(self):
        row = self.conn.execute(
            "SELECT id FROM predictions WHERE model_version = 'v1'"
        ).fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM predictions WHERE id = ?", (row["id"],))


class TestTeamResolution(PipelineTestCase):
    def test_maps_provider_spelling_to_canonical(self):
        store.team_id(self.conn, "Man United")
        self.assertEqual(
            teams.resolve(self.conn, "Manchester United", "thesportsdb"), "Man United"
        )

    def test_exact_canonical_name_resolves(self):
        self.assertEqual(teams.resolve(self.conn, "Alpha", "test"), "Alpha")

    def test_case_insensitive_match(self):
        self.assertEqual(teams.resolve(self.conn, "alpha", "test"), "Alpha")

    def test_strips_club_suffixes(self):
        self.assertEqual(teams.resolve(self.conn, "Alpha FC", "test"), "Alpha")

    def test_unknown_name_returns_none_rather_than_inventing(self):
        self.assertIsNone(teams.resolve(self.conn, "Hornchurch", "thesportsdb"))
        n = self.conn.execute(
            "SELECT count(*) AS n FROM teams WHERE name = 'Hornchurch'"
        ).fetchone()["n"]
        self.assertEqual(n, 0)

    def test_resolve_all_reports_the_gaps(self):
        resolved, unresolved = teams.resolve_all(
            self.conn, ["Alpha", "Hornchurch", "Worthing"], "thesportsdb"
        )
        self.assertEqual(resolved, {"Alpha": "Alpha"})
        self.assertEqual(unresolved, ["Hornchurch", "Worthing"])

    def test_registered_alias_is_reused(self):
        tid = teams.register(self.conn, "Wolverhampton Wanderers", "x", "Wolves")
        self.assertEqual(
            store.resolve_alias(self.conn, "Wolverhampton Wanderers", "x"), tid
        )


if __name__ == "__main__":
    unittest.main()
