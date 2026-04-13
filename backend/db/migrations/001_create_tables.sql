-- GemBlast player LTV studio — initial schema
-- Run this once in the Supabase SQL editor before executing the ETL pipeline.

-- ─────────────────────────────────────────────
-- players  (one row per player, RFM aggregates)
-- ─────────────────────────────────────────────
create table if not exists players (
    player_id       text        primary key,
    cohort          text        not null check (cohort in ('whale', 'mid', 'f2p')),
    install_date    date        not null,
    first_seen      timestamptz not null,
    last_seen       timestamptz not null,
    recency_days    integer     not null check (recency_days >= 0),
    frequency       integer     not null check (frequency >= 0),
    monetary        numeric(10, 2) not null default 0,
    updated_at      timestamptz not null default now()
);

-- index used by LTV model queries (filter by cohort, order by monetary)
create index if not exists players_cohort_idx      on players (cohort);
create index if not exists players_last_seen_idx   on players (last_seen);


-- ─────────────────────────────────────────────
-- sessions  (one row per play session)
-- ─────────────────────────────────────────────
create table if not exists sessions (
    session_id          text        primary key,
    player_id           text        not null references players (player_id),
    cohort              text        not null check (cohort in ('whale', 'mid', 'f2p')),
    session_start       timestamptz not null,
    days_since_install  integer     not null check (days_since_install >= 0),
    levels_completed    integer     not null default 0,
    ads_watched         integer     not null default 0,
    revenue             numeric(10, 2) not null default 0
);

create index if not exists sessions_player_id_idx     on sessions (player_id);
create index if not exists sessions_session_start_idx on sessions (session_start);


-- ─────────────────────────────────────────────
-- auto-update updated_at on players upsert
-- ─────────────────────────────────────────────
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists players_set_updated_at on players;
create trigger players_set_updated_at
    before update on players
    for each row execute function set_updated_at();


-- ─────────────────────────────────────────────
-- Row Level Security
-- Supabase enables RLS by default on new tables.
-- The service-role key (used by the ETL pipeline)
-- bypasses RLS automatically — no policy needed
-- for backend writes.
-- Add SELECT policies here when you expose data
-- to authenticated end-users.
-- ─────────────────────────────────────────────
alter table players  enable row level security;
alter table sessions enable row level security;
