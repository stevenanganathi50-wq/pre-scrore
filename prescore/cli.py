"""Command line entry point: python -m prescore <command>"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from . import (
    clock, config, export, publish, report, settings, store, supabase_sync,
    verify_remote,
)
from .backtest import runner
from .ingest import football_data, thesportsdb
from .model import poisson


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def cmd_init(args) -> int:
    with store.connect() as conn:
        store.init_schema(conn)
    print(f"schema applied to {config.DB_PATH}")
    return 0


def cmd_ingest(args) -> int:
    seasons = (
        tuple(range(args.start_season, args.end_season + 1))
        if args.start_season
        else config.default_seasons()
    )
    with store.connect() as conn:
        store.init_schema(conn)
        print(f"seeding {args.league} from {football_data.SOURCE}")
        football_data.seed(
            conn, args.league, seasons=seasons, refresh=args.refresh
        )
        c = store.counts(conn)
    print(f"\nteams {c['teams']}  matches {c['matches']}")
    return 0


def cmd_status(args) -> int:
    with store.connect() as conn:
        store.init_schema(conn)
        c = store.counts(conn)
        rows = conn.execute(
            """
            SELECT season,
                   sum(CASE WHEN status = 'finished' THEN 1 ELSE 0 END) AS played,
                   sum(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) AS scheduled,
                   min(match_date) AS first, max(match_date) AS last,
                   sum(CASE WHEN closing_odds_home IS NOT NULL THEN 1 ELSE 0 END) AS with_odds
            FROM matches
            GROUP BY season ORDER BY season
            """
        ).fetchall()
    print(f"database  {config.DB_PATH}")
    print(f"teams {c['teams']}  matches {c['matches']}  "
          f"predictions {c['predictions']}  backtest runs {c['backtest_runs']}")
    if rows:
        print()
        print(
            f"{'season':<10} {'played':>7} {'upcoming':>9} {'with odds':>10}  "
            f"{'first':<12} {'last'}"
        )
        for r in rows:
            print(
                f"{config.season_label(r['season']):<10} {r['played']:>7} "
                f"{r['scheduled']:>9} {r['with_odds']:>10}  "
                f"{r['first']:<12} {r['last']}"
            )
    return 0


def cmd_backtest(args) -> int:
    with store.connect() as conn:
        store.init_schema(conn)
        result = runner.run(
            conn,
            league=args.league,
            test_from=args.test_from,
            test_to=args.test_to,
            half_life_days=args.half_life,
            ridge=args.ridge,
            max_training_days=args.training_days,
            xg_weight=args.xg_weight,
            persist=not args.no_persist,
        )
    text = report.render(result)
    print(text)

    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{args.test_from.isoformat()}_hl{args.half_life:g}_r{args.ridge:g}"
    (config.REPORT_DIR / f"backtest_{stamp}.txt").write_text(text, encoding="utf-8")
    (config.REPORT_DIR / f"backtest_{stamp}.json").write_text(
        json.dumps(result.summary(), indent=2), encoding="utf-8"
    )
    print(f"\nsaved to {config.REPORT_DIR}")
    return 0


def cmd_tune(args) -> int:
    """Small grid search over the two hyperparameters that matter."""
    half_lives = [float(v) for v in args.half_lives.split(",")]
    ridges = [float(v) for v in args.ridges.split(",")]

    print(f"{'half-life':>10} {'ridge':>8} {'n':>6} {'accuracy':>9} "
          f"{'log loss':>9} {'RPS':>8}")
    print("-" * 56)
    best = None
    with store.connect() as conn:
        store.init_schema(conn)
        for hl in half_lives:
            for rg in ridges:
                result = runner.run(
                    conn,
                    league=args.league,
                    test_from=args.test_from,
                    test_to=args.test_to,
                    half_life_days=hl,
                    ridge=rg,
                    max_training_days=args.training_days,
                    persist=False,
                    log=lambda *a, **k: None,
                )
                card = result.model
                print(f"{hl:>10.0f} {rg:>8.3f} {card.n:>6} {card.accuracy:>9.3f} "
                      f"{card.log_loss:>9.4f} {card.rps:>8.4f}")
                if best is None or card.rps < best[0]:
                    best = (card.rps, hl, rg)
    print("-" * 56)
    print(f"best by RPS: half-life {best[1]:.0f}d, ridge {best[2]:g} (RPS {best[0]:.4f})")
    print("\nNote: this is selection on the test window. Confirm the winner on a")
    print("later, untouched window before trusting it.")
    return 0


def cmd_ratings(args) -> int:
    with store.connect() as conn:
        store.init_schema(conn)
        matches = store.finished_matches(conn, args.league)
    if not matches:
        print("no matches -- run: python -m prescore ingest")
        return 1
    model = poisson.fit(
        matches, half_life_days=args.half_life, ridge=args.ridge
    )
    print(report.render_ratings(model))
    return 0


def cmd_predict(args) -> int:
    """Ad-hoc probability for a single fixture, using all data on hand."""
    with store.connect() as conn:
        store.init_schema(conn)
        matches = store.finished_matches(conn, args.league)
    if not matches:
        print("no matches -- run: python -m prescore ingest")
        return 1
    model = poisson.fit(matches, half_life_days=args.half_life, ridge=args.ridge)

    # A name we have never seen is usually a newly promoted side, and the model
    # has a measured prior for exactly that. Predict, but say so -- refusing
    # would be inconsistent with `publish`, which does the same.
    unknown = [t for t in (args.home, args.away) if not model.knows(t)]
    misspelled = [t for t in unknown if t.lower() not in {n.lower() for n in model.teams}]
    if len(misspelled) == 2:
        known = ", ".join(sorted(model.teams))
        print(f"neither team is recognised: {args.home}, {args.away}")
        print(f"\nknown teams: {known}")
        return 1

    out = model.predict(args.home, args.away)
    print(f"{args.home} vs {args.away}   (model fit through {model.fitted_through})")
    print(f"  expected goals   {out.expected_home_goals:.2f} - "
          f"{out.expected_away_goals:.2f}")
    print(f"  home win  {out.p_home:6.1%}")
    print(f"  draw      {out.p_draw:6.1%}")
    print(f"  away win  {out.p_away:6.1%}")
    print(f"  pick      {out.pick}  (confidence {out.confidence:.1%})")
    if unknown:
        print(
            f"\n  NOTE: no top-flight history for {', '.join(unknown)}.\n"
            f"  Rated using the newcomer prior (promoted sides score about 68%\n"
            f"  of the league-average rate and concede about 113% of it), so\n"
            f"  this is a weaker prediction than one between known teams."
        )
    return 0


def cmd_fixtures(args) -> int:
    with store.connect() as conn:
        store.init_schema(conn)
        if args.rounds:
            lo, _, hi = args.rounds.partition("-")
            rounds = range(int(lo), int(hi or lo) + 1)
        else:
            rounds = thesportsdb.current_rounds(conn, args.league, args.season)
        print(
            f"syncing {args.league} {thesportsdb.season_string(args.season)} "
            f"rounds {min(rounds)}-{max(rounds)} from {thesportsdb.SOURCE}"
        )
        report_ = thesportsdb.sync_rounds(conn, args.league, args.season, rounds)
    print(report_.as_text())
    return 1 if report_.unresolved_teams else 0


def cmd_publish(args) -> int:
    with store.connect() as conn:
        store.init_schema(conn)
        print(f"publishing predictions for the next {args.horizon_days} days")
        result = publish.publish(
            conn,
            args.league,
            horizon_days=args.horizon_days,
            half_life_days=args.half_life,
            ridge=args.ridge,
            dry_run=args.dry_run,
        )
    verb = "would publish" if args.dry_run else "published"
    print(
        f"\n{verb} {result['written']} predictions"
        f" ({result['skipped_already_published']} already on record)"
    )
    return 0


def cmd_grade(args) -> int:
    with store.connect() as conn:
        store.init_schema(conn)
        print("grading finished matches")
        publish.grade(conn, args.league)
        summary = publish.accuracy(conn, args.league)
    overall = summary["overall"]
    if overall["n"]:
        print(
            f"\npublished record: {overall['hits']}/{overall['n']} "
            f"({overall['accuracy']:.1%})  log loss {overall['log_loss']:.4f}  "
            f"RPS {overall['rps']:.4f}"
        )
    else:
        print("\nno graded predictions yet")
    return 0


def cmd_export(args) -> int:
    with store.connect() as conn:
        store.init_schema(conn)
        target = export.write(conn, args.league)
        payload = export.build(conn, args.league)
    print(f"wrote {target}")
    print(
        f"  upcoming {len(payload['upcoming'])}  "
        f"graded {len(payload['results'])}  "
        f"generated {payload['generated_at']}"
    )
    return 0


def cmd_env(args) -> int:
    """Show which Supabase settings are loaded, without printing any of them."""
    print(settings.describe())
    return 0


def cmd_push(args) -> int:
    try:
        with store.connect() as conn:
            store.init_schema(conn)
            result = supabase_sync.push_all(conn, args.league)
    except settings.MissingSettings as exc:
        print(f"cannot push: {exc}")
        return 1
    except supabase_sync.SupabaseError as exc:
        print(f"push failed: {exc}")
        return 1
    print(
        f"\npushed  teams {result['teams']}  matches {result['matches']}  "
        f"predictions {result['predictions']}  results {result['results']}"
    )
    if result["problems"]:
        print("\nremote does not match local:")
        for problem in result["problems"]:
            print(f"  {problem}")
        return 1
    print("local and remote row counts agree")
    return 0


def cmd_pull(args) -> int:
    """Hydrate the local database from the published record on Supabase."""
    try:
        with store.connect() as conn:
            store.init_schema(conn)
            print("pulling the published record from Supabase")
            result = supabase_sync.pull_all(conn, args.league)
    except settings.MissingSettings as exc:
        print(f"cannot pull: {exc}")
        return 1
    except supabase_sync.SupabaseError as exc:
        print(f"pull failed: {exc}")
        return 1
    print(
        f"\npulled {result['predictions']} predictions and "
        f"{result['results']} results"
    )
    return 0


def cmd_verify(args) -> int:
    """Audit the live database's guarantees against real keys."""
    try:
        checks = verify_remote.run_checks()
    except settings.MissingSettings as exc:
        print(f"cannot verify: {exc}")
        return 1
    print(verify_remote.report(checks))
    return 0 if all(c.passed for c in checks) else 1


