"""Plain-text rendering of backtest output.

ASCII only -- this has to print cleanly in a Windows console.
"""

from __future__ import annotations

from .backtest.runner import BacktestResult, head_to_head


def _rule(width: int = 72) -> str:
    return "-" * width


def _cell(value: float | None, width: int, places: int) -> str:
    if value is None:
        return f"{'n/a':>{width}}"
    return f"{value:>{width}.{places}f}"


def _scorecard_row(s: dict) -> str:
    return (
        f"{s['label']:<24} {s['n']:>6} {s['accuracy']:>9.3f} "
        f"{_cell(s['log_loss'], 9, 4)} {_cell(s['rps'], 8, 4)} "
        f"{_cell(s['brier'], 8, 4)}"
    )


def render(result: BacktestResult) -> str:
    s = result.summary()
    lines: list[str] = []
    add = lines.append

    add("=" * 72)
    add("BACKTEST REPORT")
    add("=" * 72)
    add(f"Model            {s['params']['model_version']}")
    add(f"Test window      {s['test_from']} to {s['test_to']}")
    add(f"Predictions      {s['model']['n']}")
    add(
        f"Hyperparameters  half-life {s['params']['half_life_days']:.0f}d, "
        f"ridge {s['params']['ridge']}, "
        f"training window {s['params']['max_training_days']}d"
    )
    add(f"Refits           {s['params']['refits']} (one per match date)")
    add(f"Runtime          {s['elapsed_seconds']}s")
    add("")

    add("OVERALL  (lower is better for log loss / RPS / Brier)")
    add(_rule())
    add(
        f"{'':<24} {'n':>6} {'accuracy':>9} {'log loss':>9} {'RPS':>8} {'Brier':>8}"
    )
    add(_scorecard_row(s["model"]))
    for key in ("market_close", "base_rates", "home_always"):
        card = s["baselines"][key]
        if card["n"]:
            add(_scorecard_row(card))
    add(_rule())
    add("market_close = closing odds with the overround removed. Beating it is")
    add("not the goal; staying close to it means the model is genuinely informed.")
    add("home_always emits 0/1 probabilities, so only its accuracy is meaningful.")
    add("")

    h2h = head_to_head(result)
    if h2h:
        add("MODEL vs MARKET  (same matches only)")
        add(_rule())
        add(
            f"{'':<24} {'n':>6} {'accuracy':>9} {'log loss':>9} {'RPS':>8} {'Brier':>8}"
        )
        add(_scorecard_row(h2h["model"]))
        add(_scorecard_row(h2h["market"]))
        gap = h2h["model"]["rps"] - h2h["market"]["rps"]
        verdict = "model is sharper" if gap < 0 else "market is sharper"
        add(f"RPS gap {gap:+.4f}  ({verdict})")
        add(_rule())
        add("")

    add("ACCURACY BY PICK")
    add(_rule())
    add(f"{'pick':<10} {'n':>6} {'hits':>6} {'accuracy':>9}")
    labels = {"H": "home win", "D": "draw", "A": "away win"}
    for pick, row in s["model"]["by_pick"].items():
        add(
            f"{labels.get(pick, pick):<10} {row['n']:>6} {row['hits']:>6} "
            f"{row['accuracy']:>9.3f}"
        )
    add(_rule())
    add("")

    add("ACCURACY BY CONFIDENCE")
    add(_rule())
    add(f"{'confidence':<12} {'n':>6} {'hits':>6} {'accuracy':>9}")
    for row in s["confidence_buckets"]:
        add(
            f"{row['range']:<12} {row['n']:>6} {row['hits']:>6} {row['accuracy']:>9.3f}"
        )
    add(_rule())
    add("")

    add("CALIBRATION  (every probability we emitted, vs how often it happened)")
    add(_rule())
    add(f"{'bucket':<12} {'n':>7} {'predicted':>10} {'observed':>10} {'gap':>8}")
    for row in s["calibration"]:
        gap = row["observed"] - row["predicted"]
        add(
            f"{row['range']:<12} {row['n']:>7} {row['predicted']:>10.3f} "
            f"{row['observed']:>10.3f} {gap:>+8.3f}"
        )
    add(_rule())

    return "\n".join(lines)


def render_ratings(model, top: int = 30) -> str:
    lines = []
    add = lines.append
    add("=" * 60)
    add(f"TEAM RATINGS  (fit through {model.fitted_through})")
    add("=" * 60)
    add(f"base {model.base:+.3f}   home advantage {model.home_advantage:+.3f}   "
        f"rho {model.rho:+.3f}")
    add(f"matches used {model.n_matches}   log-likelihood {model.log_likelihood:.1f}")
    add("-" * 60)
    add(f"{'team':<24} {'attack':>9} {'defence':>9} {'overall':>9}")
    for name, atk, dfn in model.ratings_table()[:top]:
        add(f"{name:<24} {atk:>+9.3f} {dfn:>+9.3f} {atk + dfn:>+9.3f}")
    add("-" * 60)
    add("Higher attack = scores more. Higher defence = concedes less.")
    return "\n".join(lines)
