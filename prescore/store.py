"""SQLite access layer.

Kept thin and explicit so the same statements can be lifted to Postgres when
the Supabase side is built.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from . import clock, config


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after the first schema shipped. CREATE TABLE IF NOT EXISTS
# will not add them to a database that already exists, so patch them in.
_ADDED_COLUMNS = (
    ("matches", "source_ref", "TEXT"),
    ("matches", "kickoff_utc", "TEXT"),
    ("matches", "round", "INTEGER"),
    ("matches", "home_shots", "INTEGER"),
    ("matches", "away_shots", "INTEGER"),
    ("matches", "home_shots_on_target", "INTEGER"),
    ("matches", "away_shots_on_target", "INTEGER"),
    ("matches", "home_corners", "INTEGER"),
    ("matches", "away_corners", "INTEGER"),
)


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))
    for table, column, decl in _ADDED_COLUMNS:
        existing = {
            r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()


def team_id(conn: sqlite3.Connection, name: str) -> int:
    """Get or create the canonical team row for `name`."""
    row = conn.execute("SELECT id FROM teams WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return int(row["id"])
    cur = conn.execute("INSERT INTO teams (name) VALUES (?)", (name,))
    return int(cur.lastrowid)


def resolve_alias(conn: sqlite3.Connection, alias: str, source: str) -> int | None:
    row = conn.execute(
        "SELECT team_id FROM team_aliases WHERE alias = ? AND source = ?",
        (alias, source),
    ).fetchone()
    return int(row["team_id"]) if row else None


def add_alias(conn: sqlite3.Connection, alias: str, source: str, tid: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO team_aliases (alias, source, team_id) VALUES (?, ?, ?)",
        (alias, source, tid),
    )


@dataclass(frozen=True)
class MatchRow:
    """A finished match, flattened for the model."""

    id: int
    season: int
    match_date: date
    home: str
    away: str
    home_goals: int
    away_goals: int
    result: str
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    home_shots: int | None = None
    away_shots: int | None = None
    home_sot: int | None = None
    away_sot: int | None = None
    # Counted, not nullable: 0 means "no reported injuries or no data for this
    # era" -- callers that care about the difference (e.g. the injury-weight
    # validation study) are responsible for restricting themselves to seasons
    # with real source coverage, since the count alone can't distinguish them.
    home_injuries: int = 0
    away_injuries: int = 0


def upsert_match(
    conn: sqlite3.Connection,
    *,
    source: str,
    league: str,
    season: int,
    match_date: str,
    kickoff_time: str | None,
    home_team_id: int,
    away_team_id: int,
    status: str,
    home_goals: int | None,
    away_goals: int | None,
    result: str | None,
    odds: tuple[float | None, float | None, float | None] = (None, None, None),
    source_ref: str | None = None,
    kickoff_utc: str | None = None,
    round_no: int | None = None,
    shots: tuple[int | None, int | None] = (None, None),
    shots_on_target: tuple[int | None, int | None] = (None, None),
    corners: tuple[int | None, int | None] = (None, None),
) -> None:
    """Insert or update a match.

    Odds and kickoff_utc use COALESCE so that a source which does not carry
    them cannot wipe values another source already supplied.
    """
    conn.execute(
        """
        INSERT INTO matches (
            source, source_ref, league, season, match_date, kickoff_time,
            kickoff_utc, round, home_team_id, away_team_id, status,
            home_goals, away_goals, result,
            closing_odds_home, closing_odds_draw, closing_odds_away,
            home_shots, away_shots, home_shots_on_target, away_shots_on_target,
            home_corners, away_corners
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?)
        ON CONFLICT (league, season, home_team_id, away_team_id) DO UPDATE SET
            source_ref        = coalesce(excluded.source_ref, matches.source_ref),
            match_date        = excluded.match_date,
            kickoff_time      = coalesce(excluded.kickoff_time, matches.kickoff_time),
            kickoff_utc       = coalesce(excluded.kickoff_utc, matches.kickoff_utc),
            round             = coalesce(excluded.round, matches.round),
            status            = excluded.status,
            home_goals        = excluded.home_goals,
            away_goals        = excluded.away_goals,
            result            = excluded.result,
            closing_odds_home = coalesce(excluded.closing_odds_home, matches.closing_odds_home),
            closing_odds_draw = coalesce(excluded.closing_odds_draw, matches.closing_odds_draw),
            closing_odds_away = coalesce(excluded.closing_odds_away, matches.closing_odds_away),
            home_shots           = coalesce(excluded.home_shots, matches.home_shots),
            away_shots           = coalesce(excluded.away_shots, matches.away_shots),
            home_shots_on_target = coalesce(excluded.home_shots_on_target, matches.home_shots_on_target),
            away_shots_on_target = coalesce(excluded.away_shots_on_target, matches.away_shots_on_target),
            home_corners         = coalesce(excluded.home_corners, matches.home_corners),
            away_corners         = coalesce(excluded.away_corners, matches.away_corners),
            updated_at        = datetime('now')
        """,
        (
            source, source_ref, league, season, match_date, kickoff_time,
            kickoff_utc, round_no, home_team_id, away_team_id, status,
            home_goals, away_goals, result,
            odds[0], odds[1], odds[2],
            shots[0], shots[1], shots_on_target[0], shots_on_target[1],
            corners[0], corners[1],
        ),
    )


@dataclass(frozen=True)
class Fixture:
    """An upcoming match awaiting a prediction."""

    id: int
    league: str
    season: int
    kickoff_utc: str
    round_no: int | None
    home: str
    away: str


def upcoming_fixtures(
    conn: sqlite3.Connection, league: str, after_utc: str, before_utc: str
) -> list[Fixture]:
    rows = conn.execute(
        """
        SELECT m.id, m.league, m.season, m.kickoff_utc, m.round,
               h.name AS home, a.name AS away
        FROM matches m
        JOIN teams h ON h.id = m.home_team_id
        JOIN teams a ON a.id = m.away_team_id
        WHERE m.league = ? AND m.status = 'scheduled'
          AND m.kickoff_utc IS NOT NULL
          AND m.kickoff_utc > ? AND m.kickoff_utc <= ?
        ORDER BY m.kickoff_utc, m.id
        """,
        (league, after_utc, before_utc),
    ).fetchall()
    return [
        Fixture(
            id=int(r["id"]), league=r["league"], season=int(r["season"]),
            kickoff_utc=r["kickoff_utc"], round_no=r["round"],
            home=r["home"], away=r["away"],
        )
        for r in rows
    ]


def has_prediction(conn: sqlite3.Connection, match_id: int, model_version: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM predictions WHERE match_id = ? AND model_version = ? AND market = '1X2'",
        (match_id, model_version),
    ).fetchone()
    return row is not None


def insert_prediction(
    conn: sqlite3.Connection,
    *,
    match_id: int,
    model_version: str,
    probs: tuple[float, float, float],
    pick: str,
    confidence: float,
    created_at: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO predictions (
            match_id, model_version, market, p_home, p_draw, p_away,
            pick, confidence, created_at
        ) VALUES (?, ?, '1X2', ?, ?, ?, ?, ?, ?)
        """,
        (match_id, model_version, probs[0], probs[1], probs[2],
         pick, confidence, created_at),
    )
    return int(cur.lastrowid)


