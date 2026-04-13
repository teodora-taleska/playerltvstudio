"""
LTV model: BG/NBD + Gamma-Gamma

BG/NBD     — models when a player will churn (stop playing)
Gamma-Gamma — models expected revenue per session

Sessions are used as the "transaction" unit because most players are f2p with
zero purchases. A small ad-revenue floor is imputed for non-paying players so
the Gamma-Gamma model produces meaningful (if conservative) LTV estimates.

Supabase tables
---------------
  Input  : players    (RFM aggregates written by the ETL pipeline)
  Output : ltv_scores (upserted on every run)

Output columns
--------------
  player_id, predicted_purchases_30d, predicted_purchases_90d,
  churn_probability, expected_ltv_90d, segment, scored_at

Segments (by expected_ltv_90d percentile)
------------------------------------------
  high_ltv  — top 20 %
  mid_ltv   — next 40 %   (60th–80th percentile)
  low_ltv   — bottom 40 %

Run
---
    python -m models.ltv_model
    python -m models.ltv_model --dry-run
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from lifetimes import BetaGeoFitter, GammaGammaFitter

load_dotenv()

logger = logging.getLogger(__name__)

# Ad-revenue floor used as monetary_value for non-paying players ($USD / session).
# A conservative estimate for casual match-3 games.
AD_REVENUE_PER_SESSION: float = 0.005

PAGE_SIZE = 1_000          # Supabase pagination
BATCH_SIZE = 500           # upsert batch size
BGNBD_PENALIZER = 0.01
GAMMA_PENALIZER = 0.01

# ---------------------------------------------------------------------------
# Step 1 – fetch RFM from Supabase
# ---------------------------------------------------------------------------


def fetch_rfm(client) -> pd.DataFrame:
    """
    Pull all rows from the `players` table, handling Supabase pagination.
    Returns a DataFrame with columns as written by the ETL pipeline.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        resp = (
            client.table("players")
            .select("*")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    df = pd.DataFrame(rows)
    df["first_seen"] = pd.to_datetime(df["first_seen"])
    df["last_seen"] = pd.to_datetime(df["last_seen"])
    logger.info("Fetched %d players from Supabase", len(df))
    return df


# ---------------------------------------------------------------------------
# Step 2 – build lifetimes model inputs
# ---------------------------------------------------------------------------


def build_model_inputs(rfm: pd.DataFrame) -> pd.DataFrame:
    """
    Transform RFM data into the format expected by the lifetimes library.

    lifetimes conventions
    ---------------------
    frequency      = repeat transactions (total sessions - 1), min 0
    recency        = days between a player's first and last session
    T              = days from first session to the dataset reference date (≥ 1)
    monetary_value = average revenue per session; floored at AD_REVENUE_PER_SESSION
                     so non-paying players still receive a meaningful LTV estimate
    """
    df = rfm.copy()
    df["first_seen"] = pd.to_datetime(df["first_seen"])
    df["last_seen"] = pd.to_datetime(df["last_seen"])

    reference_date: pd.Timestamp = df["last_seen"].max()

    total_sessions = df["frequency"].clip(lower=1)

    df["frequency"] = (df["frequency"] - 1).clip(lower=0).astype(int)
    df["recency"] = (df["last_seen"] - df["first_seen"]).dt.days.clip(lower=0)
    # lifetimes requires recency == 0 for single-session players (frequency == 0):
    # with no repeat transactions there is no "time between first and last session".
    df.loc[df["frequency"] == 0, "recency"] = 0
    df["T"] = (reference_date - df["first_seen"]).dt.days.clip(lower=1)
    df["monetary_value"] = (
        (df["monetary"] / total_sessions)
        .clip(lower=AD_REVENUE_PER_SESSION)
    )

    return df[["player_id", "cohort", "frequency", "recency", "T", "monetary_value", "monetary"]]


# ---------------------------------------------------------------------------
# Step 3 – fit models
# ---------------------------------------------------------------------------


def fit_bgnbd(df: pd.DataFrame, penalizer_coef: float = BGNBD_PENALIZER) -> BetaGeoFitter:
    """
    Fit a BG/NBD model to predict future session counts and churn probability.
    All players are used regardless of frequency.
    """
    bgf = BetaGeoFitter(penalizer_coef=penalizer_coef)
    bgf.fit(df["frequency"], df["recency"], df["T"])
    logger.info(
        "BG/NBD fitted — log-likelihood: %.4f  params: %s",
        -bgf._negative_log_likelihood_,
        dict(bgf.params_),
    )
    return bgf


def fit_gamma_gamma(df: pd.DataFrame, penalizer_coef: float = GAMMA_PENALIZER) -> GammaGammaFitter:
    """
    Fit a Gamma-Gamma model to predict average revenue per session.
    Only players with repeat sessions (frequency > 0) are used for fitting;
    the model is applied to all players during scoring.
    """
    mask = df["frequency"] > 0
    n_fit = mask.sum()
    if n_fit < 10:
        logger.warning(
            "Only %d customers with repeat transactions — Gamma-Gamma fit may be unstable", n_fit
        )
    ggf = GammaGammaFitter(penalizer_coef=penalizer_coef)
    ggf.fit(df.loc[mask, "frequency"], df.loc[mask, "monetary_value"])
    logger.info(
        "Gamma-Gamma fitted on %d customers — params: %s",
        n_fit,
        dict(ggf.params_),
    )
    return ggf


# ---------------------------------------------------------------------------
# Step 4 – score players
# ---------------------------------------------------------------------------


def score_players(
    df: pd.DataFrame,
    bgf: BetaGeoFitter,
    ggf: GammaGammaFitter,
) -> pd.DataFrame:
    """
    Compute per-player LTV metrics using the fitted models.

    predicted_purchases_30d / _90d
        Expected number of sessions in the next 30 / 90 days given the
        player's observed history (BG/NBD conditional expectation).

    churn_probability
        1 − P(player is still active), derived from the BG/NBD model.

    expected_ltv_90d
        Discounted expected revenue over the next 3 months (≈ 90 days),
        computed by combining BG/NBD session predictions with the
        Gamma-Gamma revenue-per-session estimate (1 % monthly discount).
    """
    scores = df[["player_id", "cohort"]].copy()

    scores["predicted_purchases_30d"] = (
        bgf.conditional_expected_number_of_purchases_up_to_time(
            t=30,
            frequency=df["frequency"],
            recency=df["recency"],
            T=df["T"],
        )
        .clip(lower=0)
        .round(4)
    )

    scores["predicted_purchases_90d"] = (
        bgf.conditional_expected_number_of_purchases_up_to_time(
            t=90,
            frequency=df["frequency"],
            recency=df["recency"],
            T=df["T"],
        )
        .clip(lower=0)
        .round(4)
    )

    scores["churn_probability"] = (
        1
        - bgf.conditional_probability_alive(
            frequency=df["frequency"],
            recency=df["recency"],
            T=df["T"],
        )
    ).clip(0, 1).round(4)

    scores["expected_ltv_90d"] = (
        ggf.customer_lifetime_value(
            bgf,
            df["frequency"],
            df["recency"],
            df["T"],
            df["monetary_value"],
            time=3,          # 3 months ≈ 90 days
            discount_rate=0.01,
            freq="D",        # recency and T are in days
        )
        .clip(lower=0)
        .round(2)
    )

    return scores


# ---------------------------------------------------------------------------
# Step 5 – assign segments
# ---------------------------------------------------------------------------


def assign_segments(scores: pd.DataFrame) -> pd.DataFrame:
    """
    Bucket each player into a spend segment by expected_ltv_90d percentile.

        high_ltv  — top 20 %   (above 80th percentile)
        mid_ltv   — next 40 %  (40th–80th percentile)
        low_ltv   — bottom 40% (below 40th percentile)
    """
    df = scores.copy()
    p40 = df["expected_ltv_90d"].quantile(0.40)
    p80 = df["expected_ltv_90d"].quantile(0.80)

    df["segment"] = pd.cut(
        df["expected_ltv_90d"],
        bins=[float("-inf"), p40, p80, float("inf")],
        labels=["low_ltv", "mid_ltv", "high_ltv"],
    ).astype(str)

    return df


# ---------------------------------------------------------------------------
# Step 6 – diagnostics
# ---------------------------------------------------------------------------


def model_diagnostics(
    bgf: BetaGeoFitter,
    ggf: GammaGammaFitter,
    scores: pd.DataFrame,
) -> None:
    """Log model fit statistics and score distribution summaries."""
    sep = "-" * 50
    logger.info(sep)
    logger.info("BG/NBD parameters : %s", dict(bgf.params_))
    logger.info("BG/NBD log-likelihood : %.4f", -bgf._negative_log_likelihood_)
    logger.info("Gamma-Gamma parameters : %s", dict(ggf.params_))
    logger.info("Gamma-Gamma summary:\n%s", ggf.summary.to_string())
    logger.info(sep)

    for col, label in [
        ("churn_probability",       "Churn probability"),
        ("predicted_purchases_30d", "Predicted sessions 30d"),
        ("predicted_purchases_90d", "Predicted sessions 90d"),
        ("expected_ltv_90d",        "Expected LTV 90d ($)"),
    ]:
        s = scores[col]
        logger.info(
            "%s — mean=%.4f  median=%.4f  p95=%.4f  max=%.4f",
            label,
            s.mean(),
            s.median(),
            s.quantile(0.95),
            s.max(),
        )

    logger.info("Segment distribution:\n%s", scores["segment"].value_counts().to_string())
    logger.info(sep)


# ---------------------------------------------------------------------------
# Step 7 – write to Supabase
# ---------------------------------------------------------------------------


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _upsert_batched(client, table: str, records: list[dict]) -> int:
    written = 0
    for i in range(0, len(records), BATCH_SIZE):
        client.table(table).upsert(records[i : i + BATCH_SIZE]).execute()
        written += len(records[i : i + BATCH_SIZE])
    return written


def write_ltv_scores(client, scores: pd.DataFrame) -> None:
    # cohort lives in the players table — drop it to match ltv_scores schema
    cols = [c for c in scores.columns if c != "cohort"]
    n = _upsert_batched(client, "ltv_scores", _df_to_records(scores[cols]))
    logger.info("Wrote %d rows to 'ltv_scores'", n)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_model(
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    """
    Full LTV scoring pipeline.

    Parameters
    ----------
    supabase_url : overrides SUPABASE_URL env var
    supabase_key : overrides SUPABASE_KEY env var
    dry_run      : if True, skips the Supabase write step
    """
    from supabase import create_client

    url = supabase_url or os.getenv("SUPABASE_URL")
    key = supabase_key or os.getenv("SUPABASE_KEY")
    client = create_client(url, key)

    rfm = fetch_rfm(client)
    df = build_model_inputs(rfm)

    bgf = fit_bgnbd(df)
    ggf = fit_gamma_gamma(df)

    scores = score_players(df, bgf, ggf)
    scores = assign_segments(scores)
    scores["scored_at"] = datetime.now(timezone.utc).isoformat()

    model_diagnostics(bgf, ggf, scores)

    if dry_run:
        logger.info("Dry run — skipping Supabase write")
    else:
        write_ltv_scores(client, scores)

    return scores


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(description="Run GemBlast LTV scoring")
    parser.add_argument("--dry-run", action="store_true", help="Skip Supabase write")
    args = parser.parse_args()

    result = run_model(dry_run=args.dry_run)
    print(f"Scored {len(result)} players.")
