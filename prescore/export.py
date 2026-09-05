"""Generate the JSON the static frontend reads.

One file, written to web/data.json. The frontend has no backend and no build
step -- it fetches this and renders it.

Everything published here is derived from the database with no filtering that
could drop losses. If the record is bad, the site says so.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import clock, config, publish, store

WEB_DIR = config.ROOT / "web"
DATA_PATH = WEB_DIR / "data.json"

# A team with fewer finished matches than this in our history is rated close
# to league average, and its predictions deserve a visible caveat.
THIN_HISTORY_MATCHES = 30

DISCLAIMER = (
    "Statistical predictions and probabilities for informational purposes. "
    "Not betting advice."
)


def _history_counts(conn: sqlite3.Connection, league: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT t.name AS name, count(*) AS n FROM matches m
        JOIN teams t ON t.id IN (m.home_team_id, m.away_team_id)
        WHERE m.league = ? AND m.status = 'finished'
        GROUP BY t.name
        """,
        (league,),
    ).fetchall()
    return {r["name"]: int(r["n"]) for r in rows}


def _latest_backtest(conn: sqlite3.Connection, league: str) -> dict | None:
    row = conn.execute(
        """
        SELECT r.id, r.model_version, r.params, r.test_from, r.test_to,
               r.n_predictions, r.created_at,
               sum(bp.is_hit) AS hits
        FROM backtest_runs r
        JOIN backtest_predictions bp ON bp.run_id = r.id
        WHERE r.league = ?
        GROUP BY r.id
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT 1
        """,
        (league,),
    ).fetchone()
    if row is None:
        return None
    hits = int(row["hits"] or 0)
    n = int(row["n_predictions"])
    return {
        "test_from": row["test_from"],
        "test_to": row["test_to"],
        "n": n,
        "hits": hits,
        "accuracy": hits / n if n else 0.0,
        "params": json.loads(row["params"]),
        "run_at": row["created_at"],
    }


def build(
    conn: sqlite3.Connection,
    league: str = "EPL",
    model_version: str | None = config.MODEL_VERSION,
) -> dict:
    """Build the site payload.

    Published predictions are immutable, so an improved model is published
    alongside the old one rather than replacing it. Every fixture therefore
    carries one entry per model version that predicted it -- `model_version`
    (the current model) is flagged `is_current` and sorted first, but nothing
    from a superseded version is hidden. The headline accuracy figure stays
    scoped to one version at a time (mixing predictors would misrepresent
    both); `accuracy_by_version` carries the same figures for every version
    that has graded predictions, so they can be shown side by side once there
    is enough live data to compare.
    """
    league_cfg = config.LEAGUES[league]
    record = store.track_record(conn, league, None)
    counts = _history_counts(conn, league)
    versions = store.model_versions(conn, league)

    def thin(row) -> list[str]:
        return [
            team
            for team in (row["home"], row["away"])
            if counts.get(team, 0) < THIN_HISTORY_MATCHES
        ]

    matches: dict[int, dict] = {}
    for row in record:
        mid = row["match_id"]
        match = matches.get(mid)
        if match is None:
            match = {
                "match_id": mid,
                "kickoff_utc": row["kickoff_utc"],
                "round": row["round"],
                "home": row["home"],
                "away": row["away"],
                "thin_history": thin(row),
                "graded": row["status"] == "finished",
                "home_goals": row["home_goals"],
                "away_goals": row["away_goals"],
                "actual": row["actual"],
                "predictions": [],
            }
            matches[mid] = match

        match["predictions"].append(
            {
                "model_version": row["model_version"],
                "is_current": row["model_version"] == model_version,
                "p_home": round(row["p_home"], 4),
                "p_draw": round(row["p_draw"], 4),
                "p_away": round(row["p_away"], 4),
                "pick": row["pick"],
                "confidence": round(row["confidence"], 4),
                "predicted_at": row["predicted_at"],
                "is_hit": None if row["is_hit"] is None else bool(row["is_hit"]),
            }
        )

    upcoming, results = [], []
    for match in matches.values():
        # Newest version first lexically, then a stable pass pulls today's
        # model to the very front regardless -- so the current prediction
        # always leads, with every other version listed alongside it rather
        # than hidden.
        match["predictions"].sort(key=lambda p: p["model_version"], reverse=True)
        match["predictions"].sort(key=lambda p: not p["is_current"])
        (results if match["graded"] else upcoming).append(match)

    upcoming.sort(key=lambda e: e["kickoff_utc"] or "")
    results.sort(key=lambda e: e["kickoff_utc"] or "", reverse=True)

    accuracy_by_version = {}
    for v in versions:
        if v["graded"]:
            accuracy_by_version[v["version"]] = publish.accuracy(
                conn, league, v["version"]
            )

    return {
        "generated_at": clock.now_iso(),
        "league": league_cfg.name,
        "league_code": league_cfg.code,
        "model_version": model_version or "all",
        "model_versions": versions,
        "disclaimer": DISCLAIMER,
        "accuracy": publish.accuracy(conn, league, model_version),
        "accuracy_by_version": accuracy_by_version,
        "backtest": _latest_backtest(conn, league),
        "upcoming": upcoming,
        "results": results,
    }


def write(
    conn: sqlite3.Connection,
    league: str = "EPL",
    path: Path | None = None,
    model_version: str | None = config.MODEL_VERSION,
) -> Path:
    """Write data.json, plus a data.js twin.

    Browsers refuse cross-origin fetch() on file:// URLs, so a plain
    double-click on index.html cannot read data.json. The .js twin assigns the
    same payload to a global, which loads fine from file://. Hosted deploys
    use the .json.
    """
    target = path or DATA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build(conn, league, model_version)
    body = json.dumps(payload, indent=2)

    target.write_text(body, encoding="utf-8")
    target.with_suffix(".js").write_text(
        f"window.PRESCORE_DATA = {body};\n", encoding="utf-8"
    )
    return target
