# pre-scrore

Soccer match prediction with a public, honest accuracy record. Predictions are
published before kickoff and graded against the actual result — losses shown as
openly as wins.

No betting integration, no odds comparison, no staking. The product is the
prediction and the credibility built around it.

**Current status:** all six phases of the build order run end to end against a
local SQLite database. The model is backtested (result below), fixtures sync
from TheSportsDB, predictions are published before kickoff and graded after,
and a static site renders the record.

The Supabase project is live and the schema is deployed — tables, views, RLS
policies and both immutability triggers. Data has not been pushed to it yet;
that needs `.env` (see [Supabase](#supabase)).

---

## Requirements

Python 3.11+. **No third-party packages** — the whole pipeline runs on the
standard library, so there is nothing to install and nothing to break.

```bash
python -m unittest discover -s tests -t .
```

## Quick start

Seed history, check the model, then run the live cycle:

```bash
python -m prescore ingest
```

```bash
python -m prescore backtest --test-from 2018-08-01
```

```bash
python -m prescore run --season 2026 --horizon-days 14
```

Then serve the site:

```bash
python -m http.server 8765 --directory web
```

| Command | What it does |
|---|---|
| `ingest` | Download and store EPL history from football-data.co.uk |
| `status` | What is currently in the database |
| `ratings` | Current attack/defence ratings for every team |
| `predict "Arsenal" "Chelsea"` | Probabilities for one fixture |
| `backtest` | Walk-forward evaluation with full report |
| `tune` | Grid search over half-life and ridge |
| `fixtures` | Sync upcoming fixtures and results from TheSportsDB |
| `publish` | Write predictions for upcoming fixtures (`--dry-run` to preview) |
| `grade` | Score predictions whose match has finished |
| `export` | Write `web/data.json` for the frontend |
| `run` | The full cycle: fixtures → publish → grade → export |
| `env` | Show which Supabase settings are loaded (never prints a key) |
| `pull` | Hydrate the local database from Supabase (required on any runner without durable storage) |
| `push` | Push the local record to Supabase |
| `verify` | Audit the live database's guarantees with real keys |

Scheduling is installed — see [Scheduling](#scheduling).

`run` is the one to put on a schedule. It is idempotent: fixtures already
predicted are skipped, and matches already graded are not regraded.

Data lands in `data/` (gitignored): raw CSVs in `data/raw/`, the SQLite database
at `data/prescore.db`, reports in `data/reports/`.

---

## Backtest result

This is the gate the scope doc asks for: know the accuracy before building
anything public-facing.

**8 seasons, 3,040 predictions, 2018/19 through 2025/26.** Every prediction made
by refitting the model on only the matches that had finished at that point —
941 separate refits, one per match date. No future data touches any fit.

| | n | accuracy | log loss | RPS | Brier |
|---|---:|---:|---:|---:|---:|
| **model** (`poisson-dc-1.2`) | 3040 | **54.0%** | 0.9692 | 0.1999 | 0.5749 |
| closing odds (de-vigged) | 3040 | 55.3% | 0.9547 | 0.1953 | 0.5653 |
| league base rates | 3040 | 43.9% | 1.0668 | 0.2341 | 0.6457 |
| always pick home | 3040 | 43.9% | — | — | — |

Progress across versions, same window and same walk-forward method:

| version | accuracy | log loss | RPS | gap to market |
|---|---:|---:|---:|---:|
| 1.0 | 53.7% | 0.9735 | 0.2011 | +0.0058 |
| 1.1 | 53.8% | 0.9731 | 0.2010 | +0.0057 |
| **1.2** | **54.0%** | **0.9692** | **0.1999** | **+0.0046** |

About a fifth of the original gap to the market has been closed.

Lower is better for log loss, RPS and Brier.

**Read this honestly:** the model is clearly better than knowing nothing
(54.0% vs 43.9%, and a decisively better RPS), and it lands just behind the
betting market. That is the correct place for a free model built on goals data
alone to land. The market aggregates team news, injuries, lineups and money;
being 1.6 accuracy points behind it is a good result, not a failure. Any model
claiming to beat closing odds on public data should be treated as broken until
proven otherwise.

### Accuracy by confidence

The model's confidence is the probability it assigned to its own pick, and it
means what it says:

| confidence | n | accuracy |
|---|---:|---:|
| 0.70–1.00 | 299 | **82.6%** |
| 0.60–0.70 | 478 | 67.4% |
| 0.50–0.60 | 740 | 55.7% |
| 0.40–0.50 | 1096 | 45.8% |
| below 0.40 | 427 | 37.0% |

### Calibration

Across every probability the model emitted, predicted vs observed frequency
tracks within about a percentage point through the middle of the range:

| bucket | n | predicted | observed | gap |
|---|---:|---:|---:|---:|
| 0.1–0.2 | 1237 | 0.160 | 0.135 | −0.025 |
| 0.2–0.3 | 3603 | 0.250 | 0.246 | −0.004 |
| 0.3–0.4 | 1426 | 0.346 | 0.341 | −0.005 |
| 0.4–0.5 | 1096 | 0.448 | 0.458 | +0.010 |
| 0.5–0.6 | 740 | 0.545 | 0.557 | +0.012 |
| 0.6–0.7 | 478 | 0.645 | 0.674 | +0.028 |
| 0.7–0.8 | 223 | 0.742 | 0.803 | **+0.061** |
| 0.8–0.9 | 70 | 0.838 | 0.900 | **+0.062** |

**Known flaw in v1.2: it is now under-confident at the top end.** It says 74%
and delivers 80%. The blend shrinks the spread of team ratings, which pulls
extreme fixtures back toward the middle — good for the aggregate scores, which
is why RPS and log loss both improved, but it makes the confidence figure
understate itself where it is highest.

This is the opposite of v1.0's flaw and the safer direction to err for a public
record: claiming 74% and delivering 80% is a better failure than the reverse.
It is still miscalibration. A probability calibration step (Platt scaling or a
temperature parameter) is the obvious next fix, and should be validated out of
sample like everything else here.

### Known limitation: the model almost never picks a draw

Of 3,040 predictions, v1.2 picked a draw **3 times** (v1.0 picked 20). The
shots blend compresses probabilities toward the middle, which paradoxically
makes the draw even less often the single highest of the three. This is
inherent to
1X2 argmax, not a bug: a draw is rarely the single most likely outcome even
though draws happen about a quarter of the time. The published product should
therefore lead with probabilities, not just the pick — otherwise the site
looks like it does not believe in draws.

---

## How the model works

A Poisson goals model with a Dixon-Coles low-score correction.

Every team carries an attack and a defence rating. For a fixture:

```
log(expected home goals) = base + attack[home] - defence[away] + home_advantage
log(expected away goals) = base + attack[away] - defence[home]
```

Those expected goals become a full scoreline matrix, which aggregates into
home/draw/away probabilities.

Three details that matter:

- **Weighted likelihood.** A match `d` days old counts `0.5 ** (d / 270)`, so
  the model tracks current form instead of treating a 2016 result as evidence
  about today. Relegated clubs decay toward league average automatically.
  A 12-point sweep over half-life and ridge spans only 0.2009–0.2037 RPS, so
  the exact setting barely matters — do not over-tune this.
- **Ridge penalty.** Keeps newly promoted teams and small samples from being
  fit to noise.
- **Expected-goals proxy.** Ratings are fit to a 50/50 blend of goals and a
  shots-on-target proxy rather than to goals alone. A team's goals in one match
  are a noisy draw from the chances it created; shots on target measure the
  same thing more steadily. The conversion rate (~0.32 goals per shot on
  target) is estimated from the training matches themselves, so the proxy
  carries the same total as the goals it replaces and no future data enters
  the fit.
- **Newcomer prior.** A team with no top-flight history is not league average.
  Measured over 2015/16–2020/21, newly promoted sides score **68.4%** of the
  league-average rate and concede **113.4%** of it, with 14 of 15 scoring below
  average. Thin-history teams are shrunk toward that prior rather than toward
  the middle, and the pull fades as they play their way into a season.
- **Dixon-Coles `rho`.** Independent Poissons underrate 0-0 and 1-1 and
  overrate 1-0 and 0-1. `rho` corrects exactly those four cells. Fitted on EPL
  data it comes out at about −0.12, matching the published literature.

Fitting is plain gradient ascent with a backtracking step. The Poisson
likelihood is concave in these parameters, so this reaches the global optimum —
no optimizer dependency needed.

### On xG, and why this uses a proxy

Real xG weights each shot by location, angle and pressure. This model does not
use it, and the reason is worth recording: **both free providers refuse
automated access.** Understat's `robots.txt` is a blanket `User-agent: * /
Disallow: /`, and FBref returns HTTP 403 even for `robots.txt`. Those are
unambiguous refusals and scraping them anyway would be taking someone else's
infrastructure against their stated wishes.

Shot counts from football-data.co.uk are the licensed substitute — already in
the CSVs we download, present in all 11 seasons. They capture the "goals are a
noisy realisation of chances" effect, which is the bulk of the benefit, but not
shot quality. A real xG feed would likely do better; if the budget ever allows
a licensed one, this is where it plugs in.

Measured on a held-out window, the blend closes about a sixth of the remaining
gap to the market — the single largest improvement made so far.

### What was tried and rejected

**An ELO + Poisson ensemble.** Built, tested (`prescore/model/elo.py`,
`prescore/model/ensemble.py`, `tests/test_elo.py`) and measured. It is not
used, and the reason is the clearest example in this project of why every
change gets validated on a window it was not tuned on:

| window | poisson | ensemble | change |
|---|---:|---:|---:|
| tuned-on 2021+ | 0.1998 | 0.1993 | −0.0005 |
| held-out 2018–2021 | 0.2000 | 0.2003 | **+0.0003** |

Opposite signs. The apparent gain was noise in the window it was chosen on.
Shipping it on the strength of the first row alone would have added a second
model architecture, an extra hyperparameter and twice the fitting cost in
exchange for nothing.

The diagnostic explains why. The two models agree on the pick 90.4% of the
time, and across the 183 matches where they disagree the Poisson model is
right 70 times and ELO 69 — a coin flip. Two predictors of similar quality
whose disagreements carry no signal have nothing to teach each other.

One genuinely interesting finding survives: **ELO picks slightly better but
predicts slightly worse.** At k=32 it reaches 54.4% accuracy against the
Poisson model's 53.6%, while its RPS is worse (0.2009 vs 0.1998). Getting the
winner right and getting the probability right are different skills, and this
product sells the second one.

ELO's RPS was 0.2009 across every `k` and home-advantage setting tried, which
suggests the implementation is sound and simply tops out below the Poisson
model on this data. The code is kept for that reason — it may be worth
revisiting if it is ever given features the Poisson model lacks.

Charging extra decay across the summer break — the intuition being that squads
are rebuilt, so May's form shouldn't carry into August at full strength.
Swept over 0/30/60/90/150/220 days on a held-out 2021+ window, it made results
**monotonically worse**: early-season RPS 0.1884 → 0.1913, overall 0.2009 →
0.2016. Last season's form is more informative in August than it appears.

Worth knowing why: early-season RPS (0.1884) is *lower* than the rest of the
season (0.2026) — those games are easier for everyone. The market simply
exploits that better than we do, which makes the season-start deficit an
**information** problem (transfers, preseason, team news) rather than a
weighting one. It cannot be fixed by reweighting data we already hold.

The mechanism is still in the code behind `SEASON_BREAK_DAYS = 0`, because it
is one line and may behave differently in another league. Do not raise it for
the EPL without rerunning that sweep.

**A per-fixture injury-count covariate**, fed by a real data source this time
rather than a proxy: API-Football's injuries endpoint, matched to specific
fixtures (`prescore/ingest/api_football.py`, `db/schema.sql`'s `injuries`
table). The free tier blocks the current season entirely — every request
returns `"Free plans do not have access to this season, try from 2022 to
2024"` — so a Pro subscription was bought specifically to unlock it. 16,582
records were ingested and matched, covering 2020–2026 with real per-fixture
detail (player, reason, date).

The mechanism (`fit_injury_weight` in `poisson.fit`) works correctly — it
recovers a planted effect on synthetic data, moves predictions the intuitive
direction, and stays off unless explicitly requested (see
`tests/test_model.py::TestInjuryWeight`, which also caught a real bug: a
`warm_start` carrying a nonzero weight from an earlier fit was leaking through
even when the current call asked for it to stay off). But on real data it
fails the same test the ELO ensemble failed:

| window | baseline | +injuries | change |
|---|---:|---:|---:|
| held-out 2021-08–2023-05 | 0.2015 | 0.2011 | −0.0003 |
| tuned-on 2023-08–2025-05 | 0.1935 | 0.1945 | **+0.0010** |

Opposite signs again, both changes smaller than the noise floor the
hyperparameter sweep already established (0.003 wide). A raw injury *count*
probably isn't the right shape for the signal — losing three backup players
isn't the same as losing a first-choice striker and keeper, and the model's
existing time-decayed recent-form weighting likely already captures a good
share of "this team has been worse lately" without needing injuries spelled
out separately. The mechanism, the data feed, and the validation harness are
all kept; a future attempt would need to weight by player importance, not
headcount.

Not shipped, consistent with the freeze below: this was investigation and
infrastructure work with the default behaviour unchanged, not a model change.

### The model is frozen — with one authorised exception

**Frozen 2026-08-12, ahead of the first graded matchweek on 2026-08-21.**

Why: three changes had been measured against the backtest and none against
reality at the time. One real matchweek is worth more than another tuning
pass over the same 3,040 historical fixtures, and swapping predictors
underneath a track record is precisely what makes track records worthless.

**Still allowed:** bug fixes, infrastructure, scheduling, the frontend, and
anything that does not change what the model predicts for a given fixture.

**Not allowed until unfrozen:** hyperparameters, model structure, new features.

**Unfreeze when** the record holds a meaningful number of graded predictions —
roughly 100, about ten matchweeks — so that changes can be judged against
live results rather than backtest noise. Sooner if a genuine bug is found.

**The one exception:** `poisson-dc-1.3` (calibration, below) shipped on
2026-09-05 at 21 graded predictions, by explicit decision, specifically to fix
the known top-end under-confidence flaw rather than wait out the freeze. This
does not lift the freeze generally — hyperparameters, model structure, and new
features otherwise remain off the table until the same ~100-prediction bar is
met, this one change included; if it turns out to be wrong once real results
accumulate, it gets corrected the same way anything else would.

### Model versions

Published predictions are immutable, so a model change can never be applied
retroactively — only published alongside, under a new version.

| version | change |
|---|---|
| `poisson-dc-1.0` | Poisson + Dixon-Coles, time decay, uniform ridge |
| `poisson-dc-1.1` | newcomer prior for teams with little or no history |
| `poisson-dc-1.2` | ratings fit to a goals/shots-on-target blend |
| `poisson-dc-1.3` | temperature scaling on the final H/D/A probabilities |

The accuracy views group by `model_version`, so each version carries its own
record and they can never be silently averaged together.

### v1.3: temperature scaling, and why it's not a clean win

v1.2's shots blend compressed ratings toward the middle, which helped the
aggregate scores but left the confidence figure wrong at the extremes:
over-confident just below a coin flip, under-confident at the top —
`0.7–0.8` said 74.2% and delivered 80.4%, `0.8–0.9` said 83.8% and delivered
90.1%. That shape — errors growing symmetrically with distance from 1/3 — is
exactly what temperature scaling exists to fix: a single scalar `T` applied to
the final probabilities (`prescore/model/calibration.py`), `T < 1` sharpening
them, `T > 1` flattening them.

`T` is deliberately never fit inside `poisson.fit()` alongside `home_advantage`
or `rho`: those describe the data-generating process and are correctly fit
in-sample, but calibration is fundamentally an out-of-sample question — fitting
it on the same predictions the ratings were trained on would be circular. It
is fit once, externally, against the walk-forward backtest's held-out
predictions, then carried as a plain chosen hyperparameter, same lifecycle as
`xg_weight`.

**Validated on the standard 3,061-prediction backtest, split at its midpoint
date to check the direction is stable, not just the magnitude:**

| fit on | tested on | fitted T | log loss change | RPS change |
|---|---|---:|---:|---:|
| earlier half | later half | 0.8822 | −0.0000 | −0.0002 |
| later half | earlier half | 0.9375 | −0.0012 | −0.0003 |

Both directions land below 1.0 (sharpening) — a consistent sign, unlike the
ELO and injury-weight experiments, which flipped sign between windows and were
rejected for it. `0.9078`, the value fit on the full set, is what shipped.

**Read the aggregate numbers honestly: they barely move.** Both RPS changes
are inside this project's own established noise floor (the hyperparameter
sweep alone spans 0.003). What actually changes is the calibration table:

| bucket | before | after |
|---|---:|---:|
| 0.6–0.7 | +0.029 | +0.014 |
| 0.7–0.8 | +0.062 | +0.026 |
| 0.8–0.9 | +0.064 | +0.024 |
| 0.5–0.6 | +0.012 | **−0.019** |

More than half the top-end gap closes — but a single global temperature can't
fix a non-uniform miscalibration without redistributing some of it elsewhere,
and the 0.5–0.6 band picks up a smaller, new problem in the process. This
shipped anyway, by explicit decision, as a targeted fix for the one named flaw
rather than a claim that the model is now better calibrated everywhere.

---

## Layout

```
prescore/
  config.py              paths, league definitions, model defaults
  clock.py               UTC timestamp format (load-bearing, see below)
  store.py               SQLite access
  teams.py               team name resolution across sources
  publish.py             publish predictions, grade results
  export.py              write web/data.json
  report.py              plain-text report rendering
  cli.py                 python -m prescore <command>
  ingest/
    football_data.py     football-data.co.uk CSV adapter (history)
    thesportsdb.py       TheSportsDB adapter (fixtures + live results)
  model/
    poisson.py           the model: fit + predict
  backtest/
    metrics.py           log loss, RPS, Brier, calibration
    runner.py            walk-forward replay
db/
  schema.sql             local SQLite schema, with immutability triggers
supabase/
  config.toml            Supabase CLI project config
  migrations/            Postgres port, with RLS and the same triggers
web/
  index.html             the site: no framework, no build step
  styles.css             light and dark, responsive
  app.js                 renders data.json
  data.json / data.js    generated by `prescore export`
tests/                   104 tests, standard library unittest
```

### The two guarantees, enforced by the database

Both `db/schema.sql` and `supabase/migrations/` enforce the credibility
claims in the database rather than in application code:

1. **A prediction cannot be inserted at or after kickoff.** A trigger compares
   `created_at` against the match's `kickoff_utc` and rejects late writes.
2. **A prediction cannot be updated or deleted.** A trigger rejects both, and
   kickoff times cannot be edited once a prediction exists for that match.

This means `publish.py` does not have to be trusted for the record to be
honest — it just has to not crash. `tests/test_pipeline.py` asserts every one
of these constraints, including that they *don't* fire on backfilled history
(which has no kickoff time).

Both timestamps use one fixed-width UTC format — `clock.py` exists solely to
guarantee that, because the trigger is a string comparison. `2026-08-21T19:00:00Z`
sorts chronologically; `2026-08-21 19:00:00` would not compare correctly
against it.

In Postgres, public read access is granted through RLS and writes require the
service role key. The published accuracy views have no filter that could
quietly drop losses.

---

## Notes on the free data sources

Both of these cost hours to find and are the kind of thing that fails silently.

**football-data.co.uk publishes cross-division rows.** Their 2026/27 `E0.csv`
is currently populated with **National League** fixtures (`Div = EC`) rather
than Premier League ones. The ingester validates the `Div` column on every row
and skips foreign ones — without that check, clubs like Hornchurch and Worthing
get created as phantom Premier League teams and quietly corrupt every rating.

**TheSportsDB's API key `3` silently truncates responses to five results.**
A ten-fixture matchweek comes back half empty, with a 200 status and no error.
Use key `123` (the adapter's default; override with `PRESCORE_TSDB_KEY`).
Separately, `eventsnextleague.php` and `eventspastleague.php` return only *one*
event on the free tier no matter which key you use — `eventsround.php` is the
only endpoint that returns a full matchweek, which is why the adapter is
round-based.

Team names differ between the two sources ("Manchester United" vs
"Man United"), so everything routes through `prescore/teams.py`. An
unrecognised name is **never** silently turned into a new team — it is
reported, and the sync exits non-zero so a scheduled run surfaces it.

---

## Supabase

Project `pre-scrore` (`qigiwthmigmwpbabznge`), West EU (Ireland). The schema in
`supabase/migrations/` is deployed.

### Setup

Credentials live in `.env`, which is gitignored and must never be committed.
Copy `.env.example` to `.env` and fill in the two keys from
`supabase projects api-keys --project-ref qigiwthmigmwpbabznge`, then:

```bash
python -m prescore env
```

That prints which settings are loaded and the length of each key — never the
values, so it is safe to run in a shared terminal or paste into an issue.

### The two keys

- **anon** — safe to expose. It is what the browser uses. RLS is what protects
  the data, not the secrecy of this string.
- **service_role** — bypasses RLS entirely. Server-side only. It is the one
  thing in this project that genuinely must stay secret.

### Pushing data

```bash
python -m prescore push
```

Remote ids are `generated always as identity`, so the sync never sends an id.
Everything is keyed on natural keys and remapped as it goes: teams by name,
matches by `(league, season, home, away)`, predictions by
`(match_id, model_version, market)`. Re-running is safe — predictions upsert
with `ignore-duplicates` rather than merge, because the remote refuses to
update them.

The triggers are live during the push. If a prediction is ever rejected for
not predating kickoff, the local record is what needs fixing, not the
constraint.

Every push ends by reconciling local and remote row counts and exits non-zero
if they disagree. That check exists because of a real failure: **PostgREST caps
every response at `max-rows` (1000 on Supabase) and silently ignores a larger
`limit`.** The first push read back 1000 of 4210 matches, built a partial id
map, and dropped all 10 predictions while still reporting success. Reads are
now paged with a pinned `order`, since offset paging over an unordered result
can repeat or skip rows.

### Auditing the guarantees

```bash
python -m prescore verify
```

This probes the live database with both keys and checks that:

- the anon key can read every table and view
- the anon key cannot insert, update or delete
- the **service_role** key — which bypasses RLS entirely — still cannot update
  or delete a prediction, or move a kickoff once one exists
- a prediction cannot be backdated onto a match that has already been played

It deliberately attempts operations that must fail. That is safe here for two
reasons: predictions are protected by triggers as well as policies, so a probe
is stopped even if a policy were missing; and local SQLite is the source of
truth, so anything a probe somehow destroys is restored by `prescore push`.
Probes that touch real values capture the original and put it back.

An RLS `UPDATE`/`DELETE` with no matching policy affects zero rows rather than
erroring, so those checks are judged by reading the data back — an HTTP 204 on
an empty table proves nothing either way.

Last run: **12/12 passed.** The anon key reads everything and writes nothing,
and the service_role key — which bypasses RLS entirely — is still refused by
the triggers when it tries to update or delete a prediction, or move a kickoff
that has one.

One check is not yet fully exercised: "a prediction cannot be backdated onto a
played match" currently trips the *no kickoff time* branch rather than the
*after kickoff* comparison, because every finished match on the remote is
backfilled history without a kickoff time. Both branches are covered by the
local tests; the remote will exercise the second once round 1 has been played.

---

## Scheduling

```bash
powershell -ExecutionPolicy Bypass -File scripts\install-schedule.ps1
```

Registers a Windows task running `scripts/run-cycle.ps1` every 6 hours: sync
fixtures, publish predictions, grade finished matches, regenerate the site,
push to Supabase. Logs to `data/logs/cycle-YYYY-MM.log`. Remove it with
`-Uninstall`.

Two settings are deliberate:

- **`StartWhenAvailable`** — if the machine was asleep at the scheduled time,
  the run happens on wake rather than being skipped. A prediction cannot be
  written after kickoff, so a skipped run is a permanent hole in the record,
  not a delay.
- **A 7-day publish horizon.** Longer means more chances to catch a fixture if
  a run is missed; shorter means fresher ratings behind each prediction. A
  week gives roughly 28 attempts per fixture at modest staleness.

The task runs **only while you are logged on** — registering a "run whether
logged on or not" task would mean storing a Windows password. Treat it as a
backup to the GitHub Actions schedule below, not the primary runner: a laptop
closed over a weekend misses a matchweek, and those predictions can never be
backfilled.

### GitHub Actions (the always-on runner)

`.github/workflows/cycle.yml` runs the same cycle every 6 hours on GitHub's
infrastructure and deploys to Netlify (`pre-scrore.netlify.app`) — not GitHub
Pages. An earlier version of this workflow deployed to Pages instead; that
target was never enabled in this repo's settings and failed every single run
with a 404 until it was replaced. Setup:

1. Create a repository and push.
2. Add four repository secrets under **Settings → Secrets and variables →
   Actions**: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   and `NETLIFY_AUTH_TOKEN` (create the latter at app.netlify.com → User
   settings → Applications → New access token).
3. Trigger it once by hand from the Actions tab to confirm.

The site id is not a secret — it identifies the site, not who can deploy to
it — so it sits directly in `cycle.yml` rather than as a repository secret.

Tests live in a separate workflow on purpose. If a test regression blocked the
cycle, a broken build would become *missing predictions*, and a missing
prediction is permanent — better to have red tests and a record that keeps
publishing.

Two things to know about GitHub's scheduler: cron times are UTC and jobs can
run late under load (the seven-day publish horizon absorbs that), and
**scheduled workflows are disabled automatically after 60 days without repo
activity**, which would silently stop the record.

### Why the cycle starts with `pull`

A runner has no durable storage, so every run begins with an empty database.
Without `pull`, `publish` would not know a fixture was already public and
would predict it again with a fresh timestamp and different probabilities;
`grade` would then score *those* rows and `push` would attach the resulting
metrics to the remote prediction, whose probabilities nobody ever saw. Row
counts would still reconcile, so nothing would flag it.

`pull` hydrates the local database from Supabase first, so the runner works
from the published record rather than a reconstruction of it. Verified by
wiping the local database, rebuilding from nothing and comparing: picks and
timestamps byte-identical, probabilities within **5e-16** (Postgres emits
`double precision` at 15 significant digits, so exact float round-trip is not
available and does not matter).

---

## What is not built yet

- **The frontend still reads a static `data.json`.** The Actions workflow
  regenerates and redeploys it every 6 hours, so it stays fresh — but pointing
  the page at PostgREST with the anon key would make it genuinely live, and
  needs no new dependency.
- **The Windows Task Scheduler job is a manual-only fallback.** It runs the
  same cycle locally and has no cloud counterpart of its own; it is not needed
  now that GitHub Actions runs the real cycle, but it is left in place in case
  Actions is ever down.

The season kicked off on schedule and the record is real: as of the last
successful run, 21 predictions are graded at 61.9% accuracy under the current
model version. Losses are shown alongside hits on the site, exactly as
designed.

---

## Scope discipline

v1 is **1X2 only**, **EPL only**. The scoreline matrix the model already builds
makes correct score, BTTS and over/under nearly free to add — but per the scope
doc, those wait until the 1X2 record is real and public. There is no value in
publishing four markets nobody can yet judge you on.

Framing stays analytical throughout: these are predictions and probabilities,
not betting advice.
