-- LTV scores table — run after 001_create_tables.sql

create table if not exists ltv_scores (
    player_id               text           primary key references players (player_id),
    predicted_purchases_30d numeric(10, 4) not null,
    predicted_purchases_90d numeric(10, 4) not null,
    churn_probability       numeric(6,  4) not null check (churn_probability between 0 and 1),
    expected_ltv_90d        numeric(10, 2) not null,
    segment                 text           not null check (segment in ('high_ltv', 'mid_ltv', 'low_ltv')),
    scored_at               timestamptz    not null default now()
);

-- common query patterns: filter by segment, rank by LTV
create index if not exists ltv_scores_segment_idx     on ltv_scores (segment);
create index if not exists ltv_scores_ltv_desc_idx    on ltv_scores (expected_ltv_90d desc);
create index if not exists ltv_scores_churn_desc_idx  on ltv_scores (churn_probability desc);

alter table ltv_scores enable row level security;
