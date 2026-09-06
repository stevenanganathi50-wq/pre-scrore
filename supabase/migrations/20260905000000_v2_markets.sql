-- v2 markets: BTTS and Over/Under 2.5, derived from the same scoreline
-- matrix the model already builds for 1X2 (see prescore/model/markets.py).
-- No new fitting, no change to what 1X2 predicts -- this does not touch the
-- existing track record and is not another exception to the model freeze.
--
-- A genuinely generic table, not a reuse of predictions' p_home/p_draw/
-- p_away columns, which are specifically shaped for 1X2's three named
-- outcomes. BTTS is Yes/No, Over/Under is Over/Under -- neither fits that
-- shape honestly, and future markets (correct score has many outcomes) need
-- arbitrary outcome counts anyway. One row per possible outcome per market
-- per fixture.

create table if not exists public.market_predictions (
    id             bigint generated always as identity primary key,
    match_id       bigint not null references public.matches(id),
    model_version  text not null,
    market         text not null,
    outcome        text not null,
    probability    double precision not null check (probability between 0 and 1),
    is_pick        boolean not null,
    created_at     timestamptz not null default now(),
    unique (match_id, model_version, market, outcome)
);

-- log_loss and brier generalise cleanly to any number of outcomes; RPS does
-- not -- it depends on a natural ordering (1X2's H < D < A), which a 2-way
-- market like BTTS or Over/Under doesn't have anything meaningful to add
-- beyond what Brier already captures. So RPS is 1X2-only, not carried here.
--
-- Primary key is the natural (match, version, market) triple, not a
-- generated id referencing market_predictions -- a market prediction is
-- several outcome rows, not one, so there is no single row to reference.
create table if not exists public.market_prediction_results (
    match_id       bigint not null references public.matches(id),
    model_version  text not null,
    market         text not null,
    actual_outcome text not null,
    is_hit         boolean not null,
    log_loss       double precision not null,
    brier          double precision not null,
    graded_at      timestamptz not null default now(),
    primary key (match_id, model_version, market)
);

-- --- Guarantees 1 and 2, reusing the same trigger functions -------------
-- enforce_prediction_before_kickoff() and reject_prediction_mutation() only
-- reference NEW.match_id / NEW.created_at / TG_OP, nothing predictions-
-- specific, so they attach to market_predictions unchanged.

drop trigger if exists market_predictions_before_kickoff on public.market_predictions;
create trigger market_predictions_before_kickoff
    before insert on public.market_predictions
    for each row execute function public.enforce_prediction_before_kickoff();

drop trigger if exists market_predictions_immutable on public.market_predictions;
create trigger market_predictions_immutable
    before update or delete on public.market_predictions
    for each row execute function public.reject_prediction_mutation();

-- Extend the kickoff-rewrite guard to check market_predictions too: a v2
-- row can exist with zero CURRENT-version 1X2 rows for the same match (the
-- backfill case, where 1X2 was published under an older model version), so
-- checking only `predictions` would leave a real gap.
create or replace function public.reject_kickoff_rewrite()
returns trigger
language plpgsql
as $$
begin
    if new.kickoff_utc is distinct from old.kickoff_utc
       and (
           exists (select 1 from public.predictions p where p.match_id = old.id)
           or exists (select 1 from public.market_predictions mp where mp.match_id = old.id)
       )
    then
        raise exception
            'cannot move kickoff for match % after predictions were published',
            old.id;
    end if;
    new.updated_at := now();
    return new;
end;
$$;

-- --- Public view -----------------------------------------------------------

drop view if exists public.v_market_track_record;
create view public.v_market_track_record with (security_invoker = true) as
select
    mp.match_id,
    m.league,
    m.season,
    m.kickoff_utc,
    h.name              as home_team,
    a.name              as away_team,
    mp.model_version,
    mp.market,
    mp.outcome,
    mp.probability,
    mp.is_pick,
    mp.created_at       as predicted_at,
    m.status,
    m.home_goals,
    m.away_goals,
    r.actual_outcome,
    r.is_hit,
    r.log_loss,
    r.brier,
    r.graded_at
from public.market_predictions mp
join public.matches m on m.id = mp.match_id
join public.teams h on h.id = m.home_team_id
join public.teams a on a.id = m.away_team_id
left join public.market_prediction_results r
  on r.match_id = mp.match_id and r.model_version = mp.model_version
 and r.market = mp.market;

drop view if exists public.v_market_accuracy;
create view public.v_market_accuracy with (security_invoker = true) as
select
    m.league,
    r.model_version,
    r.market,
    count(*)                                        as graded,
    count(*) filter (where r.is_hit)                 as hits,
    count(*) filter (where not r.is_hit)             as misses,
    round((count(*) filter (where r.is_hit))::numeric
          / nullif(count(*), 0), 4)                  as accuracy,
    round(avg(r.log_loss)::numeric, 4)               as log_loss,
    round(avg(r.brier)::numeric, 4)                  as brier
from public.market_prediction_results r
join public.matches m on m.id = r.match_id
group by m.league, r.model_version, r.market;

-- --- Row level security ----------------------------------------------------

alter table public.market_predictions        enable row level security;
alter table public.market_prediction_results enable row level security;

drop policy if exists public_read on public.market_predictions;
create policy public_read on public.market_predictions
    for select to anon, authenticated using (true);

drop policy if exists public_read on public.market_prediction_results;
create policy public_read on public.market_prediction_results
    for select to anon, authenticated using (true);

grant select on
    public.v_market_track_record,
    public.v_market_accuracy
to anon, authenticated;
