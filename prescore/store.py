"""SQLite access layer.

Kept thin and explicit so the same statements can be lifted to Postgres when
the Supabase side is built.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import config


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


def ungraded_predictions(conn: sqlite3.Connection, league: str) -> list[dict]:
    """Published predictions whose match has finished but which have no result."""
    rows = conn.execute(
        """
        SELECT p.id, p.match_id, p.p_home, p.p_draw, p.p_away, p.pick,
               m.result
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        LEFT JOIN prediction_results r ON r.prediction_id = p.id
        WHERE m.league = ? AND m.status = 'finished' AND m.result IS NOT NULL
          AND r.prediction_id IS NULL
        ORDER BY m.kickoff_utc
        """,
        (league,),
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
               m.home_shots_on_target, m.away_shots_on_target
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
        )
        for r in rows
    ]


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for table in ("teams", "matches", "predictions", "backtest_runs"):
        out[table] = int(
            conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
        )
    return out
