"""Walk-forward backtest.

The only honest way to test this model is to replay history in order: stand at
each match date, fit using *only* matches that had already finished, predict,
then move on. Anything else leaks the future into the ratings and produces an
accuracy number that will not survive contact with real fixtures.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date
from itertools import groupby

from .. import config, store
from ..model import poisson
from . import metrics


@dataclass
class BacktestResult:
    run_id: int | None
    params: dict
    test_from: date
    test_to: date
    model: metrics.Scorecard
    baselines: dict[str, metrics.Scorecard]
    records: list[tuple[tuple[float, float, float], str]]
    market_records: list[tuple[tuple[float, float, float], str]]
    market_model_records: list[tuple[tuple[float, float, float], str]]
    elapsed_seconds: float = 0.0
    predictions: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "params": self.params,
            "test_from": self.test_from.isoformat(),
            "test_to": self.test_to.isoformat(),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "model": self.model.summary(),
            "baselines": {k: v.summary() for k, v in self.baselines.items()},
            "calibration": metrics.calibration(self.records),
            "confidence_buckets": metrics.confidence_buckets(self.records),
        }


def run(
    conn: sqlite3.Connection,
    *,
    league: str = "EPL",
    test_from: date,
    test_to: date | None = None,
    half_life_days: float = config.DEFAULT_HALF_LIFE_DAYS,
    ridge: float = config.DEFAULT_RIDGE,
    min_training_matches: int = config.MIN_TRAINING_MATCHES,
    max_training_days: int = 1095,
    newcomer_attack: float = config.NEWCOMER_ATTACK,
    newcomer_defence: float = config.NEWCOMER_DEFENCE,
    prior_strength: float = config.NEWCOMER_PRIOR_STRENGTH,
    season_break_days: float = config.SEASON_BREAK_DAYS,
    xg_weight: float = config.XG_WEIGHT,
    build_model=None,
    model_label: str | None = None,
    persist: bool = True,
    log=print,
) -> BacktestResult:
    """Replay `league` from `test_from`, refitting before every match date.

    `max_training_days` caps how far back the training window reaches. With a
    180-day half-life a match from four years ago carries under 1% weight, so
    dropping it costs nothing and keeps each refit fast.
    """
    if build_model is None:
        def build_model(window, ref_date, warm):
            return poisson.fit(
                window,
                ref_date=ref_date,
                half_life_days=half_life_days,
                ridge=ridge,
                warm_start=warm,
                tol=1e-7,
                newcomer_attack=newcomer_attack,
                newcomer_defence=newcomer_defence,
                prior_strength=prior_strength,
                season_break_days=season_break_days,
                xg_weight=xg_weight,
            )

    started = time.perf_counter()
    all_matches = store.finished_matches(conn, league)
    if not all_matches:
        raise ValueError("no finished matches in the database -- run ingest first")

    test_to = test_to or max(m.match_date for m in all_matches)

    history: list[store.MatchRow] = []
    model_card = metrics.Scorecard("model")
    baselines = {
        "home_always": metrics.Scorecard("home_always", accuracy_only=True),
        "base_rates": metrics.Scorecard("base_rates"),
        "market_close": metrics.Scorecard("market_close"),
    }
    records: list[tuple[tuple[float, float, float], str]] = []
    market_records: list[tuple[tuple[float, float, float], str]] = []
    market_model_records: list[tuple[tuple[float, float, float], str]] = []
    predictions: list[dict] = []

    warm: poisson.PoissonDixonColes | None = None
    fits = 0

    for match_date, group in groupby(all_matches, key=lambda m: m.match_date):
        todays = list(group)

        in_window = test_from <= match_date <= test_to
        if in_window and len(history) >= min_training_matches:
            cutoff = match_date.toordinal() - max_training_days
            window = [m for m in history if m.match_date.toordinal() >= cutoff]

            model = build_model(window, match_date, warm)
            warm = model
            fits += 1

            counts = _base_rates(history)

            for m in todays:
                outcome = model.predict(m.home, m.away)
                probs = outcome.as_tuple()
                records.append((probs, m.result))
                model_card.add(probs, m.result)
                baselines["home_always"].add((1.0, 0.0, 0.0), m.result)
                baselines["base_rates"].add(counts, m.result)

                market = metrics.devig((m.odds_home, m.odds_draw, m.odds_away))
                if market is not None:
                    baselines["market_close"].add(market, m.result)
                    market_records.append((market, m.result))
                    market_model_records.append((probs, m.result))

                predictions.append(
                    {
                        "match_id": m.id,
                        "date": match_date.isoformat(),
                        "home": m.home,
                        "away": m.away,
                        "p_home": probs[0],
                        "p_draw": probs[1],
                        "p_away": probs[2],
                        "pick": outcome.pick,
                        "confidence": outcome.confidence,
                        "actual": m.result,
                        "is_hit": int(outcome.pick == m.result),
                    }
                )

            if fits % 50 == 0:
                log(
                    f"  {match_date}  {model_card.n:5d} predictions  "
                    f"acc {model_card.accuracy:.3f}"
                )

        history.extend(todays)

    if not model_card.n:
        raise ValueError(
            "no predictions produced -- check test_from and min_training_matches"
        )

    params = {
        "model_version": model_label or config.MODEL_VERSION,
        "half_life_days": half_life_days,
        "ridge": ridge,
        "min_training_matches": min_training_matches,
        "max_training_days": max_training_days,
        "newcomer_attack": newcomer_attack,
        "newcomer_defence": newcomer_defence,
        "prior_strength": prior_strength,
        "season_break_days": season_break_days,
        "xg_weight": xg_weight,
        "refits": fits,
    }

    result = BacktestResult(
        run_id=None,
        params=params,
        test_from=test_from,
        test_to=test_to,
        model=model_card,
        baselines=baselines,
        records=records,
        market_records=market_records,
        market_model_records=market_model_records,
        elapsed_seconds=time.perf_counter() - started,
        predictions=predictions,
    )

    if persist:
        result.run_id = _persist(conn, league, result)

    return result


def _base_rates(history: list[store.MatchRow]) -> tuple[float, float, float]:
    """Historical H/D/A frequencies -- the 'know nothing but the league' prior."""
    n = len(history)
    if not n:
        return (1 / 3, 1 / 3, 1 / 3)
    counts = {"H": 0, "D": 0, "A": 0}
    for m in history:
        counts[m.result] += 1
    return (counts["H"] / n, counts["D"] / n, counts["A"] / n)


def head_to_head(result: BacktestResult) -> dict | None:
    """Compare model vs market on exactly the matches where both had a view."""
    if not result.market_records:
        return None
    model_card = metrics.Scorecard("model (matched sample)")
    market_card = metrics.Scorecard("market (matched sample)")
    for probs, actual in result.market_model_records:
        model_card.add(probs, actual)
    for probs, actual in result.market_records:
        market_card.add(probs, actual)
    return {"model": model_card.summary(), "market": market_card.summary()}


def _persist(conn: sqlite3.Connection, league: str, result: BacktestResult) -> int:
    cur = conn.execute(
        """
        INSERT INTO backtest_runs (
            model_version, league, params, train_from, test_from, test_to,
            n_predictions, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            config.MODEL_VERSION,
            league,
            json.dumps(result.params),
            result.test_from.isoformat(),
            result.test_from.isoformat(),
            result.test_to.isoformat(),
            result.model.n,
        ),
    )
    run_id = int(cur.lastrowid)
    conn.executemany(
        """
        INSERT INTO backtest_predictions (
            run_id, match_id, p_home, p_draw, p_away, pick, confidence,
            actual, is_hit
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id, p["match_id"], p["p_home"], p["p_draw"], p["p_away"],
                p["pick"], p["confidence"], p["actual"], p["is_hit"],
            )
            for p in result.predictions
        ],
    )
    conn.commit()
    return run_id
