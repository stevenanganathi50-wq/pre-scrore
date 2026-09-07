"""Paths, league definitions and model defaults.

Everything here is deliberately dependency-free so the pipeline runs on a bare
Python 3.11+ install.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
REPORT_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "prescore.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# FROZEN 2026-08-12, ahead of the first graded matchweek on 2026-08-21.
#
# Do not change the model or the hyperparameters below until the published
# record has real results in it. Three experiments have been run against the
# backtest and zero against reality; another tuning pass is worth far less than
# one live matchweek, and changing predictors underneath a track record is
# exactly what makes track records worthless.
#
# Bug fixes are still fair game. Model changes are not. The known open item is
# v1.2's under-confidence at the top of the range -- see the README -- and it
# waits.
#
# Bump this whenever the model's output would change for the same fixture.
# Published predictions are immutable, so a changed model cannot be applied
# retroactively -- it can only be published alongside, under a new version.
#   1.0  Poisson + Dixon-Coles, time decay, uniform ridge
#   1.1  newcomer prior: teams with little or no top-flight history are rated
#        below league average rather than at it
#   1.2  ratings fit to a 50/50 blend of goals and a shots-on-target proxy,
#        which filters out some finishing luck
#   1.3  post-hoc temperature scaling corrects v1.2's under-confidence at the
#        top of the range (see CALIBRATION_TEMPERATURE). Shipped ahead of the
#        model freeze's normal ~100-live-prediction threshold, by explicit
#        decision -- backtest-validated only, not yet checked against live
#        results the way every prior version was.
MODEL_VERSION = "poisson-dc-1.3"


@dataclass(frozen=True)
class League:
    code: str  # our internal code
    name: str
    fd_div: str  # football-data.co.uk division code


EPL = League(code="EPL", name="English Premier League", fd_div="E0")

LEAGUES = {league.code: league for league in (EPL,)}

# Seasons are named by their starting year: 2015 -> the 2015/16 season.
FIRST_SEASON = 2015
LAST_SEASON = 2026


def default_seasons() -> tuple[int, ...]:
    return tuple(range(FIRST_SEASON, LAST_SEASON + 1))


def season_label(start_year: int) -> str:
    """2015 -> '2015/16'."""
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def current_season(today: "date | None" = None) -> int:
    """The season a date falls in, by starting year.

    European seasons run August to May, so July is the boundary. This is
    computed rather than pinned to LAST_SEASON: a scheduled job that runs
    unattended for years must roll over on its own instead of quietly syncing
    a finished season forever.
    """
    from datetime import date as _date

    day = today or _date.today()
    return day.year if day.month >= 7 else day.year - 1


# --- Model defaults -------------------------------------------------------
# Time decay half-life in days. Older matches still inform the fit, but a
# match from two seasons ago counts for much less than last month's.
# A 12-point sweep (90/180/270/365 x ridge 0.02/0.05/0.10) put 270 marginally
# ahead at every ridge value -- but the whole surface spans only 0.2009-0.2037
# RPS, so this is a tie-break, not a meaningful gain. Do not read much into it.
DEFAULT_HALF_LIFE_DAYS = 270.0

# Ridge penalty on attack/defence ratings. Keeps early-season and
# newly-promoted teams from being fit to noise.
DEFAULT_RIDGE = 0.05

# Goals considered when building the scoreline matrix.
MAX_GOALS = 10

# Newly promoted teams are not league average, and treating them as such is a
# systematic error at every season start. Measured over 2015/16-2020/21, teams
# in their first season back scored 68.4% of the league-average rate and
# conceded 113.4% of it -- 14 of 15 scored below average.
#
# These are deliberately estimated from seasons <= 2020/21 only, so they can be
# evaluated on a 2021+ backtest window without leaking. The all-seasons figures
# (-0.3790 / -0.1917) are close enough to suggest the effect is stable.
NEWCOMER_ATTACK = -0.3796
NEWCOMER_DEFENCE = -0.1259

# Prior strength in weighted matches: a team with this much history is pulled
# half way from the newcomer prior back toward league average. Ratings converge
# on the data as a promoted side plays its way into the season.
NEWCOMER_PRIOR_STRENGTH = 10.0

# Extra decay age charged for each season boundary a match sits behind the
# prediction date -- the idea being that squads are rebuilt over a summer, so
# May's form should not carry into August at full strength.
#
# TESTED AND REJECTED. Swept over 0/30/60/90/150/220 on 2021-08-01 onward: it
# degrades results monotonically, both at season starts (early-season RPS
# 0.1884 -> 0.1913) and overall (0.2009 -> 0.2016). Last season's form is more
# informative in August than the intuition suggests.
#
# The mechanism is left in place because it is one line and the parameter is
# worth re-testing on another league. Do not raise it for the EPL without
# rerunning that sweep.
SEASON_BREAK_DAYS = 0.0

# How much the ratings are fit to a shots-on-target proxy rather than to raw
# goals. 0 is pure goals, 1 is pure proxy.
#
# Real xG weights every shot by location and quality; we cannot use it. Both
# free providers refuse automated access -- Understat's robots.txt is a blanket
# `Disallow: /`, and FBref returns 403 even for robots.txt. Shot counts from
# football-data.co.uk are the licensed substitute: they capture the "goals are
# a noisy realisation of chances" effect, though not shot quality.
#
# Swept over 0/0.25/0.5/0.75/1.0. A 50/50 blend wins, and the curve is a clean
# inverted U rather than a jagged one, which is what a real effect looks like.
# Validated out of sample: -0.0011 RPS on the window it was chosen on, -0.0010
# on 2018-2021 which that choice never saw.
#
# Pure shots (1.0) is worse than pure goals (0.2017 vs 0.2009) -- finishing is
# a genuine skill, and shots on target throw it away. The blend keeps both.
XG_WEIGHT = 0.5

# Post-hoc temperature scaling on the final H/D/A probabilities (see
# prescore/model/calibration.py). Corrects v1.2's known top-end
# under-confidence: it said 74% and delivered 80%.
#
# Fit on the standard 3,061-prediction out-of-sample backtest set, split at
# its midpoint date to check the fit generalises: 0.8822 fit on the earlier
# half and evaluated on the later one, 0.9375 the reverse -- same direction
# both times (sharpening), unlike the ELO and injury-weight experiments,
# which flipped sign between windows and were rejected for it. 0.9078 is the
# value fit on the full set.
#
# Read this as a real but modest, imperfect fix, not a clean win like
# XG_WEIGHT: aggregate RPS/log loss barely move (-0.0002 to -0.0003, within
# this project's established noise floor), and while it closes more than
# half the gap at the top of the range (0.8-0.9 gap: +0.064 -> +0.024), it
# introduces a smaller new one around the middle (0.5-0.6 gap: +0.012 ->
# -0.019). A single global temperature cannot fix a non-uniform miscalibration
# without redistributing some of it elsewhere.
#
# Shipped by explicit decision ahead of the model freeze's normal
# ~100-live-prediction threshold -- see MODEL_VERSION history and the README.
# Every other version bump here was checked against live results before
# shipping; this one has not been yet.
CALIBRATION_TEMPERATURE = 0.9078

# How long a match must have been "finished" (by kickoff_utc + this many
# minutes) before it is trusted enough to grade.
#
# Real incident, 2026-09-06: TheSportsDB marked Arsenal vs Chelsea "finished"
# with a score of 1-1 just 45 minutes after kickoff -- far too early for a
# genuine final whistle. The match got graded on that score (a draw). The
# real final score, corrected in a later sync, was 2-1 to Arsenal. Because
# a graded result is immutable by design, that wrong grade cannot be
# corrected the normal way; it is a permanent, documented data incident (see
# the site's "Known data incidents" note).
#
# 150 minutes covers 90 minutes' play plus stoppage/extra time plus a safety
# margin, so a "finished" flag this premature is never trusted again. There
# is no column recording when a match's status actually changed to
# "finished" -- kickoff_utc is the only timestamp available, so the buffer is
# measured from there rather than from whenever the flag first appeared.
MIN_GRADING_DELAY_MINUTES = 150

# A model needs a reasonable history before its output means anything.
MIN_TRAINING_MATCHES = 200
