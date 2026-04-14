"""
GemBlast LTV Studio — FastAPI application.

Endpoints
---------
GET  /health               liveness check
GET  /players              paginated players with LTV scores
GET  /segments             count + avg LTV per segment
GET  /campaigns            all campaign ROI results
POST /run-models           trigger ETL → LTV model → campaign model in sequence
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# ---------------------------------------------------------------------------
# Supabase client — created once at startup, shared across requests
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        logger.warning("SUPABASE_URL / SUPABASE_KEY not set — DB calls will fail")
    app.state.supabase = create_client(url, key) if url and key else None
    yield


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GemBlast LTV Studio",
    description="Player Lifetime Value prediction and campaign ROI API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_db(request: Request) -> Client:
    db = request.app.state.supabase
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    return db


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PlayerLTV(BaseModel):
    player_id: str
    cohort: str
    install_date: str
    frequency: int
    monetary: float
    segment: str
    expected_ltv_90d: float
    predicted_purchases_30d: float
    predicted_purchases_90d: float
    churn_probability: float
    scored_at: str


class PlayerPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PlayerLTV]


class SegmentSummary(BaseModel):
    segment: str
    count: int
    avg_ltv_90d: float
    total_ltv_90d: float
    pct_of_players: float


class CampaignResult(BaseModel):
    campaign_id: str
    campaign_name: str
    start_date: str
    spend: float
    n_players: int
    avg_ltv_acquired: float
    total_predicted_revenue_90d: float
    roas: float
    payback_period_days: Optional[float]
    is_profitable: bool


class PipelineStatus(BaseModel):
    status: str       # "started" | "running" | "idle"
    last_run: Optional[str]
    last_result: Optional[str]


# ---------------------------------------------------------------------------
# Background pipeline state
# ---------------------------------------------------------------------------

_pipeline: dict = {"running": False, "last_run": None, "last_result": None}


def _run_pipeline_sequence() -> None:
    """Run ETL → LTV model → campaign model. Called in a background task."""
    from etl.pipeline import run_pipeline
    from models.campaign_model import run_campaign_model
    from models.ltv_model import run_model

    _pipeline["running"] = True
    _pipeline["last_run"] = datetime.now(timezone.utc).isoformat()
    try:
        logger.info("Pipeline started")
        etl_summary = run_pipeline()
        logger.info("ETL done: %s", etl_summary)

        run_model()
        logger.info("LTV model done")

        run_campaign_model()
        logger.info("Campaign model done")

        _pipeline["last_result"] = "success"
        logger.info("Pipeline completed successfully")
    except Exception as exc:
        _pipeline["last_result"] = f"error: {exc}"
        logger.exception("Pipeline failed")
    finally:
        _pipeline["running"] = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _db_error(exc: Exception, context: str) -> HTTPException:
    """Convert a Supabase / network exception into a structured 503 response."""
    logger.error("%s failed: %s", context, exc)
    return HTTPException(
        status_code=503,
        detail=f"Database error in {context}: {exc}",
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/players", response_model=PlayerPage)
def get_players(
    segment: Optional[str] = Query(default=None, description="high_ltv | mid_ltv | low_ltv"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Client = Depends(get_db),
):
    """
    Return paginated players joined with their LTV scores.
    Ordered by expected_ltv_90d descending.
    """
    if segment and segment not in ("high_ltv", "mid_ltv", "low_ltv"):
        raise HTTPException(
            status_code=422, detail="segment must be high_ltv, mid_ltv, or low_ltv"
        )

    try:
        # Count total (for pagination metadata)
        count_query = db.table("ltv_scores").select("player_id", count="exact")
        if segment:
            count_query = count_query.eq("segment", segment)
        total = count_query.execute().count or 0

        # Fetch LTV scores page
        ltv_query = (
            db.table("ltv_scores")
            .select("*")
            .order("expected_ltv_90d", desc=True)
            .range(offset, offset + limit - 1)
        )
        if segment:
            ltv_query = ltv_query.eq("segment", segment)
        ltv_rows = ltv_query.execute().data
    except Exception as exc:
        raise _db_error(exc, "GET /players") from exc

    if not ltv_rows:
        return PlayerPage(total=total, limit=limit, offset=offset, items=[])

    try:
        player_ids = [r["player_id"] for r in ltv_rows]
        player_rows = (
            db.table("players")
            .select("player_id, cohort, install_date, frequency, monetary")
            .in_("player_id", player_ids)
            .execute()
            .data
        )
    except Exception as exc:
        raise _db_error(exc, "GET /players (player metadata)") from exc

    players_by_id = {p["player_id"]: p for p in player_rows}

    items = []
    for ltv in ltv_rows:
        p = players_by_id.get(ltv["player_id"], {})
        items.append(PlayerLTV(
            player_id=ltv["player_id"],
            cohort=p.get("cohort", ""),
            install_date=str(p.get("install_date", "")),
            frequency=int(p.get("frequency", 0)),
            monetary=float(p.get("monetary") or 0),
            segment=ltv["segment"],
            expected_ltv_90d=float(ltv["expected_ltv_90d"] or 0),
            predicted_purchases_30d=float(ltv["predicted_purchases_30d"] or 0),
            predicted_purchases_90d=float(ltv["predicted_purchases_90d"] or 0),
            churn_probability=float(ltv["churn_probability"] or 0),
            scored_at=str(ltv.get("scored_at", "")),
        ))

    return PlayerPage(total=total, limit=limit, offset=offset, items=items)


@app.get("/segments", response_model=list[SegmentSummary])
def get_segments(db: Client = Depends(get_db)):
    """
    Aggregate count and average LTV per segment.
    Returns all three segments in fixed order: high -> mid -> low.
    """
    try:
        rows = (
            db.table("ltv_scores")
            .select("segment, expected_ltv_90d")
            .execute()
            .data
        )
    except Exception as exc:
        raise _db_error(exc, "GET /segments") from exc

    if not rows:
        return []

    df = pd.DataFrame(rows)
    df["expected_ltv_90d"] = pd.to_numeric(df["expected_ltv_90d"])
    total_players = len(df)

    result = []
    for seg in ("high_ltv", "mid_ltv", "low_ltv"):
        subset = df[df["segment"] == seg]
        n = len(subset)
        result.append(SegmentSummary(
            segment=seg,
            count=n,
            avg_ltv_90d=round(float(subset["expected_ltv_90d"].mean()), 2) if n else 0.0,
            total_ltv_90d=round(float(subset["expected_ltv_90d"].sum()), 2),
            pct_of_players=round(n / total_players * 100, 1) if total_players else 0.0,
        ))
    return result


@app.get("/campaigns", response_model=list[CampaignResult])
def get_campaigns(db: Client = Depends(get_db)):
    """Return all campaign ROI results ordered by ROAS descending."""
    try:
        rows = (
            db.table("campaign_results")
            .select("*")
            .order("roas", desc=True)
            .execute()
            .data
        )
    except Exception as exc:
        raise _db_error(exc, "GET /campaigns") from exc

    results = []
    for r in rows:
        results.append(CampaignResult(
            campaign_id=r["campaign_id"],
            campaign_name=r["campaign_name"],
            start_date=str(r["start_date"]),
            spend=float(r["spend"]),
            n_players=int(r["n_players"]),
            avg_ltv_acquired=float(r["avg_ltv_acquired"]),
            total_predicted_revenue_90d=float(r["total_predicted_revenue_90d"]),
            roas=float(r["roas"]),
            payback_period_days=(
                float(r["payback_period_days"]) if r["payback_period_days"] else None
            ),
            is_profitable=bool(r["is_profitable"]),
        ))
    return results


@app.post("/run-models", response_model=PipelineStatus)
async def run_models(background_tasks: BackgroundTasks):
    """
    Trigger the full pipeline in the background:
        1. ETL  (player_events.csv → Supabase players + sessions)
        2. LTV model  (players → ltv_scores)
        3. Campaign model  (ltv_scores → campaign_results + plot)

    Returns immediately. Check logs for progress.
    """
    if _pipeline["running"]:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    background_tasks.add_task(_run_pipeline_sequence)
    return PipelineStatus(
        status="started",
        last_run=_pipeline["last_run"],
        last_result=_pipeline["last_result"],
    )


@app.get("/run-models/status", response_model=PipelineStatus)
def run_models_status():
    """Check whether the pipeline is currently running."""
    return PipelineStatus(
        status="running" if _pipeline["running"] else "idle",
        last_run=_pipeline["last_run"],
        last_result=_pipeline["last_result"],
    )
