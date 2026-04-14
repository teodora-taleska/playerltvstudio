# GemBlast LTV Studio

A player **Lifetime Value (LTV)** prediction and campaign ROI platform for a fictional mobile match-3 game. It ingests raw game events, fits statistical models to predict how much each player will spend over 90 days, segments players by value tier, and evaluates marketing campaign performance against those predictions.

---

## What it does

| Layer | What happens |
|---|---|
| **ETL** | Reads `player_events.csv`, validates with Pydantic, aggregates per-player RFM metrics, writes to Supabase |
| **LTV Model** | Fits BG/NBD + Gamma-Gamma on RFM data, scores every player with 90-day LTV, churn probability, and predicted sessions |
| **Campaign Model** | Simulates 3 marketing campaigns with different targeting strategies, computes ROAS and payback period |
| **API** | FastAPI app exposing players, segments, campaigns, and a pipeline trigger endpoint |
| **Frontend** | Next.js 14 dashboard with segment donut chart, player table (filterable + CSV export), and campaign ROAS chart |

---

## The BG/NBD model — plain English

Most mobile game players are free-to-play and will eventually stop playing ("churn"). The hard problem is: **for each player alive today, how many sessions will they have in the next 90 days — and will they still be around?**

**BG/NBD** (Beta-Geometric / Negative Binomial Distribution) solves this with two ideas:

1. **While a player is active**, they generate sessions at a random rate that varies across players (modelled by a Gamma distribution).
2. **After each session**, a player has some probability of churning permanently (modelled by a Geometric distribution). That churn probability also varies across players (modelled by a Beta distribution).

The model is fitted on three numbers per player — **frequency** (repeat sessions), **recency** (days between first and last session), and **T** (days since first session) — and learns the population-level shape parameters from those three numbers alone.

**Gamma-Gamma** then layers on top: given that a player is active, what is their average revenue per session? Combined, the two models give an expected revenue figure discounted over a 3-month window — that is `expected_ltv_90d`.

---

## Project structure

```
playerltvstudio/
  backend/
    data/
      generate_events.py     # synthetic data generator (5 000 players, 180 days)
      raw/player_events.csv  # generated CSV (not committed)
    etl/
      pipeline.py            # ETL: validate -> RFM -> Supabase
      schemas.py             # Pydantic event + record models
    models/
      ltv_model.py           # BG/NBD + Gamma-Gamma scoring
      campaign_model.py      # Campaign ROI simulation + plot
    api/
      main.py                # FastAPI application
    db/migrations/           # SQL migrations (run in Supabase SQL Editor)
    tests/                   # pytest suite
    pyproject.toml
    Procfile                 # Railway deployment
  frontend/
    app/                     # Next.js 14 App Router pages
    components/              # Shared UI components
    lib/api.ts               # Typed API client
```

---

## Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- A [Supabase](https://supabase.com) project (free tier works)

### 1 — Supabase migrations

Open the Supabase SQL Editor and run these files in order:

```
backend/db/migrations/001_create_tables.sql
backend/db/migrations/002_create_ltv_scores.sql
backend/db/migrations/003_create_campaign_results.sql
```

### 2 — Backend

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env          # fill in SUPABASE_URL and SUPABASE_KEY (service_role key)
```

Generate synthetic data and run the full pipeline:

```bash
python data/generate_events.py          # creates data/raw/player_events.csv
python -m etl.pipeline                  # ETL -> Supabase
python -m models.ltv_model              # LTV scoring -> ltv_scores table
python -m models.campaign_model         # Campaign ROI -> campaign_results table
```

Start the API:

```bash
uvicorn api.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

### 3 — Frontend

```bash
cd frontend
npm install
cp .env.example .env.local              # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                             # http://localhost:3000
```

### 4 — Run tests

```bash
cd backend
pytest
```

---

## Deployment

- **Backend**: deploy to [Railway](https://railway.app) — the `Procfile` is already configured.
- **Frontend**: deploy to [Vercel](https://vercel.com) — set `NEXT_PUBLIC_API_URL` to your Railway backend URL in the Vercel project settings.

---

## Live demo

> Vercel URL when deployed.

---

## Tech stack

| | |
|---|---|
| Language | Python 3.9+, TypeScript |
| LTV models | [lifetimes](https://github.com/CamDavidsonPilon/lifetimes) (BG/NBD + Gamma-Gamma) |
| Backend | FastAPI, Supabase (PostgreSQL), pandas |
| Frontend | Next.js 14, Tailwind CSS, Chart.js |
| CI | GitHub Actions |
| Deployment | Railway (API) + Vercel (frontend) |
