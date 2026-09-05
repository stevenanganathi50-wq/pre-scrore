"""Injuries feed from API-Football (api-sports.io).

Free tier gates the *current* season entirely: any request for it returns
`{"errors": {"plan": "Free plans do not have access to this season, try from
2022 to 2024."}}` -- a paid plan is required to see anything about the season
being predicted. Historical coverage, checked directly against this project's
account, spans roughly 2020 (partial) through the present; 2018 and earlier
return zero results, because the source simply doesn't track injuries that
far back.

Each record is tied to a specific fixture date -- "this player was listed as
injured/doubtful for this match" -- not a rolling availability status. That
is what makes it usable as a per-fixture covariate directly, with no as-of
windowing logic needed.

A record whose fixture isn't in our `matches` table yet is still stored (with
match_id left NULL) rather than dropped, and `store.resolve_pending_injuries`
re-attempts the match once that fixture has synced.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import config, settings, store, teams

SOURCE = "api-football"
BASE_URL = "https://v3.football.api-sports.io"
USER_AGENT = "pre-scrore/0.1 (+injury data)"
REQUEST_SPACING_SECONDS = 0.25  # comfortably under the Pro-tier 300/min cap

# API-Football's own league ids, not football-data.co.uk's or TheSportsDB's.
LEAGUE_IDS = {"EPL": 39}


class ApiFootballError(RuntimeError):
    """A request failed or the account's plan does not cover it."""


def _get(path: str, params: dict[str, str]) -> dict:
    key = settings.get("API_FOOTBALL_KEY")
    if not key:
        raise ApiFootballError(
            "API_FOOTBALL_KEY is not set -- copy .env.example to .env and fill it in"
        )
    url = f"{BASE_URL}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"x-apisports-key": key, "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ApiFootballError(f"GET {path} failed with HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise ApiFootballError(f"GET {path} could not connect: {exc.reason}") from None

    if payload.get("errors"):
        raise ApiFootballError(f"GET {path} returned: {payload['errors']}")
    return payload


def fetch_injuries(league_code: str, season: int) -> list[dict]:
    """Every injury record for one league-season, in a single request."""
    payload = _get(
        "injuries",
        {"league": str(LEAGUE_IDS[league_code]), "season": str(season)},
    )
    return payload.get("response") or []


class SyncReport:
    def __init__(self) -> None:
        self.seasons: list[int] = []
        self.stored = 0
        self.skipped = 0
        self.unmatched_fixtures = 0
        self.newly_resolved = 0
        self.unresolved_teams: set[str] = set()

    def as_text(self) -> str:
        lines = [f"seasons synced: {self.seasons}", f"records stored: {self.stored}"]
        if self.newly_resolved:
            lines.append(f"backfilled onto a fixture: {self.newly_resolved}")
        if self.unmatched_fixtures:
            lines.append(
                f"still unmatched to any local fixture: {self.unmatched_fixtures} "
                "(will retry on the next sync)"
            )
        if self.skipped:
            lines.append(f"skipped (missing player/team/date): {self.skipped}")
        if self.unresolved_teams:
            lines.append(
                "UNRESOLVED TEAM NAMES (add to prescore/teams.py ALIASES): "
                + ", ".join(sorted(self.unresolved_teams))
            )
        return "\n".join(lines)


def sync_injuries(
    conn, league_code: str, seasons: list[int], log=print
) -> SyncReport:
    """Pull and store every injury record for the given seasons.

    An unresolvable team name is reported, never turned into a new team --
    the same rule every other ingester in this project follows.
    """
    league = config.LEAGUES[league_code]
    report = SyncReport()

    for season in seasons:
        try:
            records = fetch_injuries(league_code, season)
        except ApiFootballError as exc:
            log(f"  season {season}: {exc}")
            continue

        report.seasons.append(season)

        for raw in records:
            player_info = raw.get("player") or {}
            team_info = raw.get("team") or {}
            fixture_info = raw.get("fixture") or {}

            player = player_info.get("name")
            reason = player_info.get("reason")
            team_name = team_info.get("name")
            fixture_date = (fixture_info.get("date") or "")[:10]

            if not player or not team_name or not fixture_date:
                report.skipped += 1
                continue

            canonical = teams.resolve(conn, team_name, SOURCE)
            if canonical is None:
                report.unresolved_teams.add(team_name)
                continue
            team_id = teams.register(conn, team_name, SOURCE, canonical)

            match_id = store.match_id_for_team_on_date(
                conn, team_id, fixture_date, league.code
            )
            if match_id is None:
                report.unmatched_fixtures += 1

            store.insert_injury(
                conn,
                source=SOURCE,
                league=league.code,
                match_id=match_id,
                team_id=team_id,
                player_name=player,
                reason=reason,
                fixture_date=fixture_date,
            )
            report.stored += 1

        conn.commit()
        log(f"  season {season}: {len(records)} records fetched")
        time.sleep(REQUEST_SPACING_SECONDS)

    report.newly_resolved = store.resolve_pending_injuries(conn, league.code)
    report.unmatched_fixtures = conn.execute(
        "SELECT count(*) AS n FROM injuries WHERE match_id IS NULL AND league = ?",
        (league.code,),
    ).fetchone()["n"]

    return report
