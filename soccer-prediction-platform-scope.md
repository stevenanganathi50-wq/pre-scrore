# Soccer Prediction Platform — Project Scope

**Type:** Pure prediction/tipster platform (no betting integration)
**Stack:** Supabase (DB + Edge Functions), Python (modeling/data pipeline)
**Budget:** $0 to start — free data sources and free-tier APIs only

---

## 1. Product Definition

A platform that predicts soccer match outcomes and publishes those predictions publicly, along with a transparent, honest accuracy track record. No odds comparison, no staking logic, no betting facilitation — the product is the prediction and the credibility built around it.

### Core value proposition
- Predict match outcomes before kickoff
- Track every prediction against the actual result
- Publish accuracy openly (wins and losses) to build trust

### Explicitly out of scope for v1
- Odds integration / value betting comparison
- Live in-play predictions
- Betting facilitation of any kind
- User accounts / monetization
- Multi-league coverage

---

## 2. Prediction Types

| Priority | Type | Notes |
|---|---|---|
| v1 | 1X2 (Home / Draw / Away) | Simplest, most defensible with a Poisson model |
| v2 | Correct score | Derived from same Poisson model, more granular |
| v2 | BTTS (Both Teams to Score) | Simple derived probability |
| v2 | Over/Under 2.5 goals | Simple derived probability |

Start with 1X2 only. Expand once the model is validated.

---

## 3. Data Layer

### Historical data (for training/backtesting)
- **football-data.co.uk** — free CSVs: match results, team stats, historical closing odds (useful for backtesting even though odds aren't part of the product)
- **Kaggle** — supplementary historical datasets if needed

### Ongoing/live data (free tiers)
- **API-Football** (via RapidAPI) — free tier, ~100 requests/day; enough for one league if cached
- **football-data.org** — free tier, rate-limited, covers major competitions
- **TheSportsDB** — free tier, fixtures/results

### Data scope for v1
- **One league only** (recommended: EPL — most documented, cleanest data)
- Fixtures, results, team-level goals scored/conceded (home & away splits)

---

## 4. Prediction Engine

### v1 model: Poisson distribution
- Estimate each team's attack strength and defense strength from historical goals scored/conceded (home/away split)
- Combine into expected goals for each side in a fixture
- Derive probabilities for Home Win / Draw / Away Win from the Poisson distributions
- Optionally output the most likely exact scoreline

### Backtesting (do this before publishing anything)
- Run the model against historical fixtures
- Compare predicted outcomes vs actual results
- Only move to live predictions once backtested accuracy is known and reasonable

### v2+ possibilities
- Logistic regression / gradient boosting with additional features (form, xG if available)
- ELO-style team rating system
- Ensemble of multiple models

---

## 5. Accuracy Tracking (core differentiator)

- Every prediction is stored **before** kickoff, timestamped, immutable
- After the match, log actual result and mark hit/miss
- Public accuracy % — overall, and broken down by league/prediction type
- Optional confidence score per prediction, so high-confidence picks can be tracked separately from low-confidence ones
- Show losses as openly as wins — this is what separates a credible tipster from a marketing gimmick

---

## 6. Platform Layer

### Backend (Supabase)
Suggested tables:
- `teams` — team metadata
- `matches` — fixtures, results, league, date
- `predictions` — match_id, predicted outcome, probabilities, confidence, timestamp
- `results` — actual outcome, hit/miss flag

### Automation
- Scheduled job (Python script or Supabase Edge Function / cron) to:
  1. Pull upcoming fixtures
  2. Run the model
  3. Store predictions before kickoff
  4. Pull results after matches complete and update hit/miss

### Frontend
- Upcoming fixtures with predictions displayed
- Past predictions with hit/miss badges
- Public accuracy dashboard (overall + breakdowns)

---

## 7. Legal/Regulatory Notes

- Pure prediction/analytics content (no betting facilitation, no stake handling) generally sits in a safer regulatory zone than betting-adjacent platforms
- Gambling advertising and facilitation rules vary by country, including South Africa — worth a light check-in with a professional if the platform grows or ever adds betting-adjacent features later
- Avoid language that could be read as "advice to bet" — frame everything as predictions/analysis, not wagering guidance

---

## 8. Build Order (Zero-Budget MVP Path)

1. Seed historical data for one league (EPL) from football-data.co.uk
2. Build the Poisson model in Python
3. Backtest against historical results — validate before building anything public-facing
4. Design and build Supabase schema (teams, matches, predictions, results)
5. Automate fixture pulling + prediction generation (free-tier API)
6. Build simple frontend: upcoming predictions + accuracy track record
7. **Only after the above works:** consider expanding to more leagues, more prediction types, user accounts, or monetization

---

## 9. Future Expansion Ideas (Post-MVP)

- Additional leagues once the model is proven on one
- Correct score / BTTS / over-under predictions
- User accounts, saved predictions, notifications
- Community/social layer (leaderboards for users who track their own picks against the platform's)
- Possible v3: odds comparison as a separate, clearly-labeled analytics feature (not betting facilitation)
