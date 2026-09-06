-- pre-scrore local schema (SQLite).
--
-- This mirrors the intended Supabase/Postgres schema so the port is a
-- straight translation. Two rules drive the design:
--   1. A published prediction is immutable and always predates kickoff.
--   2. Backtest predictions live in their own tables and can never be
--      confused with the public track record.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teams (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Maps a provider's spelling of a team onto our canonical team row.
-- football-data.co.uk says "Man United", API-Football says "Manchester United".
CREATE TABLE IF NOT EXISTS team_aliases (
    alias    TEXT NOT NULL,
    source   TEXT NOT NULL,
    team_id  INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    PRIMARY KEY (alias, source)
);

CREATE TABLE IF NOT EXISTS matches (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_ref    TEXT,                       -- the provider's own event id
    league        TEXT NOT NULL,
    season        INTEGER NOT NULL,           -- starting year: 2015 = 2015/16
    match_date    TEXT NOT NULL,              -- ISO date, competition local
    kickoff_time  TEXT,                       -- HH:MM local, may be unknown
    kickoff_utc   TEXT,                       -- ISO 8601 UTC, 'YYYY-MM-DDTHH:MM:SSZ'
    round         INTEGER,
    home_team_id  INTEGER NOT NULL REFERENCES teams(id),
    away_team_id  INTEGER NOT NULL REFERENCES teams(id),
    status        TEXT NOT NULL CHECK (status IN ('scheduled', 'finished')),
    home_goals    INTEGER,
    away_goals    INTEGER,
    result        TEXT CHECK (result IN ('H', 'D', 'A')),
    -- Shot counts, used to build an expected-goals proxy. Goals are a noisy
    -- realisation of chances; shots on target are a steadier signal of how
    -- often a team creates them.
    home_shots            INTEGER,
    away_shots            INTEGER,
    home_shots_on_target  INTEGER,
    away_shots_on_target  INTEGER,
    home_corners          INTEGER,
    away_corners          INTEGER,
    -- Closing market odds are stored for backtest benchmarking only. They are
    -- never shown in the product and never feed the model.
    closing_odds_home  REAL,
    closing_odds_draw  REAL,
    closing_odds_away  REAL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (league, season, home_team_id, away_team_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches (match_date);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches (status, match_date);

-- Injuries: a variable-count list per team per fixture, so unlike shots this
-- cannot live as flat columns on `matches`. match_id is resolved at ingest
-- time (team + fixture date -> our own match row) and left NULL when no
-- match could be matched, so a resolution gap is visible rather than the row
-- being silently dropped.
CREATE TABLE IF NOT EXISTS injuries (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    league        TEXT NOT NULL,
    match_id      INTEGER REFERENCES matches(id),
    team_id       INTEGER NOT NULL REFERENCES teams(id),
    player_name   TEXT NOT NULL,
    reason        TEXT,
    fixture_date  TEXT NOT NULL,  -- as given by the source; used for matching and audit
    ingested_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source, team_id, player_name, fixture_date)
);

CREATE INDEX IF NOT EXISTS idx_injuries_match ON injuries (match_id);

-- Published predictions. Written once, before kickoff, never updated.
CREATE TABLE IF NOT EXISTS predictions (
    id             INTEGER PRIMARY KEY,
    match_id       INTEGER NOT NULL REFERENCES matches(id),
    model_version  TEXT NOT NULL,
    market         TEXT NOT NULL DEFAULT '1X2',
    p_home         REAL NOT NULL,
    p_draw         REAL NOT NULL,
    p_away         REAL NOT NULL,
    pick           TEXT NOT NULL CHECK (pick IN ('H', 'D', 'A')),
    confidence     REAL NOT NULL,
    created_at     TEXT NOT NULL,
    UNIQUE (match_id, model_version, market)
);

-- The same two guarantees the Postgres schema enforces, enforced here too, so
-- the local pipeline is exercised against the real constraints rather than
-- discovering them at deploy time.
--
-- Both timestamps are ISO 8601 UTC in a fixed-width format, so string
-- comparison is chronological comparison.

-- Dropped and recreated rather than IF NOT EXISTS, so that tightening a rule
-- here actually reaches databases that already exist.
DROP TRIGGER IF EXISTS predictions_before_kickoff;
CREATE TRIGGER predictions_before_kickoff
BEFORE INSERT ON predictions
BEGIN
    SELECT CASE
        -- No kickoff time means the claim "this predates the match" cannot be
        -- checked, and an unverifiable claim is what this table exists to
        -- prevent. Refuse rather than assume.
        WHEN (SELECT kickoff_utc FROM matches WHERE id = NEW.match_id) IS NULL
        THEN RAISE(ABORT, 'match has no kickoff time, so a prediction cannot be verified as pre-kickoff')
        WHEN NEW.created_at >= (
            SELECT kickoff_utc FROM matches WHERE id = NEW.match_id
        )
        THEN RAISE(ABORT, 'prediction would be recorded at or after kickoff')
    END;
END;

DROP TRIGGER IF EXISTS predictions_no_update;
CREATE TRIGGER predictions_no_update
BEFORE UPDATE ON predictions
BEGIN
    SELECT RAISE(ABORT, 'predictions are immutable once published');
END;

DROP TRIGGER IF EXISTS predictions_no_delete;
CREATE TRIGGER predictions_no_delete
BEFORE DELETE ON predictions
BEGIN
    SELECT RAISE(ABORT, 'predictions are immutable once published');
END;

-- Kickoff cannot be moved once a prediction exists for that match, or
-- guarantee 1 could be rewritten after the fact.
-- Checks both predictions and market_predictions: a v2-market row can exist
-- for a match with no CURRENT-version 1X2 row yet (the backfill case, where
-- 1X2 was published under an older model version) so checking only one
-- table would not be a watertight guarantee.
DROP TRIGGER IF EXISTS matches_protect_kickoff;
CREATE TRIGGER matches_protect_kickoff
BEFORE UPDATE OF kickoff_utc ON matches
WHEN OLD.kickoff_utc IS NOT NULL
 AND NEW.kickoff_utc IS NOT OLD.kickoff_utc
 AND (
   EXISTS (SELECT 1 FROM predictions WHERE match_id = OLD.id)
   OR EXISTS (SELECT 1 FROM market_predictions WHERE match_id = OLD.id)
 )
BEGIN
    SELECT RAISE(ABORT, 'cannot move kickoff after predictions were published');
END;

-- Grading of a prediction once the match is finished.
CREATE TABLE IF NOT EXISTS prediction_results (
    prediction_id  INTEGER PRIMARY KEY REFERENCES predictions(id) ON DELETE CASCADE,
    actual         TEXT NOT NULL CHECK (actual IN ('H', 'D', 'A')),
    is_hit         INTEGER NOT NULL CHECK (is_hit IN (0, 1)),
    log_loss       REAL NOT NULL,
    rps            REAL NOT NULL,
    brier          REAL NOT NULL,
    graded_at      TEXT NOT NULL
);

-- v2 markets (BTTS, Over/Under, ...): a genuinely generic table, not a reuse
-- of `predictions`' p_home/p_draw/p_away columns, which are specifically
-- shaped for 1X2's three named outcomes. BTTS is Yes/No, Over/Under is
-- Over/Under -- neither fits that shape honestly, and future markets
-- (correct score has many outcomes) need arbitrary outcome counts anyway.
-- One row per possible outcome per market per fixture.
--
-- Derived purely from the scoreline matrix an already-fitted, already-frozen
-- model produces for 1X2 -- see prescore/model/markets.py. No new fitting, no
-- change to what 1X2 predicts, so this does not touch the existing track
-- record and is not another exception to the model freeze.
CREATE TABLE IF NOT EXISTS market_predictions (
    id             INTEGER PRIMARY KEY,
    match_id       INTEGER NOT NULL REFERENCES matches(id),
    model_version  TEXT NOT NULL,
    market         TEXT NOT NULL,       -- 'BTTS', 'OU2.5'
    outcome        TEXT NOT NULL,       -- 'Yes'/'No', 'Over'/'Under'
    probability    REAL NOT NULL,
    is_pick        INTEGER NOT NULL CHECK (is_pick IN (0, 1)),
    created_at     TEXT NOT NULL,
    UNIQUE (match_id, model_version, market, outcome)
);

-- The same immutability guarantees as `predictions`, applied to this table.
DROP TRIGGER IF EXISTS market_predictions_before_kickoff;
CREATE TRIGGER market_predictions_before_kickoff
BEFORE INSERT ON market_predictions
BEGIN
    SELECT CASE
        WHEN (SELECT kickoff_utc FROM matches WHERE id = NEW.match_id) IS NULL
        THEN RAISE(ABORT, 'match has no kickoff time, so a prediction cannot be verified as pre-kickoff')
        WHEN NEW.created_at >= (
            SELECT kickoff_utc FROM matches WHERE id = NEW.match_id
        )
        THEN RAISE(ABORT, 'prediction would be recorded at or after kickoff')
    END;
END;

DROP TRIGGER IF EXISTS market_predictions_no_update;
CREATE TRIGGER market_predictions_no_update
BEFORE UPDATE ON market_predictions
BEGIN
    SELECT RAISE(ABORT, 'predictions are immutable once published');
END;

DROP TRIGGER IF EXISTS market_predictions_no_delete;
CREATE TRIGGER market_predictions_no_delete
BEFORE DELETE ON market_predictions
BEGIN
    SELECT RAISE(ABORT, 'predictions are immutable once published');
END;

-- log_loss and brier generalise cleanly to any number of outcomes; RPS does
-- not -- it depends on a natural ordering (1X2's H < D < A), which a 2-way
-- market like BTTS or Over/Under doesn't have anything meaningful to add
-- beyond what Brier already captures. So RPS is 1X2-only, not carried here.
CREATE TABLE IF NOT EXISTS market_prediction_results (
    match_id       INTEGER NOT NULL REFERENCES matches(id),
    model_version  TEXT NOT NULL,
    market         TEXT NOT NULL,
    actual_outcome TEXT NOT NULL,
    is_hit         INTEGER NOT NULL CHECK (is_hit IN (0, 1)),
    log_loss       REAL NOT NULL,
    brier          REAL NOT NULL,
    graded_at      TEXT NOT NULL,
    PRIMARY KEY (match_id, model_version, market)
);

-- --- Backtesting ---------------------------------------------------------
-- Kept separate from `predictions` on purpose: the public accuracy number
-- must only ever be computed from predictions made before kickoff in real
-- time, not from a retrospective simulation.

CREATE TABLE IF NOT EXISTS backtest_runs (
    id             INTEGER PRIMARY KEY,
    model_version  TEXT NOT NULL,
    league         TEXT NOT NULL,
    params         TEXT NOT NULL,       -- JSON of the model hyperparameters
    train_from     TEXT NOT NULL,
    test_from      TEXT NOT NULL,
    test_to        TEXT NOT NULL,
    n_predictions  INTEGER NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_predictions (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    match_id    INTEGER NOT NULL REFERENCES matches(id),
    p_home      REAL NOT NULL,
    p_draw      REAL NOT NULL,
    p_away      REAL NOT NULL,
    pick        TEXT NOT NULL,
    confidence  REAL NOT NULL,
    actual      TEXT NOT NULL,
    is_hit      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_backtest_pred_run ON backtest_predictions (run_id);
