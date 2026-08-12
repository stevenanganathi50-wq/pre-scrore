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
DROP TRIGGER IF EXISTS matches_protect_kickoff;
CREATE TRIGGER matches_protect_kickoff
BEFORE UPDATE OF kickoff_utc ON matches
WHEN OLD.kickoff_utc IS NOT NULL
 AND NEW.kickoff_utc IS NOT OLD.kickoff_utc
 AND EXISTS (SELECT 1 FROM predictions WHERE match_id = OLD.id)
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
