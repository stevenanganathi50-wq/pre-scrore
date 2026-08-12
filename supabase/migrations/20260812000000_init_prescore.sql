-- pre-scrore: Supabase / Postgres schema.
--
-- Port of db/schema.sql with the things Postgres can enforce that SQLite
-- cannot. Two credibility guarantees are enforced by the database itself,
-- not by application code:
--
--   1. A prediction cannot be inserted after kickoff.
--   2. A prediction cannot be updated or deleted, ever.
--
-- That is what makes the published track record worth anything: it is not a
-- claim about our honesty, it is a property of the system.
--
-- Run this in the Supabase SQL editor, or via `supabase db push`.

-- --- Tables --------------------------------------------------------------

create table if not exists public.teams (
    id          bigint generated always as identity primary key,
    name        text not null unique,
    short_name  text,
    crest_url   text,
    created_at  timestamptz not null default now()
);

create table if not exists public.team_aliases (
    alias    text not null,
    source   text not null,
    team_id  bigint not null references public.teams(id) on delete cascade,
    primary key (alias, source)
);

create table if not exists public.matches (
    id            bigint generated always as identity primary key,
    source        text not null,
    source_ref    text,
    league        text not null,
    season        int not null,
    -- Nullable because backfilled history from football-data.co.uk carries a
    -- match date but no kickoff time. Scheduled fixtures must have one, and
    -- the prediction trigger below refuses to publish without it.
    kickoff_utc   timestamptz,
    home_team_id  bigint not null references public.teams(id),
    away_team_id  bigint not null references public.teams(id),
    status        text not null default 'scheduled'
                  check (status in ('scheduled', 'finished', 'postponed')),
    home_goals    int,
    away_goals    int,
    result        text check (result in ('H', 'D', 'A')),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (league, season, home_team_id, away_team_id),
    constraint finished_matches_have_a_score check (
        status <> 'finished'
        or (home_goals is not null and away_goals is not null and result is not null)
    ),
    constraint scheduled_matches_have_a_kickoff check (
        status <> 'scheduled' or kickoff_utc is not null
    )
);

create index if not exists matches_kickoff_idx on public.matches (kickoff_utc);
create index if not exists matches_status_idx on public.matches (status, kickoff_utc);

create table if not exists public.predictions (
    id             bigint generated always as identity primary key,
    match_id       bigint not null references public.matches(id),
    model_version  text not null,
    market         text not null default '1X2',
    p_home         double precision not null check (p_home between 0 and 1),
    p_draw         double precision not null check (p_draw between 0 and 1),
    p_away         double precision not null check (p_away between 0 and 1),
    pick           text not null check (pick in ('H', 'D', 'A')),
    confidence     double precision not null check (confidence between 0 and 1),
    created_at     timestamptz not null default now(),
    unique (match_id, model_version, market),
    constraint probabilities_sum_to_one check (
        abs(p_home + p_draw + p_away - 1) < 0.0001
    )
);

create table if not exists public.prediction_results (
    prediction_id  bigint primary key references public.predictions(id) on delete cascade,
    actual         text not null check (actual in ('H', 'D', 'A')),
    is_hit         boolean not null,
    log_loss       double precision not null,
    rps            double precision not null,
    brier          double precision not null,
    graded_at      timestamptz not null default now()
);

-- --- Guarantee 1: predictions must predate kickoff -----------------------

create or replace function public.enforce_prediction_before_kickoff()
returns trigger
language plpgsql
as $$
declare
    kickoff timestamptz;
begin
    select m.kickoff_utc into kickoff
    from public.matches m
    where m.id = new.match_id;

    if not found then
        raise exception 'match % does not exist', new.match_id;
    end if;

    -- No kickoff time means we cannot prove the prediction predates the
    -- match, and an unprovable claim is exactly what this table exists to
    -- prevent. Refuse rather than assume.
    if kickoff is null then
        raise exception
            'match % has no kickoff time, so a prediction cannot be verified as pre-kickoff',
            new.match_id;
    end if;

    if new.created_at >= kickoff then
        raise exception
            'prediction for match % would be recorded at %, after kickoff at %',
            new.match_id, new.created_at, kickoff;
    end if;

    return new;
end;
$$;

drop trigger if exists predictions_before_kickoff on public.predictions;
create trigger predictions_before_kickoff
    before insert on public.predictions
    for each row execute function public.enforce_prediction_before_kickoff();

-- --- Guarantee 2: predictions are immutable ------------------------------

create or replace function public.reject_prediction_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception
        'predictions are immutable: a published prediction cannot be % once written',
        case tg_op when 'DELETE' then 'deleted' else 'updated' end;
end;
$$;

