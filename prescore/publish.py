"""Publishing and grading — the loop that produces the public track record.

`publish` writes predictions for upcoming fixtures. `grade` scores them once
the matches finish. The two are deliberately separate: nothing in the grading
path can reach back and alter what was predicted.

The database refuses a prediction written at or after kickoff, and refuses any
update or delete of a prediction. This module does not need to be trusted for
the record to be honest — it just needs to not crash.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from . import clock, config, store
from .backtest import metrics
from .model import markets, poisson

# v2 markets published alongside 1X2, derived from the same fitted model's
# scoreline matrix -- see prescore/model/markets.py. Adding a market here
# does not touch the 1X2 prediction for any fixture.
MARKETS = ("BTTS", "OU2.5")


def build_model(
    conn: sqlite3.Connection,
    league: str = "EPL",
    half_life_days: float = config.DEFAULT_HALF_LIFE_DAYS,
    ridge: float = config.DEFAULT_RIDGE,
    ref_date=None,
) -> poisson.PoissonDixonColes:
    history = store.finished_matches(conn, league)
    if not history:
        raise ValueError("no finished matches -- run: python -m prescore ingest")
    return poisson.fit(
        history,
        ref_date=ref_date or clock.utc_now().date(),
        half_life_days=half_life_days,
        ridge=ridge,
    )


def _publish_market_predictions(
    conn: sqlite3.Connection,
    model: poisson.PoissonDixonColes,
    fixture,
    matrix,
    now_iso: str,
    dry_run: bool,
) -> list[str]:
    """Store BTTS/OU2.5 for one fixture, skipping any already published.
    Returns which markets were actually written (for reporting only)."""
    written_markets = []

    if not store.has_market_prediction(conn, fixture.id, model.version, "BTTS"):
        p_yes, p_no = markets.btts_probability(matrix)
        pick = "Yes" if p_yes >= p_no else "No"
        if not dry_run:
            store.insert_market_prediction(
                conn, match_id=fixture.id, model_version=model.version,
                market="BTTS", probabilities={"Yes": p_yes, "No": p_no},
                pick=pick, created_at=now_iso,
            )
        written_markets.append("BTTS")

    if not store.has_market_prediction(conn, fixture.id, model.version, "OU2.5"):
        p_over, p_under = markets.over_under_probability(matrix, line=2.5)
        pick = "Over" if p_over >= p_under else "Under"
        if not dry_run:
            store.insert_market_prediction(
                conn, match_id=fixture.id, model_version=model.version,
                market="OU2.5", probabilities={"Over": p_over, "Under": p_under},
                pick=pick, created_at=now_iso,
            )
        written_markets.append("OU2.5")

    return written_markets


def publish(
    conn: sqlite3.Connection,
    league: str = "EPL",
    *,
    horizon_days: int = 8,
    half_life_days: float = config.DEFAULT_HALF_LIFE_DAYS,
    ridge: float = config.DEFAULT_RIDGE,
    dry_run: bool = False,
    log=print,
) -> dict:
    """Predict every unpublished fixture kicking off within the horizon.

    Writes 1X2 first, then BTTS/OU2.5 derived from the same fitted model's
    scoreline matrix. The two are checked and skipped independently, so a
    fixture that already has 1X2 (e.g. published before v2 markets existed)
    still gets its market predictions backfilled rather than skipped whole.
    """
    now = clock.utc_now()
    now_iso = clock.to_iso(now)
    horizon_iso = clock.to_iso(now + timedelta(days=horizon_days))

    model = build_model(conn, league, half_life_days, ridge)
    fixtures = store.upcoming_fixtures(conn, league, now_iso, horizon_iso)

    written, skipped, no_history = [], 0, set()
    markets_written = 0

    for fixture in fixtures:
        already_published = store.has_prediction(conn, fixture.id, model.version)

        if not already_published:
            for team in (fixture.home, fixture.away):
                if not model.knows(team):
                    no_history.add(team)

            outcome = model.predict(fixture.home, fixture.away)
            probs = outcome.as_tuple()

            if not dry_run:
                store.insert_prediction(
                    conn,
                    match_id=fixture.id,
                    model_version=model.version,
                    probs=probs,
                    pick=outcome.pick,
                    confidence=outcome.confidence,
                    created_at=now_iso,
                )

            written.append(
                {
                    "match_id": fixture.id,
                    "kickoff_utc": fixture.kickoff_utc,
                    "home": fixture.home,
                    "away": fixture.away,
                    "p_home": probs[0],
                    "p_draw": probs[1],
                    "p_away": probs[2],
                    "pick": outcome.pick,
                    "confidence": outcome.confidence,
                }
            )
        else:
            skipped += 1

        matrix = model.score_matrix(fixture.home, fixture.away)
        markets_written += len(
            _publish_market_predictions(conn, model, fixture, matrix, now_iso, dry_run)
        )

    if not dry_run:
        conn.commit()

    for row in written:
        log(
            f"  {row['kickoff_utc'][:16].replace('T', ' ')}  "
            f"{row['home']:<16} vs {row['away']:<16}  "
            f"H {row['p_home']:.0%}  D {row['p_draw']:.0%}  A {row['p_away']:.0%}"
            f"   pick {row['pick']}"
        )

    if no_history:
        log(
            "\n  NOTE: no Premier League history for "
            + ", ".join(sorted(no_history))
            + ".\n  Rated using the newcomer prior (promoted sides score about"
            " 68% of the\n  league-average rate and concede about 113% of it)."
            " These remain\n  weaker predictions than ones between known teams."
        )

    if markets_written:
        log(f"\n  also published {markets_written} v2 market predictions (BTTS, OU2.5)")

    return {
        "model_version": model.version,
        "published_at": now_iso,
        "written": len(written),
        "skipped_already_published": skipped,
        "markets_written": markets_written,
        "fixtures": written,
        "teams_without_history": sorted(no_history),
    }


def grade(conn: sqlite3.Connection, league: str = "EPL", log=print) -> dict:
    """Score every published prediction whose match has now finished.

    Grades 1X2 first, then each v2 market independently -- a fixture graded
    for 1X2 always gets its BTTS/OU2.5 results at the same time, since both
    only need the match to have finished, nothing else.
    """
    graded_at = clock.now_iso()
    pending = store.ungraded_predictions(conn, league)

    hits = 0
    for row in pending:
        probs = (row["p_home"], row["p_draw"], row["p_away"])
        actual = row["result"]
        is_hit = row["pick"] == actual
        hits += int(is_hit)

        store.insert_result(
            conn,
            prediction_id=row["id"],
            actual=actual,
            is_hit=is_hit,
            log_loss=metrics.log_loss(probs, actual),
            rps=metrics.rps(probs, actual),
            brier=metrics.brier(probs, actual),
            graded_at=graded_at,
        )

    conn.commit()
    log(f"  graded {len(pending)} predictions ({hits} hits, {len(pending) - hits} misses)")

    market_graded = _grade_markets(conn, league, graded_at, log)

    return {
        "graded": len(pending),
        "hits": hits,
        "misses": len(pending) - hits,
        "markets_graded": market_graded,
    }


def _grade_markets(conn: sqlite3.Connection, league: str, graded_at: str, log) -> int:
    total = 0
    for market in MARKETS:
        pending = store.ungraded_market_predictions(conn, league, market)
        hits = 0
        for row in pending:
            actual_is_yes_or_over = (
                (row["home_goals"] > 0 and row["away_goals"] > 0)
                if market == "BTTS"
                else (row["home_goals"] + row["away_goals"] > 2.5)
            )
            actual_outcome = {
                "BTTS": "Yes" if actual_is_yes_or_over else "No",
                "OU2.5": "Over" if actual_is_yes_or_over else "Under",
            }[market]
            p_yes_side = row["probabilities"][
                "Yes" if market == "BTTS" else "Over"
            ]
            is_hit = row["pick"] == actual_outcome
            hits += int(is_hit)

            store.insert_market_result(
                conn,
                match_id=row["match_id"],
                model_version=row["model_version"],
                market=market,
                actual_outcome=actual_outcome,
                is_hit=is_hit,
                log_loss=markets.binary_log_loss(p_yes_side, actual_is_yes_or_over),
                brier=markets.binary_brier(p_yes_side, actual_is_yes_or_over),
                graded_at=graded_at,
            )
        if pending:
            log(f"  graded {len(pending)} {market} predictions ({hits} hits)")
        total += len(pending)
    conn.commit()
    return total


def accuracy(
    conn: sqlite3.Connection,
    league: str = "EPL",
    model_version: str | None = config.MODEL_VERSION,
) -> dict:
    """The public headline numbers, computed from graded predictions only.

    Scoped to one model version by default: averaging two predictors into a
    single accuracy figure would misrepresent both.
    """
    record = [
        r
        for r in store.track_record(conn, league, model_version)
        if r["is_hit"] is not None
    ]
    card = metrics.Scorecard("published")
    for row in record:
        card.add((row["p_home"], row["p_draw"], row["p_away"]), row["actual"])

    buckets = metrics.confidence_buckets(
        [((r["p_home"], r["p_draw"], r["p_away"]), r["actual"]) for r in record]
    )
    return {
        "overall": card.summary(),
        "by_confidence": buckets,
        "model_version": model_version,
    }


def market_accuracy(
    conn: sqlite3.Connection,
    league: str = "EPL",
    model_version: str | None = config.MODEL_VERSION,
) -> dict:
    """Headline accuracy for each v2 market, scoped to one model version."""
    return {market: store.market_accuracy(conn, league, market, model_version)
            for market in MARKETS}
