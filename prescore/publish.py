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
from .model import poisson


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
    """Predict every unpublished fixture kicking off within the horizon."""
    now = clock.utc_now()
    now_iso = clock.to_iso(now)
    horizon_iso = clock.to_iso(now + timedelta(days=horizon_days))

    model = build_model(conn, league, half_life_days, ridge)
    fixtures = store.upcoming_fixtures(conn, league, now_iso, horizon_iso)

    written, skipped, no_history = [], 0, set()

    for fixture in fixtures:
        if store.has_prediction(conn, fixture.id, model.version):
            skipped += 1
            continue

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

    return {
        "model_version": model.version,
        "published_at": now_iso,
        "written": len(written),
        "skipped_already_published": skipped,
        "fixtures": written,
        "teams_without_history": sorted(no_history),
    }


def grade(conn: sqlite3.Connection, league: str = "EPL", log=print) -> dict:
    """Score every published prediction whose match has now finished."""
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
    return {"graded": len(pending), "hits": hits, "misses": len(pending) - hits}


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
