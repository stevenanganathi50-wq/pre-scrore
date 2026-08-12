"""Push the local SQLite record up to Supabase over PostgREST.

Uses urllib rather than a Postgres driver, so the project keeps its
zero-dependency property on both ends.

Identity columns are `generated always as identity`, so remote ids are the
database's to assign and never ours to send. Everything is therefore keyed on
natural keys and remapped as we go:

    teams        by name
    matches      by (league, season, home_team_id, away_team_id)
    predictions  by (match_id, model_version, market)

The remote triggers are live during this push. A prediction whose
`created_at` is not strictly before its match's `kickoff_utc` will be rejected
by the database, which is the intended behaviour -- if that ever fires here,
the local record is what needs fixing, not the constraint.
"""

from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

from . import clock, settings, store

BATCH_SIZE = 500
TIMEOUT_SECONDS = 60

# PostgREST caps every response at the project's `max-rows` setting (1000 on
# Supabase by default). A `limit` above it is silently ignored, so reads must
# be paged -- otherwise the id maps built below come back short and foreign
# keys quietly fail to resolve.
PAGE_SIZE = 1000

# A dropped connection or a 502 from the edge is routine over a push of
# thousands of rows, and this runs unattended on a schedule. Retry the
# transient cases; never retry a 4xx, which means the request itself is wrong.
MAX_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 1.5
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class SupabaseError(RuntimeError):
    """A PostgREST request failed. Carries the server's explanation."""


def _chunks(rows: list, size: int = BATCH_SIZE) -> Iterator[list]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


