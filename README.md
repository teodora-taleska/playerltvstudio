# GemBlast LTV Studio

> **Built for learning.** This project was created in 3 days as a hands-on exploration of several things at once: using Claude Code as an AI pair programmer (reviewing every decision as it was made), building a full-stack application from scratch, and applying machine learning techniques — specifically statistical LTV models used in marketing analytics — inside a real product. As a data scientist, I wanted to bridge the gap between knowing the theory and shipping something end-to-end: a Python ML backend, a REST API, a production frontend, CI/CD, and cloud deployment. Everything here was built with that goal in mind.
>
> **Live demo:** https://playerltvstudio.vercel.app

---

## What is GemBlast LTV Studio?

A **Player Lifetime Value (LTV) prediction and campaign ROI platform** for a fictional mobile match-3 game called GemBlast. It answers the questions every mobile game studio cares about:

- Which players are worth spending money to retain?
- How much revenue will each player generate over the next 90 days?
- Which marketing campaigns are actually profitable?

The platform ingests raw game events, fits statistical models to predict player value, segments the player base by spend tier, and evaluates marketing campaign performance against those predictions — all visualised in a clean analytics dashboard.

---

## What you can see and do

### Overview page (`/`)
The landing page gives you a **snapshot of the entire player base at a glance**:
- **4 KPI cards** — average LTV per player, average churn probability, number of high-value players, and total predicted 90-day revenue across all players
- **Segment donut chart** — visual breakdown of players into High / Mid / Low LTV tiers with their share of the population
- **Segment breakdown table** — count, average LTV, total LTV, and population share per segment

Use this page to monitor the overall health of your player base and track how the model scores change over time as new data comes in.

### Players page (`/players`)
A **full paginated table of every scored player**, ordered by expected LTV descending:
- Filter by segment (All / High LTV / Mid LTV / Low LTV) using the buttons at the top
- Each row shows: player ID, segment badge, 90-day LTV, churn probability (colour-coded red/amber/green), predicted sessions in 30 and 90 days, total historical spend, and install date
- **Export to CSV** button downloads the current filtered view — ready to upload into a CRM, ad platform, or retention tool

Use this page to build targeted player lists — e.g. export all High LTV players with churn probability > 60% for a winback campaign, or all Mid LTV players for an upsell push.

### Campaigns page (`/campaigns`)
A **campaign ROI analyser** comparing three synthetic marketing strategies:
- **ROAS bar chart** — Return on Ad Spend per campaign with a break-even reference line at 1.0x
- **3 summary KPIs** — total spend, total predicted revenue, best ROAS across all campaigns
- **Detail table** — spend, players acquired, average LTV of acquired players, predicted 90-day revenue, ROAS, payback period in days, and a Profitable / Unprofitable badge per campaign

Use this page to understand which acquisition strategy delivers the best return given your player LTV distribution. The three campaigns (broad acquisition, whales-only lookalike, lapsed-player retargeting) represent real strategies used in mobile UA.

---

## How to navigate

The left sidebar is always visible with three icons:
- **Overview** — big picture KPIs and segment chart
- **Players** — individual player scores and export
- **Campaigns** — campaign ROI comparison

There is no login — this is an internal analytics tool designed for a single team.

---

## How the models work

### BG/NBD — plain English

Most mobile players are free-to-play and will eventually quit. The hard problem is: for each player alive today, how many sessions will they have in the next 90 days?

**BG/NBD** (Beta-Geometric / Negative Binomial Distribution) solves this with two ideas:
1. While active, players generate sessions at a random rate that varies across the population (modelled by a Gamma distribution)
2. After each session, a player has some probability of churning permanently (modelled by a Geometric distribution) — and that churn probability also varies (modelled by a Beta distribution)

The model is fitted on just three numbers per player: **frequency** (repeat sessions), **recency** (days between first and last session), and **T** (days since first session). From those it learns the population-level shape parameters and can predict future activity for every individual.