def grading_cutoff(as_of: str | None = None) -> str:
    """Latest kickoff_utc trusted enough to grade, given MIN_GRADING_DELAY_MINUTES.

    `as_of` overrides "now" for tests simulating elapsed time; production
    callers leave it unset and get the real wall clock.
    """
    now = clock.parse_iso(as_of) if as_of else clock.utc_now()
    cutoff = now - timedelta(minutes=config.MIN_GRADING_DELAY_MINUTES)
    return clock.to_iso(cutoff)


def ungraded_predictions(
    conn: sqlite3.Connection, league: str, as_of: str | None = None
) -> list[dict]:
    """Published predictions whose match finished long enough ago to trust,
    and which have no result yet.

    A "finished" flag can arrive prematurely with a wrong score (see
    MIN_GRADING_DELAY_MINUTES) -- this only grades matches whose kickoff was
    far enough in the past that a real final whistle is plausible.
    """
    cutoff = grading_cutoff(as_of)
    rows = conn.execute(
        """
        SELECT p.id, p.match_id, p.p_home, p.p_draw, p.p_away, p.pick,
               m.result
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        LEFT JOIN prediction_results r ON r.prediction_id = p.id
        WHERE m.league = ? AND m.status = 'finished' AND m.result IS NOT NULL
          AND m.kickoff_utc <= ?
          AND r.prediction_id IS NULL
        ORDER BY m.kickoff_utc
        """,
        (league, cutoff),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_result(
    conn: sqlite3.Connection,
    *,
    prediction_id: int,
    actual: str,
    is_hit: bool,
    log_loss: float,
    rps: float,
    brier: float,
    graded_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO prediction_results (
            prediction_id, actual, is_hit, log_loss, rps, brier, graded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (prediction_id, actual, int(is_hit), log_loss, rps, brier, graded_at),
    )


def match_ids_by_key(conn: sqlite3.Connection, league: str) -> dict[tuple, int]:
    """Local match ids keyed by (season, home name, away name)."""
    rows = conn.execute(
        """
        SELECT m.id, m.season, h.name AS home, a.name AS away
        FROM matches m
        JOIN teams h ON h.id = m.home_team_id
        JOIN teams a ON a.id = m.away_team_id
        WHERE m.league = ?
        """,
        (league,),
    ).fetchall()
    return {(int(r["season"]), r["home"], r["away"]): int(r["id"]) for r in rows}


def prediction_id(
    conn: sqlite3.Connection, match_id: int, model_version: str, market: str = "1X2"
) -> int | None:
    row = conn.execute(
        """SELECT id FROM predictions
           WHERE match_id = ? AND model_version = ? AND market = ?""",
        (match_id, model_version, market),
    ).fetchone()
    return int(row["id"]) if row else None


def has_result(conn: sqlite3.Connection, prediction_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM prediction_results WHERE prediction_id = ?", (prediction_id,)
    ).fetchone()
    return row is not None


def track_record(
    conn: sqlite3.Connection, league: str, model_version: str | None = None
) -> list[dict]:
    """Every published prediction with its outcome, newest first.

    `model_version` scopes the record to one model. Two versions must never be
    averaged into a single accuracy figure -- they are different predictors,
    and mixing them would make the headline number meaningless. Passing None
    returns every version, which is for auditing rather than publication.

    Note what is *not* filterable here: there is no way to ask this for hits
    only. That is deliberate.
    """
    sql = """
        SELECT p.id AS prediction_id, m.id AS match_id, m.league, m.season,
               m.kickoff_utc, m.round, m.status,
               h.name AS home, a.name AS away,
               m.home_goals, m.away_goals,
               p.model_version, p.p_home, p.p_draw, p.p_away, p.pick,
               p.confidence, p.created_at AS predicted_at,
               r.actual, r.is_hit, r.log_loss, r.rps, r.brier
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        JOIN teams h ON h.id = m.home_team_id
        JOIN teams a ON a.id = m.away_team_id
        LEFT JOIN prediction_results r ON r.prediction_id = p.id
        WHERE m.league = ?
    """
    params: list = [league]
    if model_version is not None:
        sql += " AND p.model_version = ?"
        params.append(model_version)
    sql += " ORDER BY m.kickoff_utc DESC, p.id DESC"

    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def model_versions(conn: sqlite3.Connection, league: str) -> list[dict]:
    """Every model version that has published into this league."""
    rows = conn.execute(
        """
        SELECT p.model_version AS version, count(*) AS published,
               sum(CASE WHEN r.prediction_id IS NOT NULL THEN 1 ELSE 0 END) AS graded,
               min(p.created_at) AS first_published
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        LEFT JOIN prediction_results r ON r.prediction_id = p.id
        WHERE m.league = ?
        GROUP BY p.model_version
        ORDER BY first_published
        """,
        (league,),
    ).fetchall()
    return [dict(r) for r in rows]


def finished_matches(
    conn: sqlite3.Connection, league: str = "EPL"
) -> list[MatchRow]:
    """All finished matches in chronological order."""
    rows = conn.execute(
        """
        SELECT m.id, m.season, m.match_date,
               h.name AS home, a.name AS away,
               m.home_goals, m.away_goals, m.result,
               m.closing_odds_home, m.closing_odds_draw, m.closing_odds_away,
               m.home_shots, m.away_shots,
               m.home_shots_on_target, m.away_shots_on_target,
               (SELECT count(*) FROM injuries i
                WHERE i.match_id = m.id AND i.team_id = m.home_team_id) AS home_injuries,
               (SELECT count(*) FROM injuries i
                WHERE i.match_id = m.id AND i.team_id = m.away_team_id) AS away_injuries
        FROM matches m
        JOIN teams h ON h.id = m.home_team_id
        JOIN teams a ON a.id = m.away_team_id
        WHERE m.league = ? AND m.status = 'finished'
        ORDER BY m.match_date, m.id
        """,
        (league,),
    ).fetchall()
    return [
        MatchRow(
            id=int(r["id"]),
            season=int(r["season"]),
            match_date=date.fromisoformat(r["match_date"]),
            home=r["home"],
            away=r["away"],
            home_goals=int(r["home_goals"]),
            away_goals=int(r["away_goals"]),
            result=r["result"],
            odds_home=r["closing_odds_home"],
            odds_draw=r["closing_odds_draw"],
            odds_away=r["closing_odds_away"],
            home_shots=r["home_shots"],
            away_shots=r["away_shots"],
            home_sot=r["home_shots_on_target"],
            away_sot=r["away_shots_on_target"],
            home_injuries=int(r["home_injuries"]),
            away_injuries=int(r["away_injuries"]),
        )
        for r in rows
    ]


def match_id_for_team_on_date(
    conn: sqlite3.Connection, team_id: int, match_date: str, league: str
) -> int | None:
    """The one match `team_id` played in `league` on `match_date`, if any.

    A team plays at most one match per day within a single league, so this is
    unambiguous. Used to resolve an injury record (source: team + fixture
    date) onto our own match row without needing the source's own match ids.
    """
    row = conn.execute(
        """
        SELECT id FROM matches
        WHERE league = ? AND match_date = ?
          AND (home_team_id = ? OR away_team_id = ?)
        """,
        (league, match_date, team_id, team_id),
    ).fetchone()
    return int(row["id"]) if row else None


def insert_injury(
    conn: sqlite3.Connection,
    *,
    source: str,
    league: str,
    match_id: int | None,
    team_id: int,
    player_name: str,
    reason: str | None,
    fixture_date: str,
) -> None:
    conn.execute(
        """
        INSERT INTO injuries (
            source, league, match_id, team_id, player_name, reason, fixture_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, team_id, player_name, fixture_date) DO UPDATE SET
            match_id = coalesce(excluded.match_id, injuries.match_id),
            reason   = coalesce(excluded.reason, injuries.reason)
        """,
        (source, league, match_id, team_id, player_name, reason, fixture_date),
    )


def resolve_pending_injuries(conn: sqlite3.Connection, league: str) -> int:
    """Re-attempt matching for injury rows stored before their fixture existed
    locally. `insert_injury` never drops a row for lack of a match -- this is
    the catch-up pass that lets a later fixture sync retroactively fill it in.
    """
    cur = conn.execute(
        """
        UPDATE injuries SET match_id = (
            SELECT m.id FROM matches m
            WHERE m.league = injuries.league
              AND m.match_date = injuries.fixture_date
              AND (m.home_team_id = injuries.team_id OR m.away_team_id = injuries.team_id)
        )
        WHERE match_id IS NULL AND league = ?
          AND EXISTS (
            SELECT 1 FROM matches m
            WHERE m.league = injuries.league
              AND m.match_date = injuries.fixture_date
              AND (m.home_team_id = injuries.team_id OR m.away_team_id = injuries.team_id)
          )
        """,
        (league,),
    )
    conn.commit()
    return cur.rowcount


def injury_counts(conn: sqlite3.Connection, league: str) -> dict[str, int]:
    """How many injury records resolved onto a match, by season -- the
    coverage map a validation study needs to pick a real-data window."""
    rows = conn.execute(
        """
        SELECT m.season AS season, count(*) AS n
        FROM injuries i
        JOIN matches m ON m.id = i.match_id
        WHERE m.league = ?
        GROUP BY m.season ORDER BY m.season
        """,
        (league,),
    ).fetchall()
    return {int(r["season"]): int(r["n"]) for r in rows}


# --- v2 markets (BTTS, Over/Under): a genuinely generic table, not a reuse of
# predictions' p_home/p_draw/p_away columns -- see db/schema.sql. One row per
# possible outcome per market per fixture, so a "prediction" here is really a
# small set of rows sharing (match_id, model_version, market).

def has_market_prediction(
    conn: sqlite3.Connection, match_id: int, model_version: str, market: str
) -> bool:
    row = conn.execute(
        """SELECT 1 FROM market_predictions
           WHERE match_id = ? AND model_version = ? AND market = ? LIMIT 1""",
        (match_id, model_version, market),
    ).fetchone()
    return row is not None


def insert_market_prediction(
    conn: sqlite3.Connection,
    *,
    match_id: int,
    model_version: str,
    market: str,
    probabilities: dict[str, float],
    pick: str,
    created_at: str,
) -> None:
    for outcome, p in probabilities.items():
        conn.execute(
            """
            INSERT INTO market_predictions (
                match_id, model_version, market, outcome, probability,
                is_pick, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (match_id, model_version, market, outcome, p,
             1 if outcome == pick else 0, created_at),
        )


def ungraded_market_predictions(
    conn: sqlite3.Connection, league: str, market: str, as_of: str | None = None
) -> list[dict]:
    """Published market predictions whose match finished long enough ago to
    trust, and which have no result yet. Grouped back up from
    one-row-per-outcome into one entry per fixture, since grading needs the
    whole probability set plus the pick together.

    See ungraded_predictions() for why kickoff must be at least
    MIN_GRADING_DELAY_MINUTES in the past before a "finished" match is graded.
    """
    cutoff = grading_cutoff(as_of)
    rows = conn.execute(
        """
        SELECT mp.match_id, mp.model_version, mp.outcome, mp.probability,
               mp.is_pick, m.home_goals, m.away_goals
        FROM market_predictions mp
        JOIN matches m ON m.id = mp.match_id
        LEFT JOIN market_prediction_results r
          ON r.match_id = mp.match_id AND r.model_version = mp.model_version
         AND r.market = mp.market
        WHERE m.league = ? AND mp.market = ? AND m.status = 'finished'
          AND m.home_goals IS NOT NULL AND m.kickoff_utc <= ?
          AND r.match_id IS NULL
        ORDER BY m.kickoff_utc
        """,
        (league, market, cutoff),
    ).fetchall()

    grouped: dict[tuple, dict] = {}
    for r in rows:
        key = (r["match_id"], r["model_version"])
        entry = grouped.setdefault(
            key,
            {
                "match_id": r["match_id"],
                "model_version": r["model_version"],
                "home_goals": r["home_goals"],
                "away_goals": r["away_goals"],
                "probabilities": {},
                "pick": None,
            },
        )
        entry["probabilities"][r["outcome"]] = r["probability"]
        if r["is_pick"]:
            entry["pick"] = r["outcome"]
    return list(grouped.values())


def insert_market_result(
    conn: sqlite3.Connection,
    *,
    match_id: int,
    model_version: str,
    market: str,
    actual_outcome: str,
    is_hit: bool,
    log_loss: float,
    brier: float,
    graded_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO market_prediction_results (
            match_id, model_version, market, actual_outcome, is_hit,
            log_loss, brier, graded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (match_id, model_version, market, actual_outcome, int(is_hit),
         log_loss, brier, graded_at),
    )


def market_accuracy(
    conn: sqlite3.Connection, league: str, market: str, model_version: str
) -> dict:
    """Headline accuracy for one v2 market, scoped to one model version --
    same reasoning as 1X2's `publish.accuracy`: averaging predictors together
    would misrepresent both."""
    row = conn.execute(
        """
        SELECT count(*) AS n,
               sum(r.is_hit) AS hits,
               avg(r.log_loss) AS log_loss,
               avg(r.brier) AS brier
        FROM market_prediction_results r
        JOIN matches m ON m.id = r.match_id
        WHERE m.league = ? AND r.market = ? AND r.model_version = ?
        """,
        (league, market, model_version),
    ).fetchone()
    n = int(row["n"] or 0)
    hits = int(row["hits"] or 0)
    return {
        "market": market,
        "model_version": model_version,
        "n": n,
        "hits": hits,
        "accuracy": hits / n if n else 0.0,
        "log_loss": row["log_loss"] if n else 0.0,
        "brier": row["brier"] if n else 0.0,
    }


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for table in ("teams", "matches", "predictions", "backtest_runs"):
        out[table] = int(
            conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
        )
    return out
