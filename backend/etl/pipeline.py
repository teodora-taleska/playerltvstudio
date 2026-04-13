"""
ETL pipeline: player_events.csv -> RFM aggregation -> Supabase.

Steps
-----
1. load_events      – read CSV from disk
2. validate_events  – row-level Pydantic validation; invalid rows are dropped
3. aggregate_rfm    – collapse to one RFM row per player
4. aggregate_sessions – collapse to one metrics row per session
5. write_to_supabase – upsert both tables in batches
6. run_pipeline     – orchestrates 1-5, returns a summary dict

Usage
-----
    python -m etl.pipeline                  # reads .env for Supabase creds
    python -m etl.pipeline --dry-run        # skips Supabase write
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from pydantic import ValidationError

from etl.schemas import PlayerEvent

load_dotenv()

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent.parent / "data" / "raw" / "player_events.csv"
SUPABASE_BATCH_SIZE = 500


# Step 1 – load



def load_events(path: Path = DATA_PATH) -> pd.DataFrame:
    """Read the raw event CSV. Returns a DataFrame with typed columns."""
    df = pd.read_csv(path, parse_dates=["event_time"])
    df["install_date"] = pd.to_datetime(df["install_date"]).dt.date
    logger.info("Loaded %d rows from %s", len(df), path)
    return df



# Step 2 – validate



def validate_events(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Validate every row against PlayerEvent.

    Invalid rows are dropped and counted. The first 10 distinct error
    messages are logged as warnings to avoid flooding the log.

    Returns
    -------
    valid_df : DataFrame containing only valid rows
    error_count : total number of rows that failed validation
    """
    valid_records: list[dict] = []
    error_count = 0
    logged_errors = 0

    for record in df.to_dict("records"):
        # pandas encodes missing values as float('nan'); Pydantic rejects NaN
        # as non-finite and treats it as a non-null value. Normalise to None.
        clean = {
            k: (None if isinstance(v, float) and math.isnan(v) else v)
            for k, v in record.items()
        }
        try:
            event = PlayerEvent.model_validate(clean)
            valid_records.append(event.model_dump())
        except ValidationError as exc:
            error_count += 1
            if logged_errors < 10:
                msg = exc.errors()[0]["msg"]
                logger.warning("Validation error (row %d): %s", error_count, msg)
                logged_errors += 1

    if error_count > 10:
        logger.warning("... and %d more validation errors", error_count - 10)

    valid_df = pd.DataFrame(valid_records) if valid_records else pd.DataFrame()
    logger.info(
        "Validation complete: %d valid rows, %d errors", len(valid_df), error_count
    )
    return valid_df, error_count



# Step 3 – aggregate RFM



def aggregate_rfm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate event rows to one RFM record per player.

    recency_days  – days from last_seen to the latest event_time in the dataset
    frequency     – number of distinct sessions (counted via session_start events)
    monetary      – sum of amount_usd across all purchase events
    """
    reference_date: pd.Timestamp = df["event_time"].max()

    # frequency = unique sessions per player (use session_start to avoid
    # double-counting sessions that span midnight)
    session_counts = (
        df[df["event_type"] == "session_start"]
        .groupby("player_id")["session_id"]
        .nunique()
        .rename("frequency")
    )

    rfm = (
        df.groupby("player_id")
        .agg(
            cohort=("cohort", "first"),
            install_date=("install_date", "first"),
            first_seen=("event_time", "min"),
            last_seen=("event_time", "max"),
            monetary=("amount_usd", "sum"),
        )
        .join(session_counts)
        .reset_index()
    )

    rfm["recency_days"] = (reference_date - rfm["last_seen"]).dt.days
    rfm["monetary"] = rfm["monetary"].fillna(0.0).round(2)
    rfm["frequency"] = rfm["frequency"].fillna(0).astype(int)

    logger.info("RFM aggregated for %d players", len(rfm))
    return rfm



# Step 4 – aggregate sessions



def aggregate_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate event rows to one metrics record per session.

    Columns: session_id, player_id, cohort, session_start,
             days_since_install, levels_completed, ads_watched, revenue
    """
    session_meta = (
        df[df["event_type"] == "session_start"][
            ["session_id", "player_id", "cohort", "event_time", "days_since_install"]
        ]
        .drop_duplicates(subset=["session_id"])
        .rename(columns={"event_time": "session_start"})
    )

    metrics = (
        df.groupby("session_id")
        .agg(
            levels_completed=("event_type", lambda s: (s == "level_complete").sum()),
            ads_watched=("event_type", lambda s: (s == "ad_watched").sum()),
            revenue=("amount_usd", "sum"),
        )
        .reset_index()
    )
    metrics["revenue"] = pd.to_numeric(metrics["revenue"], errors="coerce").fillna(0.0).round(2)

    sessions = session_meta.merge(metrics, on="session_id", how="left")
    logger.info("Aggregated %d sessions", len(sessions))
    return sessions



# Step 5 – write to Supabase



def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-safe dicts (handles date/datetime columns)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _upsert_batched(client, table: str, records: list[dict]) -> int:
    """Upsert records into a Supabase table in batches. Returns rows written."""
    written = 0
    for i in range(0, len(records), SUPABASE_BATCH_SIZE):
        batch = records[i : i + SUPABASE_BATCH_SIZE]
        client.table(table).upsert(batch).execute()
        written += len(batch)
    return written


def write_to_supabase(client, players_df: pd.DataFrame, sessions_df: pd.DataFrame) -> None:
    """Upsert players and sessions tables."""
    n = _upsert_batched(client, "players", _df_to_records(players_df))
    logger.info("Wrote %d rows to 'players'", n)

    n = _upsert_batched(client, "sessions", _df_to_records(sessions_df))
    logger.info("Wrote %d rows to 'sessions'", n)



# Step 6 – orchestrate



def run_pipeline(
    path: Path = DATA_PATH,
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Run the full ETL pipeline.

    Parameters
    ----------
    path         : path to player_events.csv
    supabase_url : overrides SUPABASE_URL env var
    supabase_key : overrides SUPABASE_KEY env var
    dry_run      : if True, skips the Supabase write step

    Returns
    -------
    Summary dict: rows_processed, validation_errors, players, sessions
    """
    url = supabase_url or os.getenv("SUPABASE_URL")
    key = supabase_key or os.getenv("SUPABASE_KEY")

    raw_df = load_events(path)
    valid_df, error_count = validate_events(raw_df)

    if valid_df.empty:
        logger.error("No valid rows after validation — aborting pipeline")
        return {"rows_processed": 0, "validation_errors": error_count, "players": 0, "sessions": 0}

    rfm_df = aggregate_rfm(valid_df)
    sessions_df = aggregate_sessions(valid_df)

    if dry_run:
        logger.info("Dry run — skipping Supabase write")
    elif url and key:
        from supabase import create_client  # imported here so tests don't need it

        client = create_client(url, key)
        write_to_supabase(client, rfm_df, sessions_df)
    else:
        logger.warning("SUPABASE_URL/KEY not set — skipping write (set them in .env)")

    summary = {
        "rows_processed": len(valid_df),
        "validation_errors": error_count,
        "players": len(rfm_df),
        "sessions": len(sessions_df),
    }
    logger.info("Pipeline complete: %s", summary)
    return summary



# CLI entry point


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(description="Run GemBlast ETL pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Skip Supabase write")
    parser.add_argument("--data", type=Path, default=DATA_PATH, help="Path to CSV")
    args = parser.parse_args()

    result = run_pipeline(path=args.data, dry_run=args.dry_run)
    print(result)