**Gamma-Gamma** then layers on top: given that a player is still active, what is their average revenue per session? Combined with BG/NBD, this gives a discounted expected revenue figure over a 3-month window — `expected_ltv_90d`.

---

## Project structure

```
playerltvstudio/
  backend/
    data/
      generate_events.py     # synthetic data generator (5 000 players, 180 days)
      raw/player_events.csv  # generated CSV (gitignored)
    etl/
      pipeline.py            # ETL: validate -> RFM aggregation -> Supabase
      schemas.py             # Pydantic event + record models
    models/
      ltv_model.py           # BG/NBD + Gamma-Gamma scoring
      campaign_model.py      # Campaign ROI simulation + comparison plot
    api/
      main.py                # FastAPI application (6 endpoints)
    db/migrations/           # SQL migrations (run in Supabase SQL Editor)
    tests/                   # 67 pytest tests
    pyproject.toml
    requirements.txt
    Procfile                 # Railway deployment
  frontend/
    app/                     # Next.js 14 App Router pages
    components/              # Sidebar, KpiCard, SegmentDonut, RoasChart, badges
    lib/api.ts               # Typed API client
  .github/workflows/         # GitHub Actions CI (pytest + ruff on push)
  railpack.toml              # Railway build config
```

---

## Setup

### Prerequisites
- Python 3.9+, Node.js 18+
- A [Supabase](https://supabase.com) project (free tier works)

### 1 — Supabase migrations

Run these in the Supabase SQL Editor in order:

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

python data/generate_events.py          # creates data/raw/player_events.csv
python -m etl.pipeline                  # ETL -> Supabase
python -m models.ltv_model              # LTV scoring -> ltv_scores table
python -m models.campaign_model         # Campaign ROI -> campaign_results table

uvicorn api.main:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`.

### 3 — Frontend

```bash
cd frontend
npm install
cp .env.example .env.local              # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                             # http://localhost:3000
```

### 4 — Tests

```bash
cd backend && pytest
```

---

## Deployment

- **Backend** → [Railway](https://railway.app): connect GitHub repo, set root directory to `backend`, add `SUPABASE_URL` + `SUPABASE_KEY` env vars. The `Procfile` and `railpack.toml` handle the rest.
- **Frontend** → [Vercel](https://vercel.com): connect GitHub repo, set root directory to `frontend`, add `NEXT_PUBLIC_API_URL` pointing to your Railway domain.

---

## How to extend this or turn it into a product

This project is a solid foundation. Here is what you would build next depending on the direction:

**As a real game studio tool:**
- Replace the synthetic CSV with a live event stream (Kafka, Segment, or direct DB write)
- Add a `/run-models` scheduler so LTV scores refresh nightly automatically
- Add authentication (Supabase Auth or Clerk) so only team members can access the dashboard
- Add player-level drill-down pages and cohort comparison views

**As a SaaS product:**
- Add multi-tenancy — one Supabase project per game studio, isolated data
- Build an SDK or webhook integration so studios can pipe their own event data in
- Add a white-label option and custom domain per customer
- Charge per monthly active players scored or per API call

**As a portfolio / consulting piece:**
- The BG/NBD + Gamma-Gamma stack is the industry standard used at companies like Duolingo, Spotify, and King — this demonstrates you understand it end-to-end
- The campaign ROI framework maps directly to UA (user acquisition) team workflows
- Swap the synthetic data for a public dataset (e.g. CDNOW, UCI retail) to make it fully reproducible

---

## Tech stack

| | |
|---|---|
| Language | Python 3.9+, TypeScript |
| LTV models | [lifetimes](https://github.com/CamDavidsonPilon/lifetimes) (BG/NBD + Gamma-Gamma) |
| Backend | FastAPI, Supabase (PostgreSQL), pandas |
| Frontend | Next.js 14, Tailwind CSS, Chart.js |
| CI | GitHub Actions (pytest + ruff) |
| Deployment | Railway (API) + Vercel (frontend) |