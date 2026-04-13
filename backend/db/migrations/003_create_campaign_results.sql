-- Campaign ROI results table — run after 002_create_ltv_scores.sql

create table if not exists campaign_results (
    campaign_id                 text           primary key,
    campaign_name               text           not null,
    start_date                  date           not null,
    spend                       numeric(12, 2) not null,
    n_players                   integer        not null,
    avg_ltv_acquired            numeric(10, 2) not null,
    total_predicted_revenue_90d numeric(12, 2) not null,
    roas                        numeric(8,  4) not null,
    payback_period_days         numeric(8,  2),          -- null when revenue is zero
    is_profitable               boolean        not null,
    created_at                  timestamptz    not null default now()
);

alter table campaign_results enable row level security;
