"""Ingest historical results from football-data.co.uk.

Free CSVs, one file per division per season, e.g.
https://www.football-data.co.uk/mmz4281/2425/E0.csv

We take results and closing odds. The odds are stored purely as a backtest
benchmark -- the model never sees them and the product never shows them.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .. import config, store

SOURCE = "football-data.co.uk"
BASE_URL = "https://www.football-data.co.uk/mmz4281"
USER_AGENT = "pre-scrore/0.1 (+historical data seeding)"

# Preference order for the 1X2 odds we keep as a benchmark. "C" columns are
# closing odds and only exist in later seasons.
ODDS_COLUMNS = (
    ("AvgCH", "AvgCD", "AvgCA"),
    ("PSCH", "PSCD", "PSCA"),
    ("B365CH", "B365CD", "B365CA"),
    ("AvgH", "AvgD", "AvgA"),
    ("BbAvH", "BbAvD", "BbAvA"),
    ("B365H", "B365D", "B365A"),
)


def season_code(start_year: int) -> str:
    """2015 -> '1516'."""
    return f"{str(start_year)[-2:]}{str(start_year + 1)[-2:]}"


def csv_url(start_year: int, div: str) -> str:
    return f"{BASE_URL}/{season_code(start_year)}/{div}.csv"


def download(start_year: int, div: str, cache_dir: Path, refresh: bool = False) -> str | None:
    """Fetch a season CSV, caching the raw bytes on disk.

    Returns the decoded text, or None if the season is not published.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{div}_{season_code(start_year)}.csv"

    if cached.exists() and not refresh:
        raw = cached.read_bytes()
    else:
        req = urllib.request.Request(
            csv_url(start_year, div), headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        cached.write_bytes(raw)

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _parse_date(value: str) -> str | None:
    value = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_time(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


def _parse_int(row: dict[str, str], column: str) -> int | None:
    try:
        return int(row[column])
    except (KeyError, TypeError, ValueError):
        return None


def _parse_odds(row: dict[str, str]) -> tuple[float | None, float | None, float | None]:
    for home_col, draw_col, away_col in ODDS_COLUMNS:
        try:
            odds = (
                float(row[home_col]),
                float(row[draw_col]),
                float(row[away_col]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if all(o > 1.0 for o in odds):
            return odds
    return (None, None, None)


def parse_season(text: str, div: str | None = None) -> tuple[list[dict], int]:
    """Turn one season CSV into normalized match dicts, skipping junk rows.

    Returns (matches, wrong_division_rows). Passing `div` is important: the
    source has been observed publishing a next-season file seeded with rows
    from a completely different competition, and those rows carry team names
    that would otherwise be created as phantom Premier League clubs.
    """
    reader = csv.DictReader(io.StringIO(text))
    matches = []
    wrong_div = 0

    for row in reader:
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        if not home or not away:
            continue

        if div is not None and (row.get("Div") or "").strip().upper() != div.upper():
            wrong_div += 1
            continue

        match_date = _parse_date(row.get("Date", ""))
        if match_date is None:
            continue

        try:
            home_goals = int(row["FTHG"])
            away_goals = int(row["FTAG"])
        except (KeyError, TypeError, ValueError):
            # Fixture published without a result yet.
            continue

        result = row.get("FTR", "").strip().upper()
        if result not in ("H", "D", "A"):
            result = "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D"

        matches.append(
            {
                "date": match_date,
                "time": _parse_time(row.get("Time")),
                "home": home,
                "away": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "result": result,
                "odds": _parse_odds(row),
                # Shot counts feed the expected-goals proxy. Present in every
                # EPL season we ingest, but treated as optional so a season
                # without them still loads.
                "shots": (_parse_int(row, "HS"), _parse_int(row, "AS")),
                "shots_on_target": (_parse_int(row, "HST"), _parse_int(row, "AST")),
                "corners": (_parse_int(row, "HC"), _parse_int(row, "AC")),
            }
        )
    return matches, wrong_div


def seed(
    conn: sqlite3.Connection,
    league_code: str = "EPL",
    seasons: tuple[int, ...] | None = None,
    refresh: bool = False,
    log=print,
) -> dict[int, int]:
    """Download and store every requested season. Returns matches per season."""
    league = config.LEAGUES[league_code]
    seasons = seasons or config.default_seasons()
    written: dict[int, int] = {}

    for start_year in seasons:
        text = download(start_year, league.fd_div, config.RAW_DIR, refresh=refresh)
        if text is None:
            log(f"  {config.season_label(start_year)}: not published yet, skipped")
            continue

        matches, wrong_div = parse_season(text, div=league.fd_div)
        if wrong_div:
            log(
                f"  {config.season_label(start_year)}: skipped {wrong_div} rows "
                f"from another division"
            )
        for m in matches:
            home_id = store.team_id(conn, m["home"])
            away_id = store.team_id(conn, m["away"])
            store.add_alias(conn, m["home"], SOURCE, home_id)
            store.add_alias(conn, m["away"], SOURCE, away_id)
            store.upsert_match(
                conn,
                source=SOURCE,
                league=league.code,
                season=start_year,
                match_date=m["date"],
                kickoff_time=m["time"],
                home_team_id=home_id,
                away_team_id=away_id,
                status="finished",
                home_goals=m["home_goals"],
                away_goals=m["away_goals"],
                result=m["result"],
                odds=m["odds"],
                shots=m["shots"],
                shots_on_target=m["shots_on_target"],
                corners=m["corners"],
            )
        conn.commit()
        written[start_year] = len(matches)
        log(f"  {config.season_label(start_year)}: {len(matches)} matches")

    return written