def cmd_run(args) -> int:
    """The full scheduled cycle: sync fixtures, publish, grade, export."""
    print(f"=== pre-scrore cycle {clock.now_iso()} ===\n")
    for name, fn in (
        ("fixtures", cmd_fixtures),
        ("publish", cmd_publish),
        ("grade", cmd_grade),
        ("export", cmd_export),
    ):
        print(f"--- {name} ---")
        code = fn(args)
        if code and name == "fixtures":
            print("  (unresolved team names above -- fix before trusting output)")
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prescore", description="Soccer prediction pipeline"
    )
    parser.add_argument("--league", default="EPL", choices=sorted(config.LEAGUES))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the local database schema")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("ingest", help="download and store historical results")
    p.add_argument("--start-season", type=int, default=None,
                   help="starting year, e.g. 2015 for 2015/16")
    p.add_argument("--end-season", type=int, default=config.LAST_SEASON)
    p.add_argument("--refresh", action="store_true",
                   help="re-download instead of using the local cache")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("status", help="what is in the database")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("backtest", help="walk-forward evaluation")
    p.add_argument("--test-from", type=_parse_date, default=date(2019, 8, 1))
    p.add_argument("--test-to", type=_parse_date, default=None)
    p.add_argument("--half-life", type=float, default=config.DEFAULT_HALF_LIFE_DAYS)
    p.add_argument("--ridge", type=float, default=config.DEFAULT_RIDGE)
    p.add_argument("--training-days", type=int, default=1095)
    p.add_argument("--xg-weight", type=float, default=config.XG_WEIGHT,
                   help="0 fits ratings to goals, 1 to the shots-on-target "
                        "proxy, 0.5 blends them")
    p.add_argument("--no-persist", action="store_true")
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("tune", help="grid search half-life and ridge")
    p.add_argument("--test-from", type=_parse_date, default=date(2019, 8, 1))
    p.add_argument("--test-to", type=_parse_date, default=None)
    p.add_argument("--half-lives", default="90,180,270,365")
    p.add_argument("--ridges", default="0.01,0.05,0.1")
    p.add_argument("--training-days", type=int, default=1095)
    p.set_defaults(func=cmd_tune)

    p = sub.add_parser("ratings", help="current team attack/defence ratings")
    p.add_argument("--half-life", type=float, default=config.DEFAULT_HALF_LIFE_DAYS)
    p.add_argument("--ridge", type=float, default=config.DEFAULT_RIDGE)
    p.set_defaults(func=cmd_ratings)

    p = sub.add_parser("predict", help="probabilities for one fixture")
    p.add_argument("home")
    p.add_argument("away")
    p.add_argument("--half-life", type=float, default=config.DEFAULT_HALF_LIFE_DAYS)
    p.add_argument("--ridge", type=float, default=config.DEFAULT_RIDGE)
    p.set_defaults(func=cmd_predict)

    # --- the live pipeline ---

    def add_pipeline_args(sp, *, include_all: bool = False) -> None:
        sp.add_argument("--season", type=int, default=config.current_season(),
                        help="season starting year; defaults to the season "
                             "today falls in, e.g. 2026 for 2026/27")
        sp.add_argument("--rounds", default=None,
                        help="matchweeks to sync, e.g. '1' or '1-5'")
        if include_all:
            sp.add_argument("--horizon-days", type=int, default=8)
            sp.add_argument("--half-life", type=float,
                            default=config.DEFAULT_HALF_LIFE_DAYS)
            sp.add_argument("--ridge", type=float, default=config.DEFAULT_RIDGE)
            sp.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("fixtures", help="sync upcoming fixtures and results")
    add_pipeline_args(p)
    p.set_defaults(func=cmd_fixtures)

    p = sub.add_parser("publish", help="write predictions for upcoming fixtures")
    p.add_argument("--horizon-days", type=int, default=8)
    p.add_argument("--half-life", type=float, default=config.DEFAULT_HALF_LIFE_DAYS)
    p.add_argument("--ridge", type=float, default=config.DEFAULT_RIDGE)
    p.add_argument("--dry-run", action="store_true",
                   help="show what would be published without writing")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("grade", help="score predictions whose match has finished")
    p.set_defaults(func=cmd_grade)

    p = sub.add_parser("export", help="write web/data.json for the frontend")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("run", help="full cycle: fixtures, publish, grade, export")
    add_pipeline_args(p, include_all=True)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("env", help="show which Supabase settings are loaded")
    p.set_defaults(func=cmd_env)

    p = sub.add_parser("push", help="push the local record to Supabase")
    p.set_defaults(func=cmd_push)

    p = sub.add_parser(
        "pull", help="hydrate the local database from Supabase (run before publish "
                     "on any machine without durable storage)"
    )
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("verify", help="audit the live database's guarantees")
    p.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
