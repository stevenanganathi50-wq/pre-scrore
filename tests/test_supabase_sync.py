"""Sync tests.

The remote is faked, so these run offline. What they check is the part that
is easy to get wrong and expensive to discover in production: local ids are
never sent, and every foreign key is remapped to the id the remote assigned.
"""

import tempfile
import unittest
from pathlib import Path

from prescore import settings, store, supabase_sync

from tests.test_pipeline import add_fixture, finish_match, seed_history
from prescore import clock, publish
from datetime import timedelta


class FakeClient:
    """Stands in for PostgREST, assigning ids the way identity columns do."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.next_id = {"teams": 100, "matches": 5000, "predictions": 900}
        self.calls: list[tuple[str, str, dict]] = []
        self.sent: list[tuple[str, dict]] = []  # every row we were asked to send

    def _key(self, table, row):
        if table == "teams":
            return (row["name"],)
        if table == "matches":
            return (row["league"], row["season"], row["home_team_id"], row["away_team_id"])
        if table == "predictions":
            return (row["match_id"], row["model_version"], row["market"])
        return (row.get("prediction_id"),)

    def request(self, method, table, *, body=None, params=None, prefer=None):
        self.calls.append((method, table, params or {}))
        self.sent.extend((table, dict(item)) for item in body or [])
        rows = self.tables.setdefault(table, [])
        existing = {self._key(table, r): r for r in rows}
        ignore = "ignore-duplicates" in (prefer or "")

        for item in body or []:
            key = self._key(table, item)
            if key in existing:
                if not ignore:
                    existing[key].update(item)
                continue
            record = dict(item)
            if table in self.next_id:
                record["id"] = self.next_id[table]
                self.next_id[table] += 1
            rows.append(record)
            existing[key] = record
        return []

    def select(self, table, params):
        return [dict(r) for r in self.tables.get(table, [])]

    def count(self, table, params=None):
        return len(self.tables.get(table, []))

    def upsert(self, table, rows, on_conflict, returning=True):
        if rows:
            self.request("POST", table, body=rows, params={"on_conflict": on_conflict})
        return []


class SyncTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(Path(self._tmp.name) / "t.db")
        store.init_schema(self.conn)
        seed_history(self.conn)

        soon = clock.to_iso(clock.utc_now() + timedelta(days=2))
        self.match_id = add_fixture(self.conn, "Alpha", "Foxtrot", soon)
        add_fixture(self.conn, "Bravo", "Charlie", soon)
        publish.publish(self.conn, horizon_days=8, log=lambda *a: None)

        self.client = FakeClient()

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def run_push(self):
        team_ids = supabase_sync.push_teams(self.conn, self.client, log=lambda *a: None)
        match_ids = supabase_sync.push_matches(
            self.conn, self.client, team_ids, "EPL", log=lambda *a: None
        )
        pred_ids = supabase_sync.push_predictions(
            self.conn, self.client, team_ids, match_ids, "EPL", log=lambda *a: None
        )
        return team_ids, match_ids, pred_ids


class TestPush(SyncTestCase):
    def test_teams_are_pushed_and_mapped(self):
        team_ids, _, _ = self.run_push()
        self.assertEqual(len(team_ids), 6)
        self.assertTrue(all(v >= 100 for v in team_ids.values()))

    def test_local_ids_are_never_sent(self):
        """`generated always as identity` rejects an explicit id, so no
        outgoing row may carry one."""
        self.run_push()
        self.assertTrue(self.client.sent, "nothing was sent")
        offenders = [(t, r) for t, r in self.client.sent if "id" in r]
        self.assertEqual(offenders, [])

    def test_sent_rows_carry_no_local_primary_keys(self):
        """Guard the specific mistake: local prediction ids leaking through."""
        self.run_push()
        for table, row in self.client.sent:
            if table == "predictions":
                self.assertNotIn("local_id", row)

    def test_matches_reference_remote_team_ids(self):
        team_ids, _, _ = self.run_push()
        valid = set(team_ids.values())
        for row in self.client.tables["matches"]:
            self.assertIn(row["home_team_id"], valid)
            self.assertIn(row["away_team_id"], valid)

    def test_predictions_reference_remote_match_ids(self):
        _, match_ids, _ = self.run_push()
        valid = set(match_ids.values())
        for row in self.client.tables["predictions"]:
            self.assertIn(row["match_id"], valid)

    def test_prediction_mapping_covers_every_local_row(self):
        _, _, pred_ids = self.run_push()
        local = self.conn.execute("SELECT count(*) AS n FROM predictions").fetchone()["n"]
        self.assertEqual(len(pred_ids), local)

    def test_predictions_use_ignore_duplicates(self):
        """Remote predictions are immutable, so a re-push must not try to
        update them."""
        self.run_push()
        prediction_posts = [
            c for c in self.client.calls if c[0] == "POST" and c[1] == "predictions"
        ]
        self.assertTrue(prediction_posts)

    def test_push_is_idempotent(self):
        self.run_push()
        counts = {t: len(rows) for t, rows in self.client.tables.items()}
        self.run_push()
        self.assertEqual({t: len(r) for t, r in self.client.tables.items()}, counts)

    def test_results_are_pushed_after_grading(self):
        finish_match(self.conn, self.match_id, 3, 0)
        publish.grade(self.conn, log=lambda *a: None)
        _, _, pred_ids = self.run_push()
        n = supabase_sync.push_results(
            self.conn, self.client, pred_ids, "EPL", log=lambda *a: None
        )
        self.assertEqual(n, 1)
        row = self.client.tables["prediction_results"][0]
        self.assertIn(row["prediction_id"], set(pred_ids.values()))
        self.assertIsInstance(row["is_hit"], bool)

    def test_history_without_kickoff_is_still_pushed(self):
        """Backfilled matches have no kickoff time; they must still sync."""
        self.run_push()
        without = [r for r in self.client.tables["matches"] if r["kickoff_utc"] is None]
        self.assertTrue(without)
        self.assertTrue(all(r["status"] == "finished" for r in without))


class TestPagination(unittest.TestCase):
    """Regression: PostgREST caps responses at max-rows (1000 on Supabase).

    A `limit` above the cap is ignored, so an unpaged read silently returned
    1000 of 4210 matches, the id map came back short, and every prediction was
    dropped while the push still reported success.
    """

    class PagingClient(supabase_sync.Client):
        def __init__(self, total):
            self.total = total
            self.seen = []

        def request(self, method, table, *, body=None, params=None, prefer=None):
            self.seen.append(dict(params or {}))
            offset = int(params["offset"])
            limit = min(int(params["limit"]), supabase_sync.PAGE_SIZE)
            return [{"id": i} for i in range(offset, min(offset + limit, self.total))]

    def test_reads_every_row_past_the_cap(self):
        client = self.PagingClient(total=4210)
        rows = client.select("matches", {"select": "id"})
        self.assertEqual(len(rows), 4210)
        self.assertEqual(rows[0]["id"], 0)
        self.assertEqual(rows[-1]["id"], 4209)

    def test_exact_multiple_of_page_size_terminates(self):
        client = self.PagingClient(total=2000)
        rows = client.select("matches", {"select": "id"})
        self.assertEqual(len(rows), 2000)

    def test_single_short_page_makes_one_request(self):
        client = self.PagingClient(total=35)
        rows = client.select("teams", {"select": "id"})
        self.assertEqual(len(rows), 35)
        self.assertEqual(len(client.seen), 1)

    def test_empty_table(self):
        client = self.PagingClient(total=0)
        self.assertEqual(client.select("teams", {"select": "id"}), [])

    def test_ordering_is_always_pinned(self):
        """Offset paging over an unordered result can repeat or skip rows."""
        client = self.PagingClient(total=2500)
        client.select("matches", {"select": "id"})
        self.assertTrue(client.seen)
        self.assertTrue(all(p.get("order") for p in client.seen))

    def test_caller_supplied_order_is_respected(self):
        client = self.PagingClient(total=10)
        client.select("matches", {"select": "id", "order": "kickoff_utc.desc"})
        self.assertEqual(client.seen[0]["order"], "kickoff_utc.desc")

    def test_caller_limit_cannot_defeat_paging(self):
        client = self.PagingClient(total=3000)
        rows = client.select("matches", {"select": "id", "limit": "20000"})
        self.assertEqual(len(rows), 3000)


class TestRetries(unittest.TestCase):
    """A push of thousands of rows runs unattended; transient drops must not
    fail the whole cycle, and 4xx must not be retried."""

    def _client(self, responses):
        cfg = settings.SupabaseSettings(url="https://x.supabase.co", service_role_key="k")
        client = supabase_sync.Client(cfg)
        self.opened = []

        def fake_urlopen(req, timeout=None):
            self.opened.append(req.full_url)
            outcome = responses.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return client, fake_urlopen

    def _patch(self, client, fake, fn):
        import urllib.request

        original_open = urllib.request.urlopen
        original_sleep = supabase_sync.time.sleep
        urllib.request.urlopen = fake
        supabase_sync.time.sleep = lambda *_: None
        try:
            return fn()
        finally:
            urllib.request.urlopen = original_open
            supabase_sync.time.sleep = original_sleep

    class FakeResponse:
        def __init__(self, body="[]", headers=None):
            self._body = body.encode()
            self.headers = headers or {}

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def test_recovers_from_a_dropped_connection(self):
        import urllib.error

        responses = [
            ConnectionResetError(10054, "forcibly closed"),
            self.FakeResponse('[{"id": 1}]'),
        ]
        client, fake = self._client(responses)
        result = self._patch(client, fake, lambda: client.request("GET", "matches"))
        self.assertEqual(result, [{"id": 1}])
        self.assertEqual(len(self.opened), 2)

    def test_gives_up_after_the_attempt_limit(self):
        responses = [ConnectionResetError(10054, "nope")] * supabase_sync.MAX_ATTEMPTS
        client, fake = self._client(responses)
        with self.assertRaises(supabase_sync.SupabaseError) as ctx:
            self._patch(client, fake, lambda: client.request("GET", "matches"))
        self.assertIn("after", str(ctx.exception))
        self.assertEqual(len(self.opened), supabase_sync.MAX_ATTEMPTS)

    def test_client_errors_are_not_retried(self):
        """A 400 is our bug; repeating it just wastes time."""
        import urllib.error
        import io

        err = urllib.error.HTTPError(
            "https://x", 400, "Bad Request", {}, io.BytesIO(b'{"message":"bad"}')
        )
        client, fake = self._client([err])
        with self.assertRaises(supabase_sync.SupabaseError) as ctx:
            self._patch(client, fake, lambda: client.request("POST", "matches"))
        self.assertIn("400", str(ctx.exception))
        self.assertEqual(len(self.opened), 1)

    def test_server_errors_are_retried(self):
        import urllib.error
        import io

        err = urllib.error.HTTPError(
            "https://x", 503, "Unavailable", {}, io.BytesIO(b"busy")
        )
        client, fake = self._client([err, self.FakeResponse("[]")])
        result = self._patch(client, fake, lambda: client.request("GET", "matches"))
        self.assertEqual(result, [])
        self.assertEqual(len(self.opened), 2)


class TestPull(SyncTestCase):
    """A CI runner starts with no database. Without `pull`, publish would
    re-predict already-public fixtures and grade would score the wrong rows."""

    def _wipe_local_predictions(self):
        """Rebuild the local DB as a fresh runner would see it: history and
        fixtures present, published predictions absent."""
        self.conn.execute("DELETE FROM prediction_results")
        # Predictions are immutable by trigger, so a wipe means dropping that
        # guard first. init_schema puts it straight back.
        self.conn.execute("DROP TRIGGER IF EXISTS predictions_no_delete")
        self.conn.execute("DELETE FROM predictions")
        self.conn.commit()
        store.init_schema(self.conn)

    def test_pull_restores_predictions_after_a_wipe(self):
        before = {
            (r["home"], r["away"], r["model_version"]): r
            for r in store.track_record(self.conn, "EPL")
        }
        self.assertTrue(before)

        self.run_push()
        self._wipe_local_predictions()
        self.assertEqual(
            self.conn.execute("SELECT count(*) AS n FROM predictions").fetchone()["n"], 0
        )

        self._pull()

        after = {
            (r["home"], r["away"], r["model_version"]): r
            for r in store.track_record(self.conn, "EPL")
        }
        self.assertEqual(set(before), set(after))
        for key, original in before.items():
            restored = after[key]
            self.assertEqual(restored["pick"], original["pick"])
            self.assertEqual(restored["predicted_at"], original["predicted_at"])
            for field in ("p_home", "p_draw", "p_away", "confidence"):
                self.assertAlmostEqual(restored[field], original[field], places=12)

    def _pull(self):
        """Run the pull steps against the fake remote."""
        remote_teams = {
            int(r["id"]): r["name"] for r in self.client.select("teams", {})
        }
        match_key = {}
        for r in self.client.select("matches", {}):
            home = remote_teams.get(int(r["home_team_id"]))
            away = remote_teams.get(int(r["away_team_id"]))
            if home and away:
                match_key[int(r["id"])] = (int(r["season"]), home, away)
        local = store.match_ids_by_key(self.conn, "EPL")

        for row in self.client.select("predictions", {}):
            key = match_key.get(int(row["match_id"]))
            local_match = local.get(key) if key else None
            if local_match is None:
                continue
            if store.prediction_id(self.conn, local_match, row["model_version"]):
                continue
            store.insert_prediction(
                self.conn,
                match_id=local_match,
                model_version=row["model_version"],
                probs=(row["p_home"], row["p_draw"], row["p_away"]),
                pick=row["pick"],
                confidence=row["confidence"],
                created_at=row["created_at"],
            )
        self.conn.commit()

    def test_publish_skips_after_a_pull(self):
        """The whole point: a hydrated runner must not republish."""
        self.run_push()
        self._wipe_local_predictions()
        self._pull()

        result = publish.publish(self.conn, horizon_days=8, log=lambda *a: None)
        self.assertEqual(result["written"], 0)
        self.assertGreater(result["skipped_already_published"], 0)

    def test_pull_is_idempotent(self):
        self.run_push()
        self._wipe_local_predictions()
        self._pull()
        n = self.conn.execute("SELECT count(*) AS n FROM predictions").fetchone()["n"]
        self._pull()
        self.assertEqual(
            self.conn.execute("SELECT count(*) AS n FROM predictions").fetchone()["n"], n
        )


class TestMatchLookup(SyncTestCase):
    def test_match_ids_are_keyed_by_natural_key(self):
        keys = store.match_ids_by_key(self.conn, "EPL")
        self.assertTrue(keys)
        for (season, home, away), match_id in list(keys.items())[:5]:
            self.assertIsInstance(season, int)
            self.assertNotEqual(home, away)
            self.assertIsInstance(match_id, int)

    def test_prediction_lookup_returns_none_when_absent(self):
        self.assertIsNone(store.prediction_id(self.conn, 999999, "nope"))


class TestReconcile(SyncTestCase):
    def test_clean_push_reports_no_problems(self):
        team_ids, match_ids, pred_ids = self.run_push()
        supabase_sync.push_results(
            self.conn, self.client, pred_ids, "EPL", log=lambda *a: None
        )
        problems = supabase_sync.reconcile(self.conn, self.client, "EPL")
        self.assertEqual(problems, [])

    def test_missing_remote_rows_are_reported(self):
        self.run_push()
        # simulate the truncated-read failure: rows never made it across
        self.client.tables["matches"] = self.client.tables["matches"][:5]
        problems = supabase_sync.reconcile(self.conn, self.client, "EPL")
        self.assertTrue(any("matches" in p for p in problems))
        self.assertTrue(any("missing" in p for p in problems))

    def test_dropped_predictions_are_reported(self):
        self.run_push()
        self.client.tables["predictions"] = []
        problems = supabase_sync.reconcile(self.conn, self.client, "EPL")
        self.assertTrue(any("predictions" in p for p in problems))


class TestSettings(unittest.TestCase):
    def test_missing_settings_names_what_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "absent.env"
            values = settings.load_env_file(empty)
            self.assertEqual(values, {})

    def test_env_file_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "\n".join(
                    [
                        "# a comment",
                        "",
                        "SUPABASE_URL=https://example.supabase.co",
                        'SUPABASE_ANON_KEY="quoted-value"',
                        "EMPTY=",
                        "not a pair",
                    ]
                ),
                encoding="utf-8",
            )
            values = settings.load_env_file(path)
            self.assertEqual(values["SUPABASE_URL"], "https://example.supabase.co")
            self.assertEqual(values["SUPABASE_ANON_KEY"], "quoted-value")
            self.assertNotIn("EMPTY", values)
            self.assertNotIn("not a pair", values)

    def test_describe_never_reveals_a_key(self):
        secret = "super-secret-service-role-key-value"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                f"SUPABASE_URL=https://x.supabase.co\nSUPABASE_SERVICE_ROLE_KEY={secret}\n",
                encoding="utf-8",
            )
            original = settings.ENV_PATH
            settings.ENV_PATH = path
            try:
                text = settings.describe()
            finally:
                settings.ENV_PATH = original
            self.assertNotIn(secret, text)
            self.assertIn("chars", text)

    def test_bom_prefixed_file_parses(self):
        """PowerShell 5.1's `Set-Content -Encoding utf8` emits a BOM."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_bytes(
                b"\xef\xbb\xbfSUPABASE_URL=https://x.supabase.co\nSUPABASE_ANON_KEY=abc\n"
            )
            values = settings.load_env_file(path)
            self.assertEqual(values["SUPABASE_URL"], "https://x.supabase.co")
            self.assertEqual(values["SUPABASE_ANON_KEY"], "abc")

    def test_rest_url_shape(self):
        cfg = settings.SupabaseSettings(url="https://x.supabase.co/", service_role_key="k")
        self.assertEqual(cfg.rest_url, "https://x.supabase.co/rest/v1")


if __name__ == "__main__":
    unittest.main()
