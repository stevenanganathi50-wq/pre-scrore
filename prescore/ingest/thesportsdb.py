"""Upcoming fixtures and live results from TheSportsDB.

Free tier, no account required. Two things learned the hard way and encoded
here:

* Use API key "123", not "3". Key "3" silently truncates every response to
  five results, so a 10-fixture matchweek comes back half empty with no error.
* `eventsnextleague.php` and `eventspastleague.php` return only ONE event on
  the free tier regardless of key. Round-based lookups (`eventsround.php`) are
  the only endpoint that returns a full matchweek, so this adapter is
  round-based.

Team names differ from football-data.co.uk ("Manchester United" vs
"Man United"), so everything goes through prescore.teams.resolve.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from .. import clock, config, store, teams

SOURCE = "thesportsdb"
BASE_URL = "https://www.thesportsdb.com/api/v1/json"
DEFAULT_KEY = "123"
USER_AGENT = "pre-scrore/0.1 (+fixture sync)"
REQUEST_SPACING_SECONDS = 0.4

# TheSportsDB league ids.
LEAGUE_IDS = {"EPL": "4328"}

ROUNDS_PER_SEASON = 38


def api_key() -> str:
    return os.environ.get("PRESCORE_TSDB_KEY", DEFAULT_KEY)


def season_string(start_year: int) -> str:
    """2026 -> '2026-2027', the season format TheSportsDB expects."""
    return f"{start_year}-{start_year + 1}"


def season_start_year(season: str) -> int | None:
    try:
        return int(str(season).split("-")[0])
    except (ValueError, AttributeError):
        return None


def _get(path: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}/{api_key()}/{path}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_round(league_code: str, start_year: int, round_no: int) -> list[dict]:
    """Raw events for one matchweek."""
    payload = _get(
        "eventsround.php",
        {
            "id": LEAGUE_IDS[league_code],
            "r": str(round_no),
            "s": season_string(start_year),
        },
    )
    return payload.get("events") or []


def _score(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_event(event: dict) -> dict | None:
    """Normalize one raw event. Returns None if it is unusable."""
    home = (event.get("strHomeTeam") or "").strip()
    away = (event.get("strAwayTeam") or "").strip()
    if not home or not away:
        return None

    stamp = (event.get("strTimestamp") or "").strip()
    if not stamp:
        date_part = (event.get("dateEvent") or "").strip()
        time_part = (event.get("strTime") or "00:00:00").strip()
        if not date_part:
            return None
        stamp = f"{date_part}T{time_part}"

    try:
        kickoff_utc = clock.normalize(stamp)
    except ValueError:
        return None

    home_goals = _score(event.get("intHomeScore"))
    away_goals = _score(event.get("intAwayScore"))
    finished = home_goals is not None and away_goals is not None

    result = None
    if finished:
        result = (
            "H" if home_goals > away_goals
            else "A" if away_goals > home_goals
            else "D"
        )

    try:
        round_no = int(event.get("intRound"))
    except (TypeError, ValueError):
        round_no = None

    return {
        "source_ref": str(event.get("idEvent") or "") or None,
        "home": home,
        "away": away,
        "kickoff_utc": kickoff_utc,
        "match_date": kickoff_utc[:10],
        "kickoff_time": kickoff_utc[11:16],
        "round": round_no,
        "season": season_start_year(event.get("strSeason")),
        "status": "finished" if finished else "scheduled",
        "home_goals": home_goals,
        "away_goals": away_goals,
        "result": result,
        "postponed": (event.get("strPostponed") or "no").lower() == "yes",
    }


class SyncReport:
    """What a sync actually did, including what it refused to do."""

    def __init__(self) -> None:
        self.rounds: list[int] = []
        self.scheduled = 0
        self.finished = 0
        self.unresolved_teams: set[str] = set()
        self.kickoff_conflicts: list[str] = []
        self.skipped_events = 0

    @property
    def total(self) -> int:
        return self.scheduled + self.finished

    def as_text(self) -> str:
        lines = [
            f"rounds {len(self.rounds)}  fixtures {self.total} "
            f"(scheduled {self.scheduled}, finished {self.finished})"
        ]
        if self.skipped_events:
            lines.append(f"skipped {self.skipped_events} unusable events")
        if self.unresolved_teams:
            lines.append(
                "UNRESOLVED TEAM NAMES (add them to prescore/teams.py ALIASES): "
                + ", ".join(sorted(self.unresolved_teams))
            )
        for conflict in self.kickoff_conflicts:
            lines.append(f"KICKOFF MOVED AFTER PUBLISHING: {conflict}")
        return "\n".join(lines)


def sync_rounds(
    conn: sqlite3.Connection,
    league_code: str,
    start_year: int,
    rounds,
    log=print,
) -> SyncReport:
    """Pull the given matchweeks and upsert every fixture.

    Unrecognised team names are collected and reported, never invented. A
    fixture that has moved after we published a prediction for it trips the
    kickoff-protection trigger; that is recorded as a conflict for review
    rather than being forced through.
    """
    league = config.LEAGUES[league_code]
    report = SyncReport()

    for round_no in rounds:
        try:
            events = fetch_round(league_code, start_year, round_no)
        except urllib.error.URLError as exc:
            log(f"  round {round_no}: request failed ({exc})")
            continue

        report.rounds.append(round_no)

        for raw in events:
            parsed = parse_event(raw)
            if parsed is None:
                report.skipped_events += 1
                continue

            home = teams.resolve(conn, parsed["home"], SOURCE)
            away = teams.resolve(conn, parsed["away"], SOURCE)
            if home is None or away is None:
                if home is None:
                    report.unresolved_teams.add(parsed["home"])
                if away is None:
                    report.unresolved_teams.add(parsed["away"])
                continue

            home_id = teams.register(conn, parsed["home"], SOURCE, home)
            away_id = teams.register(conn, parsed["away"], SOURCE, away)

            try:
                store.upsert_match(
                    conn,
                    source=SOURCE,
                    source_ref=parsed["source_ref"],
                    league=league.code,
                    season=parsed["season"] or start_year,
                    match_date=parsed["match_date"],
                    kickoff_time=parsed["kickoff_time"],
                    kickoff_utc=parsed["kickoff_utc"],
                    round_no=parsed["round"],
                    home_team_id=home_id,
                    away_team_id=away_id,
                    status=parsed["status"],
                    home_goals=parsed["home_goals"],
                    away_goals=parsed["away_goals"],
                    result=parsed["result"],
                )
            except sqlite3.IntegrityError as exc:
                report.kickoff_conflicts.append(
                    f"{home} vs {away} ({parsed['kickoff_utc']}): {exc}"
                )
                continue

            if parsed["status"] == "finished":
                report.finished += 1
            else:
                report.scheduled += 1

        conn.commit()
        time.sleep(REQUEST_SPACING_SECONDS)

    return report


def current_rounds(
    conn: sqlite3.Connection, league_code: str, start_year: int, span: int = 2
) -> list[int]:
    """Rounds worth refreshing: those with a kickoff near now.

    Falls back to the first few rounds when the season has no fixtures stored
    yet, which is the case right after a season rolls over.
    """
    # Bounds are computed in Python, not with SQLite's datetime(), because
    # datetime() returns 'YYYY-MM-DD HH:MM:SS' which would not compare
    # correctly against our 'YYYY-MM-DDTHH:MM:SSZ' strings.
    now = clock.utc_now()
    rows = conn.execute(
        """
        SELECT DISTINCT round FROM matches
        WHERE league = ? AND season = ? AND round IS NOT NULL
          AND kickoff_utc IS NOT NULL
          AND kickoff_utc BETWEEN ? AND ?
        ORDER BY round
        """,
        (
            league_code,
            start_year,
            clock.to_iso(now - timedelta(days=10)),
            clock.to_iso(now + timedelta(days=14)),
        ),
    ).fetchall()

    rounds = [int(r["round"]) for r in rows]
    if not rounds:
        return list(range(1, span + 2))

    lo = max(1, min(rounds) - 1)
    hi = min(ROUNDS_PER_SEASON, max(rounds) + span)
    return list(range(lo, hi + 1))
