# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Monorepo with two independent deployable units:
- `backend/` — Python FastAPI app + ML pipeline (deployed to Railway)
- `frontend/` — Next.js 14 app (deployed to Vercel)

## Backend commands

All commands run from `backend/`:

```bash
pip install -e ".[dev]"          # install with dev deps (pytest, ruff)

uvicorn api.main:app --reload --port 8000   # start API dev server

pytest                            # run all 67 tests
pytest tests/test_ltv_model.py   # run a single test file
pytest -k "test_churn"           # run tests matching a pattern

ruff check .                      # lint
ruff check . --fix                # auto-fix fixable lint errors
```

Pipeline scripts (require `.env` with `SUPABASE_URL` + `SUPABASE_KEY`):

```bash
python data/generate_events.py          # generate synthetic CSV
python -m etl.pipeline                  # ETL -> Supabase players + sessions tables
python -m models.ltv_model              # score players -> ltv_scores table
python -m models.ltv_model --dry-run    # score without writing to Supabase
python -m models.campaign_model         # ROI simulation -> campaign_results table
```

## Frontend commands

All commands run from `frontend/`:

```bash
npm run dev      # dev server at http://localhost:3000
npm run build    # production build (also used to type-check)
```

## Architecture

### Data flow

```
generate_events.py
    -> data/raw/player_events.csv
    -> etl/pipeline.py  (Pydantic validation, RFM aggregation)
        -> Supabase: players, sessions
        -> models/ltv_model.py  (BG/NBD + Gamma-Gamma via lifetimes library)
            -> Supabase: ltv_scores
            -> models/campaign_model.py  (ROI simulation)
                -> Supabase: campaign_results
                -> data/outputs/campaign_comparison.png
```

### Backend structure

- `etl/schemas.py` — Pydantic v2 models: `PlayerEvent` (raw event validation), `PlayerRecord`, `SessionRecord`
- `etl/pipeline.py` — load CSV → validate → aggregate RFM → aggregate sessions → upsert to Supabase
- `models/ltv_model.py` — BG/NBD + Gamma-Gamma: fetch RFM from Supabase → fit → score → assign segments → write ltv_scores
- `models/campaign_model.py` — select player pools by targeting strategy → compute ROAS/payback → write campaign_results → save plot
- `api/main.py` — FastAPI app; Supabase client lives in `app.state.supabase` (initialised in lifespan); all DB calls wrapped in try/except raising 503 on failure

### Key backend conventions

- **Supabase pagination**: all full-table fetches use `range(offset, offset + PAGE_SIZE - 1)` in a while loop — see `_fetch_all()` in campaign_model.py
- **Upsert batching**: writes use `BATCH_SIZE = 500` batches
- **NaN → None**: CSV nulls become `float('nan')` in pandas; must convert with `math.isnan()` check before Pydantic validation
- **lifetimes library conventions**: `frequency` = total sessions − 1 (min 0); `recency` must be 0 when `frequency == 0`; use `conditional_expected_number_of_purchases_up_to_time()` for per-player scoring (not the simpler scalar version); BG/NBD log-likelihood is `-bgf._negative_log_likelihood_`
- **Segment assignment**: `pd.cut` on p40/p80 quantiles → low_ltv / mid_ltv / high_ltv; `cohort` column is dropped before writing to `ltv_scores` (not in schema)

### Frontend structure

- `lib/api.ts` — all typed fetch functions; reads `NEXT_PUBLIC_API_URL` env var
- `app/page.tsx` — server component; fetches `/segments` + `/players` at build/request time
- `app/players/PlayersClient.tsx` — client component; handles segment filter, pagination, CSV export
- `app/campaigns/page.tsx` — server component; fetches `/campaigns`
- `components/SegmentDonut.tsx`, `components/RoasChart.tsx` — Chart.js wrappers, must be `"use client"`

### Database schema (Supabase)

Three tables, migrations in `backend/db/migrations/`:
- `players` — RFM aggregates; PK `player_id`
- `ltv_scores` — model output; PK `player_id` FK→players; includes `segment`, `expected_ltv_90d`, `churn_probability`
- `campaign_results` — ROI results; PK `campaign_id`

All tables have RLS enabled. The backend requires the **service_role key** (not anon key).

## Environment variables

Backend (`backend/.env`):
```
SUPABASE_URL=
SUPABASE_KEY=    # must be service_role key
```

Frontend (`frontend/.env.local`):
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## CI

`.github/workflows/backend-tests.yml` runs on push/PR to `main` when `backend/` changes: installs deps, runs `ruff check .`, then `pytest`. Uses placeholder Supabase credentials (tests don't hit the DB).
