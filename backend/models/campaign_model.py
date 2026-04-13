"""
Campaign ROI model.

Generates three synthetic marketing campaigns with different targeting
strategies, joins each to player LTV scores, and computes ROI metrics.

Campaigns
---------
broad_acquisition  — high volume, random mix, low CAC ($25)
                     Simulates an untargeted Facebook / Google UAC campaign.

whales_only        — low volume, high_ltv segment only, high CAC ($150)
                     Simulates a lookalike audience built from top spenders.

retargeting        — mid volume, churned players with prior spend, low CAC ($8)
                     Simulates a re-engagement push at churned paying users.

Metrics per campaign
--------------------
total_spend                  — ad budget consumed
avg_ltv_acquired             — mean expected_ltv_90d of targeted players
total_predicted_revenue_90d  — sum of expected_ltv_90d across all players
roas                         — total_predicted_revenue_90d / total_spend
payback_period_days          — days to recoup spend at the 90-day revenue rate
is_profitable                — roas >= 1.0

Outputs
-------
Supabase table : campaign_results
Plot           : data/outputs/campaign_comparison.png

Run
---
    python -m models.campaign_model
    python -m models.campaign_model --dry-run
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RANDOM_SEED = 42
BATCH_SIZE = 500
PAGE_SIZE = 1_000

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "outputs"

# ---------------------------------------------------------------------------
# Campaign definitions
# ---------------------------------------------------------------------------

CAMPAIGN_SPECS: list[dict] = [
    {
        "campaign_id":   "camp_broad_001",
        "campaign_name": "broad_acquisition",
        "spend":         50_000.0,
        "n_players":     2_000,
        "start_date":    date(2024, 4, 1),
        "targeting":     "random",
    },
    {
        "campaign_id":   "camp_whales_001",
        "campaign_name": "whales_only",
        "spend":         45_000.0,
        "n_players":     300,
        "start_date":    date(2024, 4, 1),
        "targeting":     "high_ltv",
    },
    {
        "campaign_id":   "camp_retarget_001",
        "campaign_name": "retargeting",
        "spend":         8_000.0,
        "n_players":     1_000,
        "start_date":    date(2024, 4, 15),
        "targeting":     "lapsed_spenders",
    },
]

CAMPAIGN_COLORS = {
    "broad_acquisition": "#4C72B0",
    "whales_only":       "#C44E52",
    "retargeting":       "#55A868",
}

# ---------------------------------------------------------------------------
# Step 1 – fetch data from Supabase
# ---------------------------------------------------------------------------


def _fetch_all(client, table: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        batch = (
            client.table(table)
            .select("*")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
            .data
        )
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def fetch_data(client) -> pd.DataFrame:
    """
    Fetch ltv_scores joined with players.
    The join adds cohort and monetary (needed for lapsed_spenders targeting).
    """
    ltv_df = pd.DataFrame(_fetch_all(client, "ltv_scores"))
    players_df = pd.DataFrame(_fetch_all(client, "players"))[
        ["player_id", "cohort", "monetary"]
    ]
    df = ltv_df.merge(players_df, on="player_id", how="left")
    df["expected_ltv_90d"] = pd.to_numeric(df["expected_ltv_90d"])
    df["churn_probability"] = pd.to_numeric(df["churn_probability"])
    df["monetary"] = pd.to_numeric(df["monetary"])
    logger.info("Fetched %d players with LTV scores", len(df))
    return df


# ---------------------------------------------------------------------------
# Step 2 – generate campaigns (select player pools)
# ---------------------------------------------------------------------------


def _select_players(spec: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Return a sampled subset of `df` based on the campaign's targeting rule."""
    targeting = spec["targeting"]
    n = spec["n_players"]

    if targeting == "random":
        pool = df

    elif targeting == "high_ltv":
        pool = df[df["segment"] == "high_ltv"]

    elif targeting == "lapsed_spenders":
        # Churned players who have previously spent — best retargeting audience
        pool = df[(df["churn_probability"] > 0.5) & (df["monetary"] > 0)]
        if len(pool) < 10:
            logger.warning(
                "lapsed_spenders pool has only %d players — falling back to high_churn",
                len(pool),
            )
            pool = df[df["churn_probability"] > 0.5]

    else:
        raise ValueError(f"Unknown targeting strategy: {targeting!r}")

    n_sample = min(n, len(pool))
    if n_sample < n:
        logger.warning(
            "%s: requested %d players but pool only has %d — using all",
            spec["campaign_name"], n, n_sample,
        )

    return pool.sample(n=n_sample, random_state=RANDOM_SEED)