drop trigger if exists predictions_immutable on public.predictions;
create trigger predictions_immutable
    before update or delete on public.predictions
    for each row execute function public.reject_prediction_mutation();

-- A match's kickoff time must not be edited to invalidate guarantee 1.
create or replace function public.reject_kickoff_rewrite()
returns trigger
language plpgsql
as $$
begin
    -- `is distinct from`, not `<>`: with a nullable column, `value <> null`
    -- evaluates to null and the guard would silently pass, letting a kickoff
    -- time be erased after predictions were published.
    if new.kickoff_utc is distinct from old.kickoff_utc
       and exists (select 1 from public.predictions p where p.match_id = old.id)
    then
        raise exception
            'cannot move kickoff for match % after predictions were published',
            old.id;
    end if;
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists matches_protect_kickoff on public.matches;
create trigger matches_protect_kickoff
    before update on public.matches
    for each row execute function public.reject_kickoff_rewrite();

-- --- Public views --------------------------------------------------------

-- Recreated rather than replaced: `create or replace view` refuses a changed
-- column list, which would make this migration non-rerunnable.
drop view if exists public.v_accuracy_by_confidence;
drop view if exists public.v_accuracy;
drop view if exists public.v_track_record;

-- The full public record: every prediction, with its outcome once known.
create view public.v_track_record with (security_invoker = true) as
select
    p.id                as prediction_id,
    m.id                as match_id,
    m.league,
    m.season,
    m.kickoff_utc,
    h.name              as home_team,
    a.name              as away_team,
    p.model_version,
    p.market,
    p.p_home,
    p.p_draw,
    p.p_away,
    p.pick,
    p.confidence,
    p.created_at        as predicted_at,
    m.status,
    m.home_goals,
    m.away_goals,
    r.actual,
    r.is_hit,
    r.log_loss,
    r.rps,
    r.brier,
    r.graded_at
from public.predictions p
join public.matches m on m.id = p.match_id
join public.teams h on h.id = m.home_team_id
join public.teams a on a.id = m.away_team_id
left join public.prediction_results r on r.prediction_id = p.id;

-- Headline accuracy. Losses are included by construction: the only filter is
-- "has this been graded", which cannot single out misses.
--
-- Everything is read from v_track_record, which already carries the grading
-- columns. Joining prediction_results again here would make `is_hit` and
-- `actual` ambiguous and the view would fail to create.
create view public.v_accuracy with (security_invoker = true) as
select
    league,
    model_version,
    market,
    count(*)                                        as graded,
    count(*) filter (where is_hit)                  as hits,
    count(*) filter (where not is_hit)              as misses,
    round((count(*) filter (where is_hit))::numeric
          / nullif(count(*), 0), 4)                 as accuracy,
    round(avg(log_loss)::numeric, 4)                as log_loss,
    round(avg(rps)::numeric, 4)                     as rps,
    round(avg(brier)::numeric, 4)                   as brier
from public.v_track_record
where is_hit is not null
group by league, model_version, market;

-- Accuracy split by how confident the pick was. A three-way market cannot
-- produce a pick below 1/3, so the buckets start at 0.33.
create view public.v_accuracy_by_confidence with (security_invoker = true) as
select
    league,
    model_version,
    width_bucket(confidence, 0.33, 1.0, 5)          as bucket,
    count(*)                                        as graded,
    count(*) filter (where is_hit)                  as hits,
    round((count(*) filter (where is_hit))::numeric
          / nullif(count(*), 0), 4)                 as accuracy
from public.v_track_record
where is_hit is not null
group by league, model_version, bucket
order by league, model_version, bucket;

-- --- Row level security --------------------------------------------------
-- Anyone may read. Nobody may write with the anon key; the scheduled job
-- writes with the service role key, which bypasses RLS.

alter table public.teams             enable row level security;
alter table public.team_aliases      enable row level security;
alter table public.matches           enable row level security;
alter table public.predictions       enable row level security;
alter table public.prediction_results enable row level security;

drop policy if exists public_read on public.teams;
create policy public_read on public.teams for select to anon, authenticated using (true);

drop policy if exists public_read on public.team_aliases;
create policy public_read on public.team_aliases for select to anon, authenticated using (true);

drop policy if exists public_read on public.matches;
create policy public_read on public.matches for select to anon, authenticated using (true);

drop policy if exists public_read on public.predictions;
create policy public_read on public.predictions for select to anon, authenticated using (true);

drop policy if exists public_read on public.prediction_results;
create policy public_read on public.prediction_results for select to anon, authenticated using (true);

-- The views run with security_invoker, so they respect the policies above
-- rather than bypassing them as view-owner rights would.
grant usage on schema public to anon, authenticated;
grant select on
    public.v_track_record,
    public.v_accuracy,
    public.v_accuracy_by_confidence
to anon, authenticated;