class Client:
    def __init__(self, cfg: settings.SupabaseSettings, key: str | None = None):
        """`key` defaults to the service role key. Pass the anon key to make
        requests exactly as a browser would -- that is how the RLS policies
        get audited rather than assumed."""
        self.cfg = cfg
        self.key = key or cfg.service_role_key

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        headers.update(extra or {})
        return headers

    def _open(
        self,
        method: str,
        table: str,
        *,
        body: Any = None,
        params: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> tuple[str, dict]:
        url = f"{self.cfg.rest_url}/{table}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        extra = {"Prefer": prefer} if prefer else None
        data = json.dumps(body).encode("utf-8") if body is not None else None

        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            req = urllib.request.Request(
                url, data=data, method=method, headers=self._headers(extra)
            )
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                    return resp.read().decode("utf-8"), dict(resp.headers)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {exc.code}: {detail}"
                # A 4xx means this request is malformed or forbidden. Retrying
                # it just repeats the same mistake more slowly.
                if exc.code not in RETRYABLE_STATUS:
                    raise SupabaseError(f"{method} {table} failed with {last_error}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = f"connection error: {exc}"

            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))

        raise SupabaseError(
            f"{method} {table} failed after {MAX_ATTEMPTS} attempts -- {last_error}"
        )

    def request(
        self,
        method: str,
        table: str,
        *,
        body: Any = None,
        params: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> Any:
        raw, _ = self._open(method, table, body=body, params=params, prefer=prefer)
        return json.loads(raw) if raw.strip() else []

    def count(self, table: str, params: dict[str, str] | None = None) -> int:
        """Exact row count, read from the Content-Range response header."""
        # No `select` is set on purpose: not every table has an `id` column
        # (prediction_results is keyed on prediction_id). The Content-Range
        # header carries the total regardless of which columns are projected.
        query = dict(params or {})
        query["limit"] = "1"
        _, headers = self._open("GET", table, params=query, prefer="count=exact")
        content_range = headers.get("Content-Range") or headers.get("content-range") or ""
        total = content_range.rsplit("/", 1)[-1]
        try:
            return int(total)
        except ValueError:
            raise SupabaseError(
                f"could not read a row count for {table} from Content-Range {content_range!r}"
            ) from None

    def select(self, table: str, params: dict[str, str]) -> list[dict]:
        """Read every matching row, paging past the server's max-rows cap.

        `order` is required for correctness: offset paging over an unordered
        result can repeat or skip rows between requests. It defaults to
        `id.asc`, so any table without an `id` column must pass its own.
        """
        query = dict(params)
        query.setdefault("order", "id.asc")
        query.pop("limit", None)

        out: list[dict] = []
        offset = 0
        while True:
            page = dict(query)
            page["limit"] = str(PAGE_SIZE)
            page["offset"] = str(offset)
            rows = self.request("GET", table, params=page)
            if not isinstance(rows, list):
                break
            out.extend(rows)
            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return out

    def upsert(
        self, table: str, rows: list[dict], on_conflict: str, returning: bool = True
    ) -> list[dict]:
        """Insert rows, updating any that collide on `on_conflict`."""
        if not rows:
            return []
        prefer = "resolution=merge-duplicates,return=" + (
            "representation" if returning else "minimal"
        )
        out: list[dict] = []
        for batch in _chunks(rows):
            result = self.request(
                "POST",
                table,
                body=batch,
                params={"on_conflict": on_conflict},
                prefer=prefer,
            )
            if returning and isinstance(result, list):
                out.extend(result)
        return out


# --- push steps -----------------------------------------------------------


def push_teams(conn: sqlite3.Connection, client: Client, log=print) -> dict[str, int]:
    rows = conn.execute("SELECT name FROM teams ORDER BY name").fetchall()
    payload = [{"name": r["name"]} for r in rows]
    client.upsert("teams", payload, on_conflict="name", returning=False)

    remote = client.select("teams", {"select": "id,name"})
    mapping = {r["name"]: int(r["id"]) for r in remote}
    log(f"  teams        {len(payload)} sent, {len(mapping)} on remote")
    return mapping


def push_matches(
    conn: sqlite3.Connection, client: Client, team_ids: dict[str, int], league: str, log=print
) -> dict[tuple, int]:
    rows = conn.execute(
        """
        SELECT m.source, m.source_ref, m.league, m.season, m.kickoff_utc,
               m.status, m.home_goals, m.away_goals, m.result,
               h.name AS home, a.name AS away
        FROM matches m
        JOIN teams h ON h.id = m.home_team_id
        JOIN teams a ON a.id = m.away_team_id
        WHERE m.league = ?
        ORDER BY m.match_date, m.id
        """,
        (league,),
    ).fetchall()

    payload, skipped = [], []
    for r in rows:
        home_id = team_ids.get(r["home"])
        away_id = team_ids.get(r["away"])
        if home_id is None or away_id is None:
            skipped.append(f"{r['home']} vs {r['away']}")
            continue
        payload.append(
            {
                "source": r["source"],
                "source_ref": r["source_ref"],
                "league": r["league"],
                "season": r["season"],
                "kickoff_utc": r["kickoff_utc"],
                "home_team_id": home_id,
                "away_team_id": away_id,
                "status": r["status"],
                "home_goals": r["home_goals"],
                "away_goals": r["away_goals"],
                "result": r["result"],
            }
        )

    client.upsert(
        "matches",
        payload,
        on_conflict="league,season,home_team_id,away_team_id",
        returning=False,
    )

    remote = client.select(
        "matches",
        {
            "select": "id,league,season,home_team_id,away_team_id",
            "league": f"eq.{league}",
        },
    )
    mapping = {
        (r["league"], r["season"], r["home_team_id"], r["away_team_id"]): int(r["id"])
        for r in remote
    }
    log(f"  matches      {len(payload)} sent, {len(mapping)} on remote")
    if skipped:
        log(f"    skipped {len(skipped)} with unmapped teams: {skipped[:3]}")
    return mapping


def push_predictions(
    conn: sqlite3.Connection,
    client: Client,
    team_ids: dict[str, int],
    match_ids: dict[tuple, int],
    league: str,
    log=print,
) -> dict[int, int]:
    rows = conn.execute(
        """
        SELECT p.id AS local_id, p.model_version, p.market,
               p.p_home, p.p_draw, p.p_away, p.pick, p.confidence, p.created_at,
               m.league, m.season, h.name AS home, a.name AS away
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        JOIN teams h ON h.id = m.home_team_id
        JOIN teams a ON a.id = m.away_team_id
        WHERE m.league = ?
        ORDER BY p.id
        """,
        (league,),
    ).fetchall()

    payload, local_keys = [], []
    for r in rows:
        key = (r["league"], r["season"], team_ids.get(r["home"]), team_ids.get(r["away"]))
        remote_match = match_ids.get(key)
        if remote_match is None:
            continue
        payload.append(
            {
                "match_id": remote_match,
                "model_version": r["model_version"],
                "market": r["market"],
                "p_home": r["p_home"],
                "p_draw": r["p_draw"],
                "p_away": r["p_away"],
                "pick": r["pick"],
                "confidence": r["confidence"],
                "created_at": r["created_at"],
            }
        )
        local_keys.append((r["local_id"], remote_match, r["model_version"], r["market"]))

    # Predictions are immutable remotely, so a colliding row must be left
    # alone rather than merged. ignore-duplicates makes re-running the push
    # safe instead of tripping the immutability trigger.
    for batch in _chunks(payload):
        client.request(
            "POST",
            "predictions",
            body=batch,
            params={"on_conflict": "match_id,model_version,market"},
            prefer="resolution=ignore-duplicates,return=minimal",
        )

    remote = client.select(
        "predictions", {"select": "id,match_id,model_version,market"}
    )
    by_key = {
        (int(r["match_id"]), r["model_version"], r["market"]): int(r["id"])
        for r in remote
    }
    mapping = {
        local_id: by_key[(match_id, version, market)]
        for local_id, match_id, version, market in local_keys
        if (match_id, version, market) in by_key
    }
    log(f"  predictions  {len(payload)} sent, {len(mapping)} mapped")
    return mapping


def push_results(
    conn: sqlite3.Connection, client: Client, prediction_ids: dict[int, int], league: str, log=print
) -> int:
    rows = conn.execute(
        """
        SELECT r.prediction_id AS local_id, r.actual, r.is_hit,
               r.log_loss, r.rps, r.brier, r.graded_at
        FROM prediction_results r
        JOIN predictions p ON p.id = r.prediction_id
        JOIN matches m ON m.id = p.match_id
        WHERE m.league = ?
        """,
        (league,),
    ).fetchall()

    payload = []
    for r in rows:
        remote_id = prediction_ids.get(r["local_id"])
        if remote_id is None:
            continue
        payload.append(
            {
                "prediction_id": remote_id,
                "actual": r["actual"],
                "is_hit": bool(r["is_hit"]),
                "log_loss": r["log_loss"],
                "rps": r["rps"],
                "brier": r["brier"],
                "graded_at": r["graded_at"],
            }
        )

    client.upsert("prediction_results", payload, on_conflict="prediction_id", returning=False)
    log(f"  results      {len(payload)} sent")
    return len(payload)


def pull_all(conn: sqlite3.Connection, league: str = "EPL", log=print) -> dict:
    """Hydrate the local database with the published record from Supabase.

    Required whenever local storage is not durable -- a CI runner starts with
    an empty database, and without this `publish` would re-predict fixtures
    that are already public and `grade` would then score those local rows
    instead of the ones actually published. The remote row would end up
    carrying metrics computed from probabilities nobody ever saw.

    Remote ids are never reused locally; everything is matched on the same
    natural keys the push uses.
    """
    cfg = settings.supabase(require_service_role=True)
    client = Client(cfg)

    remote_teams = {
        int(r["id"]): r["name"] for r in client.select("teams", {"select": "id,name"})
    }
    remote_matches = client.select(
        "matches",
        {"select": "id,season,home_team_id,away_team_id", "league": f"eq.{league}"},
    )
    match_key = {}
    for r in remote_matches:
        home = remote_teams.get(int(r["home_team_id"]))
        away = remote_teams.get(int(r["away_team_id"]))
        if home and away:
            match_key[int(r["id"])] = (int(r["season"]), home, away)

    local_matches = store.match_ids_by_key(conn, league)

    predictions = client.select(
        "predictions",
        {
            "select": "id,match_id,model_version,market,p_home,p_draw,p_away,"
                      "pick,confidence,created_at"
        },
    )

    inserted = skipped = unmatched = 0
    remote_to_local: dict[int, int] = {}

    for row in predictions:
        key = match_key.get(int(row["match_id"]))
        local_match = local_matches.get(key) if key else None
        if local_match is None:
            unmatched += 1
            continue

        existing = store.prediction_id(
            conn, local_match, row["model_version"], row["market"]
        )
        if existing is not None:
            remote_to_local[int(row["id"])] = existing
            skipped += 1
            continue

        try:
            local_id = store.insert_prediction(
                conn,
                match_id=local_match,
                model_version=row["model_version"],
                probs=(row["p_home"], row["p_draw"], row["p_away"]),
                pick=row["pick"],
                confidence=row["confidence"],
                created_at=clock.normalize(row["created_at"]),
            )
        except sqlite3.IntegrityError as exc:
            log(f"    refused by local constraints: {exc}")
            unmatched += 1
            continue

        remote_to_local[int(row["id"])] = local_id
        inserted += 1

    conn.commit()
    log(
        f"  predictions  {inserted} pulled, {skipped} already local"
        + (f", {unmatched} unmatched" if unmatched else "")
    )

    results = client.select(
        "prediction_results",
        {
            "select": "prediction_id,actual,is_hit,log_loss,rps,brier,graded_at",
            "order": "prediction_id.asc",
        },
    )
    graded = 0
    for row in results:
        local_id = remote_to_local.get(int(row["prediction_id"]))
        if local_id is None or store.has_result(conn, local_id):
            continue
        store.insert_result(
            conn,
            prediction_id=local_id,
            actual=row["actual"],
            is_hit=bool(row["is_hit"]),
            log_loss=row["log_loss"],
            rps=row["rps"],
            brier=row["brier"],
            graded_at=clock.normalize(row["graded_at"]),
        )
        graded += 1
    conn.commit()
    log(f"  results      {graded} pulled")

    return {
        "predictions": inserted,
        "already_local": skipped,
        "unmatched": unmatched,
        "results": graded,
    }


def reconcile(conn: sqlite3.Connection, client: Client, league: str) -> list[str]:
    """Compare local and remote row counts. Returns a list of discrepancies.

    This exists because a truncated read once produced a partial id map and a
    push that reported success while silently dropping every prediction. A
    push that cannot account for its own rows is a failed push.
    """
    local = {
        "teams": conn.execute("SELECT count(*) AS n FROM teams").fetchone()["n"],
        "matches": conn.execute(
            "SELECT count(*) AS n FROM matches WHERE league = ?", (league,)
        ).fetchone()["n"],
        "predictions": conn.execute(
            """SELECT count(*) AS n FROM predictions p
               JOIN matches m ON m.id = p.match_id WHERE m.league = ?""",
            (league,),
        ).fetchone()["n"],
        "prediction_results": conn.execute(
            """SELECT count(*) AS n FROM prediction_results r
               JOIN predictions p ON p.id = r.prediction_id
               JOIN matches m ON m.id = p.match_id WHERE m.league = ?""",
            (league,),
        ).fetchone()["n"],
    }

    problems = []
    for table, expected in local.items():
        params = {"league": f"eq.{league}"} if table == "matches" else None
        actual = client.count(table, params)
        if actual < expected:
            problems.append(
                f"{table}: {expected} local but {actual} remote ({expected - actual} missing)"
            )
    return problems


def push_all(conn: sqlite3.Connection, league: str = "EPL", log=print) -> dict:
    cfg = settings.supabase(require_service_role=True)
    client = Client(cfg)
    log(f"pushing {league} to {cfg.url}")

    team_ids = push_teams(conn, client, log=log)
    match_ids = push_matches(conn, client, team_ids, league, log=log)
    prediction_ids = push_predictions(conn, client, team_ids, match_ids, league, log=log)
    results = push_results(conn, client, prediction_ids, league, log=log)

    problems = reconcile(conn, client, league)
    for problem in problems:
        log(f"  MISMATCH  {problem}")

    return {
        "teams": len(team_ids),
        "matches": len(match_ids),
        "predictions": len(prediction_ids),
        "results": results,
        "problems": problems,
    }