def generate_campaigns(df: pd.DataFrame) -> list[dict]:
    """
    Build campaign objects: each spec + the sampled player DataFrame.
    Returns a list of dicts with keys: spec fields + 'players' (DataFrame).
    """
    campaigns = []
    for spec in CAMPAIGN_SPECS:
        players = _select_players(spec, df)
        campaigns.append({**spec, "players": players})
        logger.info(
            "Campaign %-20s | spend=$%s | players=%d | targeting=%s",
            spec["campaign_name"],
            f"{spec['spend']:,.0f}",
            len(players),
            spec["targeting"],
        )
    return campaigns


# ---------------------------------------------------------------------------
# Step 3 – compute metrics
# ---------------------------------------------------------------------------


def compute_campaign_metrics(campaigns: list[dict]) -> pd.DataFrame:
    """
    Compute ROI metrics for each campaign.

    payback_period_days
        Days to recover ad spend at the implied daily revenue rate:
        spend / (total_predicted_revenue_90d / 90).
        None when total_predicted_revenue_90d == 0.

    is_profitable
        True when ROAS >= 1 (predicted revenue at least covers spend).
    """
    rows = []
    for c in campaigns:
        players: pd.DataFrame = c["players"]
        spend = c["spend"]
        n_players = len(players)
        avg_ltv = float(players["expected_ltv_90d"].mean())
        total_revenue = float(players["expected_ltv_90d"].sum())
        roas = total_revenue / spend if spend > 0 else 0.0

        daily_revenue = total_revenue / 90
        payback = round(spend / daily_revenue, 2) if daily_revenue > 0 else None

        rows.append({
            "campaign_id":                 c["campaign_id"],
            "campaign_name":               c["campaign_name"],
            "start_date":                  c["start_date"].isoformat(),
            "spend":                       round(spend, 2),
            "n_players":                   n_players,
            "avg_ltv_acquired":            round(avg_ltv, 2),
            "total_predicted_revenue_90d": round(total_revenue, 2),
            "roas":                        round(roas, 4),
            "payback_period_days":         payback,
            "is_profitable":               roas >= 1.0,
        })

    df = pd.DataFrame(rows)

    logger.info("\n%s", df[[
        "campaign_name", "spend", "total_predicted_revenue_90d",
        "roas", "payback_period_days", "is_profitable",
    ]].to_string(index=False))

    return df


# ---------------------------------------------------------------------------
# Step 4 – comparison plot
# ---------------------------------------------------------------------------


def plot_campaign_comparison(results: pd.DataFrame, output_path: Path) -> None:
    """
    Four-panel figure comparing campaigns on:
      1. Spend vs Predicted Revenue
      2. ROAS  (reference line at 1.0)
      3. Avg LTV Acquired
      4. Payback Period  (reference line at 90 days)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    names = results["campaign_name"].tolist()
    colors = [CAMPAIGN_COLORS[n] for n in names]
    x = np.arange(len(names))
    short_labels = [n.replace("_", "\n") for n in names]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle("Campaign ROI Comparison — GemBlast LTV Studio", fontsize=14, fontweight="bold")

    # ── Panel 1: Spend vs Revenue ────────────────────────────────────────────
    ax = axes[0, 0]
    w = 0.35
    bars_spend = ax.bar(x - w / 2, results["spend"],
                        width=w, label="Ad Spend", color="#AAAAAA", edgecolor="white")
    bars_rev = ax.bar(x + w / 2, results["total_predicted_revenue_90d"],
                      width=w, label="Predicted Revenue 90d", color=colors, edgecolor="white")

    ax.set_title("Spend vs Predicted Revenue")
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.legend(fontsize=8)
    ax.set_ylabel("USD")
    _annotate_bars(ax, bars_rev, fmt="${:.0f}")

    # ── Panel 2: ROAS ────────────────────────────────────────────────────────
    ax = axes[0, 1]
    bars = ax.bar(x, results["roas"], color=colors, edgecolor="white")
    ax.axhline(1.0, color="black", linewidth=1.2, linestyle="--", label="Break-even (ROAS = 1)")
    ax.set_title("ROAS  (Predicted Revenue / Spend)")
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, fontsize=9)
    ax.set_ylabel("ROAS")
    ax.legend(fontsize=8)
    _annotate_bars(ax, bars, fmt="{:.2f}x")

    # ── Panel 3: Avg LTV Acquired ────────────────────────────────────────────
    ax = axes[1, 0]
    bars = ax.bar(x, results["avg_ltv_acquired"], color=colors, edgecolor="white")
    ax.set_title("Avg LTV per Acquired Player (90d)")
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.2f}"))
    ax.set_ylabel("USD")
    _annotate_bars(ax, bars, fmt="${:.2f}")

    # ── Panel 4: Payback Period ──────────────────────────────────────────────
    ax = axes[1, 1]
    payback_vals = []
    payback_labels = []
    for _, row in results.iterrows():
        if row["payback_period_days"] is None or pd.isna(row["payback_period_days"]):
            payback_vals.append(0)
            payback_labels.append("N/A")
        else:
            payback_vals.append(row["payback_period_days"])
            payback_labels.append(f'{row["payback_period_days"]:.0f}d')

    bars = ax.bar(x, payback_vals, color=colors, edgecolor="white")
    ax.axhline(90, color="steelblue", linewidth=1.2, linestyle="--", label="90-day window")
    ax.set_title("Payback Period (Days)")
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, fontsize=9)
    ax.set_ylabel("Days")
    ax.legend(fontsize=8)

    for bar, label in zip(bars, payback_labels):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(payback_vals) * 0.01,
            label,
            ha="center", va="bottom", fontsize=9, fontweight="bold",
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Plot saved -> %s", output_path)


def _annotate_bars(ax, bars, fmt: str) -> None:
    """Add value labels above each bar."""
    y_max = max((b.get_height() for b in bars), default=1)
    for bar in bars:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h + y_max * 0.01,
            fmt.format(h),
            ha="center", va="bottom", fontsize=9, fontweight="bold",
        )


# ---------------------------------------------------------------------------
# Step 5 – write to Supabase
# ---------------------------------------------------------------------------


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def write_campaign_results(client, results: pd.DataFrame) -> None:
    records = _df_to_records(results)
    written = 0
    for i in range(0, len(records), BATCH_SIZE):
        client.table("campaign_results").upsert(records[i : i + BATCH_SIZE]).execute()
        written += len(records[i : i + BATCH_SIZE])
    logger.info("Wrote %d rows to 'campaign_results'", written)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_campaign_model(
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
    dry_run: bool = False,
) -> pd.DataFrame:
    from supabase import create_client

    url = supabase_url or os.getenv("SUPABASE_URL")
    key = supabase_key or os.getenv("SUPABASE_KEY")
    client = create_client(url, key)

    df = fetch_data(client)
    campaigns = generate_campaigns(df)
    results = compute_campaign_metrics(campaigns)

    plot_path = OUTPUT_DIR / "campaign_comparison.png"
    plot_campaign_comparison(results, plot_path)

    if dry_run:
        logger.info("Dry run — skipping Supabase write")
    else:
        write_campaign_results(client, results)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(description="Run GemBlast campaign ROI model")
    parser.add_argument("--dry-run", action="store_true", help="Skip Supabase write")
    args = parser.parse_args()

    result = run_campaign_model(dry_run=args.dry_run)
    print(result[[
        "campaign_name", "spend", "total_predicted_revenue_90d",
        "roas", "payback_period_days", "is_profitable",
    ]].to_string(index=False))
